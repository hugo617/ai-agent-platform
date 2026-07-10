# 计划:角色管理 CRUD 全栈对齐(前后端 + 权限分配)

> 对应 feature_list.json 的 `id`: `roles-crud`
> 状态: not_started
> 参照模板: 用户管理 CRUD(`app/api/v1/users.py` + `frontend/src/pages/users-page.tsx`)

---

## 背景:为什么不是"从零搭建"

角色 CRUD 的**后端已完整实现**并接入路由(8 个端点,main.py:51 注册)。本任务的真实工作是:
1. 后端:把错误处理、测试覆盖对齐到 user 模板的稳健度
2. 前端:把 `roles-page.tsx`(122 行硬编码空壳)重写为真实数据驱动的 CRUD + 权限分配页面

### 当前状态速查

| 层 | 状态 | 文件 |
|----|------|------|
| Model | ✅ 已完成 | `app/models/rbac.py` Role 表(L38-74) |
| Repository | ✅ 已完成 | `app/repositories/rbac.py` RoleRepository + RolePermissionRepository(SCD2) |
| Service | ✅ 已完成 | `app/services/rbac_service.py` RbacService(L31-267) |
| Schema | ✅ 已完成 | `app/schemas/rbac.py` RoleRead/Create/Update + PermissionGrant/Read |
| API | ✅ 已完成 | `app/api/v1/roles.py` 8 个端点,已注册路由 |
| 测试 | ⚠️ 仅 4 个 | `tests/test_rbac_api.py`(happy path + 重复拒绝) |
| 前端 | ❌ 空壳 | `frontend/src/pages/roles-page.tsx` 硬编码静态数据 |

---

## 目标

让角色管理达到与用户管理同等的完成度:
- 后端错误处理稳健(异常类型映射,不靠字符串匹配)
- 测试覆盖完整(权限边界/超管/权限授权端点)
- 前端可用:角色列表 + 创建/编辑/删除 + 权限分配 UI

---

## 前置条件

- 无外部依赖。后端端点已就绪,前端可直接对接。

---

## 实施步骤

### 第一阶段:后端对齐(改 Service 异常 + 错误映射)

#### Step 1:RbacService 改用类型化异常

当前 `app/services/rbac_service.py` 全部抛裸 `ValueError`,API 层靠 `if "not found" in msg` 字符串匹配判 404/400。
改为抛 `NotFoundError`/`BizError`(都是 ValueError 子类,见 `app/services/errors.py`),对齐 UserService 模式。

- **改什么**(`app/services/rbac_service.py`):
  - L87 `raise ValueError(f"role {role_id} not found")` → `raise NotFoundError(f"role {role_id} not found")`
  - L109 同上(delete 里的 not found)
  - L131 同上(list_permissions 里的 not found)
  - L67 `raise ValueError("role code or name already exists...")` → `raise BizError("role code or name already exists...")`
  - L111 `raise ValueError("system roles cannot be deleted")` → `raise BizError("system roles cannot be deleted")`
  - L219 `raise ValueError("permission is not currently granted...")` → `raise NotFoundError("permission is not currently granted...")`
  - import: `from app.services.errors import BizError, NotFoundError`
- **检查**:现有 `except ValueError` 仍能捕获(因为子类),不会破坏现有调用。

#### Step 2:roles.py 错误映射改异常类型

当前 `app/api/v1/roles.py` 用 `_bad_request`/`_not_found` + 字符串匹配。
改为对齐 `users.py:29-37` 的 `_http_exc`(按 `isinstance(e, NotFoundError)` 映射)。

- **改什么**(`app/api/v1/roles.py`):
  - 删除 `_bad_request`/`_not_found` 两个辅助函数(L26-31)
  - 加 `_http_exc` 函数(照抄 `users.py:29-37` 的模式)
  - import: `from app.services.errors import NotFoundError`
  - 所有 `try/except ValueError` 块改为 `except ValueError as e: raise _http_exc(e)`
- **检查**:更新角色返回 404(而非 400)、重复 code 返回 400、系统角色删除返回 400。

### 第二阶段:测试覆盖补全

#### Step 3:补 test_rbac_api.py 的覆盖

当前 `tests/test_rbac_api.py` 只有 4 个测试。参照 `test_users_api.py` 的覆盖维度补全。

- **新增测试用例**(用 `app_client`/`member_client`/`super_admin_client` fixture):
  - 权限边界:`member_client` POST /roles → 403(member 无 roles:create)
  - 权限边界:`member_client` DELETE /roles/{id} → 403
  - 系统角色保护:DELETE 系统角色(owner/admin/member)→ 400
  - 软删除:删除角色后列表不再出现;code 可复用
  - 更新:PUT 改 name/description 后 GET 确认
  - **权限授权端点**(当前 0 覆盖):
    - POST /roles/{id}/permissions 授予权限 → 201
    - GET /roles/{id}/permissions → 含刚授的权限
    - DELETE /roles/{id}/permissions/{pid} 撤权 → 204
    - 对不存在的 role_id 操作 → 404
- **检查**:`pytest tests/test_rbac_api.py -v` 全过。

### 第三阶段:前端 API 层补全

#### Step 4:补 endpoints.ts + types.ts 缺失项

- **`frontend/src/api/types.ts`**:加 `RoleUpdate`(name?/description?/sort_order?/status?),参照 `UserUpdate`
- **`frontend/src/api/endpoints.ts`**(L214-235 当前缺 update):
  - 补 `updateRole(id, data)` → PUT /roles/{id}
  - 补 `fetchRolePermissions(id)` → GET /roles/{id}/permissions
  - 补 `grantRolePermission(id, payload)` → POST /roles/{id}/permissions
  - 补 `revokeRolePermission(id, permId)` → DELETE /roles/{id}/permissions/{permId}
- **检查**:TypeScript 编译无错误(`npm run build`)

#### Step 5:补 hooks/queries.ts

- **`frontend/src/hooks/queries.ts`**(L189-202 当前只有 useRoleLabels/useCreateRole):
  - 补 `useFetchRoles()`(列表查询,key 参照 useUsers)
  - 补 `useUpdateRole()`(mutation,成功后 invalidate roles key)
  - 补 `useDeleteRole()`(mutation,成功后 invalidate)
  - 补 `useRolePermissions(roleId)`(权限列表查询)
  - 补 `useGrantPermission()`/`useRevokePermission()`(mutation,成功后 invalidate permissions)
- **检查**:`npm run build` 通过

### 第四阶段:前端页面重写

#### Step 6:重写 roles-page.tsx

当前 `frontend/src/pages/roles-page.tsx`(122 行)是硬编码空壳。参照 `users-page.tsx`(720 行)的模式重写。

- **核心结构**(参照 users-page.tsx):
  - 角色列表表格(TanStack Table 或简单 table,显示 name/code/description/status/is_system)
  - 创建/编辑角色的弹窗(Dialog,参照 users-page 的表单弹窗)
  - 删除确认(系统角色禁用删除按钮)
  - **权限分配面板**(角色管理独有):点角色的"权限"→ 弹窗展示该角色当前权限 + 可授予/撤销
- **用到的 hook**:useFetchRoles / useCreateRole / useUpdateRole / useDeleteRole + useRolePermissions / useGrantPermission / useRevokePermission
- **权限守卫**:页面已在 `<RequireUserManagement>` 内(App.tsx),导航项已有 needsUserManagement 标记
- **检查**:能列表、创建、编辑、删除角色;能给角色授予/撤销权限

### 第五阶段:总验证

#### Step 7:全栈验证

- **命令**:
  ```bash
  # 后端
  ./init.sh                    # ruff + pytest 全绿(含新增测试)
  # 前端
  cd frontend && npm run build # 类型检查 + 构建
  ```
- **手动验证**(启动后):
  - 用 owner 登录 → 角色页 → 看到真实角色列表(非硬编码)
  - 创建一个新角色 → 列表出现 → 编辑 → 删除
  - 给新角色授权 → 权限列表更新
  - 用 member 登录 → 角色页可见(roles:read)但无创建/删除按钮
- **通过标准**:
  - `./init.sh` 全绿
  - `npm run build` 通过
  - 手动验证全过
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

(feature_list.json 的 verification 字段与这里同步)

1. `./init.sh` 全绿(ruff + pytest,含新增的角色测试)
2. `cd frontend && npm run build` 通过
3. 后端错误映射用异常类型(`isinstance`),不再用字符串匹配(`if "not found" in msg`)
4. test_rbac_api.py 覆盖:权限边界(member 403)、系统角色保护、权限授权端点 CRUD、404
5. 前端角色页接真实数据,能完成 角色 CRUD + 权限分配 全流程

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| RbacService 改异常类型后破坏现有调用 | `NotFoundError`/`BizError` 是 `ValueError` 子类,`except ValueError` 仍捕获;现有 4 个测试会验证不破 |
| 前端 roles-page 重写量大 | 参照 users-page.tsx 模式,复用相同的组件库(Dialog/Table/Form);分 Step 6 单独做 |
| 权限分配 UI 复杂(权限项可能很多) | 第一版可做"按模块分组(obj)勾选",不求花哨;后端已有 grant/revoke 端点支撑 |
| UserTenant.role 是字符串非 FK | 本任务不动这个设计(改它影响面太大);仅确保角色 code 与 casbin 角色名一致 |

### 不做的事(边界)
- 不改 `UserTenant.role` 为外键(影响面大,超本任务范围)
- 不做角色排序拖拽(sort_order 字段保留,但 UI 第一版不实现拖拽)
- 不做完整的 i18n(配合 validation-error-i18n 任务,但不强依赖)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 用户 CRUD API(模板) | `app/api/v1/users.py` |
| 用户 Service(模板) | `app/services/user_service.py` |
| 用户前端页面(模板) | `frontend/src/pages/users-page.tsx` |
| 异常定义 | `app/services/errors.py`(BizError/NotFoundError) |
| 角色 API(待改) | `app/api/v1/roles.py` |
| 角色 Service(待改) | `app/services/rbac_service.py` |
| RBAC 文档 | `项目指南/02-后端架构/06-权限模型RBAC.md` |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
