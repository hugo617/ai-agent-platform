# 计划:门店(租户)管理后端补齐 —— 平台级列表 + 编辑 + 详情

> 对应 feature_list.json 的 `id`: `tenants-admin-api`
> 状态: not_started
> 优先级: 30
> 前置: `org-cleanup`(旧 Organization 已删除,main 干净)

---

## 背景:租户(门店)管理能力现状太弱

核实发现租户后端**只有两个端点**(`app/api/v1/tenants.py`),能力严重不足:

| 现有端点 | 功能 | 问题 |
|---------|------|------|
| `POST /tenants/` | 创建租户(创建者成 owner) | ⚠️ 权限宽松(任何登录用户都能建,非 super_admin 专属) |
| `GET /tenants/` | 列出**我自己**的租户 | ⚠️ super_admin 看不到所有门店 |

**完全缺失的能力**:
- ❌ super_admin **看不到所有门店**(无平台级 list-all 端点)
- ❌ 门店**不能改名/编辑**(无 PUT)
- ❌ 门店**没有详情端点**(无 GET /tenants/{id} 含成员数等聚合信息)
- ❌ groups-ui / customers-ui 需要**门店下拉列表**,但后端提供不了(只有「我的租户」)

本任务补齐这些能力,为 groups-ui(门店挂载下拉)和 customers-ui(客户归属门店)提供数据源。

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| `app/api/v1/tenants.py` | ⚠️ 仅 2 端点 | POST 创建 + GET 我的租户(各 37 行内) |
| `app/services/tenant_service.py` | ⚠️ 仅 create + list_user_tenants | 无 list_all / get_detail / update |
| `app/repositories/tenant.py` TenantRepository | ⚠️ 仅 get_by_id | 无 list_all / 统计 |
| `app/schemas/tenant.py` | ⚠️ 仅 name 字段 | TenantRead 太简陋(无成员数/创建者/状态) |
| 权限守卫 | ⚠️ POST 无 super_admin 守卫 | 任何登录用户都能创建租户 |

---

## 目标

1. 新增 **`GET /tenants/all`**(super_admin 看所有门店,平台级列表 + 聚合信息)
2. 新增 **`GET /tenants/{id}`**(门店详情:含成员数/创建者/状态/所属 Group)
3. 新增 **`PUT /tenants/{id}`**(super_admin 编辑门店名/状态)
4. 收紧 **`POST /tenants/`** 权限(super_admin 专属;现有「任意用户可建」改为平台级管控)
5. TenantRead 扩展:加 status / member_count / created_by(供前端展示)
6. 为 groups-ui / customers-ui 提供门店下拉数据源

### 权限设计

| 端点 | 权限 |
|------|------|
| `GET /tenants/`(我的租户,保留) | 任何登录用户 |
| `GET /tenants/all`(全部门店) | super_admin |
| `GET /tenants/{id}`(详情) | super_admin(门店详情含跨租户信息) |
| `POST /tenants/`(创建) | **收紧为 super_admin**(原来是任意登录用户) |
| `PUT /tenants/{id}`(编辑) | super_admin |

---

## 前置条件

- `org-cleanup` 完成(旧 Organization 已删)—— 已 passing
- 迁移 head = `6f197cf8f964`(customers 表;执行前 `alembic heads` 确认)

---

## 实施步骤

> ⚠️ 执行前 grep 确认 `tenants.py` / `tenant_service.py` / `tenant.py`(repo)无漂移。

### 第一阶段:扩展数据模型 + 迁移

#### Step 1:Tenant model 加字段(`app/models/tenant.py`)

当前 `Tenant` 只有 `id`/`name`/`created_at`(`tenant.py:26-40`)。加:
```python
status: Mapped[str] = mapped_column(String(20), default="active")  # active/inactive/locked
created_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("users.id"), nullable=True)
description: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 门店描述/简介
address: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 门店地址
```

- ⚠️ **member_count 不存表**(运行时聚合:COUNT UserTenant),避免冗余维护

#### Step 2:Alembic 迁移

```bash
alembic revision --autogenerate -m "add tenant status/created_by/description/address"
```

- **同步**:`alembic/env.py` + `tests/conftest.py`(tenant 已 import,无需改)
- 给现有行填 server_default(status='active')
- **检查**:`alembic upgrade head` + `alembic check` 无 drift

### 第二阶段:Schema + Repository + Service

#### Step 3:扩展 Schema(`app/schemas/tenant.py`)

```python
class TenantRead(BaseModel):  # from_attributes=True
    id, name, status, description, address
    member_count: int = 0          # 运行时聚合(非表字段)
    created_by: str | None
    created_at: datetime

class TenantUpdate(BaseModel):   # 全 Optional,super_admin 编辑
    name: str | None
    status: str | None
    description: str | None
    address: str | None
```

#### Step 4:扩展 Repository(`app/repositories/tenant.py`)

TenantRepository 加方法:
```python
async def list_all() -> list[Tenant]                              # 平台级全部(super_admin)
async def list_all_with_member_count() -> list[tuple[Tenant, int]]  # JOIN 聚合成员数
async def get_detail(tenant_id) -> Tenant | None
async def update(tenant, payload) -> Tenant
```

#### Step 5:扩展 Service(`app/services/tenant_service.py`)

```python
async def list_all(self, platform_role=None) -> list[TenantRead]:
    # require_super_admin 在 API 层守卫;Service 直接查全部 + 聚合 member_count

async def get_detail(self, tenant_id, platform_role=None) -> TenantRead:
    # 单门店详情 + member_count

async def update(self, tenant_id, payload, platform_role=None) -> TenantRead:
    # 编辑门店信息
```

- `create_tenant` 加 `platform_role` 参数(用于 API 层收紧权限后仍兼容内部调用)

### 第三阶段:API + 权限收紧

#### Step 6:扩展 API(`app/api/v1/tenants.py`)

```python
@router.get("/all", response_model=list[TenantRead],
             dependencies=[Depends(require_super_admin())])    # 新增:super_admin 全部
@router.get("/{tenant_id}", response_model=TenantRead,
             dependencies=[Depends(require_super_admin())])    # 新增:详情
@router.put("/{tenant_id}", response_model=TenantRead,
             dependencies=[Depends(require_super_admin())])    # 新增:编辑

# 收紧 POST 权限
@router.post("/", ..., dependencies=[Depends(require_super_admin())])  # 原来无守卫,现改 super_admin
```

- ⚠️ `GET /tenants/`(我的租户,保留无守卫)与 `GET /tenants/all`(全部,super_admin)路径不冲突
- import `require_super_admin` from deps

### 第四阶段:测试 + 总验证

#### Step 7:测试(`tests/test_tenants_api.py` 扩展)

当前 `test_tenants_api.py`(8 tests,覆盖现有 create + list_my)。新增:
- **super_admin list_all**:GET /tenants/all → 200 返回所有门店
- **非 super_admin list_all**:GET /tenants/all → 403
- **super_admin get_detail**:GET /tenants/{id} → 200 含 member_count
- **super_admin update**:PUT /tenants/{id} 改 name/status → 200
- **POST 权限收紧**:非 super_admin POST /tenants/ → 403(原 201,行为变更)
- **404**:GET/PUT 不存在的 tenant_id → 404
- **回归**:现有 GET /tenants/(我的租户)仍对普通用户 200

#### Step 8:总验证

```bash
./init.sh                       # ruff + pytest 全绿
APP_ENV=testing alembic upgrade head && alembic check  # 迁移 + 无 drift
```

- **通过标准**:ruff 绿 + pytest 全绿(基线 + 新增 ≈ 7)+ alembic check 无 drift
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `./init.sh` 全绿(ruff + pytest,含扩展的 test_tenants_api.py)
2. `alembic upgrade head` + `alembic check` 无 drift
3. super_admin 能:GET /tenants/all(全部门店)、GET /tenants/{id}(详情含 member_count)、PUT /tenants/{id}(编辑)
4. 非 super_admin:GET /tenants/all → 403、POST /tenants/ → 403(权限收紧)
5. GET /tenants/(我的租户)对普通用户仍 200(无回归)
6. TenantRead 含 member_count(供前端门店列表展示)

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| POST 权限收紧破坏现有 dashboard 创建租户 | dashboard 的「创建租户」按钮原面向所有用户;收紧后普通用户 403。需同步改前端:创建按钮仅 super_admin 可见(在 tenants-admin-ui 任务处理) |
| bootstrap 路径依赖 POST /tenants/ | `main.py` 的 dev-seed / init_admin.py 若用 POST /tenants/ 建初始租户,收紧后会 403。改用 Service 层直接调 `tenant_service.create_tenant`(绕过 HTTP 守卫),grep 确认 bootstrap 路径 |
| member_count 聚合性能 | 门店数量小(MVP),JOIN COUNT 无虑 |
| GET /tenants/all 与 GET /tenants/ 路径 | 不冲突(all 是子路径,但 FastAPI 路由匹配顺序要注意:把 /all 定义在 /{tenant_id} 之前,否则 "all" 被当 tenant_id) |

### 不做的事(边界)

- 不做门店删除(DELETE,门店软删除涉及数据归属复杂,MVP 不做)
- 不做门店切换登录(切租户需重新登录,JWT tenant_id 绑定,属认证增强)
- 不做门店导入/导出
- 不做前端(tenants-admin-ui 是下一任务)
- 不改 casbin seed(门店管理走 require_super_admin,不进租户级 RBAC)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 现有租户 API(待扩展) | `app/api/v1/tenants.py` |
| 现有租户 Service(待扩展) | `app/services/tenant_service.py` |
| 现有 TenantRepository(待扩展) | `app/repositories/tenant.py:18-25` |
| 现有 Tenant model(待加字段) | `app/models/tenant.py:26-40` |
| require_super_admin | `app/api/deps.py:246-262` |
| 跨租户聚合范式 | `app/repositories/user.py:155-198`(statistics 的 super_admin 分支) |
| 测试范式 | `tests/test_tenants_api.py`(现有 8 tests) |
