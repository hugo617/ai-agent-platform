# 计划:Dashboard 数据看板(真实统计 + 趋势 + 门店/总部双视角)

> 对应 feature_list.json 的 `id`: `dashboard-analytics`
> **状态**: passing(单 commit 整体完成,PR #51 合并入 main `0b0d397`,Session 083,2026-07-14;Stage 3 后续升级 recharts)
> 优先级: 47
> 前置: 无(基础统计独立;消耗维度可选依赖 token-usage-tracking 43)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 实施结果(2026-07-28 回填状态债,三源对齐)

> 本段是对齐 [`feature_list.json`](../../feature_list.json) `status: passing` + 代码现实的真相源回填。
> 下方「背景 / 实施步骤 / 验收标准」是**规划时(2026-07-12)的历史记录**,保留不删,但「现状」描述已过时。

**实际交付**(对应下方 Step 1-6,全部落地):

| Step | 规划 | 实际 |
|---|---|---|
| Step 1 各实体 stats 端点 | 补 agents/conversations/customers `/statistics` | ✅ 全部新增(门店/HQ 双视角,service 按 `platform_role` 分流) |
| Step 2 趋势端点 | `GET /dashboard/trends?days=N` | ✅ 新增(每日对话/消息计数,零填充连续时间线) |
| Step 3 总部汇总端点 | `GET /dashboard/overview`(super_admin 专属) | ✅ 新增(平台总数 + 门店活跃 Top 10,非 super_admin → 403) |
| Step 4 前端数据层 | types + endpoints + hooks | ✅ 全部新增(`AgentStatistics`/`ConversationStatistics`/`CustomerStatistics`/`TrendPoint`/`DashboardTrends`/`PlatformTotals`/`DashboardOverview` + 对应 fetch/use hook) |
| Step 5 重写 dashboard-page.tsx | 门店视角 + 总部视角,纯 CSS 柱状 | ✅ 重写为 `StoreView`(4 统计卡 + 趋势)+ `HqView`(5 平台总数 + 门店 Top10),按 `me.platform_role === 'super_admin'` 分流。**图表方案演进**:规划写「优先纯 CSS 柱状条」,初版按此落地;**Stage 3 后续升级为 recharts**(`AreaChartMini`/`BarChartMini`,见现 `dashboard-page.tsx`),超出本 plan 原始范围,属后续增强 |
| Step 6 总验证 | `./init.sh` + `npm run build` | ✅ `./init.sh` 全绿:`ruff check` 全绿 + `pytest` 371 passed(基线 356 + 本任务新增 15 个 `tests/test_dashboard_api.py`);`npm run build` 0 错误;`npx oxlint` 0 warnings 0 errors |

**验收标准 1-6**(下方「验收标准」段):全部满足。

**关联产出**:
- alembic 迁移 `2026_07_14_0900_a1b2c3d4e5f6_add_trend_indexes.py`:给 `conversations`/`messages` 加 `(tenant_id, created_at)` 复合索引(把门店级趋势 GROUP BY 扫描降为索引范围扫描;对应「风险/注意事项」表第 1 条的缓解措施)
- ship-it 收尾(Session 083):PR #51,首轮 CI Migrations 红(alembic check 报「Detected removed index」—— 迁移建了复合索引但 ORM 模型 `Conversation`/`Message` 未声明),修复:在两个模型 `__table_args__` 加同名 `Index` 声明(commit `0ad4ed0`),复验 371 passed;第二轮 CI 四任务全绿;squash 合并入 main `0b0d397`

**铁律遵循**:Controller→Service→Repository→Model 单向依赖;多租户隔离全在 Repository 层(`TenantScopedRepository` / 显式 `WHERE tenant_id`);soft-delete 语义在 Customer 计数中保留 `is_deleted=False`。

完整证据见 [`feature_list.json`](../../feature_list.json) `dashboard-analytics.evidence`(7 条)。

---

## 背景:dashboard 是 4 个硬编码占位卡片

> ⚠️ **以下「现状」描述为 2026-07-12 规划时取证,已过时**(当时 dashboard 是占位页)。
> 实施完成后现状见上方「实施结果」段。

### 现状(2026-07-12 规划时取证,已过时)

`frontend/src/pages/dashboard-page.tsx`(L53-58)构建 `stats` 数组,只有 4 个硬编码卡片:当前角色(字符串)、Agent 数量(`agents?.length`)、截断的 tenant_id、硬编码 `"在线"`。无图表、无趋势、无时间序列。**未装任何图表库**(package.json 无 recharts/echarts/d3)。

**关键发现**:后端 `app/api/v1/users.py`(L40-52)已有 `/users/statistics` 聚合端点(`UserStatistics` schema,返回用户计数),但 **dashboard 页根本没调它**——只在 `users-page.tsx:142` 用了。这是成本最低的首胜。

### 目标

把占位页改成真实数据看板:
1. **统计卡片**:用户数 / Agent 数 / 对话数 / 客户数(门店级);门店汇总(总部级)
2. **趋势图**:近 7/30 天活跃趋势(对话创建/消息量)
3. **门店/总部双视角**:门店用户看本租户数据,super_admin 看跨租户汇总
4. **(可选)消耗维度**:token-usage-tracking(43)完成后,加 token 消耗趋势卡片

---

## 前置条件

- 无(基础统计独立)。token 消耗维度可选依赖 43。

---

## 实施步骤

### 第一阶段:后端统计端点

#### Step 1:补齐各实体 stats 端点

- **现状**:`/users/statistics` 已有;agents/conversations/customers 无 stats 端点
- **改什么**(各 Service 加 `count_for_tenant` 方法 + 各 API 加 `/statistics` 端点):
  - `GET /agents/statistics` → `{total: N, active: N}`
  - `GET /conversations/statistics` → `{total: N, last_7d: N, last_30d: N}`
  - `GET /customers/statistics` → `{total: N, active: N, last_7d_new: N}`
- **权限**:门店级用 `require_permission("<obj>", "read")`;总部级(super_admin)跨租户汇总用 `require_super_admin`
- **检查**:各端点返回正确计数;跨租户隔离

#### Step 2:趋势数据端点

- **新增** `GET /dashboard/trends?days=7|30`:
  - 返回近 N 天每日的对话创建数 + 消息数(按 created_at 日期分组)
  - 门店级:`WHERE tenant_id = current GROUP BY date`
  - 总部级(super_admin):跨租户汇总
- **实现**:`SELECT DATE(created_at) as d, COUNT(*) FROM conversations WHERE tenant_id=? AND created_at >= now()-N days GROUP BY d`
- **检查**:返回 `[{date: "2026-07-06", conversations: 12, messages: 45}, ...]`

#### Step 3:总部汇总端点(super_admin)

- **新增** `GET /dashboard/overview`(super_admin 专属):
  - 全平台统计:租户数 / 总用户 / 总对话 / 总 Agent / 总客户
  - 各门店 Top N(按对话活跃度)+ 各门店 token 消耗(依赖 43)
- **检查**:super_admin 调用返回跨租户汇总;非 super_admin → 403

### 第二阶段:前端数据层

#### Step 4:types + endpoints + hooks

- **改什么**(`frontend/src/api/types.ts`):加 `EntityStatistics` / `DashboardTrends` / `DashboardOverview` 类型
- **改什么**(`frontend/src/api/endpoints.ts`):加 `fetchAgentStats` / `fetchConversationStats` / `fetchCustomerStats` / `fetchDashboardTrends(days)` / `fetchDashboardOverview`
- **改什么**(`frontend/src/hooks/queries.ts`):加 `useAgentStats` / `useConversationStats` / `useCustomerStats` / `useDashboardTrends` / `useDashboardOverview`
- **检查**:tsc 无错;hooks 返回数据

### 第三阶段:前端页面重写

#### Step 5:重写 dashboard-page.tsx

- **改什么**(`frontend/src/pages/dashboard-page.tsx`,重写):
  - **门店视角**(非 super_admin):
    ```
    ┌──────────────────────────────────────────┐
    │ 门店概览 · 朝阳理疗中心                    │
    ├──────────┬──────────┬──────────┬────────┤
    │ 用户 12   │ Agent 4  │ 对话 89  │ 客户 23 │
    ├──────────┴──────────┴──────────┴────────┤
    │ 近 7 天活跃趋势(柱状图)                  │
    │   █ █ █ █ █ █ █                          │
    │   周一 周二 ... 周日                      │
    └──────────────────────────────────────────┘
    ```
  - **总部视角**(super_admin):
    ```
    ┌──────────────────────────────────────────┐
    │ 平台总览(super_admin)                    │
    ├────────┬────────┬────────┬──────────────┤
    │ 租户 3  │ 用户 7 │ Agent 4│ 对话 89       │
    ├────────┴────────┴────────┴──────────────┤
    │ 各门店活跃度 Top                          │
    │ 朝阳店 ████████ 89 对话                  │
    │ 海淀店 █████ 45                          │
    │ 王府井 ███ 23                            │
    └──────────────────────────────────────────┘
    ```
  - 统计卡片调各 `use*Stats()`;趋势调 `useDashboardTrends(7)`
  - **图表方案**:用轻量纯 CSS 柱状条(避免引重型库);或若需要折线,加 `recharts`(轻量,~50KB)
- **检查**:`npm run build` 通过;真实数据显示

### 第四阶段:验证

#### Step 6:总验证

- **命令**:
  ```bash
  ./init.sh   # 后端 stats 端点测试
  cd frontend && npm run build
  ```
- **手动验证**:门店用户看到本租户统计 + 趋势;super_admin 看到跨租户汇总
- **通过标准**:后端全绿 + 前端 build 通过 + 真实数据(非硬编码)
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准(全部满足 ✅,PR #51 / main `0b0d397`,2026-07-14)

1. ✅ agents/conversations/customers 各补 `/statistics` 端点(门店级 + super_admin 跨租户)
2. ✅ `GET /dashboard/trends?days=7|30` 返回每日活跃趋势
3. ✅ `GET /dashboard/overview`(super_admin)返回平台总览 + 门店 Top
4. ✅ dashboard-page.tsx 重写:门店视角(统计卡 + 趋势)+ 总部视角(总览 + 门店排行)
5. ✅ 接入已有 `/users/statistics`(此前未用)
6. ✅ `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 趋势查询性能(全表 GROUP BY) | 加 `(tenant_id, created_at)` 索引;限制 days ≤ 90 |
| 图表库依赖膨胀 | 优先纯 CSS 柱状条;折线才引 recharts |
| super_admin 跨租户查询慢 | overview 端点缓存 5 分钟(可选);或限制 Top N=10 |

### 不做的事(边界)

- 不做复杂 BI(自定义报表/拖拽图表)——后续增强
- 不做实时刷新(手动刷新即可)
- 不做 token 消耗维度(依赖 43,可后补)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| dashboard 页(已重写,Stage 3 升级 recharts) | `frontend/src/pages/dashboard-page.tsx` |
| stats 端点(已接入 + 后续补齐 4 个) | `app/api/v1/users.py` `/users/statistics`、`agents.py`、`conversations.py`、`customers.py`、`dashboard.py` |
| 各实体 Statistics schema | `app/schemas/{user,agent,conversation,customer,dashboard}.py` |
| 实体 stats 模板(原模板,其余照此) | `app/api/v1/users.py` `/users/statistics` |
| 验证测试 | `tests/test_dashboard_api.py`(15 个,门店/HQ 隔离 + 跨租户 + 零填充 + 403) |
