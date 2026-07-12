# 计划:Group(组织)前端 —— 组织管理页 + 门店挂载

> 对应 feature_list.json 的 `id`: `groups-ui`
> 状态: not_started
> 优先级: 31
> 前置: `groups-api`(Group 后端 CRUD + 挂载端点就绪)

---

## 背景:从硬编码组织页到真实 Group 管理

`org-cleanup` 已删除旧 `organizations-page.tsx`。本任务新建 `groups-page.tsx`,数据来自后端真实 Group 端点。与旧组织页的本质区别:
- 旧组织页:管「门店内部的部门」(租户级,树形)
- 新组织页:管「经营主体」(平台级,平级列表 + 门店挂载)

后端已就绪(前置 `groups-api` 完成后):
- `GET /groups/` —— super_admin 看全部;门店用户看自己所属
- `GET /groups/{id}` —— 详情含 tenant_ids/tenants
- `POST /groups/` —— 创建(super_admin)+ 批量挂载门店
- `PUT /groups/{id}` —— 编辑(super_admin)
- `DELETE /groups/{id}` —— 删除(super_admin)
- `POST/DELETE /groups/{id}/tenants/{tenant_id}` —— 挂载/卸载单个门店

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| 组织页 | ❌ 已删(org-cleanup) | 需全新建 groups-page.tsx |
| API 层 | ❌ 无 group 相关 | 需加 types + endpoints |
| hooks 层 | ❌ 无 | 需加 qk.groups + hooks |
| 路由导航 | ⚠️ 旧「组织」项已删 | 需重新加「组织」NAV_ITEMS |
| 后端端点 | ✅ 前置任务 | 7 个端点就绪 |
| 权限守卫 | super_admin 写 / 所有人读 | 路由不加 RequireUserManagement(member 也能读自己 Group) |

---

## 目标

1. 新建 `groups-page.tsx`:组织列表 + 创建/编辑 Dialog + 门店挂载面板
2. 列表展示:组织名、编码、地址、关联门店数、状态
3. 详情/编辑:可查看/增删关联门店(门店用 Tenant 列表下拉)
4. 权限守卫:写操作仅 super_admin 可见按钮;门店用户只读自己所属组织
5. 路由 `/groups` 注册 + 导航加「组织」项

---

## 前置条件

- `groups-api` 完成(7 个端点就绪)
- `org-cleanup` 完成(旧前端组织代码已清,无冲突)

---

## 实施步骤

### 第一阶段:类型 + API 层

#### Step 1:types.ts 加 Group 类型(`frontend/src/api/types.ts`)

```typescript
export interface TenantBrief { id: string; name: string; }

export interface Group {
  id: string;
  name: string;
  code: string | null;
  address: string | null;
  description: string | null;
  status: string;
  sort_order: number;
  tenant_ids: string[];
  tenants: TenantBrief[];
  created_at: string;
  updated_at: string;
}

export interface GroupCreate {
  name: string;
  code?: string;
  address?: string;
  description?: string;
  tenant_ids?: string[];
  status?: string;
  sort_order?: number;
}

export interface GroupUpdate {
  name?: string;
  code?: string;
  address?: string;
  description?: string;
  status?: string;
  sort_order?: number;
}
```

#### Step 2:endpoints.ts 加 Group 端点(`frontend/src/api/endpoints.ts`)

```typescript
// ---------- groups ----------
export async function fetchGroups(): Promise<Group[]> {
  const { data } = await api.get<Group[]>("/groups/");
  return data;
}
export async function fetchGroup(id: string): Promise<Group> { ... }
export async function createGroup(payload: GroupCreate): Promise<Group> { ... }
export async function updateGroup(id: string, payload: GroupUpdate): Promise<Group> { ... }
export async function deleteGroup(id: string): Promise<void> { ... }
export async function attachTenant(groupId: string, tenantId: string): Promise<void> {
  await api.post(`/groups/${groupId}/tenants/${tenantId}`);
}
export async function detachTenant(groupId: string, tenantId: string): Promise<void> {
  await api.delete(`/groups/${groupId}/tenants/${tenantId}`);
}
```

- **检查**:tsc 无错;需要 fetchTenants(获取门店下拉列表,已有 `useTenants`)

### 第二阶段:hooks 层

#### Step 3:queries.ts 加 Group hooks(`frontend/src/hooks/queries.ts`)

```typescript
qk: { ..., groups: ["groups"] as const, group: (id) => ["groups", id] as const }

export function useGroups() { return useQuery({ queryKey: qk.groups, queryFn: fetchGroups }); }
export function useGroup(id: string) { return useQuery({ queryKey: qk.group(id), queryFn: () => fetchGroup(id), enabled: !!id }); }
export function useCreateGroup() { /* onSuccess invalidate qk.groups */ }
export function useUpdateGroup() { /* onSuccess invalidate qk.groups + qk.group(id) */ }
export function useDeleteGroup() { /* onSuccess invalidate qk.groups */ }
export function useAttachTenant() { /* onSuccess invalidate qk.groups + qk.group(groupId) */ }
export function useDetachTenant() { /* onSuccess invalidate qk.groups + qk.group(groupId) */ }
```

### 第三阶段:页面 + 路由

#### Step 4:新建 groups-page.tsx(`frontend/src/pages/groups-page.tsx`)

参照 `roles-page.tsx` / `users-page.tsx` 模式(列表表格 + Dialog + 删除确认):

- **列表表格列**:组织名 / 编码 / 地址 / 关联门店数(Badge 显示 N) / 状态 / 操作
- **创建 Dialog**:name / code / address / description / 关联门店(多选 Checkbox 列表,数据来自 useTenants)
- **编辑 Dialog**:同上 + 可增删关联门店(门店挂载面板:已关联门店列表 + 「添加门店」下拉)
- **门店挂载交互**:
  - 已关联门店显示为 Badge/Chip,点 ✕ 调 detachTenant
  - 底部「+ 添加门店」下拉,选一个调 attachTenant
- **权限守卫**:`const canManage = me?.platform_role === "super_admin"`;非 super_admin 隐藏创建/编辑/删除按钮,只读列表

#### Step 5:路由 + 导航注册

- `frontend/src/App.tsx`:`<Route path="/groups" element={<GroupsPage />} />`(在 ProtectedRoute 内,**不加 RequireUserManagement**——member 可读自己 Group)
- `frontend/src/components/layout/dashboard-layout.tsx`:NAV_ITEMS 加 `{ to: "/groups", label: "组织", icon: Building2 }`(不带 needsUserManagement,所有人可见)
- **检查**:导航「组织」项出现;member 登录能看到(只读)

### 第四阶段:总验证

#### Step 6:前端构建

```bash
cd frontend && npm run build   # tsc + vite 0 类型错误
npx oxlint src/pages/groups-page.tsx src/hooks/queries.ts src/api/endpoints.ts src/api/types.ts
```

- **手动验证**(前后端启动):
  - super_admin 登录 → 组织页 → 看到全部组织 → 创建一个组织并挂载 2 家门店 → 列表显示「关联 2 家」
  - 编辑组织 → 增删关联门店 → Badge 实时更新
  - 门店 owner 登录 → 组织页 → 只读看到自己所属组织(不能创建/编辑/删除)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)+ oxlint 0 warning
2. 组织页数据来自真实 `/groups/` 端点(非硬编码)
3. super_admin 能 CRUD 组织 + 挂载/卸载门店
4. 门店用户只读自己所属组织(无写操作按钮)
5. 路由 `/groups` 注册 + 导航「组织」项可见

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 门店多选用 Checkbox 还是 Select | 门店数量少(MVP),用 Checkbox 列表直观;参照 members-page 的添加成员 Dialog |
| 关联门店实时增删的 UX | 用 Badge + ✕(detach)+ 下拉(attach);onSuccess invalidate 自动刷新 |
| 非 super_admin 看空列表的体验 | 后端返回自己所属 Group(可能为空);前端空态提示「您还未归属任何组织,请联系总部」 |
| Building2 图标已被 org-cleanup 清理 | dashboard-layout 重新 import Building2(或换 Store 图标) |

### 不做的事(边界)

- 不做 Group 的树形层级(MVP 平级)
- 不做 Group 内成员管理(人员归属走 UserTenant + members-page)
- 不做 Group 的权限分配(Group 不进 casbin,无权限矩阵)
- 不做后端改动(纯前端,后端 groups-api 已就绪)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 数据驱动页面模板 | `frontend/src/pages/roles-page.tsx` / `users-page.tsx` |
| 成员管理(多选交互) | `frontend/src/pages/members-page.tsx` |
| 现有 hooks 模式 | `frontend/src/hooks/queries.ts`(useRoles/useAgents) |
| 后端端点(前置任务) | `GET/POST/PUT/DELETE /groups/` + 挂载端点 |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
