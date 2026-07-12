# 计划:删除旧 Organization 模块(清理场地,为 Group 让路)

> 对应 feature_list.json 的 `id`: `org-cleanup`
> 状态: not_started
> 优先级: 29(下一个该做的)
> 参照模板: agents-api-hardening 的「当前状态速查」模式

---

## 背景:为什么删

现有 `Organization` 是「**租户内部的部门树**」(朝阳店内部的导购部/收银组),`tenant_id` 非空外键、永远不能跨门店。用户的新业务模型用「**Group(组织)跨租户管理门店**」替代它——一个 Group 是经营主体(连锁企业或单店),旗下挂 1~N 个门店(tenant)。两个概念同名但完全不同(详见对话设计),**新 Group 建在旧 Organization 删除之后**(groups-api 任务)。

本任务**只做删除 + 清理耦合**,不建任何新表/新模块。删除是破坏性改动,必须把 User 模块对 Organization 的深度耦合一并清理干净,否则 user CRUD 会全线崩溃。

### 当前状态速查(删除影响面)

| 类别 | 文件 | 处理方式 |
|------|------|---------|
| 组织专属-后端 model | `app/models/organization.py`(Organization + UserOrganization) | **整删** |
| 组织专属-后端 repository | `app/repositories/organization.py` | **整删** |
| 组织专属-后端 service | `app/services/organization_service.py` | **整删** |
| 组织专属-后端 api | `app/api/v1/organizations.py` | **整删** |
| 组织专属-后端 schema | `app/schemas/organization.py` | **整删** |
| 组织专属-测试 | `tests/test_organizations_api.py` | **整删** |
| 聚合迁移(建 organizations/user_organizations 表) | `alembic/versions/2026_07_07_0000_c1d2e3f4a5b6_extend_user_rbac_orgs_sessions_logs.py` | **编辑**(抠掉 organizations 相关 create/drop 块,保留其它表) |
| 路由注册 | `app/main.py`(import organizations + include_router) | 编辑删 2 行 |
| model 发现(Alembic) | `alembic/env.py`(import organization) | 编辑删 1 行 |
| model 发现(测试) | `tests/conftest.py`(import organization) | 编辑删 1 行 |
| **User schema 耦合** | `app/schemas/user.py`(`OrganizationBrief` 类 + UserRead.organizations + UserCreate/Update.organization_ids) | **编辑**(删类 + 删字段) |
| **User repository 耦合** | `app/repositories/user.py`(import Organization/UserOrganization + list_organizations + sync_organizations + serialize_user 的 organizations 形参) | **编辑**(删 import + 删两方法 + 简化 serialize_user) |
| **User service 耦合** | `app/services/user_service.py`(import Organization + _validate_org_ids + 调用 list_organizations/sync_organizations) | **编辑**(删 import + 删校验 + 删调用) |
| 校验中文化映射 | `app/core/validation_errors.py`(`"organization_ids": "所属组织"`) | 编辑删 1 行 |
| 权限 seed-生产 | `app/services/permission_service.py`(DEFAULT_OWNER/ADMIN/MEMBER_PERMS 的 organizations 项) | 编辑删 4-5 个 tuple |
| 权限 seed-测试 | `tests/conftest.py`(_make_casbin 里 owner/admin/member 的 organizations 策略行) | 编辑删对应行 |
| 前端-组织页 | `frontend/src/pages/organizations-page.tsx` | **整删** |
| 前端-API 层 | `frontend/src/api/endpoints.ts`(fetchOrganizationTree 等)+ `types.ts`(Organization 等) | 编辑删对应块 |
| 前端-hooks | `frontend/src/hooks/queries.ts`(qk.organizations + useOrganization* 等) | 编辑删对应块 |
| 前端-路由导航 | `frontend/src/App.tsx` + `components/layout/dashboard-layout.tsx`(NAV_ITEMS 组织项) + `pages/dashboard-page.tsx`(残留 Link) | 编辑删对应行 |
| 前端-权限矩阵页 | `frontend/src/pages/permissions-page.tsx`(organizations 权限项展示) | 编辑删对应项 |
| 前端-用户表单耦合 | `frontend/src/pages/users-page.tsx`(组织多选下拉 + organization_ids 提交) | **编辑**(删组织字段表单,若存在) |

---

## 目标

1. 彻底移除 `Organization` / `UserOrganization` 两张表 + 全部后端代码 + 全部前端代码
2. 清理 User 模块对 Organization 的耦合(schema/repository/service/前端表单),User CRUD 保持正常
3. 清理权限 seed(permission_service 3 常量 + conftest casbin)
4. 聚合迁移文件 `c1d2e3f4a5b6` 抠掉建表/删表块(保留其它表),迁移链仍可 `alembic upgrade head` + `alembic check` 无 drift
5. `./init.sh` 全绿(ruff + pytest)+ `cd frontend && npm run build` 通过

---

## 前置条件

- 无外部依赖。main 当前干净(基线 250 passed)。
- **WIP=1**:本任务执行期间,不开始 groups-api。

---

## 实施步骤

> ⚠️ 执行前先快速 grep 确认下表文件路径无漂移(行号可能因 main 演进变化)。

### 第一阶段:删组织专属文件(后端 5 + 测试 1)

#### Step 1:整删 6 个组织专属文件

```bash
rm app/models/organization.py
rm app/repositories/organization.py
rm app/services/organization_service.py
rm app/api/v1/organizations.py
rm app/schemas/organization.py
rm tests/test_organizations_api.py
```

- **检查**:`git status` 显示 6 个 deleted;此时 `./init.sh` 会因 import 报错(import organization 失败),**预期**,后续 Step 会修。

### 第二阶段:清理 User 模块对 Organization 的耦合(高风险区)

> 这是整个任务最易出错的地方。User 的 repository JOIN 了 user_organizations 表,service 直接查 Organization 表——必须同步清理,否则 user 列表/详情/创建全部崩溃。

#### Step 2:清理 User schema(`app/schemas/user.py`)

- **删** `OrganizationBrief` 类(L15-19)
- **删** `UserRead.organizations` 字段(L43)
- **删** `UserCreate.organization_ids` 字段(L61)
- **删** `UserUpdate.organization_ids` 字段(L73)
- **检查**:grep `"organization" app/schemas/user.py` 零命中

#### Step 3:清理 User repository(`app/repositories/user.py`)

- **删** import:`from app.models.organization import Organization, UserOrganization`(L16)
- **删** `list_organizations` 方法(L217-224)
- **删** `sync_organizations` 方法(L226-243)
- **改** `serialize_user` 函数:删 `organizations: list[Organization] | None = None` 形参(L253)+ 删 orgs 构造块(L267-270)+ 删返回 dict 的 `"organizations": orgs`(L281)
- **检查**:grep `"Organization" app/repositories/user.py` 零命中;`serialize_user` 不再含 organizations

#### Step 4:清理 User service(`app/services/user_service.py`)

- **删** import:`from app.models.organization import Organization`(L23)
- **删** `_validate_org_ids` 方法(L487 附近)
- **删** 所有调用 `self.list_repo.list_organizations` / `sync_organizations` / `_validate_org_ids` 的位置(grep 定位,约 L139-140/165-166/202-203/232-233/322-325)
- **改** `serialize_user` 调用点:去掉 `organizations=orgs` 实参
- **检查**:grep `"organization" app/services/user_service.py` 零命中;`./init.sh` 此时 pytest 应该开始变绿(除前端外)

#### Step 5:清理校验中文化映射(`app/core/validation_errors.py`)

- **删** `"_FIELD_LABELS"` 里的 `"organization_ids": "所属组织"`(L35)
- **检查**:grep `"organization" app/core/validation_errors.py` 零命中

### 第三阶段:清理迁移 + model 注册 + 路由

#### Step 6:编辑聚合迁移 `c1d2e3f4a5b6`(抠 organizations 块)

⚠️ **不能整删这个文件**(它一次建了多张表:users 扩展/rBAC/orgs/sessions/logs)。只编辑它,移除:
- upgrade() 里 `op.create_table("organizations", ...)` 块(L141-158 附近)+ 2 个索引(L159-160)
- upgrade() 里 `op.create_table("user_organizations", ...)` 块(L163-175)+ 2 个索引(L176-177)
- downgrade() 里对应的 drop 块(L289-295)
- 文件头注释里提 organizations 的部分(L11,若提及)

- **检查**:`alembic upgrade head`(SQLite 测试库)成功;`alembic check` 无 drift(因 metadata 也没了 organization,autogenerate 不会误判)

#### Step 7:清理 model 发现 + 路由注册

- `alembic/env.py`:删 `organization,`(L23 的 import 块内)
- `tests/conftest.py`:删 `organization,`(L95 的 import 块内)
- `app/main.py`:删 `organizations,`(import 块)+ 删 `app.include_router(organizations.router, ...)`(L70)
- **检查**:grep `"organization" app/main.py alembic/env.py tests/conftest.py` 仅剩 conftest 的 casbin seed(下一 Step 处理)

### 第四阶段:清理权限 seed

#### Step 8:清理生产权限 seed(`app/services/permission_service.py`)

`DEFAULT_OWNER_PERMS`(L378-379)/ `DEFAULT_ADMIN_PERMS`(L387)/ `DEFAULT_MEMBER_PERMS`(L394)各删 `("organizations", ...)` tuple:
- OWNER 删 4 条:organizations read/create/update/delete
- ADMIN 删 1 条:organizations read
- MEMBER 删 1 条:organizations read

#### Step 9:清理测试 casbin seed(`tests/conftest.py`)

`_make_casbin`(L31-69)owner(L47-48)/ admin(L59)/ member(L59 附近)各删 `("organizations", ...)` 策略行。

- **检查**:`./init.sh` 全绿(ruff + pytest,基线 250 减去 test_organizations_api 的条数;无回归)

### 第五阶段:清理前端

#### Step 10:删组织页 + 清理 API/hooks/types/路由导航

- **删** `frontend/src/pages/organizations-page.tsx`
- **编辑** `frontend/src/api/endpoints.ts`:删 import(L19-22)+ 删 fetchOrganizationTree/fetchOrganizations/createOrganization/updateOrganization/deleteOrganization 函数块(L286-313)
- **编辑** `frontend/src/api/types.ts`:删 Organization/OrganizationTreeNode/OrganizationCreate/OrganizationUpdate 接口(L183/196-197/200/208)。**保留** OrganizationBrief(L52)和 organization_ids(L86)? ——不,这些是 User 关联字段,随 Step 2 schema 删除一并清理:删 types.ts 里 UserCreate/UserUpdate 的 organization_ids 字段 + UserRead 的 organizations 字段
- **编辑** `frontend/src/hooks/queries.ts`:删 import + 删 qk.organizations(L83-84)+ 删 useOrganizationTree/useCreateOrganization/useUpdateOrganization/useDeleteOrganization(L309-343)
- **编辑** `frontend/src/App.tsx`:删 import OrganizationsPage(L13)+ 删 Route(L58)
- **编辑** `frontend/src/components/layout/dashboard-layout.tsx`:删 NAV_ITEMS 组织项(L36)+ 清理 Building2 图标 import(若仅组织项用)
- **编辑** `frontend/src/pages/dashboard-page.tsx`:删残留 `<Link to="/organizations">`(L146)
- **编辑** `frontend/src/pages/permissions-page.tsx`:删 organizations 权限项展示(L40/70/81 附近,obj 分组里的 organizations)
- **编辑** `frontend/src/pages/users-page.tsx`:删组织多选下拉 + organization_ids 表单字段(grep organization_ids 定位)

#### Step 11:前端总验证

```bash
cd frontend && npm run build   # tsc + vite 0 类型错误
npx oxlint .                    # 0 warnings
```

- **检查**:build 通过 + oxlint 0 warning + grep `"organization" frontend/src/` 零残留(或仅注释)

### 第六阶段:总验证

#### Step 12:全栈验证

```bash
./init.sh                       # ruff + pytest 全绿
cd frontend && npm run build    # tsc + vite 0 类型错误
APP_ENV=testing alembic upgrade head   # 迁移链通
APP_ENV=testing alembic check          # 无 drift
```

- **通过标准**:
  - ruff All checks passed!
  - pytest 全绿(基线 250 - test_organizations_api 条数,无其它回归)
  - npm build 0 类型错误
  - alembic check 无 drift
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

(feature_list.json 的 verification 字段与这里同步)

1. `./init.sh` 全绿(ruff + pytest,除 test_organizations_api 整删外无其它回归)
2. `cd frontend && npm run build` 通过(tsc + vite)+ oxlint 0 warning
3. `alembic upgrade head` + `alembic check` 无 drift(聚合迁移文件已抠 organizations 块)
4. grep `"organization" app/ frontend/src/`(排除注释)零残留,或仅注释里提及
5. User CRUD 全部正常(list/get/create/update/delete 不因删 Organization 崩溃)
6. 权限矩阵页不再显示「组织」列

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| User repository JOIN 删除后 user 列表崩 | Step 3 必须同步删 list_organizations/sync_organizations/serialize_user 形参;改完先跑 `pytest tests/test_users_crud.py` 验证 |
| 聚合迁移整删会丢其它表历史 | **只编辑不删**;抠掉 organizations 相关 create/drop 块,保留 users/rbac/sessions/logs |
| 其它测试引用 organization | Step 9 同步清 conftest casbin seed;grep `tests/` 找 test_rbac_api/test_service_platform_role/test_users_crud 里的 organization 引用,逐处改 |
| 前端 users-page 表单含 organization_ids | Step 10 末尾 grep `organization_ids frontend/src/` 确认零残留 |
| validation_errors 中文映射残留报错 | Step 5 删 `"organization_ids"` 映射;grep 确认 |
| 权限矩阵页 obj 分组硬编码 organizations | permissions-page.tsx 可能硬编码 obj 列表,删 organizations 项;若 obj 来自后端 catalogue 则自动消失 |

### 不做的事(边界)

- **不建任何新表**(Group 是 groups-api 任务)
- 不改 User 表核心字段(只删 schema 的 organization 关联字段,不动 User 表本身)
- 不改 casbin 模型文件(`casbin_model.conf`)
- 不删除 `Organization` 的中文文档篇(项目指南可能有提及,文档影响评估单独处理)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| Organization model(待删) | `app/models/organization.py` |
| User schema 耦合点(待改) | `app/schemas/user.py:15-19,43,61,73` |
| User repository 耦合点(待改) | `app/repositories/user.py:16,217-243,253,267-270,281` |
| User service 耦合点(待改) | `app/services/user_service.py:23,139-140,165-166,202-203,232-233,322-325,487` |
| 聚合迁移(待编辑) | `alembic/versions/2026_07_07_0000_c1d2e3f4a5b6_extend_user_rbac_orgs_sessions_logs.py:141-177,289-295` |
| 权限 seed | `app/services/permission_service.py:373-395` + `tests/conftest.py:31-69` |
| 前端组织页(待删) | `frontend/src/pages/organizations-page.tsx` |
