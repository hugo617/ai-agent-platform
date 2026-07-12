# 计划:Customer(客户)后端 —— 全局身份 + 门店档案 + 跨店聚合

> 对应 feature_list.json 的 `id`: `customers-api`
> 状态: not_started
> 优先级: 32
> 前置: `groups-api`(建议先做,Group 是 Customer 可选归属;MVP 阶段非硬依赖)

---

## 背景:客户域的核心难点

客户域是 MVP 的核心业务模块,难点在于**一个客户可能去了好几个门店**。设计采用「**全局身份 + 门店档案**」双层模型:
- `Customer`(全局身份):手机号/证件号全局唯一,识别「同一个张三」
- `CustomerProfile`(门店档案):每店一条,带 `tenant_id` 隔离,存该店对客户的私有数据(备注/标签/状态)

这保证**不破坏租户隔离铁律**(门店只看自己 tenant 的档案),同时支持**跨店识别同一人**(总部 JOIN 两表看聚合)。

### 关键业务规则

| 场景 | 数据流 |
|------|--------|
| 门店 A 创建客户张三(手机 138xxx) | 先查 Customer(138xxx)是否存在;不存在则建 Customer + 建 Profile(tenant=A);存在则只建 Profile(tenant=A) |
| 张三去门店 B | 查 Customer(138xxx)已存在 → 只建 Profile(tenant=B);张三现在有 2 条档案 |
| 门店 A 查看张三 | 只看 Profile(tenant=A),看不到 B 的备注/标签 |
| 总部查看张三 | JOIN Customer + 所有 Profile,看到「张三去过 A、B 两家店」+ 每店档案 |
| 跨店校验 | identity_key 全局唯一 → 同一手机号在系统里只对应一个 Customer |

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| Customer/Profile model | ❌ 不存在 | 全新,参照 tenant.py 的 UserTenant 双表模式 |
| 跨租户查询范式 | ✅ user.py 有现成模式 | `super_admin` 形参分支(user.py:117-149)照搬 |
| 权限 seed | ❌ 无 customers 项 | 待加 `customers:read/create/update/delete` |
| 迁移 head | groups-api 后的 head | 执行时 `alembic heads` 确认 |

---

## 目标

1. 新建 `Customer` 表(全局身份,tenant_id 可空)+ `CustomerProfile` 表(门店档案,有 tenant_id)
2. **门店内 CRUD**:门店用户创建/查看/编辑/删除本店客户档案(`require_permission('customers', act)`)
3. **跨店聚合只读**:super_admin JOIN 两表看聚合视图(照搬 user.py 的 super_admin 分支)
4. **identity_key 全局唯一**:同手机号/证件号只建一个 Customer,复用全局身份
5. 权限:owner/admin/member 分级(casbin);super_admin 跨店只读
6. `./init.sh` 全绿 + 迁移无 drift

---

## 前置条件

- `org-cleanup` 完成
- `groups-api` 建议(非硬依赖):MVP Customer 可不绑 Group,后续增强再绑
- 迁移链当前 head(执行时确认)

---

## 实施步骤

> ⚠️ 执行前 grep 确认迁移 head:`alembic heads`。

### 第一阶段:数据模型 + 迁移

#### Step 1:Customer + CustomerProfile model(`app/models/customer.py` 新建)

```python
class Customer(Base):
    """全局客户身份。tenant_id 可空(平台级),identity_key 全局唯一。"""
    __tablename__ = "customers"
    __table_args__ = (
        Index("uq_customers_identity_active", "identity_key",
              unique=True, postgresql_where=text("is_deleted = false"), sqlite_where=text("is_deleted = 0")),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    identity_key: Mapped[str] = mapped_column(String(100), nullable=False)  # 手机号/证件号,全局唯一
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at / updated_at

class CustomerProfile(Base):
    """门店客户档案。每店一条,带 tenant_id 隔离。"""
    __tablename__ = "customer_profiles"
    __table_args__ = (
        # 同一客户在同一门店只有一条档案(部分唯一索引,软删除后可重建)
        Index("uq_profile_customer_tenant_active", "customer_id", "tenant_id",
              unique=True, postgresql_where=text("is_deleted = false"), sqlite_where=text("is_deleted = 0")),
        Index("idx_customer_profiles_tenant_id", "tenant_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String(32), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)       # 本店私有备注
    tags: Mapped[dict] = mapped_column(JSONB/JSON, default=dict)          # 本店打的标签
    status: Mapped[str] = mapped_column(String(20), default="active")     # potential/active/lost
    last_visit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id"), nullable=True)
    is_deleted / deleted_at / created_at / updated_at
```

#### Step 2:Alembic 迁移

```bash
alembic revision --autogenerate -m "add customers and customer_profiles tables"
```

- **同步**:`alembic/env.py` + `tests/conftest.py` 两处 model import 块加 `customer,`(Session 018 教训)
- **down_revision** = groups-api 后的 head
- **检查**:`alembic upgrade head` + `alembic check` 无 drift

### 第二阶段:Schema + Repository(跨租户分支)

#### Step 3:Schema(`app/schemas/customer.py` 新建)

```python
class CustomerProfileBrief(BaseModel):  # 门店档案摘要(嵌入 CustomerRead)
    tenant_id, tenant_name, remark, tags, status, last_visit_at

class CustomerRead(BaseModel):  # 全局身份 + 跨店档案聚合(总部视角)
    id, identity_key, name, gender, birthday, avatar
    profiles: list[CustomerProfileBrief] = []   # 该客户在所有门店的档案
    profile_count: int = 0                        # 去过几家店

class CustomerProfileRead(BaseModel):  # 门店视角的单店档案
    id, customer_id, tenant_id, remark, tags, status, last_visit_at
    customer: CustomerBrief  # 嵌入全局身份(id+name+identity_key+gender+birthday)

class CustomerProfileCreate(BaseModel):  # 门店创建客户(同时建全局身份或复用)
    identity_key: str  # 手机号/证件号
    name: str
    gender, birthday: optional
    remark, tags, status: optional  # 本店档案字段

class CustomerProfileUpdate(BaseModel):  # 门店编辑本店档案
    name, gender, birthday: optional     # 全局身份字段(同步到 Customer)
    remark, tags, status: optional       # 本店档案字段
```

#### Step 4:Repository(`app/repositories/customer.py` 新建)

```python
class CustomerRepository:  # 全局身份,无 tenant_id
    async def get_by_identity(identity_key) -> Customer | None   # 跨店识别同一人
    async def get(customer_id) / add / delete

class CustomerProfileRepository(TenantScopedRepository):  # 门店档案,有 tenant_id
    # 门店视角(带 tenant_id 过滤,继承基类)
    async def list_for_tenant(tenant_id, filters, super_admin=False):
        if super_admin: return await self._list_all(filters)   # 照搬 user.py:117-122 分支
        return await self._base(tenant_id)...                   # 带 tenant_id 过滤
    async def _list_all(filters):  # 跨店:JOIN Customer + Tenant,不带 tenant_id
    async def get_for_tenant(tenant_id, profile_id)
    async def get_by_customer_tenant(customer_id, tenant_id)  # 本店是否已有该客户档案
```

### 第三阶段:Service + API + 权限

#### Step 5:Service(`app/services/customer_service.py` 新建)

**门店视角 CRUD**(走 `require_permission('customers', act)`):
```python
class CustomerService:
    OBJECT = "customers"

    async def list_profiles(self, actor_id, tenant_id, filters, platform_role=None):
        is_super = platform_role == "super_admin"
        if not is_super:
            await permission_service.require(actor_id, tenant_id, self.OBJECT, "read", platform_role=platform_role)
        # 超管走跨店聚合(JOIN Customer);门店走本店 Profile(带 tenant_id)

    async def create_profile(self, actor_id, tenant_id, payload, platform_role=None):
        await permission_service.require(actor_id, tenant_id, self.OBJECT, "create", platform_role=platform_role)
        # 核心:先 get_by_identity(payload.identity_key)
        #   存在 → 复用 Customer,只建 Profile(tenant_id)
        #   不存在 → 建 Customer + 建 Profile(tenant_id)
        # 校验:本店是否已有该 identity_key 的 Profile(get_by_customer_tenant)→ 400 重复

    async def update_profile(self, actor_id, tenant_id, profile_id, payload, platform_role=None):
        # 同步更新 Customer 全局字段(name/gender/birthday)+ 本店 Profile 字段(remark/tags/status)

    async def delete_profile(self, actor_id, tenant_id, profile_id, platform_role=None):
        # 软删除本店 Profile;Customer 全局身份不删(其它店可能还在用)
```

**跨店聚合**(总部视角):
```python
    async def get_customer_aggregate(self, actor_id, customer_id, platform_role=None):
        # 仅 super_admin;JOIN Customer + 所有 Profile,返回 CustomerRead 含 profiles 列表
```

#### Step 6:API(`app/api/v1/customers.py` 新建)

```python
router = APIRouter(prefix="/customers", tags=["customers"])

# 门店视角(租户级,走 require_permission)
@router.get("/profiles/", dependencies=[Depends(require_permission("customers", "read"))])
@router.post("/profiles/", dependencies=[Depends(require_permission("customers", "create"))])
@router.put("/profiles/{profile_id}", dependencies=[Depends(require_permission("customers", "update"))])
@router.delete("/profiles/{profile_id}", dependencies=[Depends(require_permission("customers", "delete"))])

# 总部视角(平台级,走 require_super_admin)
@router.get("/{customer_id}/aggregate", dependencies=[Depends(require_super_admin())])
@router.get("/", dependencies=[Depends(require_super_admin())])  # 全局客户列表(聚合)
```

- handler 透传 `platform_role=user.platform_role`
- 错误映射用 `_http_exc`(照抄 users.py:29-37)

#### Step 7:注册路由 + 权限 seed

- `app/main.py`:import customers + include_router(字母序)
- **权限 seed**(关键,5 处同步):
  - `app/services/permission_service.py`:
    - `DEFAULT_OWNER_PERMS` 加 4 条:`customers:read/create/update/delete`
    - `DEFAULT_ADMIN_PERMS` 加 2 条:`customers:read/create/update`(无 delete)
    - `DEFAULT_MEMBER_PERMS` 加 1 条:`customers:read`
  - `tests/conftest.py` `_make_casbin`:owner/admin/member 三段各加对应策略行

### 第四阶段:测试 + 总验证

#### Step 8:测试(`tests/test_customers_api.py` 新建)

覆盖维度:
- **门店创建客户(新身份)**:POST /customers/profiles/ 带 identity_key → 201,自动建 Customer + Profile
- **门店创建客户(复用身份)**:同一 identity_key 在门店 A 创建后,门店 B 再创建 → 复用 Customer,只建 Profile(B)
- **本店重复创建**:门店 A 对同一 identity_key 创建两次 → 400 重复
- **门店视图隔离**:门店 A 查 list_profiles 看不到门店 B 的 Profile
- **跨店聚合(super_admin)**:GET /customers/{id}/aggregate 返回 Customer + 所有 profiles
- **权限边界**:member 能 read 不能 create/update/delete;admin 能 create/update 不能 delete;owner 全权
- **更新同步**:update_profile 改 name → Customer 全局 name 同步更新
- **软删除**:delete_profile 软删本店档案;Customer 全局身份保留;聚合视图不再含已删 profile
- **404**:操作不存在的 profile_id/customer_id → 404

#### Step 9:总验证

```bash
./init.sh                       # ruff + pytest 全绿
APP_ENV=testing alembic upgrade head && alembic check  # 迁移 + 无 drift
```

- **通过标准**:ruff 绿 + pytest 全绿(基线 + 新增 ≈ 12)+ alembic check 无 drift
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `./init.sh` 全绿(ruff + pytest,含新增 test_customers_api.py)
2. `alembic upgrade head` + `alembic check` 无 drift
3. 门店能创建/查看/编辑/删除本店客户档案;identity_key 全局唯一,跨店复用同一 Customer
4. 门店视图严格隔离(看不到别店 Profile)
5. super_admin 能看跨店聚合(GET /customers/{id}/aggregate)
6. 权限边界:member read-only / admin 无 delete / owner 全权

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| identity_key 唯一性并发 | Customer 表部分唯一索引(DB 层兜底);Service 层 get_by_identity + try/except IntegrityError |
| 跨店复用 Customer 的并发 | 两个门店同时建同一 identity_key → 一个成功一个 IntegrityError → Service 捕获后重试 get_by_identity |
| 删除 Profile 不删 Customer | Customer 可能被多店引用;delete_profile 只软删本店 Profile;Customer 全局身份保留 |
| update_profile 改 name 同步全局 | Service 内同步更新 Customer.name;若并发改不同 name 以最后为准(MVP 不做冲突检测) |
| 跨店聚合性能 | MVP 客户量小,JOIN 无虑;后续可加缓存 |
| env.py/conftest.py 忘 import | Session 018 教训;alembic check 报 drift 兜底 |

### 不做的事(边界)

- **不做消费记录/订单/服务历史**(MVP 只做档案基础信息)
- **不做跟进/沟通记录**(属 CRM 增强)
- 不做 Customer 与 Group 的绑定(MVP Customer 不绑 Group)
- 不做客户去重/合并(MVP identity_key 唯一即足够)
- 不做前端(customers-ui 是下一任务)
- 不做 hq_staff 跨店只读(hq-platform-role 任务;本任务 super_admin 跨店已够)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 双表 model 模式 | `app/models/tenant.py`(User + UserTenant)+ 已删 organization.py 的 Organization+UserOrganization |
| 跨租户查询范式 | `app/repositories/user.py:117-149`(super_admin 分支)+ `:200-215`(batch_tenant_info) |
| Service super_admin 范式 | `app/services/user_service.py:61-122`(list/get/statistics 三件套) |
| 权限 seed 5 处 | `permission_service.py:373-395` + `conftest.py:31-69` |
| _http_exc 错误映射 | `app/api/v1/users.py:29-37` |
| 测试范式 | `tests/test_agents_api.py` / `tests/test_users_crud.py` |
