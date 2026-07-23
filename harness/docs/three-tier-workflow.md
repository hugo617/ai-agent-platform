# 三层入口工作流(EP1 / EP2 / EP3)

> 这份文档定义本项目的「任务怎么从想法走到上线」——把单线流程拆成**三个显式入口**,每层有清晰的 skill 串、产物、跨会话策略。
> 它是对 [`harness-router`](../../.agents/skills/harness-router/SKILL.md) SKILL 的「整层编排」补充(router 回答「下一步调哪个 skill」,本文档回答「我在哪一层、这层完整流程是什么」)。
>
> 配套:[`task-workflow.md`](./task-workflow.md)(状态机 / WIP=1)、[`prd-template.md`](./prd-template.md)(单 feature PRD 模板)。

---

## §0. 一句话

三层 = **EP1 大方向→多任务** / **EP2 大任务→全切片** / **EP3 切片→实施→提交**。

三类任务**不走完整三层**(见 §7 例外旁路):wide refactor、bug、小改动。

---

## §1. 三层速查表

| 层 | 输入 | skill 串 | 产物 | 跨会话策略 | 入口判定 |
|---|---|---|---|---|---|
| **EP1** | 一个大方向(如"设备管理系列") | `/grill-with-docs` → `/to-spec` | `plan-<series>-overview.md` + feature_list.json 登记 N 条 `not_started` | **可独立结束会话** | plan 文档不存在 + 用户描述的是"系列/多任务" |
| **EP2** | 一个已登记的大任务 | `/grill-with-docs` → `/to-spec` → `/to-tickets` | `plan-<feature>.md` 含「实施切片」段(齐 0/1/N 片) | ⚠️ **必须一个回环内完成**(context>60% 用 `/handoff` 换 session 继续) | feature 的 plan 文档**无**「实施切片」段 |
| **EP3** | 一个已拆切片的 feature | `/implement` → `/code-review` → 勾 checklist → commit + evidence | 代码 + plan checklist 勾选 + feature evidence | **可跨多会话**(每切片一个 fresh context) | feature 的 plan 文档**有**「实施切片」段且 checklist 有未勾项 |

> **入口怎么判断**:读该 feature 的 plan 文档(`harness/docs/plan-<feature>.md`)有无「实施切片」章节 + checklist 有无未勾项。这是 harness-router 状态路由表「是否已拆切片」列的判定规则。

---

## §2. EP1:大方向 → 多任务

**做什么**:把一个模糊的大方向(如"设备管理系列"、"权限重构")拆成 N 个可执行的大任务(feature),登记进 feature_list.json。

**skill 串**:
1. `/grill-with-docs` —— 烤清大方向的边界、子任务、依赖拓扑(有 codebase 时用;无 codebase 用 `/grill-me`)
2. `/to-spec` —— 把共识落成 overview 文档:`harness/docs/plan-<series>-overview.md`

**产物**:
- `plan-<series>-overview.md` —— 含:背景/痛点、子任务清单(顺序/id/priority/范围/**depends_on**/plan 文档路径)、依赖关系图、系列边界
- `feature_list.json` —— 登记 N 条 `not_started` feature(每条 `depends_on` 指向同系列前置任务;`plan` 字段暂可留空,EP2 拆切片时再回填)

**跨会话策略**:**可独立结束会话**。EP1 产出后,会话可就此结束;下次会话从 EP2 接。

**overview 不写持续进度段**:子任务清单记 id + depends_on 即可;**进度段只在系列收官时写一次**(见 §5 规则 ④)。进行中的系列,进度信息看 progress.md 顶部摘要。

**范例**:
- [plan-permission-redesign-overview.md](./plan-permission-redesign-overview.md) —— 4 任务串行/并行,收官有进度段
- [plan-mvp-completion-overview.md](./plan-mvp-completion-overview.md) —— 12 缺口按梯队,含 ASCII 依赖图

---

## §3. EP2:大任务 → 全部切片

**做什么**:把一个大任务(feature)拆成 N 个 tracer-bullet 垂直切片(每片切穿 schema→API→UI→test 全栈,单片可独立验证)。

**skill 串**(⚠️ **三步必须一个回环内完成**,见下文硬约束):
1. `/grill-with-docs` —— 烤清这个 feature 的需求边界
2. `/to-spec` —— 落 PRD 到 `plan-<feature>.md`(参考 [`prd-template.md`](./prd-template.md) 完整模板)
3. `/to-tickets` —— 产齐「实施切片」段:每片含 `### 切片 NN — 标题` + **Blocked by** + **What it delivers** + **Acceptance criteria**(`- [ ]` checklist)

**产物**:`plan-<feature>.md` 含完整的「实施切片」段(切片依赖图 + 每片 acceptance criteria checklist)。同时**回填 feature_list.json 的 `plan` 字段**指向该文档(让"是否进入过 EP2"可判)。

### ⚠️ 硬约束:一个回环内完成

grill → to-spec → to-tickets 三步基于**同一套思考**,必须在一个连续 context window 里跑完。

**中途 context 接近 60%** → 立刻 `/handoff` 换新 session **继续同一回环**(不是开新方向),并在 progress.md 顶部记录断点:

```
- **当前 EP2 回环**:<feature-id>(grill ✅ 共识X → to-spec ⏳ 中断于 Y)
```

新会话 agent 读到这行,从断点接(不重跑 grill)。**别在阶段中途 compact** —— agent 会迷路。

### EP2 完成定义

plan 文档的「实施切片」段**齐全**(含 0/1/N 个切片):
- **0 切片**(feature 太简单,无需切片)→ EP2 产物就是 plan 主体本身,EP3 读 plan 主体实施
- **1 切片** → 仍走 EP3 入口实施(**保持入口一致性**,不在 EP2 会话里直接 implement)
- **N 切片** → 正常情况

> 即:**EP2 只产切片规划,不含实施**。实施一律走 EP3。

### EP2 收尾:plan 自检(进 EP3 前的轻量 gate)

EP2 产出 N 个切片后、正式进 EP3 实施前,跑一次**轻量自检**(防止规划缺陷拖到实施期才暴露,返工成本高):

- [ ] **切片依赖图无环**:每个切片的 `Blocked by` 指向更早的切片,不存在循环依赖
- [ ] **每片有 acceptance criteria**:每片至少有 1 条 `- [ ]` 可执行检查(文件级或行为级)
- [ ] **首片可立即开工**:至少存在 1 个 `Blocked by: 无` 的切片(frontier)
- [ ] **plan 主体决策已落定**:PRD 段(Problem/Solution/Implementation Decisions)无 `TODO`/`待定` 悬空项

自检不过 → 回到 `/to-tickets` 补齐,不要带病进 EP3。自检通过 → 回填 feature_list.json 的 `plan` 字段指向本文档;`status` 按 §5 规则:**依赖满足(当前 frontier)置 `in_progress`,依赖未满足(排队)保持 `not_started` + plan 已填**。

---

## §4. EP3:切片 → 实施 → 提交

**做什么**:挨个挑切片,实施 → 审查 → 提交。每个切片一个 fresh context。

**skill 串**:
1. `/implement` —— 实施单个切片(内部驱动 `/tdd` 红绿循环)
2. `/code-review` —— 双轴评审(Standards + Spec)
3. **勾 plan checklist**(见下文切片完成动作)
4. commit + 填 evidence

**跨会话策略**:**可跨多会话**(`/to-tickets` 明示 "clearing context between tickets")。切片边界天然是断点;切片中途 context 满 → 先完成当前切片再切会话,若无法完成用 `/handoff` 并注明"切片 NN 做到哪步"。

### 从哪个切片开始:frontier 规则

读 plan 文档的**切片依赖图**,选 **frontier 切片**(所有 blocker 切片已完成的第一个)。例:
```
01 ✅ ──┬─→ 02 ✅ ──┐
        ├─→ 03 ✅ ──┤
        └─→ 04 ⏳ ──┴→ 05 ⬜ → 06 ⬜
```
frontier = 切片 05(其 blocker 切片 02/03/04 中,04 是最后一个完成的)。

### 切片完成动作(勾 checklist,强制)

`/code-review` 通过后、**commit 前**,agent 把该切片 acceptance criteria 的所有 `- [ ]` 改成 `- [x]`,**证据挂在切片标题行**(不每行重复 PR 号):

```markdown
### 切片 01 — 后端地基:Device 表 + 软删租户隔离 CRUD ✅ PR #90 commit fbbee29

- [x] `app/models/device.py`:`Device` ORM model(...)
- [x] alembic 迁移:...
```

> 这一条由 [`clean-state-checklist.md`](../clean-state-checklist.md) 第 9 项强制:不勾不算干净状态。

### 末切片 = feature 收尾仪式(硬规则)

当 plan checklist 的**最后一个切片**(通常是整合验证切片,如 devices-crud-ui 的切片 07)勾选时,**强制执行 feature 收尾**:

1. `./init.sh` 全绿(ruff + pytest)
2. 完整验证:`alembic upgrade head && alembic check` + `cd frontend && npm run build` + `npx oxlint`
3. `feature_list.json`:`status` 改 `passing` + `evidence` 字段写实测结果
4. `./scripts/sync-active-features.sh` 刷新 active 视图
5. `progress.md` 加 Session 记录 + 更新「当前最高优先级未完成功能」
6. 文档影响评估(4 行格式,见 [`doc-impact-assessment.md`](./doc-impact-assessment.md))
7. **依赖解锁扫描**(防下游 feature 卡在错误的 not_started):扫描 feature_list.json,凡 `depends_on` 指向**本 feature** 且 EP2 已完成(`plan` 字段已填)的下游 feature,其依赖现已满足 → 按 §5 规则置 `in_progress`(当前新 frontier)。例:devices-crud-ui 收尾 passing 后,device-booking(EP2 已完成 + depends_on=devices-crud-ui)应立即从 not_started 翻 in_progress。

> 这 7 条 = [`task-workflow.md`](./task-workflow.md) §3「完成定义 4 条」的展开。**第 7 步是依赖链自动推进的关键** —— 漏跑会导致下游 feature 的 status 字段与实际「已可实施」状态脱节,新会话 agent 误判"还没轮到"。

---

## §5. 切片状态真相源规则(四层,各司其职)

| 层级 | 真相源 | 状态字段 | 维护时机 |
|---|---|---|---|
| 切片级 | **plan 文档 checklist**(`plan-<feature>.md` 的「实施切片」段) | `- [ ]` / `- [x]` + 标题行 `✅ PR #NN` | `/code-review` 通过后、commit 前(强制,clean-state 第 9 项) |
| feature 级 | **feature_list.json** 的 `status` | `not_started` / `in_progress` / `passing` | **EP2 完成 + 依赖满足(当前 frontier)→ `in_progress`**;EP2 完成但依赖未满足(排队)→ `not_started` + `plan` 字段已填;全切片完才 `passing` |
| 会话级 | **progress.md** 顶部摘要 + Session 记录 | 自由文本(`切片 01 ✅ PR#90 / 切片 04 ⏳`)| agent 做 Session 记录时同步(**手维护,非脚本派生**) |
| 系列级 | **overview 文档** 的「系列状态」段 | `✅ 全部完成` | **只在系列收官时写一次**(进行中不写) |

### 关键规则

1. **plan checklist 是切片级唯一结构化真相源**。git log 是辅助取证(PR 号/commit hash 从这取),但不替代 checklist。
2. **多切片 feature EP2 完成且依赖已满足 → `in_progress`**(不是 `not_started`)。理由:`not_started` 表示"连规划都没做",会让新会话 agent 误判"没开始"从而重跑 EP2 grill——这正是本工作流要防的。规则:
   - **EP2 完成 + 所有 `depends_on` 已 `passing`**(= 当前 frontier)→ 置 `in_progress`
   - **EP2 完成但依赖未满足**(排队等着,如 device-booking 等 devices-crud-ui 收官)→ 保持 `not_started`,但靠 `plan` 字段已填区分「已规划待实施」vs「未规划」(plan 字段为空 = 未规划)
   - 这样既守 WIP=1(同时只有一个 in_progress),又让 feature_list.json 能区分三种态:未规划(not_started + plan 空)/ 已规划待实施(not_started + plan 已填)/ 进行中(in_progress)
3. **progress.md 顶部摘要是手维护**(由 agent 在 Session 记录时同步)。注意:**`scripts/sync-active-features.sh` 不碰 progress.md**(它只生成 active.json + archive.json),所以不存在"派生"机制,必须人手对齐 plan checklist。
4. **overview 进度段只在系列收官写**。进行中的系列,进度看 progress.md 顶部摘要;overview 只在最后一个 feature passing 时追加「系列状态:✅ 全部完成」段(范例见 [plan-permission-redesign-overview.md](./plan-permission-redesign-overview.md) 末尾)。
5. **切片跨 feature 引用约定**:用 `<feature-id>#NN` 格式(如 `devices-crud-ui#04`)。切片本身无独立 id,沿用「切片 NN」序数。

### 现状债警示

> ⚠️ 本规则建立前,plan-devices-crud-ui.md 的 64 个 checklist 曾全未勾选(切片 01-04 已合并 main),feature_list.json 里 devices-crud-ui 曾长期 `not_started`。本规则 + clean-state 第 9 项 + 一次性回填(见 §9)共同修复此债。**落地后 2 周回看**:抽查任一进行中多切片 feature 的 plan checklist,勾选状态应与 git log 一致。

---

## §6. EP1 → EP2:挑哪个大任务

EP1 产出 N 条 `not_started` feature 后,EP2 要挑一个拆切片。**决策规则**:

读 `feature_list.json`,选**所有 `depends_on` 已 `passing` 的最高 priority `not_started` feature**。

- device 系列:`device-models-crud`(61)✅ → `devices-crud-ui`(62)→ `device-booking`(63)→ `device-poweron`(64),严格串行(depends_on 链)
- permission 系列:任务 2/3 可并行(depends_on 都指向任务 1),WIP=1 下仍顺序执行

> 对齐 [`AGENTS.md`](../../AGENTS.md) 开工流程第 3 步「选优先级最高的 not_started 功能」。

---

## §7. 例外任务旁路(不走完整三层)

| 任务类型 | 入口 | 说明 |
|---|---|---|
| **wide refactor**(重命名列 / 改共享类型签名) | EP3 单入口 | `/to-tickets` 产 **expand-contract 序列**(非 tracer-bullet 切片),写成 plan 的「实施批次」章(加新形式并存 → 分批迁移 caller → 最后删旧)。批次完成同样勾 checklist。详见 [`prd-template.md`](./prd-template.md) §2.2 |
| **bug** | 独立旁路 | `/diagnosing-bugs`(系统根因 + 复现 + 回归测试),走 [`bug-tracking.md`](./bug-tracking.md) 的 5 态状态机(reported→...→closed),**不进三层**。plan 用 bug 简化模板 |
| **小改动**(1-2 文件,无 schema 变化) | 直接 EP3 | plan 用 [`task-workflow.md`](./task-workflow.md) §5 附录 A 简单模板,无切片,直接 `/implement` |

---

## §8. 与现有文档的关系(不重复)

| 文档 | 角色 | 本文不重复它的 |
|---|---|---|
| [`task-workflow.md`](./task-workflow.md) | 任务管理规则(状态机 / WIP=1 / 完成定义 / 收尾清单) | 状态机四态、WIP=1 定义、收尾清单 |
| [`prd-template.md`](./prd-template.md) | 单 feature 的 PRD/切片 Design 模板 | PRD 11 节模板、切片字段、对抗式审查段 |
| [`harness-router`](../../.agents/skills/harness-router/SKILL.md) SKILL | 单步状态路由(迷茫时用) | 「下一步调哪个 skill」的单步推荐 |
| **本文档** | **三层编排**(整层流程 + 当前在哪层 + 跨会话策略) | 三层入口定义、EP2 单回环约束、切片状态四层真相源 |

> 一句话区分:task-workflow = "状态机规则";prd-template = "单 feature 怎么写";harness-router = "单步去哪";**本文档 = "整层流程 + 我在哪层"**。

---

## §9. 落地后回看(自检项,审查 E14 要求)

本工作流的价值不在"文档建好",而在"真让用户少走弯路"。落地 2 周后回看:

- [ ] **勾选机制真被用**:抽查任一进行中多切片 feature 的 plan checklist,勾选状态与 git log 一致(无"切片已合并但 checklist 全未勾"的塌方)
- [ ] **状态恢复真生效**:新会话 agent 开工,对已开工的多切片 feature 不再重跑 EP2 grill(读 `in_progress` + progress 顶部摘要即知做到哪)
- [ ] **EP2 单回环真守住**:EP2 中断时有 progress 顶部断点记录,新会话从断点接而非重跑

**一次性现状债回填**(本次落地同步做,非持续维护):
- `plan-devices-crud-ui.md`:切片 01-04 的 acceptance criteria 勾 `- [x]` + 标题追加 `✅ PR #90/#92/#93/#94 commit fbbee29/2043dec/9ac9ac4/125ad2b`
- `feature_list.json` + `feature_list.active.json`:`devices-crud-ui` status `not_started` → `in_progress`,evidence 补切片 01-04 PR 链接
- `progress.md` 顶部摘要:修正"切片 04 待做" → "切片 04 ✅ PR #94"
- 跑 `./scripts/sync-active-features.sh` 刷新 active 视图
