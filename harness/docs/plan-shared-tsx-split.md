# 计划:bookings/shared.tsx 按功能职责拆分(Divergent Change 收债)

> **id**: bookings-shared-split
> **状态**: in_progress(EP2 回环完成:grill 7 决策 + 子智能体对抗式审查 v2 回炉 + 3 切片就绪。status: draft v2 → in_progress)
> **优先级**: 73(「工程化」area,bookings-page-split 留痕的后续候选;feature_list.json 真相源)
> **创建日期**: 2026-07-29
> **最后修订**: 2026-07-29(v2:子智能体审查发现 3 P0 + 4 P1,全部坐实并回炉决策)
> **来源**: [progress.md](../../progress.md) bookings-page-split ✅ 留痕登记的后续候选 —— "ScheduleGridCard + 其私有 date helpers(slotTone/dayLabel/hhmm 等)只被 StoreView 消费,却混在所有 view 共享的 shared.tsx,Divergent Change"。

---

## 0. v1 → v2 变更摘要(对抗式审查回炉)

本 plan 的 v1 是 grill 会话的决策矩阵(D1 全拆 5 文件 / D2 删 shared / D3 补 ~10 单测 / D4 无 barrel / 走 EP2)。v1 经**子智能体独立审查**(重新读代码核查事实)+ 主持人复核,发现以下问题,全部在 v2 修正:

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| export 计数错(说 17,实际 **19 个导出符号**:漏数 `NONE` + `BookingFilter` type + re-export 双名) | 🔴 P0 | 重算战场规模,所有数字回炉 |
| 消费者计数错(说 6,实际 **5 个**:`config-dialog.tsx` 不消费 shared,`grep exit=1` 已确认) | 🔴 P0 | 消费者清单修正 |
| `fmt`/`fromDatetimeLocalValue` 归属盲点(5 文件清单完全没提,实为 `@/lib/format` 的便利 re-export) | 🔴 P0 | **回源 `@/lib/format`**(config-dialog 已这么做是正确范式),不进新文件 |
| `deviceNameOf` 归属盲点(单消费者 store-view,5 文件清单无它的位置) | 🔴 P0 | 留在瘦身后的 shared.tsx(避免单符号孤儿文件) |
| D3 补单测违反 plan-bookings-page-split.md 范式(:91 测试跟 view 走 / :112 现有测试全绿验证 / :160 补测是独立候选 4) | 🟡 P1 | **撤销 D3**,沿用"测试跟 view 走",零行为变更靠现有 view 测试验证 |
| `slotTone` 原计划放 badges.tsx,但它是 ScheduleSlot 的私有 helper(与 BookingStatusBadge 是不同视觉系统) | 🟡 P1 | **移到 schedule-grid-card.tsx**(单消费者内聚) |
| D2 删 shared + D4 无 barrel 导致 store-view import 从 1 行变 5 行(全 frontend 13 行 import 改动) | 🟡 P1 | **D2 改为瘦身保留** shared.tsx 作真共享底座,只抽功能内聚的 4 块 |

**审查方法论说明**:v1 决策是在 grill 会话中由用户选择"全拆 5 文件",但子智能体以代码功能 + 范式合规双轴审查后,主持人向用户确认标准为"以代码功能为标准,以实现的目标为标准"。在此标准下,**全拆方向正确**(每个功能组确实单一内聚),但需修正三个盲点(fmt/deviceNameOf/slotTone 归属)+ 撤销违反范式的 D3 补测。v2 = 全拆方向 + 盲点修正 + 范式对齐。

---

## 1. Problem Statement

`frontend/src/pages/bookings/shared.tsx`(14KB,**19 个导出符号**)是 bookings-page-split 重构(Session 139)后留下的"杂项共享"文件。它在拆分时承担了"把原 1373 行胖文件里所有跨 view 共享的符号集中到一处"的过渡职责,但随之产生了 **Divergent Change** smell:

- 文件混了 **5 类功能不相关的符号**:① booking 状态领域模型(STATUS_META 等)② 列表过滤逻辑 ③ 日期/时间纯函数 ④ 跨 view 显示原语 ⑤ StoreView 专属的 ScheduleGridCard 组件树。
- 其中 `ScheduleGridCard` + `ScheduleSlot` + `slotTone` + `dayLabel` 是 **StoreView 专属的私有组件树**,却和"所有 view 共享的常量"混在同一文件 —— 改 StoreView 的网格逻辑会触发这个"共享文件"的变更,违反单一职责。
- `fmt` / `fromDatetimeLocalValue` 是从 `@/lib/format` 的**便利 re-export**(`shared.tsx:149-151` 注释明示"so views import everything from one place"),这是一个可消除的间接层 —— `config-dialog.tsx` 已经直接从 `@/lib/format` import,证明回源是正确范式。

**为什么现在做**:bookings-page-split 的 /code-review 明确把这个 smell 登记为独立后续候选 `bookings-shared-split`(progress.md:1934 留痕)。composite-chat 系列(优先级 72)已于 2026-07-28 收官,feature_list 当前 0 活跃任务,这是排新需求的窗口。

**以代码功能为标准的目标**:让 `shared.tsx` 里的每个符号归位到"功能单一、内聚、可独立理解"的模块,消除"改一个功能要碰一个名义上共享的文件"的 Divergent Change。

---

## 2. Solution

按**代码功能内聚度**把 `shared.tsx` 的 19 个导出符号归位到 4 个新文件 + 1 个瘦身后保留的 shared.tsx 底座,同时消除 `fmt`/`fromDatetimeLocalValue` 的便利 re-export(回源 `@/lib/format`)。

**零行为变更**:纯文件挪动 + import 路径调整,符合 Divergent Change 重构特征。现有 5 个 view 测试(store-view/hq-view/my-bookings-view/schedule-grid/config-dialog)全绿验证 carry 正确性,沿用 plan-bookings-page-split.md "测试跟 view 走"范式,**不补新单测**(补测是独立候选 4,不混入本次 locality 重构)。

---

## 3. User Stories

- 作为**前端开发者**,我想 `shared.tsx` 的每个文件功能单一内聚,以便改 ScheduleGridCard 时只碰 `schedule-grid-card.tsx`,不必触动"共享文件"。
- 作为**前端开发者**,我想 booking 状态机常量集中在 `status-meta.ts`,以便未来加新状态(如 `confirmed` 真正启用)只改一个领域文件。
- 作为**前端开发者**,我想 date helpers 集中在 `date-utils.ts`,以便 hq-view / schedule-grid / filter / schedule-grid-card 各自按需 deep import,不再从一个杂项文件抓取。
- 作为**code reviewer**,我想 `fmt`/`fromDatetimeLocalValue` 直接从 `@/lib/format` import,以便消除一个不必要的 re-export 间接层(与 config-dialog 范式对齐)。

---

## 4. Implementation Decisions

### 4.0 决策矩阵(v2 最终)

| # | 决策 | 选择 | 事实依据 |
|---|---|---|---|
| D1 | 拆分粒度 | **按功能职责拆 4 新文件 + shared.tsx 瘦身保留** | 每个功能组单一内聚(状态模型/过滤/日期/网格卡);shared.tsx 保留作真共享底座(BookingStatusBadge 跨 3 view + deviceNameOf) |
| D2 | shared.tsx 去留 | **瘦身保留** | 避免单消费者 deviceNameOf 成孤儿文件或塞进 store-view;BookingStatusBadge 是跨 3 view 的真共享原语 |
| D3 | 测试 | **不补新单测** | 沿用 plan-bookings-page-split.md 范式(测试跟 view 走,零行为变更靠现有 view 测试全绿验证);补测是独立候选 4 |
| D4 | import 策略 | **纯 deep import(无新 barrel)** | 新 barrel 实质复活 shared.tsx 的便利层,与"消除间接层"目标冲突;消费者按需从具体功能文件 import |
| D5 | `fmt`/`fromDatetimeLocalValue` | **回源 `@/lib/format`** | 它们是便利 re-export 不是 shared 真实职责;config-dialog 已直接从 @/lib/format import 是正确范式 |
| D6 | `slotTone` 归属 | **schedule-grid-card.tsx**(非 badges) | 单消费者(ScheduleSlot),与 BookingStatusBadge 是不同视觉系统(三态色 vs 状态徽章) |
| D7 | `deviceNameOf` 归属 | **留在瘦身后的 shared.tsx** | 单消费者 store-view,但语义是"显示原语"(与 BookingStatusBadge 同类),留 shared 避免孤儿文件 |

### 4.1 文件归位清单(19 个导出符号逐一定位)

#### 新建 4 文件

**① `status-meta.ts`** —— booking 状态领域模型(功能组 A)
```
STATUS_META         (6 状态→{label,badge} 映射)
MUTABLE_STATUS      ({pending} 可改约/取消集)
ACTIONABLE_STATUS   ({pending,confirmed,in_service} 生命周期菜单可见集)
NONE                ("_none" walk-in 哨兵)
```
- 消费者:`shared-dialog.tsx`(直接 import MUTABLE/ACTIONABLE/NONE)、`badges.tsx`(经 STATUS_META)、`schedule-grid-card.tsx`(经 STATUS_META)
- 依赖:无(叶子节点)
- 注:`BookingFilter` type 不在这里(归 filter.ts,与过滤逻辑同组)

**② `date-utils.ts`** —— 日期/时间纯函数(功能组 C)
```
startOfToday / addDays / isoDate / hhmm / dayLabel
```
- 消费者:`hq-view.tsx`(startOfToday/isoDate)、`schedule-grid.tsx`(hhmm,既有邻居)、`filter.ts`(applyBookingFilter 内部用)、`schedule-grid-card.tsx`(网格窗口计算)
- 依赖:无(叶子节点)

**③ `filter.ts`** —— 列表过滤逻辑(功能组 B)
```
BookingFilter (type) / FILTER_OPTIONS / FilterChips / applyBookingFilter
```
- 消费者:仅 `store-view.tsx`
- 依赖:`date-utils.ts`(applyBookingFilter 用 startOfToday/addDays/isoDate)

**④ `schedule-grid-card.tsx`** —— StoreView 专属网格卡组件树(功能组 D)
```
ScheduleGridCard / ScheduleSlot / slotTone
```
- 消费者:仅 `store-view.tsx`
- 依赖:`status-meta.ts`(STATUS_META)、`date-utils.ts`(startOfToday/addDays/isoDate/dayLabel/hhmm)
- 注:`slotTone` 是 ScheduleSlot 的私有 helper(单消费者),与 BookingStatusBadge 是不同视觉系统,故归此非 badges

#### shared.tsx 瘦身保留(功能组 E)
```
BookingStatusBadge  (跨 store-view/hq-view/my-bookings-view 三 view 的状态徽章)
deviceNameOf        (device_id→序列号,单消费者 store-view,但语义是显示原语)
```
- 删除:STATUS_META/MUTABLE/ACTIONABLE/NONE(→ status-meta.ts)、Filter 相关 4 符号(→ filter.ts)、5 个 date helpers(→ date-utils.ts)、ScheduleGridCard/ScheduleSlot/slotTone(→ schedule-grid-card.tsx)
- 删除:`fmt`/`fromDatetimeLocalValue` re-export(D5 回源)
- 瘦身后约 50-60 行,只剩 2 个真共享显示原语 + 各自 import(BookingStatusBadge 从 status-meta 拿 STATUS_META)

#### D5 回源(不进任何新文件)
```
fmt / fromDatetimeLocalValue → 消费者直接 import from "@/lib/format"
```
- 改动消费者:`store-view.tsx`、`hq-view.tsx`、`my-bookings-view.tsx`(以上三处用 fmt)、`shared-dialog.tsx`(用 fromDatetimeLocalValue)
- 范式依据:`config-dialog.tsx:63` 已 `import { toDatetimeLocalValue } from "@/lib/format"`,证明 @/lib/format 是这些 helper 的正确归属地

### 4.2 依赖图(DAG,已验证无环)

```
status-meta.ts ──┬──→ badges.tsx(shared 内,BookingStatusBadge)
                 ├──→ filter.ts(无,filter 不依赖状态模型)
                 └──→ schedule-grid-card.tsx(ScheduleSlot 用 STATUS_META)

date-utils.ts ───┬──→ filter.ts(applyBookingFilter)
                 ├──→ schedule-grid-card.tsx(网格窗口)
                 └──→ schedule-grid.tsx(hhmm,既有外部邻居)

shared.tsx(瘦身) ──→ status-meta.ts(BookingStatusBadge 用 STATUS_META)
```

- `status-meta.ts` 和 `date-utils.ts` 是叶子(不 import 任何新模块)
- `filter.ts` 依赖 `date-utils.ts`
- `schedule-grid-card.tsx` 依赖 `status-meta.ts` + `date-utils.ts`
- `shared.tsx`(瘦身)依赖 `status-meta.ts`
- **无环** ✅(所有边单向向上指向叶子)

### 4.3 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 0 | 纯前端重构 |
| 数据库迁移 | 0 | 无 schema 变化 |
| 前端文件改动 | **10** | 新建 4(status-meta.ts/date-utils.ts/filter.ts/schedule-grid-card.tsx)+ 改 5 消费者(store-view/hq-view/my-bookings-view/shared-dialog/schedule-grid)+ shared.tsx 瘦身 |
| 新增测试类 | 0 | D3 撤销,沿用现有 view 测试 |
| 路由改动 | 0 | index.tsx/bookings-page.tsx barrel 不动 |

### 4.4 多租户影响评估
- N/A(纯前端文件挪动,无后端/数据/权限变化)

### 4.5 权限影响评估
- N/A(无 permission code / require_permission caller 变化)

### 4.6 范式对齐(呼应 plan-bookings-page-split.md)

本任务是 bookings-page-split 的延续收尾债,严格对齐其范式:
- **测试跟 view 走**(plan :91):零行为变更,现有 5 个 view 测试全绿验证 carry 正确性,不补新单测。
- **只拆分,不碰逻辑**(plan :103):纯文件挪动 + import 路径调整,不动 StoreView/HqView/MyBookingsView/ScheduleGrid 业务逻辑。
- **不越界**(plan :160):补测是独立候选 4,cast 处理是候选 8,cancel 状态机是候选 2 —— 均不在本次范围。

### 4.7 Out of Scope(明确不做)
- ❌ 给纯函数(slotTone/applyBookingFilter/isoDate)补单测(候选 4 范围,plan-bookings-page-split.md:160 明确排除)
- ❌ 处理 store-view 的 `as Booking[]` / `as Device[]` cast(候选 8 范围)
- ❌ 抽 deviceNameOf 进 store-view.tsx(单消费者但语义是显示原语,留 shared 避免孤儿)
- ❌ 拆 bookings-page.tsx barrel 或 index.tsx 三叉路由(不在本候选范围)
- ❌ 任何后端/数据/权限改动

---

## 5. Testing Decisions

- **测试金字塔**:沿用现有(零新增)
  - 前端组件测:store-view.test.tsx(6)+ my-bookings-view.test.tsx(6)+ hq-view.test.tsx(13)+ schedule-grid.test.tsx + config-dialog.test.tsx
  - 后端:无改动,init.sh 基线不回归
- **验证策略**(对齐 plan-bookings-page-split.md D4 范式):
  - 现有 vitest 全部必须全绿(零行为变更,测试不该断)
  - `npm run build` 绿
  - `npx oxlint` 0 warning
  - `npx tsc -b` 绿(尤其验证 import 路径改对)
  - `./init.sh` 全绿(后端无改动,基线不应回归)
- **覆盖率目标**:不降(无新增测试,现有覆盖不丢失)
- **边界 case**:无需新增(纯 locality)

---

## 6. 切片规划

本任务是 **wide refactor**(纯 locality 搬运,零行为变更),按 [three-tier-workflow.md](./three-tier-workflow.md) §7,wide refactor 走 **EP3 单入口 + expand-contract 序列**(加新形式并存 → 分批迁移 caller → 最后清理旧形式)。

### 切片 1:抽底座(status-meta.ts + date-utils.ts) ✅
- **What to build**:新建 `status-meta.ts`(4 符号)+ `date-utils.ts`(5 符号),`shared.tsx` 暂时从这两个新文件 re-export(过渡期 facade,消费者 import 路径不变)。
- **Blocked by**: 无(frontier)
- **文件清单**:新建 2 + 改 shared.tsx(加 re-export)= 3 文件
- **验证命令**:`cd frontend && npx vitest run && npm run build && npx oxlint && npx tsc -b`
- **AC**:
  - [x] `status-meta.ts` 含 STATUS_META/MUTABLE_STATUS/ACTIONABLE_STATUS/NONE,语义注释完整 ✅(4 符号齐全,4 段语义注释逐字迁移自原 shared.tsx,新增模块级 JSDoc 头)
  - [x] `date-utils.ts` 含 startOfToday/addDays/isoDate/hhmm/dayLabel ✅(5 符号齐全,3 段 JSDoc 逐字迁移,section 注释升格为模块头)
  - [x] `shared.tsx` 从两个新文件 re-export,消费者零改动 ✅(import-then-export 模式:9 符号入本地作用域供内部消费 + re-export;`git diff --stat` 仅 shared.tsx tracked 改动,5 消费者零触碰)
  - [x] vitest 全绿 + build + oxlint + tsc 全绿 ✅(vitest 65/65 pass / npm run build 绿 / oxlint 0 warning / tsc -b 干净;后端 `./init.sh full` 828 passed 零回归)

> **切片 1 完成证据(2026-07-29)**:新建 status-meta.ts(4 符号)+ date-utils.ts(5 符号),shared.tsx 删本地定义改 import+re-export facade(360→290 行,-88/+24)。expand-contract 的 expand 阶段完成,消费者零改动。/code-review 双轴 APPROVE:Standards 0 硬违反(facade 是正当过渡态)/ Spec AC1-4 全满足、无 scope creep(D3 不补测/D5 re-export 未提前删/D7 deviceNameOf 未动/§4.7 范围外符号全留 shared)。非末切片,不做 feature 收尾。下一步切片 2:抽 filter.ts + schedule-grid-card.tsx + 改 5 消费者 deep import + shared 瘦身 + D5 回源。

### 切片 2:抽组件层 + 改消费者 deep import + shared 瘦身 + D5 回源 ✅
- **What to build**:新建 `filter.ts`(4 符号)+ `schedule-grid-card.tsx`(ScheduleGridCard/ScheduleSlot/slotTone);改 5 消费者(store-view/hq-view/my-bookings-view/shared-dialog/schedule-grid)deep import 指向新文件;`fmt`/`fromDatetimeLocalValue` 回源 `@/lib/format`(4 处消费者改 import 源);`shared.tsx` 瘦身到只留 BookingStatusBadge + deviceNameOf,删除所有 re-export。
- **Blocked by**: 切片 1
- **文件清单**:新建 2 + 改 5 消费者 + 改 shared.tsx = 8 文件
- **验证命令**:`cd frontend && npx vitest run && npm run build && npx oxlint && npx tsc -b`
- **AC**:
  - [x] `filter.ts` 含 BookingFilter/FILTER_OPTIONS/FilterChips/applyBookingFilter ✅(4 符号齐全;落地为 `filter.tsx` —— FilterChips 含 JSX,TS 硬约束要求 .tsx 扩展名,内容与 plan 一致;消费者用无扩展名 `from "./filter"` 故对调用方不可见)
  - [x] `schedule-grid-card.tsx` 含 ScheduleGridCard/ScheduleSlot/slotTone ✅(3 符号逐字迁移;slotTone 归此非 badges — D6;依赖 status-meta + date-utils)
  - [x] `shared.tsx` 只剩 BookingStatusBadge + deviceNameOf(约 50-60 行),无 re-export ✅(瘦身至 38 行,2 符号,零 re-export;BookingStatusBadge 从 status-meta 取 STATUS_META)
  - [x] store-view 从 4 个文件 import(badges[shared]/filter/schedule-grid-card/@/lib/format),不再 from "./shared" 抓 ScheduleGridCard ✅(grep 确认 store-view 无已迁出符号残留)
  - [x] hq-view 从 badges[shared]/date-utils/@/lib/format import ✅
  - [x] shared-dialog 从 status-meta/@/lib/format import ✅(fromDatetimeLocalValue 合并进既有 @/lib/format import)
  - [x] schedule-grid 从 date-utils import hhmm ✅
  - [x] vitest 全绿 + build + oxlint + tsc 全绿 ✅(vitest 65/65 pass / npm run build 绿 / oxlint 0 warning / tsc -b exit 0)

> **切片 2 完成证据(2026-07-29)**:新建 filter.tsx(4 符号)+ schedule-grid-card.tsx(3 符号),5 消费者改 deep import(D4 纯 deep import 无 barrel),fmt/fromDatetimeLocalValue 回源 @/lib/format(D5,shared-dialog 合并进既有 import),shared.tsx 瘦身 290→38 行(-252 行,零 re-export,只剩 BookingStatusBadge + deviceNameOf — D2/D7)。expand-contract 的 contract 阶段完成。/code-review 双轴 APPROVE:Standards 0 硬违反(Divergent Change 已消解,提取逐字搬移无逻辑漂移,新文件注释风格对齐切片 1 sibling)+ Spec AC1-8 全满足、决策 D2/D4/D5/D6/D7 全遵守、§4.7 范围外项全未碰(无新单测/无 cast 处理/无状态机改动)、唯一偏差 filter.ts→filter.tsx 是 TS 硬约束必要偏差。非末切片(后接切片 3 末切片),不做 feature 收尾。

### 切片 3:收尾验证 + feature passing
- **What to build**:无新源码,纯验证 + 文档收尾。
- **Blocked by**: 切片 2
- **文件清单**:0 源码 + 文档(feature_list.json evidence + progress.md 更新)
- **验证命令**:`./init.sh full`(全量后端)+ `cd frontend && npm run build`(前端构建)
- **AC**:
  - [ ] `./init.sh full` 全绿(后端基线无回归)
  - [ ] `cd frontend && npm run build` 绿
  - [ ] feature_list.json status → passing,evidence 写齐
  - [ ] progress.md 顶部「最高优先级未完成」更新
  - [ ] 跑 `./scripts/sync-active-features.sh` 刷新 active 视图
  - [ ] 对照 progress.md:1934 候选描述,确认 ScheduleGridCard smell 已消解

---

## 7. 验证清单(收尾对照 [clean-state-checklist.md](../clean-state-checklist.md))

- [ ] WIP=1:本任务是当前唯一 in_progress(收尾时确认)
- [ ] 零行为变更:vitest 全绿 + build chunk 大小与拆分前一致
- [ ] 无新 TODO/FIXME(基线 2 处 Logto 占位不变)
- [ ] import 路径全部正确(tsc -b 绿)
- [ ] feature status passing 证据齐全(evidence)
- [ ] sync-active-features.sh 刷新
- [ ] progress.md:1934 候选描述消解确认
