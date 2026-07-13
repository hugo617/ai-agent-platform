# 计划:Dashboard 数据看板(真实统计 + 趋势 + 门店/总部双视角)

> 对应 feature_list.json 的 `id`: `dashboard-analytics`
> 状态: not_started
> 优先级: 47
> 前置: 无(基础统计独立;消耗维度可选依赖 token-usage-tracking 43)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:dashboard 是 4 个硬编码占位卡片

### 现状(2026-07-12 取证)

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

## 验收标准

1. agents/conversations/customers 各补 `/statistics` 端点(门店级 + super_admin 跨租户)
2. `GET /dashboard/trends?days=7|30` 返回每日活跃趋势
3. `GET /dashboard/overview`(super_admin)返回平台总览 + 门店 Top
4. dashboard-page.tsx 重写:门店视角(统计卡 + 趋势)+ 总部视角(总览 + 门店排行)
5. 接入已有 `/users/statistics`(此前未用)
6. `./init.sh` + `npm run build` 全绿

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
| dashboard 占位页(待重写) | `frontend/src/pages/dashboard-page.tsx` |
| 已有 stats 端点(接入) | `app/api/v1/users.py` L40-52 |
| UserStatistics schema | `app/schemas/user.py` L83 |
| 实体 stats 模板 | `app/api/v1/users.py` `/users/statistics` |
