# 代码健康度巡检日志

> 每次跑 [`/improve-codebase-architecture`](codebase-health-check.md) 后追加一行。
> baseline 快照段记录 `wc -l` top 10,作为下次巡检的对比基准。

---

## 巡检记录

| 日期 | 候选数 | Top recommendation | 进 grill? | 产出 plan | HTML 归档 |
|---|---|---|---|---|---|
| 2026-07-20 | 6 候选(P0:permission_service / token_context+deps / graph.py / chat.py;P1:user_service / exports.py;P2:前端 fat files) | ③ Agent 流式模块(graph.py,SSE + asyncio.timeout + 工具内权限) | No(用户改做设备功能系列 61-64,未走 grill) | — | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-20.html` |
| 2026-07-25 | 8 候选(Strong ×4:Booking 单文件三视图 / 状态机 cancel 未并入 / end-no_show auth 推 body / 前端 9 page 零单测;Worth exploring ×4:Customer principal 参数透传 / HQ Panorama mirror / 三叉路由 4 page 复制 / union endpoint cast) | ① Booking 三视图拆 module(零行为变更)+ ② cancel 并入状态机(完成 deep module) | Yes(候选 1) | [plan-bookings-page-split.md](./plan-bookings-page-split.md)(grill 4 决策:bookings/ 子文件夹 / 测试跟 view / 只拆不碰 cast / 现有测试全绿+补 HqView smoke) | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-25.html` |

---

## Baseline 快照(2026-07-20,首次巡检)

### 后端 service top 10(按行数)

```
     197 app/services/auth_service.py
     228 app/services/knowledge_service.py
     268 app/services/api_token_service.py
     268 app/services/billing_service.py
     271 app/services/agent_service.py
     327 app/services/rbac_service.py
     351 app/services/conversation_service.py
     353 app/services/customer_service.py
     476 app/services/user_service.py
     617 app/services/permission_service.py     <-- 最大,横切关注点
```

### 后端 api top 10(按行数)

```
     246 app/api/v1/customers.py
     258 app/api/v1/conversations.py
     260 app/api/v1/auth.py
     311 app/api/v1/chat.py
     313 app/api/v1/billing.py
     495 app/api/v1/exports.py     <-- 最大,1 endpoint 内含 6 实体生成
```

### 前端 fat files top 5

```
    1188 frontend/src/pages/settings-page.tsx
    1079 frontend/src/hooks/queries.ts
    1048 frontend/src/api/endpoints.ts
     954 frontend/src/pages/chat-page.tsx
     862 frontend/src/api/types.ts
```

### 质量基线(本次巡检时点)

- 后端测试:**561 passed**
- 覆盖率:**93%**(门槛 ≥80%)
- oxlint:**0 warning 0 error**
- ruff:**All checks passed**
- `app/` 内 TODO/FIXME/HACK/XXX:**0 处**(已过 3 轮 cleanup)
- 前端单测:**0**(仅 1 个 Playwright e2e)
- CONTEXT.md:**首次创建**(本次 Step 0)
- docs/adr/:**尚不存在**(等 Step 3 grill 触发 lazy 创建)

### 下次巡检 trigger

- 第 **70** 个 feature 完成时(当前 64,距下次 6 个)
- 或 §1.2 触发条件任一满足

---

## Baseline 快照(2026-07-25,第 2 次巡检)

### 后端 service top 10(按行数)

```
     228 app/services/knowledge_service.py
     268 app/services/api_token_service.py
     268 app/services/billing_service.py
     271 app/services/agent_service.py
     327 app/services/rbac_service.py
     351 app/services/conversation_service.py
     353 app/services/customer_service.py
     374 app/services/device_service.py          <-- 新增(device 系列)
     476 app/services/user_service.py
     681 app/services/booking_service.py         <-- 新增(device 系列),第二大
     867 app/services/permission_service.py     <-- 最大,+250(+40% vs 上次 617)
```

### 后端 api top 10(按行数)

```
     192 app/api/v1/users.py
     246 app/api/v1/customers.py
     258 app/api/v1/conversations.py
     262 app/api/v1/bookings.py                  <-- 新增
     265 app/api/v1/auth.py
     283 app/api/v1/devices.py                   <-- 新增
     311 app/api/v1/chat.py
     313 app/api/v1/billing.py
     495 app/api/v1/exports.py     <-- 仍最大,1 endpoint 内含 6 实体生成
```

### 前端 fat files top 7

```
     727 frontend/src/pages/devices-page.tsx     <-- 新增
     834 frontend/src/pages/customers-page.tsx
     841 frontend/src/pages/agents-page.tsx
     954 frontend/src/pages/chat-page.tsx
    1054 frontend/src/api/types.ts                <-- +192 vs 上次 862
    1188 frontend/src/pages/settings-page.tsx
    1225 frontend/src/api/endpoints.ts            <-- +177 vs 上次 1048
    1293 frontend/src/hooks/queries.ts            <-- +214 vs 上次 1079
    1373 frontend/src/pages/bookings-page.tsx     <-- 新增,现为最大(超 settings)
```

### 质量基线(本次巡检时点)

- 后端测试:**714 passed**(+153 vs 上次 561)
- 前端 vitest:**12 tests / 2 files**(device-poweron 切片 02 引入,仅 bookings 2/3 view)
- oxlint:**0 warning 0 error**
- ruff:**All checks passed**
- `app/` + `frontend/src/` 内 TODO/FIXME/HACK/XXX:**2 处**(均 Logto OIDC 集成占位,非新增债,auth-context.tsx:12 + login-page.tsx:263)
- CONTEXT.md:**已存在**(2026-07-20 创建)
- docs/adr/:**仍不存在**(等本次 Step 3 grill 触发 lazy 创建)

### 涨幅分析(vs 2026-07-20)

- **触发条件 §1.2「top 10 平均涨幅 >20%」已满足**:permission_service +40%(617→867)
- 涨幅来源:device 系列 4 feature 全新 booking_service(681)+ device_service(374 涨至 374)+ permission seed 回填(+250)
- 前端三 fat files(queries/endpoints/types)各 +180~214,主因 booking/device domain 类型与 hook 注入
- bookings-page.tsx 1373 行成新最大,超上次最大 settings-page(1188)

### 下次巡检 trigger

- 第 **70** 个 feature 完成时(当前 64,距下次 6 个)
- 或 §1.2 触发条件任一满足(尤其 permission_service 再涨 >20%,或前端单测覆盖率仍 <10%)
