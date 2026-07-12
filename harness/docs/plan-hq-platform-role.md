# 计划:平台角色 hq_staff —— 总部业务员(各司其职)+ 跨租户只读

> 对应 feature_list.json 的 `id`: `hq-platform-role`
> 状态: not_started
> 优先级: 34
> 前置: `customers-api`(用 Customer 域作为跨租户只读的验证载体)

---

## 背景:「各司其职」的具体含义

用户要求总部内部细分角色(各司其职),MVP 设两个平台角色(`platform_role` 字段):
- `super_admin`(已有):总部全权管理员,管理所有组织/门店/客户/系统配置
- `hq_staff`(**本任务新增**):总部业务员,**跨店只读**所有门店 + 客户档案聚合

两者差异:
| 能力 | super_admin | hq_staff |
|------|-------------|----------|
| 跨租户读(所有门店/客户) | ✅ | ✅ |
| 跨租户写(创建/编辑/删除) | ✅ | ❌ |
| 平台配置(LLM/Token) | ✅ | ❌ |
| 门店内写(若门店给了角色) | ✅ | 走 casbin(若有该门店角色) |

`hq_staff` 的定位是「**总部看板/巡检员**」:能看所有门店和客户的全貌,但不能改。这覆盖用户「总部各司其职」「客户数据跨店只读权限」两个需求。

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| platform_role 字段 | ✅ 自由字符串,无 Enum 约束 | `tenant.py:92-96`,写 "hq_staff" 无需迁移 |
| check() 短路 | ⚠️ 只有 super_admin 分支 | `permission_service.py:63`,需加 hq_staff 分支 |
| Customer/Group Service 的 is_super_admin 判定 | ⚠️ 硬编码 == "super_admin" | customers-api/groups-api 里的跨租户分支需扩展为 in (super_admin, hq_staff) |
| JWT 提取 | ✅ 无白名单 | `security.py:160-163`,hq_staff 直接透传 |

---

## 目标

1. `permission_service.check()` 加 `hq_staff` + `act == "read"` 短路(任意 obj 的 read 放行)
2. 抽象 helper `is_cross_tenant_viewer(platform_role)`(super_admin + hq_staff 都算跨租户查看者)
3. Customer/Group Service 的跨租户查询分支:从 `== "super_admin"` 扩展为 `in ("super_admin", "hq_staff")`
4. 写操作:hq_staff 不短路,走 casbin(若无门店角色则 403)→ 天然只读
5. 测试:hq_staff 能跨店读客户/组织、不能创建/删除、super_admin 行为不回归

---

## 前置条件

- `customers-api` 完成(Customer 域有跨租户聚合端点,作为验证载体)
- `groups-api` 完成(Group 域有跨租户读)

---

## 实施步骤

### 第一阶段:权限层改造

#### Step 1:check() 加 hq_staff 只读短路(`app/services/permission_service.py`)

当前 `check()`(L50-71)只有 `super_admin` 短路。加 `hq_staff` + read 放行:

```python
async def check(self, user_id, tenant_id, obj, act, platform_role=None) -> bool:
    if platform_role == "super_admin":
        return True
    if platform_role == "hq_staff" and act == "read":
        return True                      # 新增:总部业务员跨租户只读
    # ... 其余走 casbin
```

- **检查**:hq_staff 对任意 obj 的 read 放行;写操作(act != read)落入 casbin(无策略则 403)

#### Step 2:抽象跨租户查看者 helper(`app/services/permission_service.py`)

```python
def is_cross_tenant_viewer(platform_role: str | None) -> bool:
    """True if the role grants cross-tenant read access (super_admin or hq_staff)."""
    return platform_role in ("super_admin", "hq_staff")
```

- 这个 helper 给 Service 层判定「是否走跨租户查询分支」用(替代硬编码 `== "super_admin"`)

### 第二阶段:Service 层扩展跨租户分支

#### Step 3:Customer Service 扩展(`app/services/customer_service.py`)

customers-api 里写的 `is_super = platform_role == "super_admin"` 改为:

```python
is_cross_tenant = is_cross_tenant_viewer(platform_role)   # super_admin + hq_staff
if not is_cross_tenant:
    await permission_service.require(actor_id, tenant_id, self.OBJECT, "read", platform_role=platform_role)
# list_profiles 走跨租户分支(super_admin=True 参数保留语义,实际含 hq_staff)
```

- **写操作**(create/update/delete):**不改**。hq_staff 在 check() 不短路(act != read),走 casbin → 若无该门店 customers:create 策略 → 403,天然只读。
- **关键**:hq_staff 跨租户查询用 super_admin 形参分支(Repository 层的 `super_admin=True` 语义实际是「跨租户」,可重命名为 `cross_tenant` 更准确,但功能不变)

#### Step 4:Group Service 扩展(`app/services/group_service.py`)

同 Step 3,Group 的 list/get 跨租户分支扩展为 `is_cross_tenant_viewer(platform_role)`。

- ⚠️ Group 的**写操作**(create/update/delete/挂载/卸载)仍用 `require_super_admin()`(API 层守卫),hq_staff 被 403 拦住——这是期望行为(组织架构只有 super_admin 能改)。

### 第三阶段:测试 + 总验证

#### Step 5:测试(`tests/test_hq_platform_role.py` 新建)

新增 hq_staff fixture(参照 super_admin_client,在 conftest 加 `hq_staff_client`:platform_role="hq_staff" 的用户 + token):

```python
# conftest 加 fixture
@pytest.fixture
async def hq_staff_client(app_client, db_session):
    # 建 platform_role="hq_staff" 的用户 + token,返回带 Authorization 的 client
```

覆盖维度:
- **hq_staff 跨店读客户**:GET /customers/ → 200(返回全局客户列表)
- **hq_staff 读聚合**:GET /customers/{id}/aggregate → 200
- **hq_staff 读组织**:GET /groups/ → 200(返回全部 Group)
- **hq_staff 写客户**:POST /customers/profiles/ → 403(无 customers:create)
- **hq_staff 删客户**:DELETE /customers/profiles/{id} → 403
- **hq_staff 改组织**:POST /groups/ → 403(require_super_admin 拦截)
- **hq_staff 读门店内其它资源**:GET /agents/ → 200(check 放行 read)
- **super_admin 不回归**:super_admin_client 全部行为不变(测试现有 test_service_platform_role 仍过)

#### Step 6:总验证

```bash
./init.sh                       # ruff + pytest 全绿
```

- **通过标准**:ruff 绿 + pytest 全绿(基线 + 新增 ≈ 8)+ 现有 super_admin 测试无回归
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `./init.sh` 全绿(ruff + pytest,含新增 test_hq_platform_role.py)
2. hq_staff 能跨租户读所有门店的客户/组织(GET /customers/、GET /groups/ → 200)
3. hq_staff 不能跨租户写(POST/PUT/DELETE → 403)
4. hq_staff 不能改组织架构(require_super_admin 端点 → 403)
5. super_admin 行为完全不变(现有测试无回归)
6. 前端:customers-page / groups-page 的 super_admin 视角对 hq_staff 同样生效(前端按 `platform_role !== null` 或新增 hq_staff 判定——MVP 可让 hq_staff 复用 super_admin 的总部视角 UI)

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| check() 加 hq_staff 分支影响其它模块 | 只对 act=="read" 放行;写操作仍走 casbin;现有 test_permission_service 的 super_admin 断言不变 |
| hq_staff 无门店角色但想读单个门店详情 | check() 放行 read → 进入 Service 跨租户分支 → 能读;这是期望行为(总部业务员看板) |
| Repository 层 super_admin 形参语义 | 保留形参名 `super_admin=True`(功能是跨租户);或重命名为 `cross_tenant`(更准但改动面大,MVP 保留原名) |
| 前端 hq_staff 视角 | customers-ui/groups-ui 写的是 `isSuperAdmin = platform_role === "super_admin"`;hq_staff 需改为 `isHQ = platform_role in ("super_admin","hq_staff")` 或 `isCrossTenant`——**本任务可顺带改前端判定**,或留作 customers-ui 微调(若 customers-ui 已合并则此处改) |
| conftest 加 hq_staff_client | 参照 super_admin_client 模式建(platform_role="hq_staff" 的 User 行 + token) |

### 不做的事(边界)

- 不做平台级 casbin domain(hq_staff 用 check() 硬编码分支,不引入平台级 RBAC;后续要加更多平台角色再升级)
- 不做 hq_staff 的细粒度权限(hq_staff 统一只读;若要「财务只看财务数据」属后续增强)
- 不做 hq_staff 的前端独立视角(MVP 复用 super_admin 的总部 UI;若 customers-ui 已用 isSuperAdmin 判定,本任务顺带改为 isCrossTenantViewer)
- 不做 User 域的 hq_staff 适配(user_service 的 super_admin 分支较复杂,MVP 阶段 hq_staff 看用户列表可后续)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| check() 超管短路 | `app/services/permission_service.py:50-71`(短路在 :63) |
| require_super_admin | `app/api/deps.py:246-262` |
| platform_role 自由字符串字段 | `app/models/tenant.py:92-96` |
| super_admin_client fixture | `tests/conftest.py`(参照建 hq_staff_client) |
| super_admin 回归测试 | `tests/test_service_platform_role.py`(确保不破) |
| Customer Service 跨租户分支 | `app/services/customer_service.py`(customers-api 写的 is_super 判定) |
