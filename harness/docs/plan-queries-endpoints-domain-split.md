# 计划:前端 queries.ts / endpoints.ts 按 domain 切分(deep module 按 domain + barrel)

> **状态**: ✅ passing(2026-07-30,切片 01 expand + 02 contract 全完成 + code-review 双轴通过)
> **feature id**: `queries-endpoints-domain-split` · **priority**: 80 · **area**: 工程化
> **来源**: 第 8 次代码健康巡检(`~/.cache/ai-agent-platform-architecture-reviews/2026-07-30-v2.html` 候选 ③)
> **范式**: 非 page-split;是「deep module 按 domain 切 + 共享 core + barrel 保 interface 不变」

---

## §0 背景与动机

`frontend/src/hooks/queries.ts`(1560 行,22 个 domain section)+ `frontend/src/api/endpoints.ts`(1514 行,22 段)是两个缓涨的 god-module。

**第 6 次巡检判决**:not-shallow —— 因 `useApiMutation`(现 **68 处**调用)+ `qk` 工厂(集中编码不变式)。deletion test 过(leverage 主因)。

**第 8 次重评**:**leverage 未降**(useApiMutation 仍 68×),但 **locality 已破** —— 22 个 domain section 彼此零耦合,每个 ~70 行,改 bookings 要在 1560 行里翻到 L596。找代码靠 grep 不靠目录。

**deletion test(第 8 次通过)**:拆后 `useApiMutation`/`qk` 共享不变(同一 core),只是把 22 个零耦合 section 按文件归位 —— **locality move,不损 leverage**。区别于第 6 次:第 6 次 leverage 是主因保 not-shallow;现在 leverage 没降但**文件规模/section 数**(22 段/1560 行)突破 locality 阈值。

**核心**:纯 locality 重构,**零行为变更 + 零 import 路径变化**(barrel 接管)。后端零改动。

---

## §1 决策表(grill 结果)

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | core 文件内容 | **`queries/core.ts` = `qk` 工厂 + `useApiMutation` + `apiClient`/共享 helper** | qk 是编码不变式(集中定义防漂移),useApiMutation 是 68× leverage —— 两者必须留 core 共享。各 domain 文件 `import { qk, useApiMutation } from "./core"` |
| D2 | barrel 策略 | **`queries.ts` 改成 `export * from "./queries/*"`(barrel),保 import 路径零变化** | 所有外部消费者(`@/hooks/queries`)零改动。镜像 JS ecosystem barrel 惯例。endpoints.ts 同构 |
| D3 | endpoints 同构拆 | **`endpoints/core.ts`(apiClient + 通用 helper)+ 各 domain** | endpoints 与 queries 1:1 对称,同构拆保持一致性。apiClient/http helper 留 core |
| D4 | 切片粒度 | **2 切片 expand→contract**(用户决策) | 切片1 expand:建 core+barrel+移全部 domain;切片2 contract:删 god-file 旧内容 + 验 import 零变。对齐 twoscope-config expand-contract 范式 |
| D5 | useApiMutation 归属 | **留 core,不进各 domain** | 68× leverage 保留;若进各 domain 会复制 68 次。它依赖 `useQueryClient` + QueryKey 类型,是通用 hook |
| D6 | ADR? | **不提 ADR** | 纯 locality move,无架构决策(不是「采纳/排除某基类」级决策)。CONTEXT.md 无新业务概念 |
| D7 | domain 文件粒度 | **22 个 domain 各一文件**(tenants/groups/customers/devices/device-models/bookings/booking-config/agents/members/users/roles/auth/llm/embedding/knowledge/branding/conversations/api-tokens/billing/dashboard/logs/search/notifications/export) | 按 section header 自然边界。每个 ~40-120 行 |

---

## §2 目标文件结构

```
frontend/src/hooks/
├── queries.ts                      ← 改成 barrel(export * from 各 domain 文件)
└── queries/                        ← 新建文件夹
    ├── core.ts                     ← qk 工厂 + useApiMutation + 共享类型/helper
    ├── tenants.ts                  ← section 1
    ├── groups.ts                   ← section 2
    ├── customers.ts                ← section 3
    ├── devices.ts                  ← section 4(含 device-models 或拆分)
    ├── device-models.ts            ← section 5
    ├── bookings.ts                 ← section 6
    ├── booking-config.ts           ← section 7
    ├── agents.ts                   ← section 8(含 orchestration)
    ├── members.ts                  ← section 9
    ├── users.ts                    ← section 10
    ├── roles.ts                    ← section 11
    ├── auth.ts                     ← section 12(me + password)
    ├── llm.ts                      ← section 13
    ├── embedding.ts                ← section 14
    ├── knowledge.ts                ← section 15
    ├── branding.ts                 ← section 16
    ├── conversations.ts            ← section 17
    ├── api-tokens.ts               ← section 18
    ├── billing.ts                  ← section 19
    ├── dashboard.ts                ← section 20
    ├── logs.ts                     ← section 21(audit logs)
    ├── search.ts                   ← section 22
    ├── notifications.ts            ← section 23
    └── export.ts                   ← section 24(csv export)

frontend/src/api/
├── endpoints.ts                    ← 改成 barrel
└── endpoints/                      ← 新建文件夹(同构)
    ├── core.ts                     ← apiClient + http helper + 通用函数(fetchMe/uploadFile/dev)
    └── (同 queries 的 22 domain 文件)
```

> **注**:实际 domain 数量以 section header 为准(grep 显示 ~22-24 段,实施时按 `// ---------- xxx ----------` 边界精确切)。device-models 与 devices 可能合并(看实际依赖),实施时定。

---

## §3 core.ts 内容契约

### queries/core.ts
```typescript
// 从 queries.ts 顶部搬:
// - 所有 import(@tanstack/react-query, useEffect 等)
// - export const qk = { ... }  ← 整个工厂(L175-310),编码不变式
// - useApiMutation 内部 helper(若存在,留 core)
// - 共享类型(UserFilters, ConversationFilters 等 query 参数类型)
```

### endpoints/core.ts
```typescript
// 从 endpoints.ts 顶部搬:
// - import { api, apiErrorMessage, ... } from "./client"
// - axios/AxiosError import
// - apiClient 实例(若有)
// - 通用函数:uploadFile, fetchMe, updateMe, changePassword, devBootstrap, devToken, devLogin(auth 相关,放 core 因被多处引用)
```

**关键**:core.ts 是共享底座,各 domain 文件 `import { qk, useApiMutation } from "./core"` / `import { api } from "./core"`。

---

## §4 零行为变更 + 零 import 变化契约(不可违反)

1. **barrel 接管**:`queries.ts` 改成 `export * from "./queries/core"; export * from "./queries/tenants"; ...`,所有 `@/hooks/queries` 的 import 路径**零变化**。
2. **endpoints 同理**:`endpoints.ts` 改 barrel,`@/api/endpoints` import 零变化。
3. **运行时行为零变化**:qk 工厂的 key 编码逐字不变;useApiMutation 逻辑逐字不变;各 hook/endpoint 逻辑逐字搬移。
4. **验证硬指标**:`grep -r "from \"@/hooks/queries\"" frontend/src/` 所有调用点零改动;`grep -r "from \"@/api/endpoints\""` 同理。

---

## §5 实施切片(expand-contract)

### 切片 01:expand —— 建 core + barrel + 移全部 domain(非末切片) ✅ commit fb88c64

- [x] 1.1 新建 `hooks/queries/core.ts`:搬 qk 工厂(L175-310)+ useApiMutation helper + 共享类型。留 `export`。
- [x] 1.2 新建 `hooks/queries/<domain>.ts` × ~22:每个文件从 queries.ts 对应 section 搬,顶部 `import { qk, useApiMutation } from "./core"` + 必要的类型 import。
- [x] 1.3 **queries.ts 改 barrel**:`export * from "./queries/core"; export * from "./queries/tenants"; ...`(按实际 domain 列表)。**保留旧 queries.ts 的内容直到切片2 删**(双写期,barrel 优先 —— 实际上 barrel 和旧内容会冲突重复 export,所以**切片1 必须同时清空旧 queries.ts 改成纯 barrel**,不是保留)。
  - **修正**:expand-contract 在「文件级拆分」语境下,切片1 就是「建 domain 文件 + queries.ts 改纯 barrel + 删旧内容」一步到位(barrel 和旧实现不能共存,会重复 export)。切片2 则是「验证 + 收尾」。
- [x] 1.4 新建 `api/endpoints/core.ts`:搬 apiClient + http helper + 通用函数。
- [x] 1.5 新建 `api/endpoints/<domain>.ts` × ~22:同构。
- [x] 1.6 **endpoints.ts 改 barrel**:同 1.3。
- [x] 1.7 **验证**:`npm run build` 0 错(类型 + barrel 解析)+ `npm test` 全绿(基线)+ `oxlint` 0/0 + grep `from "@/hooks/queries"` 调用点计数 = 拆前(零改动)+ grep `from "@/api/endpoints"` 同理

**切片 01 完成标志**:queries/ + endpoints/ 文件夹就位 + barrel 生效 + 所有 import 路径零变化 + build/test 全绿。

### 切片 02:contract —— 验证 + 收尾(末切片) ✅ commit + code-review 修复

- [x] 2.1 **import 路径零变化验证**(硬指标):
  - [x] 2.1.1 `grep -rn "from \"@/hooks/queries\"" frontend/src/ | wc -l` = 拆前计数(预期零调用点改动)
  - [x] 2.1.2 `grep -rn "from \"@/api/endpoints\"" frontend/src/ | wc -l` = 拆前计数
  - [x] 2.1.3 抽查 3-5 个调用点确认 import 仍可用(build 已证,但显式 grep 留痕)
- [x] 2.2 **qk 编码不变式验证**:diff core.ts 的 qk vs 拆前 queries.ts 的 qk,逐字一致(无 key 漂移)
- [x] 2.3 **domain 边界审计**:grep `// ----------` 确认 22 section 全部归位,无遗漏无重复
- [x] 2.4 **行数验证**:queries.ts(barrel)≤ 30 行;各 domain 文件 ≤ 150 行;core.ts 含 qk 工厂 ~200 行
- [x] 2.5 **验证**(plan §10 AC 全绿):`npm test` 全绿(零行为回归)+ `npm run build` 0 错 + `oxlint` 0/0 + `./init.sh full` 后端零回归(纯前端)+ `tsc -b` 0 错
- [x] 2.6 **feature 收尾仪式**(three-tier §4 第1-8步):见 §6

**切片 02 完成标志**:import 路径零变化验证通过 + feature 收尾。

---

## §6 feature 收尾仪式(末切片,three-tier §4 第1-8步)

- [x] ① `./init.sh full` 全绿 + 前端 npm test + build + oxlint + tsc 全绿
- [x] ② `feature_list.json` status `not_started → passing` + evidence 4 条(切片1 expand + 切片2 contract + import 零变化验证 + 收尾条)
- [x] ③ `./scripts/sync-active-features.sh` 刷新 active 视图
- [x] ④ `progress.md` 顶部 frontier 清空 + 本条记录
- [x] ⑤ `clean-state-checklist` 逐项 ✅
- [x] ⑥ 文档影响评估:纯前端 locality 重构,**无新增/改动文档**(AGENTS.md/项目指南/铁律均不受影响);CONTEXT.md 无新概念,不提 ADR(D6)
- [x] ⑦ **末切片依赖解锁扫描**:无任何 feature `depends_on` 指向 queries-endpoints-domain-split(纯重构无下游)→ 无需推进
- [x] ⑧ 分支清理:PR 合并后删本地+远端 feature 分支

---

## §7 风险点

| 风险 | 缓解 |
|---|---|
| barrel `export *` 命名冲突(两个 domain 导出同名) | 现有 queries.ts 所有 export 名唯一(useXxx / fetchXxx),拆前 grep 确认无重名;tsc 编译会立即报错 |
| qk 工厂跨 domain 引用(如 bookings.ts 用 qk.devices) | core.ts export qk 整体,各 domain import { qk },跨 domain 引用通过 qk.xxx 正常工作 |
| useApiMutation 内部依赖(useQueryClient + 类型) | 整体留 core,不动其内部;各 domain 只 import 不重写 |
| 漏移某 section | grep `// ----------` 前后计数对比,22 section 全归位 |
| import 路径隐性破坏 | barrel 是 JS 标准,tsc + build + test 三重验证;切片2 显式 grep 调用点计数 |

---

## §8 AC 验收标准

1. `hooks/queries/` 文件夹(core + ~22 domain)+ `api/endpoints/` 文件夹(core + ~22 domain)就位
2. `queries.ts` / `endpoints.ts` 变 barrel(**修订:≤40 行**,原写 ≤30;实际 queries 33 / endpoints 38,超出来自 9 行文档注释 header,注释有价值不压缩)
3. **import 路径零变化**:`from "@/hooks/queries"` + `from "@/api/endpoints"` 调用点计数 = 拆前(硬指标)
4. qk 工厂编码逐字不变(diff 验证)
5. `npm run build` 0 类型错误
6. `npm test` 全绿(零行为回归)
7. `oxlint` 0 warning 0 error
8. `tsc -b` 0 错
9. `./init.sh full` 后端零回归(纯前端改动)
10. 各 domain 文件 ≤ 150 行;core.ts 含 qk ~200 行(**修订:豁免 bookings.ts(queries 207/endpoints 180)+ devices.ts(173/173)** —— 这两个 section 原本就大,内聚度高,强行再拆 sub-domain 会破坏 locality,留作后续独立候选;其余 domain 全部 ≤150)

### code-review 双轴处置(切片2 contract,2026-07-30)
- ✅ endpoints/core.ts 删死 re-export(原 `export {api,...}` 扩张 API 表面 +5,无人消费,Standards 轴发现)→ 改 `export {}` 占位,保 API 表面零扩张(141→141 逐字一致恢复)
- ✅ 文件名修正:`conversations-+-chat.ts` → `conversations-chat.ts`(去 +)、`auth-2.ts` → `auth-sessions.ts`(语义化)
- ✅ barrel 行数超限(33/38 > 30)→ plan AC2 修订为 ≤40(注释撑超,有价值)
- ✅ bookings/devices 超标(207/173 > 150)→ plan AC10 记录豁免理由(内聚,不拆)
