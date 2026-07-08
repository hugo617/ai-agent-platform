# 06 - 权限模型 RBAC

📍 相关文档:[05-认证体系](05-认证体系.md) · [01-分层架构](01-分层架构与依赖方向.md)

> 这一篇讲「谁能做什么」。读完后你会知道:RBAC 是什么、casbin 怎么工作、三档默认角色、
> 为什么权限校验有两处(声明式 + 工具内)。

---

## 先分清:认证 vs 授权

这是两个容易混的概念:

| | 认证(Authentication) | 授权(Authorization) |
|---|---|---|
| 问的是 | **你是谁?** | **你能干这个吗?** |
| 举例 | 张三登录成功,拿到 token | 张三想删用户 →「你是 owner 吗?是 → 允许」 |
| 在哪做 | [05-认证体系](05-认证体系.md) | 这一篇 |

**顺序**:先认证(确认身份),再授权(检查权限)。两者都在 `get_current_user` 之后。

---

## RBAC 是什么?

**R**ole-**B**ased **A**ccess **C**ontrol(基于角色的访问控制)。

核心思路:**不直接**给每个人配权限,而是「人 → 角色 → 权限」三层:

```mermaid
graph LR
    ZS["张三"] -->|"分配角色"| R[owner 角色]
    R -->|"角色拥有"| P["权限:删除用户"]
    ZS -.->|"所以张三能"| ACT["删用户"]
```

**为什么这样?** 因为给每个人一个个配权限太累。给「角色」配好权限,新人来了分个角色就行。
张三离职、李四接班,把 owner 角色从张三转给李四,权限立刻跟着转。

---

## 项目里的三档默认角色

每个租户创建时,系统自动「种」(seed)好三个角色(在 `app/services/permission_service.py`
的 `seed_tenant_defaults`):

| 角色 | 能做什么(权限矩阵) |
|------|-------------------|
| **owner**(所有者) | 一切:agents 读写删 + conversations + users 全权 + roles 全权 + organizations 全权 |
| **admin**(管理员) | 大部分:agents 读改 + conversations + users 读改 + roles 读 + organizations 读(不能删 agent、不能管角色) |
| **member**(普通成员) | 基础:agents 只读 + conversations 读/建/对话 + roles 读 + organizations 读 |

> 💡 这三个角色同时存在**两套**记录:
> - **casbin 的策略**(真正生效的权限判断)
> - **`roles` 表的显示记录**(给管理员界面看的,有名字/描述/排序)
>
> 两套的 `code`(owner/admin/member)是对应的。`roles` 表是「显示层」,真正管事的是 casbin。

---

## casbin 怎么工作?(权限引擎)

项目用 **pycasbin** 做权限判断。规则定义在 `casbin_model.conf`:

```ini
[request_definition]
r = sub, dom, obj, act          # 一次权限请求:谁(sub)在哪个租户(dom)对什么资源(obj)做什么动作(act)

[matchers]
# 允许的条件:sub 在 dom 里继承了某角色,且该角色有对应的 (obj, act) 策略
m = g(r.sub, p.sub, r.dom) && r.dom == p.dom && keyMatch(r.obj, p.obj) && r.act == p.act
```

**通俗翻译**:当张三想「在租户 A 里删除用户」,casbin 检查:
1. 张三在租户 A 里是不是有某个角色?(通过 `g` 分组关系)
2. 那个角色在租户 A 里,有没有「users + delete」这条策略?
3. 两个都满足 → 允许;否则 → 拒绝

### 四个关键概念

```mermaid
graph TB
    REQ["权限请求<br/>sub=张三, dom=租户A, obj=users, act=delete"] --> M{"匹配器 matcher"}
    G["g 分组策略<br/>张三 → owner(在租户A)"] --> M
    P["p 权限策略<br/>owner → users + delete(在租户A)"] --> M
    M -->|"两个都匹配"| ALLOW["✅ 允许"]
    M -->|"任一不匹配"| DENY["❌ 拒绝"]
```

| 概念 | 含义 | 例子 |
|------|------|------|
| **sub**(主体) | 谁在请求 | 张三的 user_id |
| **dom**(域) | 在哪个租户 | 租户 A 的 tenant_id |
| **obj**(对象) | 操作什么资源 | `users` / `agents` / `conversations` |
| **act**(动作) | 具体操作 | `read` / `create` / `update` / `delete` / `chat` |

> 💡 **dom(域)是多租户的关键**:同一个「owner」角色名,在租户 A 和租户 B 是独立的。
> 张三是 A 的 owner,不代表他是 B 的 owner。casbin 的 domain 模式天然支持这种隔离。

---

## 怎么用?(声明式校验)

权限校验在 **Controller 层**「声明」,像贴标签一样简单。看 `app/api/v1/users.py`:

```python
@router.get("/", dependencies=[Depends(require_permission("users", "read"))])
async def list_users(...):
    ...
```

`require_permission("users", "read")` 就是「贴标签」:告诉框架「进这个接口必须有
users:read 权限」。框架自动调 casbin 判断,不通过就 403。

### require_permission 怎么实现的?

`app/api/deps.py` 的 `require_permission` 是个**闭包工厂**:

```python
def require_permission(obj, act):
    async def _guard(user: CurrentUser = Depends(get_current_user)):
        allowed = await permission_service.check(user.user_id, user.tenant_id, obj, act)
        if not allowed:
            raise HTTPException(403, f"forbidden: cannot {act} {obj}")
        return user
    return _guard
```

它内部:① 先过 `get_current_user`(认证,拿到 user);② 调 `permission_service.check`
(授权);③ 不通过抛 403。

### permission_service:casbin 的唯一封装

所有 casbin 操作都集中在 `app/services/permission_service.py`,这是**唯一**碰 casbin 的地方:

```python
class PermissionService:
    async def check(self, user_id, tenant_id, obj, act) -> bool:
        # 用 run_in_threadpool 桥接同步的 pycasbin 到异步层
        ...
    def require(self, user_id, tenant_id, obj, act):
        # 不通过抛 PermissionError(被 main.py 转成 403)
        ...
```

> 💡 **为什么集中一处?** casbin 的 API 是同步的,而我们的 Service 是异步的,要包一层
> `run_in_threadpool`。集中封装让这个桥接逻辑只写一次,好测试、好替换。

---

## 双重校验(重要!)

权限不止在 Controller 校验一次。**AI 工具被调用时,工具内部会再校验一次**。

为什么?因为 AI 是不可控的——大模型可能「决定」调用某个工具,即使接口层没拦。看
`app/agents/graph.py` 的工具:

```python
@tool
async def get_my_agents():
    # 工具内部自己查权限!不是依赖接口层
    allowed = await permission_service.check(user_id, tenant_id, "agents", "read")
    if not allowed:
        return "ERROR: permission denied"
    ...
```

**这就是「双重校验」**:
1. **Controller 层**:声明式校验接口权限。
2. **工具内部**:再次校验,防止 AI 绕过。

> 💡 **改权限时两处都要想到**。详见 [07-Agent与LLM集成](07-Agent与LLM集成.md)。

---

## 改角色时怎么立即生效?

管理员改了某用户的角色(比如 member → admin),casbin 的策略要**同步更新**,否则还是
旧权限。看 `permission_service.py` 的 `set_role_for_user_in_domain`:

```python
async def set_role_for_user_in_domain(self, user_id, role, tenant_id):
    # 1. 删掉旧角色
    for old in e.get_roles_for_user_in_domain(user_id, tenant_id):
        e.delete_roles_for_user_in_domain(user_id, old, tenant_id)
    # 2. 加上新角色
    e.add_role_for_user_in_domain(user_id, role, tenant_id)
```

`UserService` 改用户角色时会调它,所以**改完立刻生效**,不用重新登录。

---

## casbin 的策略存哪?

存数据库的 `casbin_rule` 表(由 `casbin-sqlalchemy-adapter` 自动管理)。

> ⚠️ **重要**:这张表是 casbin 自己管的,**我们的 Alembic 迁移要排除它**(`alembic/env.py`
> 的 `_EXCLUDED_TABLES`)。否则 autogenerate 每次都想删它。详见
> [03-数据库与ORM](03-数据库与ORM.md)。

---

## 记住三句话

1. **RBAC = 人 → 角色 → 权限**,不直接给人配权限。
2. **声明式校验**:接口上贴 `require_permission` 标签,框架自动拦。
3. **双重校验**:Controller 校验 + AI 工具内部再校验,防绕过。

---

**关键文件清单**:
- 权限模型定义:`casbin_model.conf`
- casbin 封装(唯一入口):`app/services/permission_service.py`
- casbin enforcer:`app/core/casbin_enforcer.py`
- 声明式校验:`app/api/deps.py` 的 `require_permission`
- 默认角色 seed:`permission_service.py` 的 `seed_tenant_defaults`
- 角色 CRUD(显示层):`app/services/rbac_service.py`、`app/models/rbac.py`

**相关文档**:
- [05-认证体系](05-认证体系.md) — 认证在前,授权在后
- [07-Agent与LLM集成](07-Agent与LLM集成.md) — AI 工具的二次权限校验
- [01-分层架构](01-分层架构与依赖方向.md) — 权限声明在 Controller 层
