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
| 2026-07-30(第 8 次) | 6 候选(2 Strong + 4 Worth exploring)+ 5 deep 判定 + 1 拒绝;**Explore agent ×2 并行**后端+前端扫描。**Strong ×2**:④ Customers 双视图拆分(Top,第 4 个未拆的 store/hq 双视图 page,834 行单文件 4 组件,零单测,镜像 bookings/devices/chat split 第 4 实例)/ ③ queries.ts+endpoints.ts 按 domain 切(1560+1514 行,22 个零耦合 section,useApiMutation 68× leverage 保留放 core,barrel 保 import 零变化,第 6 次 not-shallow 判决 locality 阈值破)。**Worth exploring ×4**:① Booking 写路径 Principal 接缝泄漏(5× if access.require idiom + 顺序漂移,device +6× 同受益;受 end/no_show get-before-require 枚举防御约束,authorize_write 便利方法)/ ② chat 计费配对双实现(SSE _record_usage 不扣费 vs composite 内置 charge,seam 最清晰无 ADR 张力)/ ⑤ Settings 抽 ApiTokenCard(非 split,子组件抽离,ApiTokenCard 354 行临界)/ ⑥ bookings/shared-dialog 按 Dialog 拆(5 Dialog+RowMenu 668 行)。**deep 判定 5**:permission_service 845(SCD2↔casbin 仍 depth)/ booking_state+booking_service 整体(状态机完整 7 边 + 4 integrity guard)/ exports.py 4 generator 查询异构深(抽 Protocol 只搬 4-liner YAGNI)/ agents-page 单 function 单职责 / users+billing-admin 单视图。**拒绝 1**:customerNameOf(实测 2 处非 3,fallback null vs "-" 语义故意不同,leverage 为负) | ④ Customers 双视图拆分(范式第 4 实例 + 解锁单测 + 零行为变更零 ADR 风险) | No(待用户选) | — | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-30-v2.html` |
| 2026-07-31(第 9 次,**2026-08-14 补录**:当时漏记本表) | 5 候选(英文格式报告):① UserLocator — UserService super_admin lookup seam(Top)/ ② TurnAccountant record+charge 单 seam / ③ Principal.authorize_write + booking order unify / ④ MemberService 无直测 / ⑤ composite 扇出注入 session factory | ① UserLocator | Yes(候选 1) | [plan-user-service-lookup-seam.md](./plan-user-service-lookup-seam.md)(feature `user-service-lookup-seam` pri 84,2026-08-01 passing;候选 ②③④⑤ 未立项,② 于第 10 次三度复现) | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-31.html` |
| 2026-08-14(第 10 次) | 6 候选(Strong ×4:① permission check() bypass 判定链结构化(Top,≠第 7/8 次已关闭的「拆 permission_service」,新切口:knowledge-tiered 刚加第五层带可选 db 的 bypass,顺序错=静默权限漏洞,87 调用点)/ ② TurnAccountant 计费编排下沉(第 6/9/10 次三度独立复现,升 Strong)/ ③ graph.py 三路编排分家 composite/orchestrator/tools(deletion test 干净,468→854 行 +82%,顺带收敛 3 份 usage_acc 循环 + 第 9 次候选⑤ session factory)/ ⑤ 前端类型契约防线(types.ts 1350 行唯一未拆的 api 层 module + CI frontend job 不执行 228 个已写 vitest 用例);Worth exploring ×1:④ TenantScopedRepository 软删契约进基类(5 子类同形状覆盖,ApiTokenRepository 漏覆盖靠 service 手工过滤,与 ADR-0002 无交集);Speculative ×1:⑥ settings-page 迁 knowledge 目录范式(第 7 次降级前科,新论据=knowledge 范式已验证+settings 零测试))+ <b>业务功能风险 Top5 新板块</b>(🔴无限流+7天TTL / 🔴booking TOCTOU 无唯一约束 / 🔴计费 best-effort 无对账+SSE 无钱包放行 / 🟡super_admin 跨租户写零审计 / 🟡dev 后门押注 APP_ENV)+ Quick wins 6 条(CI 加 npm run test 居首);**Explore agent ×3 并行**(后端架构/业务功能/前端与测试)+ 主 agent 事实抽查 7 组 + 冒烟 201 passed | ① 权限 check() bypass 判定链结构化(安全单点 + 恶化中 + interface 不变 87 调用点零改动) | No(待用户选) | — | `~/.cache/ai-agent-platform-architecture-reviews/2026-08-14.html` |

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

---

## Baseline 快照(2026-07-30,第 8 次巡检)

### 后端 service/api top 15(按行数)

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
     559 app/api/v1/chat.py
     845 app/services/permission_service.py    <-- -72 vs 上次 917(backfill 去重生效)
     867 app/services/booking_service.py       <-- 最大(原第二大,permission_service 让位)
```

### 前端 fat files top 15(按行数)

```
     544 frontend/src/pages/chat/conversation-list-panel.tsx   <-- 新(chat-page split 产物)
     545 frontend/src/pages/groups-page.tsx
     590 frontend/src/pages/chat/index.tsx                     <-- 新(chat-page split 产物)
     655 frontend/src/pages/bookings/__tests__/hq-view.test.tsx
     668 frontend/src/pages/bookings/shared-dialog.tsx
     670 frontend/src/pages/bookings/hq-view.tsx
     690 frontend/src/pages/billing-admin-page.tsx
     719 frontend/src/pages/users-page.tsx
     834 frontend/src/pages/customers-page.tsx                 <-- 候选 ④(Top,第 4 个未拆 store/hq 双视图)
     841 frontend/src/pages/agents-page.tsx
    1188 frontend/src/pages/settings-page.tsx                  <-- 持平最大 page(ApiTokenCard 354 行待抽)
    1240 frontend/src/api/types.ts
    1514 frontend/src/api/endpoints.ts                         <-- 候选 ③(domain 切临界)
    1560 frontend/src/hooks/queries.ts                         <-- 候选 ③(domain 切临界,22 section)
```

### 质量基线(本次巡检时点)

- 后端测试:**842 passed**(+2 vs 上次 840,稳定)
- 前端 vitest:**94 tests**(bookings 15 + chat 16 + devices 13 + format 15 + key-spec + config-dialog;device-poweron 2 + hq-view 8 + store-view 5)
- oxlint:**0 warning 0 error**
- ruff:**All checks passed**
- `app/` + `frontend/src/` 内 TODO/FIXME/HACK/XXX:**2 处**(持平 Logto 占位)
- Note(candidate-):**0 处**(union-cast 候选 8 已全清)
- `as` cast 角色分支:**0 处**(union-cast-split 已消解)
- CONTEXT.md:**存在,2 条 Principal + Two-Scope Config 业务条目**
- docs/adr/:**2 个**(0001 Principal scope boundary / 0002 TwoScopeConfig repository)

### 涨幅分析(vs 2026-07-29 第 6 次)

- **booking_service 867 行成新最大**(原第二大,permission_service 917→845 让位)
- permission_service 917→845(-72,backfill 参数化去重生效,前 7 次候选消解)
- 前端 queries.ts 1505→1560 / endpoints.ts 1466→1514(各 +55/+48 缓涨,22 section 破 locality 阈值 → 候选 ③ 第 6 次 not-shallow 判决重评为 Strong)
- **前端 5 大 page 零单测**(settings/devices/chat/agents/customers/users,共 ~5700 行)→ chat/devices 已 split 解决,剩 settings/agents/customers/users/billing-admin 5 个,其中 **customers 是第 4 个 store/hq 双视图 page(候选 ④ Top)**,agents/users/billing-admin 判定 deep 不拆

### 第 8 次关键判定(deletion test 结果)

- **Customers split(候选 ④)** = Strong:镜像已验证 3 次的 bookings/devices/chat split 第 4 实例,store(411)+hq(175)+Dialog(90)+零单测 → 一石三鸟
- **queries/endpoints domain 拆(候选 ③)** = Strong:第 6 次 not-shallow 判决重评 —— leverage(useApiMutation 68×)未降但 locality(22 section/1560 行)破阈值,barrel 保 import 零变化
- **5 大 page 逐个裁决**:customers 拆 / settings 抽 ApiTokenCard / agents+users+billing-admin **deep 不动**(单 function 或单视图,拆=搬)—— 比把 5 个都标候选更重要
- **permission_service 845** = deep 确认(第 6 次判决维持,4 cluster 各有真深度)
- **customerNameOf** = 拒绝(实测 2 处非 3,fallback null vs "-" 语义故意不同,leverage 为负)

### 下次巡检 trigger

- 第 **90** 个 feature 完成时(当前 78,距下次 12 个)
- 或 §1.2 触发条件任一满足(尤其 booking_service 再涨 >20%、或 queries.ts 突破 1700 行未拆 domain)
- 或候选 ④ Customers split 完成后(customer-helpers 范式扩展,可评估是否复用)

---

## Baseline 快照(2026-08-14,第 10 次巡检)

### 后端 service top 11 + api top 5 + agents(按行数)

```
     268 app/services/billing_service.py
     271 app/services/agent_service.py
     301 app/services/category_service.py          <-- 新(knowledge-tiered)
     327 app/services/rbac_service.py
     374 app/services/customer_service.py
     381 app/services/conversation_service.py
     444 app/services/device_service.py
     485 app/services/user_service.py
     633 app/services/knowledge_service.py          <-- 新(knowledge-tiered,3 子域)
     867 app/services/booking_service.py            <-- 最大 service(持平)
     949 app/services/permission_service.py         <-- 最大,+104 vs 上次 845(+12%)
     328 app/api/deps.py        559 app/api/v1/chat.py(计费编排 ~140 行在 api 层)
     854 app/agents/graph.py    <-- 首巡 468 → 854(+82%,§1.2 触发:composite+orchestrator 落地)
```

### 前端 fat files top 8(按行数)

```
     545 frontend/src/pages/groups-page.tsx
     590 frontend/src/pages/chat/index.tsx
     670 frontend/src/pages/bookings/hq-view.tsx
     668 frontend/src/pages/bookings/shared-dialog.tsx
     690 frontend/src/pages/billing-admin-page.tsx
     719 frontend/src/pages/users-page.tsx
     841 frontend/src/pages/agents-page.tsx
    1192 frontend/src/pages/settings-page.tsx       <-- 持平最大 page(24 useState/0 useForm/0 测试)
    1350 frontend/src/api/types.ts                  <-- +110 vs 上次 1240,api 三件套唯一未拆
    (queries.ts / endpoints.ts 已按域拆分完成,退出本表 ✅)
```

### 质量基线(本次巡检时点)

- 后端测试:**926 用例 / 55 文件**(+84 vs 上次 842);冒烟 `pytest -m smoke` **201 passed 全绿**
- 前端 vitest:**228 用例 / 28 文件**(knowledge 11 / bookings 5 / customers 3 / chat 2 / devices 2 / 其他 5)——**CI frontend job 只跑 oxlint+build,不执行 vitest ⚠️**
- TODO/FIXME/HACK/XXX:**3 处**(Logto OIDC 占位 ×2 + 1)
- 依赖方向:repo→service / model→上层 **0 违规**;service→api 反向 import **2 处**(api_token_service.py:19 常量 / permission_service.py:37 contextvar)
- 迁移:35/35 模型表全有对应迁移(孤儿表 `verification_codes` 1 个)
- 测试金字塔:~89% HTTP API 层 / ~11% 纯单元(头重脚轻)
- CONTEXT.md / docs/adr:2 个 ADR 均维持 Accepted,本次候选零冲突

### 涨幅分析(vs 2026-07-30 第 8 次)

- **graph.py +82%(468→854)** —— §1.2 触发;composite-chat(~335 行)+ orchestration(~205 行)同居 → 候选 ③
- permission_service 845→949(+12%,未破 20%),但增量几乎全在 check() bypass 链与 knowledge 种子 → 候选 ①(新切口,非拆模块)
- knowledge 域全线新增(knowledge_service 633 / category_service 301 / api 276 / 前端 15 文件+11 测试)——新代码质量高(msw 契约层/目录化范式),是 settings 等旧页的对照范本
- 第 8 次候选 ②③ 已完成(customers split / queries+endpoints 域拆)✅;候选 ②(chat 计费)三度复现升 Strong

### 下次巡检 trigger

- 第 **100** 个 feature 完成时(当前 89,距下次 11 个)
- 或 §1.2 触发条件任一满足(尤其 graph.py 再涨 >20%、check() 再加 bypass 层、permission_service 破 1100 行)
- 或:CI 仍未执行前端测试 / booking TOCTOU 未加 DB 兜底(业务风险 Top2 未消)时,下次巡检优先复评
