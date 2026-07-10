# 计划:权限矩阵前端(真实数据 + 可编辑矩阵)

> 对应 feature_list.json 的 `id`: `permission-matrix-ui`
> 状态: not_started
> 优先级: 15
> 前置: `permission-matrix-api`(矩阵聚合端点就绪)

---

## 背景:当前 permissions-page 是硬编码空壳

`permissions-page.tsx`(108 行)是一个**纯静态只读视图**:
- 矩阵数据写死在 `MATRIX` 常量(L26-35),只覆盖 2 资源 × 2 角色(失真)
- 不接后端,不能编辑
- 资源/动作清单写死在 `OBJECTS`/`ACTIONS` 常量(L21-22)

真实权限模型是 **5 资源 × 3 角色 × 多动作**,前端展示完全失真。本任务把它重写为真实数据驱动 + 可在线编辑。

后端已就绪(前置任务 `permission-matrix-api` 完成后):
- `GET /permissions/matrix` —— 真实聚合矩阵
- `GET /permissions/catalogue` —— 全部权限项目录
- grant/revoke —— `roles.py` 已有,**hooks 已接通**(`useGrantRolePermission`/`useRevokeRolePermission`)

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| 矩阵数据源 | ❌ 硬编码 | `MATRIX` 常量,2 资源 × 2 角色 |
| 可编辑性 | ❌ 只读 | 无 grant/revoke 调用 |
| grant/revoke hooks | ✅ 已有 | `queries.ts` `useGrantRolePermission`/`useRevokeRolePermission` |
| 矩阵端点 | ✅ 前置任务 | `GET /permissions/matrix`(真实数据) |
| 目录端点 | ✅ 前置任务 | `GET /permissions/catalogue`(全量权限项) |

---

## 目标

重写 permissions-page.tsx:
1. 数据来自 `GET /permissions/matrix`(真实,5 资源 × 3 角色 + 自定义角色)
2. 可在线编辑:点格子 → grant/revoke → 矩阵实时刷新
3. 权限守卫:member 只读,owner/admin 可编辑

---

## 前置条件

- `permission-matrix-api` 完成(矩阵 + 目录端点就绪)

---

## 实施步骤

### 第一阶段:类型 + API 层

#### Step 1:types.ts 加矩阵类型 + endpoints.ts 加矩阵端点

- **改什么**(`frontend/src/api/types.ts`):
  ```typescript
  export interface PermissionItem {
    id: string;
    code: string;     // "<obj>:<act>"
    name: string;
    obj: string;
    act: string;
  }
  export interface PermissionMatrix {
    roles: Role[];                          // 全部角色
    permissions: PermissionItem[];          // 全部权限项
    matrix: Record<string, Record<string, boolean>>; // {role_code: {perm_code: bool}}
  }
  ```
- **改什么**(`frontend/src/api/endpoints.ts`):
  ```typescript
  export async function fetchPermissionMatrix(): Promise<PermissionMatrix> {
    const { data } = await api.get<PermissionMatrix>("/permissions/matrix");
    return data;
  }
  export async function fetchPermissionCatalogue(): Promise<PermissionItem[]> {
    const { data } = await api.get<PermissionItem[]>("/permissions/catalogue");
    return data;
  }
  ```
- **检查**:tsc 无错

### 第二阶段:hooks 层

#### Step 2:queries.ts 加矩阵 hook

- **改什么**(`frontend/src/hooks/queries.ts`):
  ```typescript
  export function usePermissionMatrix() {
    return useQuery({
      queryKey: ["permission-matrix"],
      queryFn: fetchPermissionMatrix,
    });
  }
  // grant/revoke 成功后要 invalidate ["permission-matrix"](已有 hook 的 onSuccess 里加)
  ```
- **注意**:现有的 `useGrantRolePermission`/`useRevokeRolePermission`(L241/256)的 `onSuccess` 目前 invalidate `["role-permissions"]`,要**加上 invalidate `["permission-matrix"]`**,这样矩阵页编辑后能刷新。
- **检查**:`npm run build` 通过

### 第三阶段:页面重写

#### Step 3:重写 permissions-page.tsx

当前 108 行硬编码,重写为真实数据驱动 + 可编辑矩阵。参照 roles-page.tsx 的模式。

- **核心结构**:
  ```
  权限矩阵
  ─────────────────────────────────────────────
        | 智能体(read) | 智能体(create) | ... | 对话(chat)
  ─────────────────────────────────────────────
  owner  |     ✅         |     ✅          | ... |    ❌
  admin  |     ✅         |     ✅          | ... |    ✅
  member |     ✅         |     ❌          | ... |    ✅
  自定义 |     ❌         |     ❌          | ... |    ❌
  ```
- **数据来源**:`usePermissionMatrix()`(返回 roles + permissions + matrix 三部分)
- **渲染逻辑**:
  - 行 = 角色(roles),列 = 权限项(permissions,按 obj 分组排序)
  - 每个格子:`matrix[role.code][perm.code]` → ✅ / ❌
  - 列头用中文友好名(obj 映射:agents→智能体、conversations→对话、users→用户、roles→角色、organizations→组织;act 保留 read/create/update/delete/chat)
- **可编辑交互**(仅 owner/admin):
  - 点格子:
    - 当前 ✅(有权限)→ 调 `useRevokeRolePermission`({role_id, permission_id})→ 格子变 ❌
    - 当前 ❌(无权限)→ 调 `useGrantRolePermission`({role_id, permission_id})→ 格子变 ✅
  - 成功后:`invalidate ["permission-matrix"]` → 矩阵刷新
  - 失败:toast 报错,格子不变
  - **loading 态**:编辑中的格子显示 spinner,防止重复点击
- **权限守卫**:
  - member(无 roles:update)→ 矩阵只读(格子不可点),顶部提示"只读视图"
  - owner/admin(有 roles:update)→ 可编辑
  - 用现有 `canManageUsers(me)` 或新增 `canManageRoles(me)` 判断(参照 auth-context 的权限判断模式)
- **系统角色保护**:owner/admin/member 是系统角色,**其权限是 seed 默认值**。第一版允许编辑(后端 grant/revoke 不拦系统角色),但 UI 给系统角色的格子加个小图标提示"系统默认"。若要保护系统角色不被改,后端 roles.py 已有系统角色删除保护,但 grant/revoke 无保护——本任务**不增加系统角色编辑保护**(超范围,见风险表)。

#### Step 4:增强友好性(可选)

- **分组**:列按 obj 分组(智能体组 / 对话组 / 用户组…),用分隔线或小标题
- **图例**:保留现有的"允许/拒绝"图例(已有)
- **刷新**:顶部加"刷新"按钮(手动 refetch)

### 第四阶段:总验证

#### Step 5:前端构建 + 手动验证

- **命令**:
  ```bash
  cd frontend && npm run build   # tsc + vite 通过
  ```
- **手动验证**(前后端都启动):
  - owner 登录 → 权限矩阵页 → 看到 5 资源 × 3 角色的真实矩阵(非 2×2 硬编码)
  - 点 member 的"智能体 create"格子(❌→✅)→ grant 成功 → 格子变绿
  - 再点一次(✅→❌)→ revoke 成功 → 格子变灰
  - member 登录 → 矩阵只读,格子不可点
- **通过标准**:
  - `npm run build` 通过
  - 矩阵显示真实数据 + 可编辑 + member 只读
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. permissions-page.tsx 重写:数据来自 `GET /permissions/matrix`(真实,非硬编码)
2. 可编辑:点格子调 grant/revoke,成功后矩阵实时刷新
3. 权限守卫:member 只读(无 roles:update),owner/admin 可编辑
4. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)
5. (手动)真实矩阵 5 资源 × 3 角色 + 编辑生效

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| grant/revoke 需要 permission_id(矩阵里要有) | `PermissionMatrix.permissions` 含 id;`matrix` 的 key 是 perm_code,渲染时按 code 查 id |
| 编辑中矩阵闪烁 | 用 TanStack Query 的 optimistic update,或编辑中禁用格子 + 局部 state |
| 系统角色被误改 | 第一版允许改(后端不拦);UI 给系统角色加"系统"标记提示。严格保护是后续增强 |
| 自定义角色不在矩阵 | `usePermissionMatrix` 返回全部角色(含自定义),自动出现在矩阵行 |
| role.code vs role.id | grant/revoke 用 role_id;矩阵 key 是 role_code(来自 casbin 策略名)。渲染时要 code→id 映射 |

### 不做的事(边界)

- 不做系统角色的编辑保护(超范围;后端 grant/revoke 不拦,本任务不改后端)
- 不做权限项的增删(Permission 目录由 seed 生成)
- 不做批量编辑(逐格编辑,第一版不做批量勾选)
- 不做权限变更的 diff 视图(与默认值的差异)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 当前硬编码页面(待重写) | `frontend/src/pages/permissions-page.tsx` |
| 数据驱动页面模板 | `frontend/src/pages/roles-page.tsx`(含权限分配面板) |
| grant/revoke hooks(已有) | `frontend/src/hooks/queries.ts` `useGrantRolePermission`/`useRevokeRolePermission` |
| grant/revoke endpoints(已有) | `frontend/src/api/endpoints.ts` L250-265 |
| 角色类型 | `frontend/src/api/types.ts` `Role` / `RolePermissionRead` |
| 后端矩阵端点(前置任务) | `GET /permissions/matrix`、`GET /permissions/catalogue` |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
