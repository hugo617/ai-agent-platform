# 计划:门店(租户)管理前端 —— 独立门店管理页

> 对应 feature_list.json 的 `id`: `tenants-admin-ui`
> 状态: not_started
> 优先级: 31
> 前置: `tenants-admin-api`(门店管理后端就绪)

---

## 背景:从 dashboard 简陋卡片到独立门店管理页

现状:前端**没有独立门店管理页**,侧边栏导航也没有「门店」项。唯一入口是 dashboard(`/`)概览页的「我的租户」卡片 + 一个「创建租户」按钮(只填名字)。

`tenants-admin-api` 完成后,后端能力补齐:
- `GET /tenants/all`(super_admin 看全部,含 member_count)
- `GET /tenants/{id}`(详情)
- `POST /tenants/`(super_admin 创建,权限已收紧)
- `PUT /tenants/{id}`(super_admin 编辑)

本任务建独立门店管理页,并保留 dashboard 的「我的租户」卡片(面向普通用户,只读自己的)。

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| 独立门店页 | ❌ 不存在 | 需新建 tenants-page.tsx |
| 侧边栏导航 | ❌ 无门店项 | 需加 NAV_ITEMS「门店」(super_admin 可见) |
| dashboard 卡片 | ✅ 已有 | 保留(普通用户看自己租户);创建按钮改为 super_admin 可见 |
| API 层 | ⚠️ 仅 fetchTenants/createTenant | 需加 fetchAllTenants/updateTenant/fetchTenant |
| hooks 层 | ⚠️ 仅 useTenants/useCreateTenant | 需加 useAllTenants/useUpdateTenant |
| 后端端点 | ✅ 前置任务 | 4 个端点就绪 |

---

## 目标

1. 新建 `tenants-page.tsx`:super_admin 视角的门店列表(名/状态/地址/成员数/创建者)+ 创建/编辑 Dialog
2. 侧边栏加「门店」导航项(仅 super_admin 可见)
3. dashboard「我的租户」卡片保留(普通用户视角),创建按钮仅 super_admin 可见
4. 权限守卫:门店管理页路由仅 super_admin 可进;普通用户只看 dashboard 卡片

---

## 前置条件

- `tenants-admin-api` 完成(4 个端点就绪)
- `org-cleanup` 完成

---

## 实施步骤

### 第一阶段:类型 + API 层

#### Step 1:types.ts 扩展 Tenant 类型(`frontend/src/api/types.ts`)

当前 `Tenant` 只有 `id/name/created_at`(`types.ts:4-8`)。扩展:
```typescript
export interface Tenant {
  id: string;
  name: string;
  status: string;           // 新增
  description: string | null; // 新增
  address: string | null;     // 新增
  member_count: number;        // 新增
  created_by: string | null;   // 新增
  created_at: string;
}

export interface TenantUpdate {  // 新增
  name?: string;
  status?: string;
  description?: string;
  address?: string;
}
```

#### Step 2:endpoints.ts 加门店端点(`frontend/src/api/endpoints.ts`)

```typescript
// ---------- tenants ----------
// 保留现有 fetchTenants(GET /tenants/ 我的)+ createTenant
export async function fetchAllTenants(): Promise<Tenant[]> {  // 新增 super_admin
  const { data } = await api.get<Tenant[]>("/tenants/all");
  return data;
}
export async function fetchTenant(id: string): Promise<Tenant> {  // 新增
  const { data } = await api.get<Tenant>(`/tenants/${id}`);
  return data;
}
export async function updateTenant(id: string, payload: TenantUpdate): Promise<Tenant> {  // 新增
  const { data } = await api.put<Tenant>(`/tenants/${id}`, payload);
  return data;
}
```

### 第二阶段:hooks 层

#### Step 3:queries.ts 加门店 hooks(`frontend/src/hooks/queries.ts`)

```typescript
qk: { ..., tenants: ["tenants"] as const, allTenants: ["tenants", "all"] as const, tenant: (id) => ["tenants", id] as const }

// 保留现有 useTenants(我的)+ useCreateTenant
export function useAllTenants() {  // 新增 super_admin 列表
  return useQuery({ queryKey: qk.allTenants, queryFn: fetchAllTenants });
}
export function useUpdateTenant() {  // 新增
  return useMutation({
    mutationFn: ({ id, payload }) => updateTenant(id, payload),
    onSuccess: (_, { id }) => { qc.invalidateQueries({ queryKey: qk.allTenants }); qc.invalidateQueries({ queryKey: qk.tenant(id) }); },
  });
}
```

### 第三阶段:门店管理页 + 路由

#### Step 4:新建 tenants-page.tsx(`frontend/src/pages/tenants-page.tsx`)

参照 `roles-page.tsx` / `users-page.tsx` 模式:
- **列表表格列**:门店名 / 状态(Badge active/inactive)/ 地址 / 成员数 / 创建者 / 创建时间 / 操作
- **创建 Dialog**:name / status(默认 active)/ description / address
- **编辑 Dialog**:同上(可改名/状态/描述/地址)
- **权限守卫**:整页仅 super_admin(路由层 + 页面内 `me.platform_role === "super_admin"` 双层防御)
- **删除**:MVP 不做(后端无 DELETE)

#### Step 5:路由 + 导航注册

- `frontend/src/App.tsx`:`<Route path="/tenants" element={<TenantsPage />} />`(ProtectedRoute 内)
- `frontend/src/components/layout/dashboard-layout.tsx`:NAV_ITEMS 加 `{ to: "/tenants", label: "门店", icon: Store, needsSuperAdmin: true }`
  - ⚠️ 需在 NAV_ITEMS 的 filter 逻辑加 `needsSuperAdmin` 判定(仅 `me.platform_role === "super_admin"` 可见)。若 NAV_ITEMS 无此机制,改用条件渲染
- **检查**:super_admin 侧边栏看到「门店」项;普通用户看不到

#### Step 6:dashboard 卡片调整

- `frontend/src/pages/dashboard-page.tsx`:「创建租户」按钮加 `me?.platform_role === "super_admin"` 条件(权限收紧后普通用户 POST 会 403,隐藏按钮避免误点)
- 「我的租户」卡片本身保留(普通用户仍可看自己所属门店列表)

### 第四阶段:总验证

#### Step 7:前端构建

```bash
cd frontend && npm run build   # tsc + vite 0 类型错误
npx oxlint src/pages/tenants-page.tsx src/hooks/queries.ts src/api/endpoints.ts src/api/types.ts src/pages/dashboard-page.tsx
```

- **手动验证**(前后端启动):
  - super_admin 登录 → 侧边栏「门店」项 → 门店页看到全部门店 + member_count
  - 创建门店(填名/地址/描述)→ 列表出现
  - 编辑门店(改名/改状态)→ 列表更新
  - 普通用户登录 → 侧边栏无「门店」项 → dashboard「我的租户」卡片正常(无创建按钮)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)+ oxlint 0 warning
2. 门店管理页数据来自 `GET /tenants/all`(super_admin 看全部,含 member_count)
3. super_admin 能创建/编辑门店;普通用户看不到门店页 + 创建按钮隐藏
4. dashboard「我的租户」卡片保留(普通用户视角不变)
5. 侧边栏「门店」项仅 super_admin 可见

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| NAV_ITEMS 无 needsSuperAdmin 机制 | 参照 needsUserManagement 模式新增;或用条件渲染 filter out |
| dashboard 创建按钮权限收紧后误点 403 | Step 6 显式隐藏按钮(me.platform_role 判定) |
| Store 图标是否可用 | lucide-react 有 Store 图标;若与其它页冲突改 Store/ShoppingBag |
| groups-ui 依赖门店下拉 | 本任务完成后,groups-ui 的门店挂载下拉用 useAllTenants() 取数据(依赖链确认) |

### 不做的事(边界)

- 不做门店删除 UI(后端无 DELETE)
- 不做门店切换登录(切租户属认证增强)
- 不做门店导入/导出
- 不做后端改动(纯前端,tenants-admin-api 已就绪)
- 不改普通用户的 dashboard 体验(「我的租户」卡片保留)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 数据驱动页面模板 | `frontend/src/pages/roles-page.tsx` / `users-page.tsx` |
| dashboard 现有租户卡片 | `frontend/src/pages/dashboard-page.tsx:100-177` |
| NAV_ITEMS 机制 | `frontend/src/components/layout/dashboard-layout.tsx:33-44` |
| canManageUsers 权限守卫范式 | `frontend/src/lib/auth-context.tsx` |
| 后端端点(前置任务) | `GET /tenants/all` + `GET/PUT /tenants/{id}` + `POST /tenants/`(super_admin) |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
