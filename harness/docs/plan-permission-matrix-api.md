# 计划:权限矩阵后端(聚合查询 + 全量权限项端点)

> 对应 feature_list.json 的 `id`: `permission-matrix-api`
> 状态: not_started
> 优先级: 14
> 前置: 无(grant/revoke 端点已在 roles.py,本任务补聚合查询)

---

## 背景:为什么需要这个任务

`permissions-page.tsx` 当前**硬编码**了一个失真的矩阵:只覆盖 `agents`/`conversations` 两个资源 + `owner`/`member` 两个角色,而真实权限模型有 **5 个资源**(agents/conversations/users/roles/organizations)× **3 个角色**(owner/admin/member)× **多种动作**。

前端要展示真实矩阵并支持在线编辑,后端必须提供两个聚合端点:
1. **矩阵端点**:返回"某租户全部角色 × 全部权限"的当前生效状态(从 SCD2 当前态取)
2. **权限目录端点**:返回该租户所有可用的权限项(资源 + 动作清单)

grant/revoke 端点已在 `roles.py`(L118-158),不需要重建。

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| grant/revoke 端点 | ✅ 已有 | `app/api/v1/roles.py` L118-158 |
| 角色的当前权限查询 | ✅ 已有 | `RolePermissionRepository.current_permissions` |
| 权限目录表(Permission) | ✅ 已有 | `app/models/rbac.py` Permission(code="<obj>:<act>") |
| 默认权限矩阵(真相源) | ✅ 已有 | `permission_service.py` L320-338 DEFAULT_*_PERMS |
| 聚合矩阵端点 | ❌ 缺 | 无"全部角色 × 全部权限"聚合 |
| 权限目录端点 | ❌ 缺 | 无"列出全部权限项"端点 |

---

## 目标

提供两个只读端点,让前端能拿到真实、完整的权限矩阵数据:
1. `GET /permissions/matrix` —— 返回 `{roles: [{id, code, name}], matrix: {role_code: {permission_code: bool}}}`
2. `GET /permissions/catalogue` —— 返回全部权限项 `[{id, code, obj, act, name}]`

---

## 前置条件

- 无。所有底层数据(SCD2 表、Permission 表、casbin)已就绪。

---

## 实施步骤

### 第一阶段:Schema 定义

#### Step 1:定义矩阵响应 schema

- **改什么**(`app/schemas/rbac.py`,末尾追加):
  ```python
  class PermissionItem(BaseModel):
      """A single permission catalogue entry."""
      model_config = ConfigDict(from_attributes=True)
      id: str
      code: str          # "<obj>:<act>"
      name: str
      obj: str           # 解析自 code 的资源部分
      act: str           # 解析自 code 的动作部分

  class PermissionMatrix(BaseModel):
      """Aggregated role × permission matrix for a tenant."""
      roles: list["RoleRead"]              # 该租户全部角色
      permissions: list[PermissionItem]    # 该租户全部权限项
      matrix: dict[str, dict[str, bool]]   # {role_code: {permission_code: granted}}
  ```
- **检查**:tsc 无关(后端 schema);`app/schemas/rbac.py` 现有 RoleRead 可前向引用

### 第二阶段:Service 聚合方法

#### Step 2:PermissionService 加矩阵聚合方法

- **改什么**(`app/services/permission_service.py`,加新方法 或 在 `rbac_service.py` 加):
  ```python
  async def get_permission_matrix(self, tenant_id: str, db: AsyncSession) -> dict:
      """Aggregate the current role × permission matrix for a tenant.
      数据源:RolePermissionRepository.current_permissions(SCD2 当前态)
      """
      # 1. 取该租户全部角色(code, id, name)
      # 2. 取该租户全部 Permission 目录(code, obj, act)
      # 3. 对每个角色,取 current_permissions → 得到 {permission_code: True}
      # 4. 组装 matrix: {role_code: {perm_code: bool}}
  ```
- **数据源说明**:
  - 角色:`select(Role).where(tenant_id=..., is_deleted=False)`
  - 权限目录:`select(Permission).where(tenant_id=..., is_deleted=False)`
  - 角色权限:`RolePermissionRepository(role).current_permissions(role_id, tenant_id)`(已有方法,返回 SCD2 当前生效行)
- **检查**:返回的 matrix 与 `DEFAULT_*_PERMS` 对得上(新建租户的初始矩阵 = 默认 seed)

### 第三阶段:API 端点

#### Step 3:新建 permissions.py API(矩阵 + 目录)

- **新建文件** `app/api/v1/permissions.py`:
  ```python
  router = APIRouter(prefix="/permissions", tags=["permissions"])

  @router.get(
      "/matrix",
      response_model=PermissionMatrix,
      dependencies=[Depends(require_permission("roles", "read"))],
  )
  async def get_permission_matrix(user, db):
      # 调 service.get_permission_matrix(user.tenant_id, db)
      # 返回 PermissionMatrix

  @router.get(
      "/catalogue",
      response_model=list[PermissionItem],
      dependencies=[Depends(require_permission("roles", "read"))],
  )
  async def get_permission_catalogue(user, db):
      # 返回该租户全部 Permission 目录项
  ```
- **权限选择**:用 `require_permission("roles", "read")`——能看角色的人才能看权限矩阵(权限管理语义相近;避免新增权限项增加管理负担)
- **路由注册**(`app/main.py`):import `permissions` + `app.include_router(permissions.router, prefix=prefix)`

### 第四阶段:测试

#### Step 4:补测试

- **新建或追加** `tests/test_permissions_api.py`(若无):
  - **矩阵正确性**:新建租户后 GET /permissions/matrix → owner 有全部 19 项,admin 有 11 项,member 有 5 项(对照 DEFAULT_*_PERMS)
  - **grant 后矩阵更新**:grant 某 permission 给 member → 再 GET → matrix 反映
  - **revoke 后矩阵更新**:revoke → matrix 反映
  - **跨租户隔离**:租户 B GET → 看不到租户 A 的角色/权限
  - **权限边界**:member_client GET /permissions/matrix → 200(member 有 roles:read);但若无 roles:read 的角色 → 403
  - **目录端点**:GET /permissions/catalogue → 返回全部权限项,code 形如 "agents:read"
- **检查**:`pytest tests/test_permissions_api.py -v` 全过

### 第五阶段:总验证

#### Step 5:全栈验证

- **命令**:
  ```bash
  ./init.sh   # ruff + pytest 全绿(含新增权限矩阵测试)
  ```
- **通过标准**:
  - `./init.sh` 全绿
  - GET /permissions/matrix 返回真实数据(非硬编码)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. 新增端点:`GET /permissions/matrix`、`GET /permissions/catalogue`
2. 矩阵数据来自 SCD2 当前态(`RolePermissionRepository.current_permissions`),非硬编码
3. `./init.sh` 全绿(ruff + pytest,含矩阵正确性/grant后更新/跨租户隔离测试)
4. 矩阵覆盖 5 资源 × 3 角色(owner 19 项 / admin 11 项 / member 5 项,与 DEFAULT_*_PERMS 一致)

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 矩阵聚合查询性能(角色×权限笛卡尔积) | 租户内角色数极少(默认 3 个),权限项 ≤ 20,无性能问题;一次查询 + 内存组装 |
| SCD2 当前态与 casbin 不一致 | 按"宪法",SCD2 当前态是 casbin 的同步源;grant/revoke 已做同步。矩阵只读 SCD2,一致性有保证 |
| 自定义角色(非 owner/admin/member) | 矩阵包含全部角色(含自定义),current_permissions 对任何 role_id 都有效 |
| 权限项 `obj`/`act` 解析 | Permission.code = "<obj>:<act>",split(":", 1) 解析;已有 `_permission_obj_act` 方法可复用 |

### 不做的事(边界)

- 不做矩阵的批量编辑端点(编辑走现有 roles.py 的 grant/revoke 单项端点)
- 不改前端(那是 `permission-matrix-ui` 任务)
- 不改 grant/revoke 逻辑(已就绪)
- 不做权限项的增删(Permission 目录由 seed 自动生成,不手动增删)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| grant/revoke 端点(已有) | `app/api/v1/roles.py` L118-158 |
| SCD2 当前权限查询 | `app/repositories/rbac.py` `RolePermissionRepository.current_permissions` |
| 默认权限矩阵(真相源) | `app/services/permission_service.py` L320-338 `DEFAULT_*_PERMS` |
| Permission 目录表 | `app/models/rbac.py` `Permission` |
| RBAC schema | `app/schemas/rbac.py` |
| API 端点模板 | `app/api/v1/roles.py` |
| RBAC 文档 | `项目指南/02-后端架构/06-权限模型RBAC.md` |
