# 计划:Token 计费前端看板(门店/总部两级 + 充值 + 用量明细)(Token 费用管理系列 4/4)

> 对应 feature_list.json 的 `id`: `token-billing-ui`
> 状态: not_started
> 优先级: 46
> 前置: `token-usage-tracking` + `token-wallet-billing` + `customer-conversation-link`(三者完成后,本任务做前端收官)
> 系列总纲: [`plan-token-billing-overview.md`](plan-token-billing-overview.md)

---

## 背景:后端计费就绪,缺前端可视化

### 现状(前置三任务完成后)

后端已具备:
- UsageEvent(用量事件)+ Message token 列(任务 1)
- Wallet + WalletTransaction + ModelPricing + 扣减/充值/拦截(任务 2)
- Conversation.customer_id + 客户用量聚合(任务 3)

但前端没有任何计费相关页面。门店看不到自己余额/消耗,总部没法给门店充值、看不了各店经营。

### 目标

两级计费看板 + 充值操作:
1. **门店级看板**(owner/admin/member):当前余额 + 消耗趋势 + 最近流水 + 余额预警
2. **总部级看板**(super_admin):各门店余额/消耗/充值汇总 + ModelPricing 维护
3. **充值操作**:super_admin 给门店充值 Dialog
4. **用量明细**:按客户/Agent/时间段钻取消耗
5. 侧边栏加菜单:「费用管理」(门店级)、「计费管理」(总部级)

---

## 前置条件

- `token-usage-tracking` 完成
- `token-wallet-billing` 完成
- `customer-conversation-link` 完成
- 三者均 passing

---

## 实施步骤

### 第一阶段:类型 + API 层

#### Step 1:types.ts 加计费类型

- **改什么**(`frontend/src/api/types.ts`):
  ```typescript
  export interface Wallet { id: string; tenant_id: string; balance: number; total_recharged: number; total_consumed: number; low_balance_threshold: number; }
  export interface WalletTransaction { id: string; type: "recharge"|"consume"|"refund"|"adjust"; amount: number; balance_after: number; model?: string; remark?: string; operator_id?: string; created_at: string; }
  export interface ModelPricing { id: string; tenant_id?: string; model: string; input_price_per_1k: number; output_price_per_1k: number; currency: string; is_active: boolean; }
  export interface UsageSummary { total_tokens: number; total_cost: number; conversation_count: number; last_active_at: string; }
  ```
- **检查**:tsc 无错

#### Step 2:endpoints.ts 加计费端点

- **改什么**(`frontend/src/api/endpoints.ts`):
  - `fetchWallet()` / `fetchWalletByTenant(tenantId)` / `fetchTransactions(params)` / `recharge({tenant_id, amount, remark})` / `fetchPricing()` / `upsertPricing()` / `fetchUsage({customer_id?, agent_id?, from?, to?})` / `fetchCustomerUsage(customerId)`
- **检查**:tsc 无错

#### Step 3:queries.ts 加 hooks

- **改什么**(`frontend/src/hooks/queries.ts`):
  - `useWallet()` / `useWalletByTenant()` / `useTransactions()` / `useRecharge()` / `useModelPricing()` / `useUsage()` / `useCustomerUsage()`
  - recharge 成功后 invalidate `["wallet"]` + `["transactions"]`
- **检查**:`npm run build` 通过

### 第二阶段:门店级看板

#### Step 4:billing-page.tsx(门店级)

- **新建**(`frontend/src/pages/billing-page.tsx`):
  - **余额卡片**:当前余额(token 数)+ 累计充值 + 累计消耗 + 预警提示(余额 < 阈值变红)
  - **消耗趋势**:近 7/30 天每日 token 消耗折线图(用 UsageEvent 聚合,可用轻量图表或纯 CSS 柱状)
  - **最近流水**:WalletTransaction 表(类型/金额/余额后/备注/时间),TanStack Table
  - **用量明细 tab**:按客户/按 Agent 分组的消耗钻取
- **数据来源**:`useWallet()` + `useTransactions()` + `useUsage()`
- **权限**:有 `wallet:read` 的角色可见(owner/admin/member);member 只读
- **检查**:门店用户看到自己门店的余额/消耗/流水

### 第三阶段:总部级看板 + 充值

#### Step 5:billing-admin-page.tsx(总部级,super_admin)

- **新建**(`frontend/src/pages/billing-admin-page.tsx`):
  - **门店汇总表**:每个门店的余额/累计消耗/累计充值/最近活跃(调 `GET /billing/wallet` 逐店 或 新增汇总端点)
  - **充值操作**:点某门店「充值」→ Dialog(金额 + 备注)→ 调 `recharge({tenant_id, amount, remark})`
  - **ModelPricing 维护**:定价表 CRUD(模型名/input 单价/output 单价/币种),平台级 + 租户覆盖
- **权限**:`require_super_admin`(平台级)
- **检查**:super_admin 看到所有门店汇总;充值生效;定价可维护

#### Step 6:侧边栏 + 路由

- **改什么**(`frontend/src/components/layout/dashboard-layout.tsx` NAV_ITEMS):
  - 加「费用管理」(`/billing`,门店级,有 wallet:read 可见)
  - 加「计费管理」(`/billing/admin`,needsSuperAdmin)
- **改什么**(`frontend/src/App.tsx` 路由):
  - `/billing` → BillingPage(RequireUserManagement 或 wallet:read 守卫)
  - `/billing/admin` → BillingAdminPage(RequireSuperAdmin)
- **检查**:门店用户侧边栏见「费用管理」;super_admin 额外见「计费管理」

### 第四阶段:增强 + 验证

#### Step 7:余额预警 + 友好性

- **余额预警**:余额卡片在余额 < low_balance_threshold 时变红 + 提示「余额不足,请联系总部充值」
- **刷新**:顶部刷新按钮
- **格式化**:token 数千分位;cost 两位小数 + ¥ 符号;时间相对化(「3 小时前」)
- **检查**:预警显示正确;格式友好

#### Step 8:总验证

- **命令**:
  ```bash
  cd frontend && npm run build   # tsc + vite + oxlint
  ./init.sh   # 后端不回归
  ```
- **手动验证**:
  - 门店 owner 登录 → 费用管理 → 看到余额/消耗/流水;对话后余额减少并刷新
  - super_admin → 计费管理 → 各门店汇总;充值某门店 → 该门店余额增加;维护定价
  - 余额为 0 → 对话被拦(前端显示余额不足)
  - 用量明细按客户钻取(联动任务 3)
- **通过标准**:
  - `npm run build` + oxlint 0 warning
  - 两级看板数据正确;充值生效;预警显示;用量钻取
- **全过 → 填 evidence + status 改 passing + 更新 progress.md + 更新系列总纲状态**

---

## 验收标准

1. billing-page.tsx(门店级):余额卡片 + 消耗趋势 + 流水表 + 用量明细,有 wallet:read 可见
2. billing-admin-page.tsx(总部级):门店汇总 + 充值 Dialog + ModelPricing 维护,super_admin 专属
3. 侧边栏加「费用管理」(门店级)、「计费管理」(总部级);路由守卫正确
4. 充值操作生效(调 wallet:recharge → 余额增加 → 列表刷新)
5. 余额预警(余额 < 阈值变红提示)
6. 用量明细按客户/Agent/时间段钻取(联动任务 3 归因数据)
7. `npm run build` + oxlint 0 warning;`./init.sh` 不回归
8. 对话消耗后门店余额实时减少;余额为 0 对话被拦

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 消耗趋势图表依赖 | 用轻量方案(纯 CSS 柱状 或 recharts 若已在依赖);不引重型图表库 |
| 门店汇总查询逐店慢 | 后端加汇总端点(一次查全部门店 wallet),前端一次请求;或分页 |
| 充值金额单位混淆 | 明确:输入是 token 数(整数);提示「1 万 token ≈ ¥X」换算参考 |
| 定价维护误操作影响全平台 | 平台级定价改值加确认弹窗;记录操作日志(operator_id) |
| member 看到敏感财务数据 | member 有 wallet:read(只读看余额),不可充值;流水对 member 可配隐藏金额只看 token |

### 不做的事(边界)

- 不做支付集成(纯额度划拨)
- 不做导出报表 CSV(后续增强)
- 不做实时余额推送(刷新/refetch 即可)
- 不做预算/限额配置(只余额拦截,不设月度上限)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-token-billing-overview.md` |
| 数据驱动页面模板 | `frontend/src/pages/customers-page.tsx` |
| 表格组件参照 | `frontend/src/pages/roles-page.tsx` |
| 导航机制 | `frontend/src/components/layout/dashboard-layout.tsx` NAV_ITEMS |
| 后端端点(任务2建) | `app/api/v1/billing.py` |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
