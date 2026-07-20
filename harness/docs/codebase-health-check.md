# 代码健康度巡检流程(Stage 5)

> 本文档定义本项目的「项目级代码健康度巡检」机制,对应 Harness Stage 5。
> 与 [`task-workflow.md`](./task-workflow.md)(任务级规则)和 [`/code-review`](file:///Users/star/.agents/skills/code-review/SKILL.md)(任务级评审)互补:巡检是**项目级**,review 是**任务级**。
> 范例参考首次巡检记录:见 [`codebase-health-log.md`](./codebase-health-log.md)。

---

## 1. 何时跑(定期提醒 + 人工决定)

`/improve-codebase-architecture` 是 **user-invoked** skill(`disable-model-invocation: true`),只能用户手动键入触发,不能自动跑。本文档定义「何时该考虑跑」的判定条件,由人决定。

### 1.1 定期提醒节奏

每 **10 个 feature** 完成(从 60 起算:70 / 80 / 90 ...)后,在 `progress.md` 末尾的「下一步建议」追加一行:
```
- 🔔 建议巡检:已完成 N 个 feature,可考虑跑 /improve-codebase-architecture(详见 harness/docs/codebase-health-check.md)
```

> 这是**提醒**,不是强制。人工评估是否真跑。

### 1.2 触发判定清单(满足任一则建议跑)

| 触发条件 | 怎么查 |
|---|---|
| **行数 top 10 service/api 文件平均涨幅 >20%** | `wc -l app/services/*.py app/api/v1/*.py \| sort -n \| tail -10` 与上次巡检 baseline 对比 |
| **新增 TODO/FIXME/HACK/XXX >5 处** | `grep -rE "TODO\|FIXME\|HACK\|XXX" app/ frontend/src/ \| wc -l` |
| **测试覆盖率跌破 90%**(基线 93%)| `pytest --cov=app --cov-report=term` |
| **横切文件被改 >3 处**(permission_service / token_context / deps / graph) | `git log --since=<上次巡检> --name-only \| grep -E "(permission_service\|token_context\|deps\|graph)" \| sort \| uniq -c` |
| **有意识重构前** | 人主观判断 |
| **大版本发布前** | 人主观判断 |
| **感觉代码变乱** | 人主观判断 |

### 1.3 何时不跑

- 单个 feature 刚完成,无任何 §1.2 触发条件 → 不跑(走 `/code-review` 即可)
- 紧急 bug 修复 → 不跑(走 [`bug-tracking.md`](./bug-tracking.md))
- 纯文档改动 → 不跑

---

## 2. 怎么跑(3 步对齐 skill + 本项目适配)

> 完整 skill 文档:`~/.agents/skills/improve-codebase-architecture/SKILL.md`
> 术语纪律:必须用 codebase-design 词汇(**module / interface / depth / seam / adapter / leverage / locality**),禁止漂移到 component/service/API/boundary/wrapper

### Step 0:bootstrap CONTEXT.md(首次必做,之后跳过)

若仓库根**没有** `CONTEXT.md`(纯 glossary,domain-modeling skill 维护):

1. 调 `/domain-modeling` skill
2. 从以下来源提炼核心 domain terms(不引入新词,只录现有):
   - [`项目指南/附录/术语表.md`](../../项目指南/附录/术语表.md)
   - [`AGENTS.md`](../../AGENTS.md) 铁律
   - [`项目指南/00-总览/01-项目是什么.md`](../../项目指南/00-总览/01-项目是什么.md)
3. 产 `CONTEXT.md`(根目录),格式参考 `~/.agents/skills/domain-modeling/CONTEXT-FORMAT.md`

**不预建 `docs/adr/`** —— 等 Step 3 grill 时按需 lazy 创建。

### Step 1:Explore(主 agent,Read/Grep/Bash)

> skill 假设的 `subagent_type=Explore` 是 Claude Code 原生概念。本项目 ZCode `.zcode/agents/` 只有 ship-it,**主 agent 直接用 Read/Grep/Bash 干**(本质动作:commit history + organic walk + deletion test)。

1. **读前置**:`CONTEXT.md` + `AGENTS.md` 铁律 + 任何已有 `docs/adr/`(若有)
2. **找 hot spots**:`git log --oneline -30 --name-only | grep -v '^[a-f0-9]' | sort | uniq -c | sort -n | tail -15` 看近期改动集中点
3. **organic walk**(对每个 hot spot,问 4 个问题):
   - 理解这个概念要在多少个小模块之间跳?
   - 这里是 **shallow module**(interface 几乎和 implementation 一样复杂)吗?
   - 有没有「为了可测性抽出来的纯函数,但真正的 bug 藏在 caller 处」(无 **locality**)?
   - 紧耦合模块在 **seam** 处泄漏吗?
4. **deletion test**(对任何疑似 shallow 的模块):删了它会**集中**复杂度(好的 deep 信号),还是**只是搬走**(shallow 信号)?

输出:**5-8 个候选**(YAGNI,只列 friction 最大的,不贪多)。每个候选 8 字段:
- Title(用 CONTEXT.md 业务术语命名,不用代码类名)
- Badge(Strong / Worth exploring / Speculative)
- Files(涉及的文件清单)
- Before/After diagram(Mermaid graph 或手绘 SVG)
- Problem(一句话,为什么现在有 friction)
- Solution(一句话,改成什么)
- Wins(每条 ≤6 词,用 glossary 术语:locality / leverage / interface / implementation)
- ADR callout(可选,若与现有 ADR 冲突)

### Step 2:HTML 报告(不入库)

1. 仿 `~/.agents/skills/improve-codebase-architecture/HTML-REPORT.md` scaffold 写自包含 HTML
2. 产物路径:`$TMPDIR/architecture-review-<timestamp>.html`(macOS `$TMPDIR` 通常是 `/var/folders/.../T/`,fallback `/tmp`)
3. 技术栈:Tailwind via CDN + Mermaid via CDN(本机 staticfile CDN 实测可达,Session 120 的 `harness-practice-guide.html` 已验证;4 源 fallback + 离线降级)
4. macOS 打开:`open <absolute-path>`
5. **末尾 Top recommendation** 段:推荐先做哪个 + 一句话理由
6. **必须停下问用户**:"Which of these would you like to explore?" —— 不自动进 Step 3

### Step 3:Grill 选定项(交互式)

1. 等用户从 HTML 报告选 1 个 candidate
2. 调 `/grilling` skill:**一次一个问题**,每个问题附带推荐答案;fact 自己查,decision 才问
3. grill 中触发 `/domain-modeling`:
   - 命名新概念 → 更新 `CONTEXT.md`
   - 用户拒绝 candidate 且理由符合 ADR 三条件(hard to reverse + surprising without context + real trade-off)→ 创建 `docs/adr/<NNNN>-<topic>.md`
4. 产出 `harness/docs/plan-<重构主题>.md`(用 [`prd-template.md`](./prd-template.md) 模板)

> **重要**:grill 产出的 plan 是**独立后续任务**,不在巡检本身范围。本次只到 plan,不实施重构。

---

## 3. 产物归档

### 3.1 HTML 报告归档(解决 `$TMPDIR` 会被清的问题)

每次跑完 Step 2(无论是否进 Step 3):
```bash
mkdir -p ~/.cache/ai-agent-platform-architecture-reviews
cp "$TMPDIR/architecture-review-<timestamp>.html" \
   ~/.cache/ai-agent-platform-architecture-reviews/<YYYY-MM-DD>.html
```

**不入库**(SKILL.md 明确"so nothing lands in the repo")。

### 3.2 巡检日志(入库)

在 [`codebase-health-log.md`](./codebase-health-log.md) 追加一行:

```markdown
| YYYY-MM-DD | N 候选 | Top: <candidate title> | grill: Yes/No | plan: <plan 文档名 或 "—"> | 归档: ~/.cache/.../<date>.html |
```

### 3.3 baseline 快照(可选)

把本次 `wc -l app/services/*.py | sort -n | tail -10` 的结果记进 `codebase-health-log.md` 末尾代码块,作为下次巡检的对比 baseline。

---

## 4. 不越界声明

- ❌ **不自动跑** —— skill 是 user-invoked,只能手动调 `/improve-codebase-architecture`
- ❌ **不在 repo 内落地 HTML** —— SKILL.md 明确,只能归档到 `~/.cache/`
- ❌ **不预建空 CONTEXT.md / docs/adr/** —— domain-modeling lazy 契约
- ❌ **不替代 /code-review** —— 巡检是项目级(找重构机会),review 是任务级(评单个 diff)
- ❌ **不实施 grill 产出的重构 plan** —— 那是独立后续任务,走正常 task-workflow 流程

---

## 5. 与其他文档的关系

| 文档 | 关系 |
|---|---|
| [`task-workflow.md`](./task-workflow.md) §9 | 任务管理规则里指向本文档的入口 |
| [`AGENTS.md`](../../AGENTS.md) §自动触发规则 | 路由表「代码健康度巡检」行 |
| [`codebase-health-log.md`](./codebase-health-log.md) | 巡检历史日志(每次跑追加一行) |
| [`prd-template.md`](./prd-template.md) | Step 3 grill 产出的 plan 用此模板 |
| [`doc-impact-assessment.md`](./doc-impact-assessment.md) | 巡检完成后做文档影响评估 |
| `~/.agents/skills/improve-codebase-architecture/SKILL.md` | skill 完整文档(user-invoked) |
| `~/.agents/skills/codebase-design/SKILL.md` | 术语纪律来源(module / interface / depth / seam ...) |
| `~/.agents/skills/domain-modeling/SKILL.md` | CONTEXT.md / docs/adr/ 维护流程 |

---

## 6. 首次巡检(2026-07-20)的 P0 候选 baseline

来自首次 Explore 调研(详见 [`codebase-health-log.md`](./codebase-health-log.md) 2026-07-20 行):

| 优先级 | 文件 | 行数 | 关注点 |
|---|---|---|---|
| 🔴 P0 | `app/services/permission_service.py` | 617 | 17 方法,71 处直调 + 123 处 dep,contextvar 闸门刚加(Session 114) |
| 🔴 P0 | `app/api/token_context.py` + `app/api/deps.py` | — | contextvar + StreamingResponse 子任务传播(Python async 陷阱区) |
| 🔴 P0 | `app/agents/graph.py` | 468 | SSE + asyncio.timeout + LangGraph + 工具内权限检查 + ChatOpenAI 外调 |
| 🔴 P0 | `app/api/v1/chat.py` | 311 | SSE 流式 + usage 记录 + billing 联动,最难测端点 |
| 🟡 P1 | `app/services/user_service.py` | 476 | org-cleanup 后耦合痕迹,God Service 候选 |
| 🟡 P1 | `app/api/v1/exports.py` | 495 | 1 endpoint 内含 6 实体生成,类 God endpoint |
| 🟢 P2 | 前端 fat files | settings 1188 / queries 1079 / endpoints 1048 / chat-page 954 | 零单测,改一处怕动全身 |
