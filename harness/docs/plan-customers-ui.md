# 计划:Customer(客户)前端 —— 门店档案 + 跨店聚合视图

> 对应 feature_list.json 的 `id`: `customers-ui`
> 状态: not_started
> 优先级: 33
> 前置: `customers-api`(Customer 后端 CRUD + 聚合端点就绪)

---

## 背景:客户管理的双视角

客户页需要支持**两种视角**(按 `me.platform_role` 切换):
- **门店视角**(owner/admin/member):管理本店客户档案列表/详情/创建/编辑(只看自己 tenant)
- **总部视角**(super_admin):跨店客户聚合视图,看一个客户去过哪几家店 + 每店档案

后端已就绪(前置 `customers-api` 完成后):
- `GET /customers/profiles/` —— 门店视角:本店客户档案列表
- `POST /customers/profiles/` —— 门店创建客户(自动复用全局身份)
- `PUT/DELETE /customers/profiles/{id}` —— 编辑/删除本店档案
- `GET /customers/` —— 总部视角:全局客户列表(聚合)
- `GET /customers/{id}/aggregate` —— 总部视角:单客户跨店详情

### 当前状态速查

| 层 | 状态 | 说明 |
|----|------|------|
| 客户页 | ❌ 不存在 | 全新建 customers-page.tsx |
| API 层 | ❌ 无 | 需加 types + endpoints |
| hooks 层 | ❌ 无 | 需加 qk.customers + hooks |
| 路由导航 | ❌ 无客户项 | 需加 NAV_ITEMS「客户」 |
| 后端端点 | ✅ 前置任务 | 5 个端点就绪 |
| 双视角切换 | 参照 users-page super_admin 分支 | 按 me.platform_role 切列表数据源 + UI |

---

## 目标

1. 新建 `customers-page.tsx`:按 platform_role 切换门店视角 / 总部视角
2. **门店视角**:本店客户列表(姓名/手机/状态/最近到店)+ 创建/编辑 Dialog + 删除确认
3. **总部视角**:全局客户列表(姓名/手机/去过 N 家店)+ 点击展开跨店档案详情
4. 权限守卫:member 只读;admin 可创建/编辑不可删除;owner 全权;super_admin 跨店只读
5. 路由 `/customers` 注册 + 导航加「客户」项

---

## 前置条件

- `customers-api` 完成(5 个端点就绪)
- `hq-platform-role` 可后做(本任务 super_admin 跨店视图已够验证)

---

## 实施步骤

### 第一阶段:类型 + API 层

#### Step 1:types.ts 加 Customer 类型(`frontend/src/api/types.ts`)

```typescript
// 门店档案视角
export interface CustomerBrief {
  id: string; identity_key: string; name: string; gender: string | null; birthday: string | null;
}
export interface CustomerProfile {
  id: string; customer_id: string; tenant_id: string;
  remark: string | null; tags: Record<string, unknown>; status: string; last_visit_at: string | null;
  customer: CustomerBrief;
  created_at: string; updated_at: string;
}
export interface CustomerProfileCreate {
  identity_key: string; name: string; gender?: string; birthday?: string;
  remark?: string; tags?: Record<string, unknown>; status?: string;
}
export interface CustomerProfileUpdate {
  name?: string; gender?: string; birthday?: string;
  remark?: string; tags?: Record<string, unknown>; status?: string;
}

// 总部聚合视角
export interface CustomerProfileBrief {
  tenant_id: string; tenant_name: string; remark: string | null;
  tags: Record<string, unknown>; status: string; last_visit_at: string | null;
}
export interface CustomerAggregate {
  id: string; identity_key: string; name: string; gender: string | null; birthday: string | null;
  profiles: CustomerProfileBrief[];
  profile_count: number;
}
```

#### Step 2:endpoints.ts 加 Customer 端点(`frontend/src/api/endpoints.ts`)

```typescript
// ---------- customers ----------
// 门店视角
export async function fetchCustomerProfiles(): Promise<CustomerProfile[]> {
  const { data } = await api.get<CustomerProfile[]>("/customers/profiles/");
  return data;
}
export async function createCustomerProfile(payload: CustomerProfileCreate): Promise<CustomerProfile> { ... }
export async function updateCustomerProfile(id: string, payload: CustomerProfileUpdate): Promise<CustomerProfile> { ... }
export async function deleteCustomerProfile(id: string): Promise<void> { ... }
// 总部视角
export async function fetchCustomers(): Promise<CustomerAggregate[]> {  // super_admin
  const { data } = await api.get<CustomerAggregate[]>("/customers/");
  return data;
}
export async function fetchCustomerAggregate(id: string): Promise<CustomerAggregate> { ... }
```

### 第二阶段:hooks 层

#### Step 3:queries.ts 加 Customer hooks(`frontend/src/hooks/queries.ts`)

```typescript
qk: {
  ..., 
  customerProfiles: ["customers", "profiles"] as const,
  customers: ["customers"] as const,           // 总部聚合列表
  customer: (id) => ["customers", id] as const, // 总部单客户聚合
}

// 门店视角 hooks
export function useCustomerProfiles() { return useQuery({ queryKey: qk.customerProfiles, queryFn: fetchCustomerProfiles }); }
export function useCreateCustomerProfile() { /* onSuccess invalidate customerProfiles */ }
export function useUpdateCustomerProfile() { /* onSuccess invalidate customerProfiles */ }
export function useDeleteCustomerProfile() { /* onSuccess invalidate customerProfiles */ }

// 总部视角 hooks
export function useCustomers() { return useQuery({ queryKey: qk.customers, queryFn: fetchCustomers }); }
export function useCustomerAggregate(id: string) { return useQuery({ queryKey: qk.customer(id), queryFn: () => fetchCustomerAggregate(id), enabled: !!id }); }
```

### 第三阶段:页面(双视角)+ 路由

#### Step 4:新建 customers-page.tsx(`frontend/src/pages/customers-page.tsx`)

**核心:按 `me.platform_role` 切视角**:
```typescript
const { me } = useAuth();
const isSuperAdmin = me?.platform_role === "super_admin";
```

**门店视角 UI**(isSuperAdmin === false):
- 列表表格:姓名 / 手机(identity_key 脱敏或全显)/ 状态(Badge)/ 最近到店 / 备注 / 操作
- 创建 Dialog:identity_key(手机)+ name + gender + birthday + remark + tags + status
- 编辑 Dialog:同上(可改全局身份字段 + 本店档案字段)
- 权限:`canCreate = canManageUsers(me)`(owner/admin);`canDelete = me?.tenant_role === 'owner'`
- 创建时若 identity_key 已存在(跨店复用)→ 后端自动处理,前端正常显示 201

**总部视角 UI**(isSuperAdmin === true):
- 列表表格:姓名 / 手机 / 去过 N 家店(Badge profile_count)/ 操作(查看详情)
- 点击行 → 展开/抽屉显示该客户的跨店档案列表:每条显示 [门店名 + 该店备注 + 状态 + 最近到店]
- **只读**:super_admin 跨店视图不提供创建/编辑/删除(写操作在门店视角;若 super_admin 需要写,切到门店视角——MVP 简化为总部只读)
- 用 `useCustomerAggregate(id)` 按需加载详情

#### Step 5:路由 + 导航注册

- `frontend/src/App.tsx`:`<Route path="/customers" element={<CustomersPage />} />`(ProtectedRoute 内)
- `frontend/src/components/layout/dashboard-layout.tsx`:NAV_ITEMS 加 `{ to: "/customers", label: "客户", icon: Users }`
  - ⚠️ Users 图标可能已被「用户管理」页占用,改用 `Contact` 或 `UserCircle`
- **检查**:导航「客户」项出现;member 和 super_admin 都能进(视角不同)

### 第四阶段:总验证

#### Step 6:前端构建

```bash
cd frontend && npm run build   # tsc + vite 0 类型错误
npx oxlint src/pages/customers-page.tsx src/hooks/queries.ts src/api/endpoints.ts src/api/types.ts
```

- **手动验证**(前后端启动):
  - 门店 A owner 登录 → 客户页(门店视角)→ 创建客户张三(138xxx)→ 列表出现
  - 门店 B owner 登录 → 客户页 → 创建客户张三(138xxx,同手机)→ 复用身份,列表出现(本店新档案)
  - super_admin 登录 → 客户页(总部视角)→ 看到张三 + 「去过 2 家店」→ 点击展开看到 A/B 两店档案
  - member 登录 → 客户页只读,无创建/编辑按钮
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)+ oxlint 0 warning
2. 门店视角:owner/admin/member 看本店客户档案;创建时跨店复用 identity_key 自动处理
3. 总部视角:super_admin 看跨店聚合(一个客户 + N 家店档案)
4. 权限守卫:member 只读;admin 无 delete;owner 全权;super_admin 总部只读
5. 路由 `/customers` 注册 + 导航「客户」项可见

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 双视角切换的 UI 复杂度 | 用 `isSuperAdmin` 条件渲染两套表格;复用 Table/Dialog 组件,差异在数据源 + 操作按钮 |
| identity_key 脱敏显示 | 门店视角手机号可全显(内部员工);总部聚合视图同理;不做脱敏(MVP) |
| 跨店档案详情的加载 | 用 useCustomerAggregate(id) 按需加载(展开时);或列表已含 profiles 直接展示(MVP 量小可直接全返回) |
| tags(JSONB)的编辑 UI | MVP 用 textarea 填 JSON 或简单的 key-value 编辑器;参照 settings-page 的 available_models 标签编辑器 |
| Users 图标冲突 | 客户页用 Contact/UserCircle 图标,避免与用户管理页冲突 |

### 不做的事(边界)

- 不做消费记录/订单/服务历史 UI(后端未提供)
- 不做客户搜索/筛选(MVP 列表全量,后续加)
- 不做客户导入/导出
- 不做客户去重/合并 UI
- 不做 hq_staff 视角(那是 hq-platform-role 任务;本任务只 super_admin + 门店视角)
- 不做后端改动(纯前端)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 双视角(super_admin 分支)参照 | `frontend/src/pages/users-page.tsx`(有 super_admin 跨租户视图) |
| 数据驱动页面模板 | `frontend/src/pages/roles-page.tsx` / `users-page.tsx` |
| super_admin 判定 | `useAuth().me.platform_role === "super_admin"` |
| canManageUsers 权限守卫 | `frontend/src/lib/auth-context.tsx` |
| 后端端点(前置任务) | `GET/POST/PUT/DELETE /customers/profiles/` + `GET /customers/` + `/customers/{id}/aggregate` |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
