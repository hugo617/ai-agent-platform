# 代码健康度巡检日志

> 每次跑 [`/improve-codebase-architecture`](codebase-health-check.md) 后追加一行。
> baseline 快照段记录 `wc -l` top 10,作为下次巡检的对比基准。

---

## 巡检记录

| 日期 | 候选数 | Top recommendation | 进 grill? | 产出 plan | HTML 归档 |
|---|---|---|---|---|---|
| 2026-07-20 | 6 候选(P0:permission_service / token_context+deps / graph.py / chat.py;P1:user_service / exports.py;P2:前端 fat files) | ③ Agent 流式模块(graph.py,SSE + asyncio.timeout + 工具内权限) | No(用户改做设备功能系列 61-64,未走 grill) | — | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-20.html` |
| 2026-07-25 | 8 候选(Strong ×4:Booking 单文件三视图 / 状态机 cancel 未并入 / end-no_show auth 推 body / 前端 9 page 零单测;Worth exploring ×4:Customer principal 参数透传 / HQ Panorama mirror / 三叉路由 4 page 复制 / union endpoint cast) | ① Booking 三视图拆 module(零行为变更)+ ② cancel 并入状态机(完成 deep module) | Yes(候选 1) | [plan-bookings-page-split.md](./plan-bookings-page-split.md)(grill 4 决策:bookings/ 子文件夹 / 测试跟 view / 只拆不碰 cast / 现有测试全绿+补 HqView smoke) | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-25.html` |
| 2026-07-27 | 14 候选(Strong ×4:Principal 深模块吸收 77 处角色扇出 / permission_service 拆 3 模块(899 行)/ devices-page.tsx 1073 行拆 module / chat-page.tsx 954 行单 function 拆 panel;Worth exploring ×4:exports.py 4 row generator 吸收回 service / union endpoint cast 扩散至 7 处(candidate-8 恶化)/ schedule-grid datetime helper 收编 format.ts / settings-page ApiTokenCard 抽出;Speculative ×6:状态机残留 _MUTABLE_STATUSES / deps.py 重复 / graph.py streaming 循环 / _to_read ×12 重写 / conversation 6 metadata 方法 / queries+endpoints 按 domain 拆) | ① Principal 深模块(leverage 最大,77 处 → 1 处,顺带吸收 candidate-8) | No(用户刚启动巡检,未走 grill) | — | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-27.html` |
| 2026-07-28 | 20 候选(第 3 次 14 候选复评:1 ✅ 已解决 / 7 🟢 仍存在 / 4 🔴 恶化 / 1 ⚪ 误判 + 10 新候选;Strong ×4:候选 2 配置范式 leverage 4 TwoScopeConfig(Top)/ 候选 1 permission_service 915 行拆 / 候选 3 Principal 半收口漂移 / 候选 4 union cast 7→11+;Worth exploring ×9;Speculative ×7) | ② 候选 3 Principal 半收口(CONTEXT vs 代码张力,leverage 小但最紧迫) | Yes(候选 3) | [plan-principal-scope-doc-alignment.md](./plan-principal-scope-doc-alignment.md)(grill 6 决策:文档对齐非扩 Principal + ADR-0001 项目首个 ADR + 单一切片 7 改动 + opus 审查 ×2)+ [ADR-0001](../../docs/adr/0001-principal-scope-boundary.md) 项目首个 ADR 钉死边界 | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-27-v2.html` |
| 2026-07-29 | 12 候选(第 4 次 20 候选复评:1 ✅ 已解决[Principal 半收口] / 2 🔴 恶化[TwoScopeConfig 2→3 repo+3 service / chat.py 双轨计费 composite 引入] + 5 新候选;Strong ×4:候选 1 TwoScopeConfig 抽基类+协议(Top,从上次候选 2 恶化升级)/ 候选 2 permission_service 917 行拆 5 cluster / 候选 3 chat.py 双轨计费 TurnAccountant / 候选 4 union-cast 扩散 ~10 处;Worth exploring ×5:graph.py usage_acc ×3 / endpoints+queries 按域拆 / booking_config API 层重复契约 / booking_service 4 auth idiom(ADR 保护)/ exports.py Protocol;Speculative ×3:billing 两阶段写 / Principal safe-use 类型强制 / shared-dialog 补单测) | ① 候选 1 TwoScopeConfig 抽 TwoScopeRepository 基类(leverage 最大,3 repo+3 service 归一,ADR 风险低) | Yes(候选 1) | [plan-twoscope-config.md](./plan-twoscope-config.md)(grill 5 决策 + opus 对抗式审查 ×2[真相核查+业务设计]→ 3 P0 回炉:决策3 加 is_active 死列→改钩子 _active_filter / 删 slice3 ModelPricingService 空架子 / 补 ADR-0002 → v2 零 schema 零死列纯架构卫生 + 2 P1:frontier 改 llm + repo 契约测试先行)+ 待产出 [ADR-0002](../../docs/adr/0002-twoscope-config-repository.md)(末切片) | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-29.html` |
| 2026-07-29 | 6 候选(第 5 次 12 候选复评:1 ✅ 已解决[TwoScopeConfig → twospace-config passing + ADR-0002] / 0 🔴 恶化 / 8 🟢 仍存在 + 2 🔵 新候选[composite_chat 单函数 / — ];Strong ×2:候选 A permission_service 拆 5 cluster(仍存在,917 行,backfill migrator 错位塞 runtime)/ 候选 B 前端 union-cast 扩散 12 处(微恶化,上次 ~10→12);Worth exploring ×3:候选 C composite_chat endpoint 5 concern 单函数(新发现)/ 候选 D graph.py usage 累加循环重复 2 处(仍存在)/ 候选 E 前端 6 大 page 零单测(仍存在,扩大);Speculative ×1:候选 F chat.py 双轨计费 record 路径(上次候选 3 降级,plan 明确要求独立防签名耦合)) | ② 候选 B 前端 union-cast 扩散(leverage 高 + 风险低:role 解析上移 hook 是纯类型重构消 12 cast 零行为变更无 ADR 风险;候选 A 虽 friction 大但 check 被 163 调用点依赖需 contract test 兜底) | Yes(候选 B) | [plan-union-cast.md](./plan-union-cast.md)(grill 8 决策:D1 拆 role-specific hook / D2 ModelOption 投影不纳入 / D3 只拆 3 个有调用的 / D4 按 domain 分 3 切片 / D5 queryKey 共享 / D6 All 后缀随 useAllTenants 先例 / D7 改 mock 名 + tsc 验证 / D8 不提 ADR)+ 登记 feature_list.json `union-cast-split` priority 75 not_started | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-29-v2.html` |
| 2026-07-30 | 10 候选(第 6 次 6 候选复评 + 新发现;3 Strong + 1 Worth exploring + 2 关闭 + 2 拒绝 + 2 降级;**Explore agent ×2 并行**后端+前端扫描)。**Strong ×3**:① chat-page.tsx 拆 ConversationListPanel + buildWorkingList 纯函数(Top,1038 行单函数 + A2 不可测结构性债)/ ② devices-page.tsx 拆 store-view/hq-view(1083 行,镜像 bookings/ 范式)/ ③ permission backfill 参数化去重(Strong WORSENED,两个函数逐字节镜像)。**Worth exploring ×1**:④ composite_chat billing seam(暂缓,刚 ship)。**关闭 ×2**:ScheduleGridCard(已迁移 schedule-grid-card.tsx,Divergent Change 消解)/ permission_service 拆 5 cluster(正式关闭为 not-shallow,SCD2↔casbin 宪法是 depth,真 friction 是 backfill 去重)。**拒绝 ×2**:queries/endpoints/types god-module(通过 deletion test,useApiMutation 72× leverage + qk 编码不变式)/ settings-page ApiTokenCard(降级,cards 已 module-level)。**降级 ×2**:graph.py usage 循环(→ Speculative,composite 已抽 helper)/ chat.py 双轨计费(维持 Speculative,分歧有据) | ① chat-page 拆 ConversationListPanel(一石三鸟:消膨胀 + 解 A2 不可测债 + 抽纯函数;比 ② 多解一维) | Yes(候选①②③同批,「批量规划+串行实施」) | ① [plan-chat-page-split.md](./plan-chat-page-split.md)(grill 9 决策:D1 Panel+纯函数 / D2 传 handler / D3 独立.ts / D4 建 chat/ 文件夹 / D5 Dialog 随 Panel / D6 不动 chat panel / D7 customerNameOf 共享 / D8 两测试 / D9 router barrel)+ ③ [plan-perm-backfill-dedupe.md](./plan-perm-backfill-dedupe.md)(grill 4 决策:D1 合并+改 caller / D2 合并 scripts / D3 测试 parametrize / D4 白名单约束)+ ② [plan-devices-page-split.md](./plan-devices-page-split.md)(grill 5 决策:D1 完全镜像 bookings/ / D2 4 Dialog→device-dialogs.tsx / D3 helper 按职责拆 / D4 store+hq 两测试 / D5 router barrel)。登记 3 feature(chat-page-split pri 76 / perm-backfill-dedupe pri 77 / devices-page-split pri 78)。Phase 2 实施顺序 ①→③→② | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-30.html` |

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

---

## Baseline 快照(2026-07-29,第 6 次巡检)

### 后端 service top 10(按行数)

```
     268 app/services/billing_service.py
     271 app/services/agent_service.py
     296 app/api/v1/devices.py
     313 app/api/v1/billing.py
     327 app/services/rbac_service.py
     335 app/api/v1/bookings.py
     374 app/services/customer_service.py
     381 app/services/conversation_service.py
     444 app/services/device_service.py
     476 app/services/user_service.py
     495 app/api/v1/exports.py
     559 app/api/v1/chat.py          <-- +248 vs 上次 311(composite-chat 引入)
     867 app/services/booking_service.py
     917 app/services/permission_service.py    <-- 最大,+50 vs 上次 867
```

### 前端 fat files top 7(按行数)

```
     674 frontend/src/pages/bookings/hq-view.tsx
     690 frontend/src/pages/billing-admin-page.tsx
     719 frontend/src/pages/users-page.tsx
     834 frontend/src/pages/customers-page.tsx
     841 frontend/src/pages/agents-page.tsx
    1038 frontend/src/pages/chat-page.tsx       <-- +84 vs 上次 954(composite 模式)
    1073 frontend/src/pages/devices-page.tsx    <-- +346 vs 上次 727
    1188 frontend/src/pages/settings-page.tsx   <-- 持平(最大 page)
    1240 frontend/src/api/types.ts              <-- +186 vs 上次 1054
    1466 frontend/src/api/endpoints.ts          <-- +241 vs 上次 1225
    1505 frontend/src/hooks/queries.ts          <-- +212 vs 上次 1293
```

### 质量基线(本次巡检时点)

- 后端测试:**840 passed**(+126 vs 上次 714)
- 前端 vitest:**65 tests / 8 files**(bookings 5 view + format + key-spec-rows + config-dialog)
- oxlint:**0 warning 0 error**
- ruff:**All checks passed**
- `app/` 内 TODO/FIXME/HACK/XXX:**0 处**
- CONTEXT.md:**存在,2 条 Principal + Two-Scope Config 业务条目**
- docs/adr/:**2 个**(0001 Principal scope boundary / 0002 TwoScopeConfig repository)

### 涨幅分析(vs 2026-07-25 第 2 次)

- permission_service 917 行(+50,稳定,未触发 §1.2「再涨 >20%」)
- chat.py 559 行(+248,composite-chat feature 引入,属功能扩展非债)
- 前端三 fat files(queries/endpoints/types)各 +186~241,主因 composite + booking_config domain
- **前端单测覆盖率仍低**:6 大 page(settings/devices/chat/agents/customers/users,共 ~5700 行)零单测,仅 bookings/ 文件夹有覆盖 → 候选 E

### 下次巡检 trigger

- 第 **80** 个 feature 完成时(当前 74,距下次 6 个)
- 或 §1.2 触发条件任一满足(尤其 union-cast 再增 >2 处,或前端大 page 单测覆盖率仍为 0)
