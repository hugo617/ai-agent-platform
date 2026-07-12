# 计划:Group(组织)后端 —— 跨租户经营主体 + 门店归属

> 对应 feature_list.json 的 `id`: `groups-api`
> 状态: not_started
> 优先级: 30
> 前置: `org-cleanup`(旧 Organization 已删除)

---

## 背景:Group 是什么

用户业务里的「组织」是**经营主体**:可能是一家连锁企业(旗下多家门店),也可能就是一家单店。Group 是**跨租户的平台级实体**——它不属于某个 tenant,而是**把多个 tenant(门店)组织起来**。这与旧 Organization(租户内部部门树)完全不同,故新建而非复用。

**核心业务规则**:
- 一个 Group 关联 1~N 个门店(tenant)
- Group 是平台级(无 tenant_id),由总部(super_admin)维护
- 门店视角:知道自己属于哪个 Group
- 总部视角:看所有 Group + 每个 Group 下的门店

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| Group model | ❌ 不存在 | 全新,参照 `app/models/organization.py`(已删)的双表模式 |
| 迁移 head | `5dd68e90d6f0` | org-cleanup 后 head 不变(只抠块不改 revision) |
| 权限 seed | ❌ 无 groups 项 | 待加 `groups:read/create/update/delete` |
| 参照模板 | `app/models/agent.py` + `app/services/agent_service.py` | 最干净的 CRUD 范式 |

---

## 目标

1. 新建 `Group` 表(平台级,无 tenant_id)+ `GroupTenant` 关联表(Group↔Tenant 多对多)
2. Group CRUD API(谁有权管?见下方权限设计)
3. 门店挂载/卸载 API(把 tenant 挂到 Group / 从 Group 移除)
4. 权限:`super_admin` 全权;门店 owner/admin 只读看自己所属 Group
5. `./init.sh` 全绿 + `alembic upgrade head` + `alembic check` 无 drift

### 权限设计(Group 是平台级实体)

Group 不属于任何 tenant,所以**不能用租户级 `require_permission('groups', act)`**。方案:
- **写操作(create/update/delete/挂载/卸载)**:用 `require_super_admin()`(纯平台级,只有 super_admin 能改组织架构)
- **读操作(list/get)**:super_admin 看全部;门店用户(super_admin 外)只看自己所属的 Group(通过 GroupTenant 反查)

---

## 前置条件

- `org-cleanup` 完成(旧 Organization 已删,main 干净)
- 迁移 head = `5dd68e90d6f0`

---

## 实施步骤

> ⚠️ 执行前 grep 确认 head revision 无漂移:`alembic heads`。

### 第一阶段:数据模型 + 迁移

#### Step 1:Group + GroupTenant model(`app/models/group.py` 新建)

参照 `app/models/organization.py`(已删,但从调研报告知其结构)+ `tenant.py` 的 `_uuid` 模式:

```python
class Group(Base):
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 经营主体编码
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 总部地址
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at / updated_at  # server_default + onupdate

class GroupTenant(Base):
    """Many-to-many: 一个 Group 关联多个门店(tenant)。"""
    __tablename__ = "group_tenants"
    __table_args__ = (UniqueConstraint("group_id", "tenant_id", name="uq_group_tenant"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(String(32), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- **检查**:import 跑通;`from app.models.group import Group, GroupTenant` 无错

#### Step 2:Alembic 迁移

```bash
alembic revision --autogenerate -m "add groups and group_tenants tables"
alembic upgrade head
alembic check   # 无 drift
```

- **同步**(Session 018 教训):`alembic/env.py` + `tests/conftest.py` 两处 model import 块加 `group,`(若 autogenerate 未自动加)
- **down_revision** = `5dd68e90d6f0`
- **检查**:迁移链通;`alembic check` → No new upgrade operations detected

### 第二阶段:Schema + Repository + Service

#### Step 3:Schema(`app/schemas/group.py` 新建)

```python
class GroupRead(BaseModel):  # from_attributes=True
    id, name, code, address, description, status, sort_order
    tenant_ids: list[str] = []        # 关联的门店 id 列表
    tenants: list[TenantBrief] = []   # 门店简要信息(id+name),便于前端直接渲染
    created_at, updated_at

class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code, address, description: optional
    tenant_ids: list[str] = []        # 创建时可指定关联门店
    status, sort_order: optional

class GroupUpdate(BaseModel):  # 全 Optional
    name, code, address, description, status, sort_order: optional
```

- 新增 `TenantBrief`(id+name)用于 GroupRead.tenants,或复用现有(若有)

#### Step 4:Repository(`app/repositories/group.py` 新建)

Group 是平台级(无 tenant_id),**不继承 TenantScopedRepository**,直接用 `BaseRepository` 或自建:

```python
class GroupRepository:
    async def list_all() -> list[Group]              # super_admin 看全部
    async def get(group_id) -> Group | None
    async def add(group) -> Group
    async def delete(group) -> None
    async def list_for_tenant(tenant_id) -> list[Group]   # 门店视角:反查自己所属 Group(经 GroupTenant JOIN)

class GroupTenantRepository:
    async def list_tenants(group_id) -> list[str]    # Group 下的 tenant_id 列表
    async def attach(group_id, tenant_id) -> None    # 挂载门店
    async def detach(group_id, tenant_id) -> None    # 卸载门店
    async def replace_all(group_id, tenant_ids) -> None  # 全量替换(创建/更新时用)
```

#### Step 5:Service(`app/services/group_service.py` 新建)

参照 `app/services/agent_service.py` CRUD 范式,但权限用平台级:

```python
class GroupService:
    OBJECT = "groups"

    async def list(self, actor_id, tenant_id, platform_role=None):
        if platform_role == "super_admin":
            # 全部 Group + 每个 Group 的 tenant_ids
        else:
            # 门店视角:只看自己所属 Group(await permission_service.require(..., "groups", "read", ...))
            return await self.repo.list_for_tenant(tenant_id)

    async def get(self, actor_id, tenant_id, group_id, platform_role=None):
        # super_admin 看任意;门店用户只能看自己所属的 Group

    async def create(self, actor_id, payload, platform_role=None):
        # require_super_admin 在 API 层守卫;Service 直接建 + 批量挂载 tenant_ids

    async def update(self, actor_id, group_id, payload, platform_role=None): ...
    async def delete(self, actor_id, group_id, platform_role=None): ...
    async def attach_tenant(self, actor_id, group_id, tenant_id, platform_role=None): ...
    async def detach_tenant(self, actor_id, group_id, tenant_id, platform_role=None): ...
```

- **异常**:用 `NotFoundError`(`from app.services.errors`),对齐 users/roles 模式

### 第三阶段:API + 权限 + 注册

#### Step 6:API(`app/api/v1/groups.py` 新建)

```python
router = APIRouter(prefix="/groups", tags=["groups"])

@router.get("/", dependencies=[Depends(get_current_user)])  # 读:登录即可(Service 内分流)
@router.get("/{group_id}", dependencies=[Depends(get_current_user)])
@router.post("/", dependencies=[Depends(require_super_admin())])      # 写:仅 super_admin
@router.put("/{group_id}", dependencies=[Depends(require_super_admin())])
@router.delete("/{group_id}", dependencies=[Depends(require_super_admin())])
@router.post("/{group_id}/tenants/{tenant_id}", dependencies=[Depends(require_super_admin())])  # 挂载
@router.delete("/{group_id}/tenants/{tenant_id}", dependencies=[Depends(require_super_admin())]) # 卸载
```

- 错误映射用 `_http_exc`(照抄 `users.py:29-37` 的 isinstance 模式)
- handler 透传 `platform_role=user.platform_role` 给 Service

#### Step 7:注册路由 + 权限 seed

- `app/main.py`:import groups + include_router(字母序插)
- **权限 seed**:Group 是平台级,**不进 DEFAULT_OWNER/ADMIN/MEMBER_PERMS**(门店角色无权管 Group)。super_admin 通过 `require_super_admin()` 守卫,不走 casbin。所以 **conftest casbin seed 不需要加 groups 项**。
- ⚠️ 但 `permission_service.seed_tenant_defaults` 可能需要感知 groups 权限项存在(供权限矩阵页展示)——若 Permission 表需要登记 groups 条目,在 seed 流程加。执行时 grep 确认 Permission 表是否需要手动登记。

### 第四阶段:测试 + 总验证

#### Step 8:测试(`tests/test_groups_api.py` 新建)

参照 `test_agents_api.py` / `test_rbac_api.py` 模式,覆盖:
- **super_admin**:CRUD 全通 + 挂载/卸载门店通
- **owner/admin**(门店角色):GET /groups/ 只看自己所属 Group;POST/PUT/DELETE → 403
- **member**:同上,只读自己 Group
- **404**:GET 不存在的 group_id → 404
- **挂载校验**:挂载不存在的 tenant_id → 404;重复挂载 → 400
- **跨租户隔离**:门店 A 的 owner 看不到门店 B 独有的 Group

#### Step 9:总验证

```bash
./init.sh                       # ruff + pytest 全绿
APP_ENV=testing alembic upgrade head && alembic check  # 迁移 + 无 drift
```

- **通过标准**:ruff 绿 + pytest 全绿(基线 + 新增 ≈ 10)+ alembic check 无 drift
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `./init.sh` 全绿(ruff + pytest,含新增 test_groups_api.py)
2. `alembic upgrade head` + `alembic check` 无 drift(env.py + conftest.py 两处 import 同步)
3. super_admin 能 CRUD Group + 挂载/卸载门店
4. 门店 owner/admin/member 只读自己所属 Group,写操作 403
5. GET /groups/{nonexistent} → 404

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| Group 平台级无 tenant_id,不能用 TenantScopedRepository | 自建 GroupRepository,不继承基类;参照 user.py 的 UserListRepository 跨租户查询模式 |
| require_super_admin 守卫 vs Service 内 require 双层 | 写操作用 require_super_admin 在 API dependencies 层守卫(纯平台级),Service 内不再 require(避免重复) |
| env.py/conftest.py 忘加 group import | Session 018 教训:autogenerate 后必查两处;alembic check 会报 drift 兜底 |
| 门店视角查自己所属 Group 需 JOIN GroupTenant | list_for_tenant 用 JOIN;性能无虑(Group/门店数量极小) |
| Permission 表是否需登记 groups 条目 | 执行时 grep Permission 表登记逻辑;若矩阵页需要展示 groups 权限项,在 seed 流程加 |

### 不做的事(边界)

- **不做树形层级**(MVP Group 是平的,多个 Group 平级,总部凌驾其上)
- 不做 Group 内部角色(Group 不含人员,人员归属走 UserTenant)
- 不做 Group 的客户归属(Customer 是 customers-api 任务,可选绑 Group)
- 不做前端(groups-ui 是下一任务)
- 不做 Group 的审计 SCD2(Group 变更用 system_logs 即可,非合规刚需)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| model 模板(双表) | 已删的 `app/models/organization.py` 结构(调研报告有记录)+ `tenant.py` `_uuid` |
| CRUD Service 范式 | `app/services/agent_service.py`(最干净) |
| require_super_admin | `app/api/deps.py:246-262` |
| _http_exc 错误映射 | `app/api/v1/users.py:29-37` |
| 跨租户查询范式 | `app/repositories/user.py:117-149`(super_admin 分支) |
| 测试范式 | `tests/test_agents_api.py` / `tests/test_rbac_api.py` |
