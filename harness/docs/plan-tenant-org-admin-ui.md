# 计划:租户/组织/成员管理前端(控制台补齐)

> 对应 feature_list.json 的 `id`: `tenant-org-admin-ui`
> 状态: not_started
> 优先级: 16
> 前置: 无(后端端点全齐,纯前端任务)

---

## 背景:管理控制台功能不闭环

多租户是脚手架核心卖点,但**前端没有独立的管理页面**让管理员管租户/组织/成员。后端 11 个端点全齐,前端 endpoints.ts 也接了一半,但没有页面承载。

### 当前状态速查

| 模块 | 后端端点 | 前端 endpoints | 前端 hooks | 前端页面 |
|------|---------|---------------|-----------|---------|
| 租户 tenants | ✅ 2 个(POST/GET) | ✅ fetchTenants/createTenant | ⚠️ 部分 | ❌ 无 |
| 组织 organizations | ✅ 5 个(GET tree/GET/POST/PUT/DELETE) | ⚠️ 缺 update/delete | ⚠️ 部分 | ❌ 无 |
| 成员 members | ✅ 4 个(GET/POST/PATCH/DELETE) | ✅ fetchMembers/addMember | ⚠️ 部分 | ❌ 无 |

**结论**:后端零工作,前端要补页面 + 补齐缺失的 endpoints/hooks。

---

## 目标

管理员能在 UI 完整管理:
1. **租户**:查看自己所属租户、创建新租户
2. **组织**:CRUD 组织(树形结构)、查看组织树
3. **成员**:查看租户成员、增删成员、改成员角色

---

## 前置条件

- 无。后端端点全齐(`tenants.py`/`organizations.py`/`members.py`)。

---

## 实施步骤

### 第一阶段:补齐 endpoints + types

#### Step 1:补缺失的 API 函数

当前 endpoints.ts 有 fetchTenants/createTenant/fetchMembers/fetchOrganizations/createOrganization/fetchOrganizationTree,缺 update/delete + 成员管理。

- **改什么**(`frontend/src/api/endpoints.ts`):
  ```typescript
  // 组织:补 update + delete
  export async function updateOrganization(id: string, payload: Partial<OrganizationCreate>): Promise<Organization>
  export async function deleteOrganization(id: string): Promise<void>

  // 成员:补 update role + remove(已有 addMember/fetchMembers)
  export async function updateMemberRole(userId: string, payload: { role: string }): Promise<Member>
  export async function removeMember(userId: string): Promise<void>
  ```
- **改什么**(`frontend/src/api/types.ts`):确认 Member/Organization 类型完整(对照后端 schema)
- **检查**:tsc 无错

### 第二阶段:补齐 hooks

#### Step 2:queries.ts 加管理 hooks

- **改什么**(`frontend/src/hooks/queries.ts`):
  ```typescript
  // 租户
  export function useTenants()             // GET 列表
  export function useCreateTenant()        // POST,成功 invalidate ["tenants"]

  // 组织
  export function useOrganizations()       // GET 列表
  export function useOrganizationTree()    // GET 树
  export function useCreateOrganization()  // POST
  export function useUpdateOrganization()  // PUT
  export function useDeleteOrganization()  // DELETE

  // 成员
  export function useMembers()             // GET 列表
  export function useAddMember()           // POST
  export function useUpdateMemberRole()    // PATCH
  export function useRemoveMember()        // DELETE
  ```
- **检查**:`npm run build` 通过

### 第三阶段:管理页面

#### Step 3:组织管理页(organizations-page.tsx)

组织是树形结构(后端有 tree 端点),参照 users-page.tsx 模式。

- **新建** `frontend/src/pages/organizations-page.tsx`:
  - **左侧**:组织树(`useOrganizationTree`,递归渲染树节点)
  - **右侧**:选中组织的详情 + 编辑/删除
  - **顶部**:创建组织(选父组织)
  - CRUD:创建(POST)/编辑(PUT)/删除(DELETE)
- **UI**:树用缩进 + 图标;节点点击选中;操作按钮在详情面板
- **权限守卫**:用 `require_permission("organizations", "*")`,owner/admin 可写,member 只读

#### Step 4:成员管理页(members-page.tsx)

成员管理 = 查看租户成员 + 改角色 + 移除。

- **新建** `frontend/src/pages/members-page.tsx`:
  - **表格**:成员列表(头像/姓名/角色/加入时间)
  - **操作**:改角色(下拉:owner/admin/member)、移除成员(确认)
  - **添加成员**:输入 user_id/email + 角色 → addMember
- **参照**:users-page.tsx 的表格 + Dialog 模式
- **权限守卫**:`require_permission("organizations", "*")` 或独立成员管理权限(看后端 members.py 用什么 obj/act)

#### Step 5:租户管理(整合进 dashboard 或独立页)

租户管理较轻(只能看自己租户 + 创建新租户),不必独立整页。

- **方案**:在 dashboard-page 加"我的租户"卡片(列出 + 创建入口),或做独立 tenants-page.tsx
- **决策建议**:若租户切换是常用功能,独立页;否则整合进 dashboard。**第一版整合进 dashboard**(轻量)
- **创建租户**:Dialog 表单(name)→ createTenant → 创建后提示切换

### 第四阶段:路由 + 导航注册

#### Step 6:路由与导航

- **改什么**(`frontend/src/App.tsx`):
  ```tsx
  <Route path="/organizations" element={<OrganizationsPage />} />
  <Route path="/members" element={<MembersPage />} />
  // tenants 整合进 dashboard,不单独加路由
  ```
- **改什么**(`dashboard-layout.tsx` NAV_ITEMS):
  ```typescript
  { to: "/organizations", label: "组织", icon: Building2 },
  { to: "/members", label: "成员", icon: Users },
  ```
- **权限守卫**:organizations/members 管理页放 `<RequireUserManagement>` 内(或新增 RequireAdmin),member 只读或隐藏

### 第五阶段:总验证

#### Step 7:前端构建 + 手动验证

- **命令**:
  ```bash
  cd frontend && npm run build   # tsc + vite 通过
  ```
- **手动验证**:
  - 组织页:看树 → 创建子组织 → 编辑 → 删除
  - 成员页:看列表 → 改某人角色 → 移除 → 添加成员
  - dashboard:看我的租户 → 创建新租户
- **通过标准**:`npm run build` 通过 + 手动 CRUD 全通
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. 前端新增:组织管理页(树形 CRUD)、成员管理页(列表 + 改角色 + 移除)
2. 租户管理整合进 dashboard(查看 + 创建)
3. endpoints.ts/hooks 补齐(update/delete organization、update/remove member)
4. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)
5. (手动)组织树 CRUD、成员管理、租户创建全流程通

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 组织树递归渲染复杂 | 参照 OrganizationTreeNode 类型(children 递归);用递归组件 <OrgNode> |
| 成员管理权限边界不清 | 看后端 members.py 的 require_permission 用什么 obj/act;对齐前端守卫 |
| 租户切换功能 | 第一版不做租户切换(token 绑租户);只做查看 + 创建 |
| 删除组织有子组织 | 后端 delete_org 可能拒(有子);前端捕获 400 提示"先删子组织" |

### 不做的事(边界)

- 不做租户切换(当前 token 绑定租户,切换需重登录;是后续增强)
- 不做组织成员分配(成员属租户级,不属组织级;若后端支持再说)
- 不改后端(端点全齐)
- 不做组织拖拽排序

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| CRUD 页面模板 | `frontend/src/pages/users-page.tsx`、`roles-page.tsx` |
| 现有 endpoints(已有部分) | `frontend/src/api/endpoints.ts`(fetchTenants/fetchMembers/fetchOrganizations) |
| 后端 tenants 端点 | `app/api/v1/tenants.py`(POST/GET) |
| 后端 organizations 端点 | `app/api/v1/organizations.py`(5 个,含 tree) |
| 后端 members 端点 | `app/api/v1/members.py`(4 个) |
| 类型定义 | `frontend/src/api/types.ts`(Organization/Member/Tenant) |
| 路由/导航 | `frontend/src/App.tsx`、`dashboard-layout.tsx` NAV_ITEMS |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
