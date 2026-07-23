---
name: harness-router
description: 任务状态路由器 —— 告诉你下一步该调哪个 skill。当任务发生变化（新任务、需求清楚了、PRD 写完了、实施做完了、出现 bug、context 快满了）而你不确定该调哪个 skill 时用。用户键入 /harness-router 触发；agent 自动触发请看 AGENTS.md 的「自动触发规则」路由表。
disable-model-invocation: true
---

# Harness Router

> 本项目的 skill 路由器。**用户迷茫时手动求助的路由器**(不是 agent 自动调度器 —— agent 自动触发靠 AGENTS.md 的「自动触发规则」路由表,这是硬触发)。
>
> `disable-model-invocation: true` 意味着**只能由用户键入 `/harness-router` 调用**,agent 不会自动触发。若未来需要 agent 自动路由,去掉此 flag 即可。

## 入口 A:项目方向探索(不知道做什么时用)

用户说「探索下一步」「项目还能做什么」「给关键词」时走这条路。**读项目数据 → 输出 3 类选项 → 选后给可复制提示词**。

> 🔑 **触发词 `hugo`**:用户键入 `hugo`(单独一个词,无业务语义)是本入口的**硬触发暗号**。收到 `hugo` → **立即执行下方 4 步流程,不得追问语义、不得询问"hugo 指什么"**。`hugo` 纯粹是"跑一遍探索流程"的信号词,本身不代表任何业务方向。用户若给其他关键词(如「排期」「导出」),同样触发流程,但可从该关键词切入定位相关选项。

### 探索流程(4 步)

**第 1 步:读数据**(并行读 3 个源)
- `feature_list.json` —— 扫活跃任务(`in_progress`/`not_started`),提取 id/status/depends_on/plan 字段
- `harness/docs/plan-mvp-completion-overview.md` —— 扫 12 个 MVP backlog 缺口(三梯队:SaaS 体面/配套/V2),提取 priority/现状/依赖
- `progress.md` 顶部摘要 —— 确认当前 frontier(谁在 in_progress、卡在哪)

**第 2 步:分类输出选项**(3 类,用表格)

| 类别 | 条件 | 数据来源 |
|---|---|---|
| **① 添加新开发任务**(EP1) | 用户给关键词,或从 backlog 选 | MVP backlog 12 缺口 + 现场关键词 |
| **② 对未拆切片的任务拆切片**(EP2) | feature 状态 `not_started` + plan 字段为空 | feature_list.json 扫「未拆」 |
| **③ 完成某任务的切片**(EP3) | feature 状态 `in_progress`/`not_started` + plan 已填 + checklist 有未勾 | feature_list.json + plan 文档 |

**第 3 步:用户选** —— 用户挑一个(或给新关键词现场拆)。**触发词 `hugo` 或无匹配关键词时**:不得追问,直接把 3 类选项完整列出(① 含 backlog 全量 + 现场 grill 选项),让用户从全局挑。若用户给的关键词在 backlog 找不到匹配,转现场 `/grill-with-docs` 拆新方向(EP1)。

**第 4 步:输出可复制提示词** —— 按选定类别,套用下方模板,输出「复制到新会话」的完整提示词块。

### 提示词模板(3 类,套用即出)

**① EP1 新任务**(用户选了 backlog 缺口,如「数据导出」):
```
针对"<关键词/缺口名>"启动 EP1:按 harness/docs/three-tier-workflow.md §2,
用 /grill-with-docs 烤清大方向边界,再用 /to-spec 落
harness/docs/plan-<series>-overview.md + feature_list.json 登记 N 条 not_started。
参考 MVP backlog: harness/docs/plan-mvp-completion-overview.md。
```

**② EP2 拆切片**(用户选了未拆 feature,如 device-poweron):
```
为 <feature-id> 拆分全部切片(EP2):按 three-tier-workflow.md §3,用
/grill-with-docs → /to-spec → /to-tickets 一个回环内完成,产出
harness/docs/plan-<feature>.md 的「实施切片」段。中途 context>60% 就
/handoff 换 session 继续,并在 progress.md 顶部记 EP2 断点。
先跑 three-tier §3 的 plan 自检 4 项再交付。
```

**③ EP3 做切片**(用户选了已拆 feature 的某切片,如 device-booking 切片01):
```
继续推进 <feature-id> 的切片 <NN>(<切片标题简述>)。
这是 EP3:读 harness/docs/plan-<feature>.md 的「切片 <NN>」章节,
按 acceptance criteria 实施。用 /implement 实施,完成后 /code-review,
通过后勾选 plan checklist 对应项 + 标题追加 ✅ PR 证据。
<若是末切片,补:因这是末切片,完成后执行 feature 收尾仪式
(three-tier §4 第1-7步,含依赖解锁扫描)。>
```

> 提示词里 `<尖括号>` 部分由探索器从数据填充。EP3 要判断是不是末切片(查 plan 依赖图,看后面还有没有未完成切片)。

---

## 入口 B:先确认你在哪一层(EP1 / EP2 / EP3)

本项目的任务流程分**三层入口**,先判断你在哪一层,再决定 skill 串。详见 [`harness/docs/three-tier-workflow.md`](../../../harness/docs/three-tier-workflow.md)。

| 层 | 做什么 | skill 串 | 跨会话 |
|---|---|---|---|
| **EP1** 大方向→多任务 | 一个大方向拆 N 个 feature | `/grill-with-docs` → `/to-spec`(落 overview) | 可独立结束 |
| **EP2** 大任务→全切片 | 一个 feature 拆齐 N 个切片 | `/grill-with-docs` → `/to-spec` → `/to-tickets` | ⚠️ 必须一个回环内 |
| **EP3** 切片→实施→提交 | 挨个切片实施审查提交 | `/implement` → `/code-review` → 勾 checklist | 可跨多会话 |

**例外**(不走完整三层):wide refactor(expand-contract,走 EP3 单入口)/ bug(`/diagnosing-bugs` 旁路)/ 小改动(直接 EP3)。

---

## 主流程:idea → ship

任务从想法到上线,大多数走这条主路(= EP1 → EP2 → EP3 串起来):

1. **`/grill-with-docs`** —— 烤清需求。**有 codebase 时从这里开始**:它会保留访谈成果到 `CONTEXT.md`,留下纸面轨迹。没 codebase?用 **`/grill-me`**(无状态版)。
2. **`/to-spec`** —— 把共识落成 PRD(模板见 `harness/docs/prd-template.md`)。不做访谈,综合已有线索。
3. **`/to-tickets`** —— 把 PRD 拆成 tracer-bullet 垂直切片,每片声明 blocking edges。
4. **`/implement`** —— 实施单个 ticket,内部驱动 **`/tdd`** 红绿循环。
5. **`/code-review`** —— 实施完成后双轴评审(Standards + Spec)。
6. **勾 plan checklist** + commit + 填 evidence + 改 status=passing + 更新 `progress.md`(详见 three-tier-workflow.md §4)。

**Context 卫生**:1-3 步(EP2 回环)尽量在一个连续 context window 里完成,别中途 compact/clear —— 烤清 / spec / tickets 都基于同一套思考。一旦接近 60% context,立刻 **`/handoff`** 换新 session 继续同一回环(并在 progress.md 顶部记断点),不要硬撑。

## 状态路由表(速查)

> **怎么用**:先看「是否已拆切片」列判断 EP 层级(查该 feature 的 `plan-<feature>.md` 有无「实施切片」章节 + checklist 有无未勾项),再看「当前状态」列定单步动作。

| 当前状态 | 是否已拆切片 | 推荐下一步 |
|---|---|---|
| 新建任务 / 想法模糊 + 有 codebase | plan 文档不存在 | `/grill-with-docs`(EP1 若是系列,否则 EP2) |
| 想法模糊 + 无 codebase | plan 文档不存在 | `/grill-me` |
| 需求清楚,要落 PRD | plan 主体无「实施切片」段 | `/to-spec` |
| PRD 完成,要拆切片 | plan 主体无「实施切片」段 | `/to-tickets`(**EP2 回环**,一个 context 内) |
| 要继续未完切片 | plan 有「实施切片」段 + 有未勾 `- [ ]` | `/implement`(**EP3**,从 frontier 切片开始) |
| 切片实施中 | — | `/implement`(继续当前) |
| context 接近 60% | — | `/handoff`(EP2 中断要在 progress 顶部记断点) |
| 实施完成 | — | `/code-review` → **勾 plan checklist** → commit |
| 末切片完成 | plan checklist 全勾 | **feature 收尾仪式**(见 three-tier §4)+ status=passing |
| 复杂任务评审 | — | `/code-review`(多模型投票见下文「复杂任务判定」)|
| bug 出现 | —(不走三层) | `/diagnosing-bugs`(流程见 `harness/docs/bug-tracking.md`)|
| wide refactor | expand-contract 序列 | `/to-tickets`(产批次)→ EP3 单入口 `/implement` |
| 小改动(1-2 文件) | 无切片 | 直接 `/implement`(EP3,简单 plan 模板) |
| 堆积的 issue 要分流 | — | `/triage` |
| 项目过大、迷雾 | — | `/wayfinder` |

## 分支决策(常见判断)

- **Branch — 不知道做什么?** 走**入口 A(项目方向探索)**:读项目数据 → 输出 3 类选项(新任务/拆切片/做切片)→ 选后给可复制提示词。这是「连方向都没定」时的起点。
- **Branch — 这是不是 bug?** Yes → `/diagnosing-bugs`(系统性根因 + 复现 + 回归测试),流程见 `harness/docs/bug-tracking.md`。No → 走主流程。
- **Branch — 任务能不能一次会话做完?** No(改 >10 文件 / 跨模块 / 需技术选型)→ 先 `/to-spec` 落 PRD,再 `/to-tickets` 拆切片,每片一个 context。Yes → 直接 `/implement`。
- **Branch — PRD 已经在 plan 文档里了?** Yes → 跳过 `/to-spec`,直接 `/to-tickets` 拆切片。No → 先 `/to-spec`。
- **Branch — 这次改动是不是 wide refactor(重命名列 / 改共享类型)?** Yes → 不用 tracer-bullet,用 expand–contract 序列(加新形式并存 → 分批迁移 caller → 最后删旧),详见 `/to-tickets` SKILL.md。No → 正常垂直切片。

## 复杂任务判定(用于未来多模型投票触发)

满足任一即复杂任务:
- 改动文件 >10
- 涉及鉴权 / 权限 / 数据迁移 / 跨服务调用
- plan 有 v1→v2 对抗式审查记录
- 涉及安全敏感操作(token / 密钥 / 支付)
- 涉及不可逆操作(删表 / 删列 / 改列类型)

> **多模型投票机制当前为「未来态·待试点」** —— 见 `harness/docs/multi-model-voting.md`(阶段 4 后可用)。试点通过前,复杂任务评审**仍用单模型 `/code-review` 双轴**(Standards + Spec)。机制就绪后,本路由器会在「复杂任务评审」分支自动提示「是否启动多模型投票」。

## 词汇层(underneath)

两个 model-invoked 的参考 skill,跑在其他 skill 下面,各是各自词汇的真相源:

- **`/domain-modeling`** —— 锐化项目领域语言(挑战模糊术语、消解多义词、记 ADR)。`/grill-with-docs` 驱动的就是这套。
- **`/codebase-design`** —— 深模块词汇(module / interface / depth / seam / adapter / leverage / locality),设计模块「形状」用。`/tdd` 和 `/improve-codebase-architecture` 都说它。

## 跨 session

- **`/handoff`** —— 当前 thread 满了或要分支(如切去 `/prototype` session)时,把对话压缩成 markdown 文件。不在原地继续,而是**新开 session 引用该文件**。是 context window 之间的桥。
- **`/compact`**(内建)—— 留在**同一对话**,让早期 turns 被总结。在阶段之间的**有意断点**用。别在阶段中途 compact —— agent 会迷路。

## Codebase health(非功能工作)

- **`/improve-codebase-architecture`** —— 有空时跑,保持 codebase 对 agent 友好。它找出「深模块化机会」,挑一个 _产生一个 idea_,可以带进主流程的 `/grill-with-docs`。

## 配套文档

- [`harness/docs/three-tier-workflow.md`](../../../harness/docs/three-tier-workflow.md) —— **三层入口工作流(EP1/EP2/EP3)**:整层流程定义、EP2 单回环约束、切片状态四层真相源、例外旁路
- [`harness/docs/task-workflow.md`](../../../harness/docs/task-workflow.md) —— 任务管理规则(状态机 / WIP=1 / 完成定义 / 收尾清单),含自动触发流程图
- [`harness/docs/prd-template.md`](../../../harness/docs/prd-template.md) —— PRD/切片 Design 模板
- [`harness/docs/bug-tracking.md`](../../../harness/docs/bug-tracking.md) —— Bug 管理流程
- [`harness/docs/multi-model-voting.md`](../../../harness/docs/multi-model-voting.md) —— 多模型投票机制(未来态)
- [`harness/docs/doc-impact-assessment.md`](../../../harness/docs/doc-impact-assessment.md) —— 文档影响评估(每任务完成必填)
- [`AGENTS.md`](../../../AGENTS.md) —— 项目入口(含自动触发规则路由表的硬触发版本)
