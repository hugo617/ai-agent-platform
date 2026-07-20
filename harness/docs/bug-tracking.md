# Bug 管理流程

> 这份文档定义本项目的「bug 怎么管」——从发现到修复关闭。
> 它是 [`task-workflow.md`](./task-workflow.md) 的补充:普通功能走 task-workflow,bug 走本文档。
> 范例参考 [`plan-chat-overflow-title-fix.md`](./plan-chat-overflow-title-fix.md)(已是 passing 状态)。

---

## 1. bug 与普通功能的区别

| 维度 | 普通功能 | bug |
|---|---|---|
| id 前缀 | kebab-case 功能名(如 `agents-api-hardening`) | **`bug-`** 前缀(如 `bug-chat-overflow`) |
| 起因 | 主动规划的需求 | 用户反馈 / 测试发现 / 线上告警 |
| plan 重点 | 实施步骤 | **复现脚本 + 根因 + 回归测试** |
| 验收 | 行为符合预期 | **原复现脚本失败 + 不引入新 bug** |
| 优先级 | 功能 roadmap | **严重度驱动**(见 §5) |

> **id 前缀核实**:`bug-` 已 grep 现有 60 条 feature_list.json id 确认**无冲突**(现有 id 全是功能名,无 `bug-`/`fix-` 前缀)。若未来发生冲突,改用 `fix-` 前缀。

---

## 2. bug 的 5 个状态

```
  reported ──▶ reproducing ──▶ fixing ──▶ verifying ──▶ closed
     │             │              │             │
     │             └──无法复现───┴─────────────▶ closed (wontfix/working-as-intended)
     │
     └──重复 bug──▶ closed (duplicate)
```

| 状态 | 含义 | 进入条件 | 退出条件 |
|---|---|---|---|
| `reported` | 刚记录 | feature_list.json 录入 + 复现步骤写进 plan | 开始尝试复现 |
| `reproducing` | 正在复现 | — | 稳定复现 / 判定无法复现 / 判定重复 |
| `fixing` | 正在修复 | 根因已定位 + 修复方案已定 | 改完代码 + 自测通过 |
| `verifying` | 正在验证 | 改完代码 + `./init.sh` 全绿 | 回归测试通过 + evidence 已填 |
| `closed` | 终态 | — | — |

> **feature_list.json 状态映射**:`reported`/`reproducing`/`fixing` 都映射到 `not_started` 或 `in_progress`(WIP=1 仍生效,同时只能一个 bug 在 `fixing`)。`verifying` = `in_progress`。`closed` = `passing`(终态)。无法复现/重复/working-as-intended 的 `closed` 在 `evidence` 写明原因。

---

## 3. bug 在 feature_list.json 的登记方式

### 3.1 录入示例

```json
{
  "id": "bug-<简短描述>",
  "priority": <按严重度,见 §5>,
  "area": "受影响模块",
  "title": "一句话标题(用户能看到的症状)",
  "user_visible_behavior": "用户实际看到的现象(对比预期)",
  "status": "not_started",
  "plan": "harness/docs/plan-bug-<简短描述>.md",
  "verification": [
    "原复现脚本不再触发(给出可执行命令)",
    "./init.sh 全绿(无回归)",
    "边界场景测试 N 条"
  ],
  "evidence": [],
  "notes": "严重度:critical/high/medium/low;来源:用户反馈/测试/线上"
}
```

### 3.2 命名规范

- id:`bug-<kebab-case-描述>`,如 `bug-chat-overflow`、`bug-tenant-data-leak`
- plan 文件:`plan-bug-<同 id 后缀>.md`,如 `plan-bug-chat-overflow.md`
- 一个 bug 一个 plan,不要在同一个 plan 里塞多个 bug

---

## 4. bug 修复 plan 模板(简化版)

```markdown
# 计划:bug <标题>

> 对应 feature_list.json 的 `id`: bug-<描述>
> 严重度: critical / high / medium / low
> 来源: 用户反馈 / 测试发现 / 线上告警
> 状态: reported

## 1. 症状(用户视角)
<用户看到什么,对比预期看到什么>

## 2. 复现脚本(可执行)
```bash
# 1. 准备环境
docker-compose up -d && alembic upgrade head
# 2. 触发
curl -X POST http://localhost:8000/api/v1/... -H "Authorization: Bearer <token>"
# 3. 预期 vs 实际
```

## 3. 根因(代码佐证)
- <文件:符号> 当前行为:<描述>
- 为什么错:<分析>
- (参考范例:plan-chat-overflow-title-fix.md 的「根因」段)

## 4. 修复方案
- 改什么:`文件路径:符号` 当前 → 目标
- 为什么这么改:<理由>
- 是否影响其他地方:<影响面清单>

## 5. 回归测试
- 新增测试用例 N 条(覆盖根因 + 边界)
- 跑 `./init.sh` 确认全绿
- 手动跑原复现脚本确认不再触发

## 6. 验收标准(同步 feature_list.json verification)
1. 原复现脚本失败(不再触发)
2. ./init.sh 全绿
3. 边界场景全过

## 7. 风险
- <修复可能引入的副作用>
- <回滚方案>
```

---

## 5. 严重度分级与 SLA

| 严重度 | 定义 | priority 建议值 | 处理时机 |
|---|---|---|---|
| **critical** | 数据泄漏 / 资金损失 / 安全漏洞 / 全站不可用 | 1-5(最高) | 立刻中断当前 WIP,优先修复 |
| **high** | 核心功能不可用 / 影响多租户 / 数据完整性受损 | 6-15 | 当前 WIP 完成后立即接手 |
| **medium** | 非核心功能问题 / 有 workaround | 16-40 | 排进下个迭代 |
| **low** | 体验问题 / 文档错误 / 边角 case | 41+ | 有空就修 |

> **WIP=1 仍生效**:同时只能一个 bug 在 `fixing`。critical 级 bug 可以中断当前 in_progress(退回 `not_started`),但要在 progress.md 记录中断理由。

---

## 6. 与 diagnosing-bugs skill 的衔接

本项目接入了 [`diagnosing-bugs`](file:///Users/star/.agents/skills/diagnosing-bugs/SKILL.md) skill,用于系统性定位根因。

**衔接方式**:
1. **bug 出现** → agent 调 `/diagnosing-bugs` 系统性排查
2. **skill 产出根因**(代码佐证 + 复现路径)→ 写进 plan 的「根因」段
3. **plan 落地修复** → 按 §4 模板写修复方案 + 回归测试

> 不确定何时调?参考 [harness-router](../../.agents/skills/harness-router/SKILL.md)(阶段 3 后)或 AGENTS.md 的自动触发规则表(阶段 2b 后)。

---

## 7. 与 task-workflow.md 的关系

| 场景 | 走哪个流程 |
|---|---|
| 新功能 / 重构 / 技术债 | [task-workflow.md](./task-workflow.md) |
| bug 修复 | 本文档 |
| 安全漏洞 | 本文档 + critical 严重度 + 额外安全审查 |
| 性能问题 | 介于两者之间,看是否是「行为不符合预期」:是 → bug,否 → 功能优化 |

**核心区别**:bug 必须有「复现脚本 + 根因 + 回归测试」三件套,普通功能只要「实施步骤 + 验收标准」。

---

## 8. 已有范例

| bug id | 严重度 | 状态 | 文档 | 关键经验 |
|---|---|---|---|---|
| `chat-overflow-title-fix` | medium | passing | [plan-chat-overflow-title-fix.md](./plan-chat-overflow-title-fix.md) | 兜底逻辑的调用处传参缺失,导致 fallback 永不触发 |
| `embedding-tiktoken-fix`(Session 113) | high | passing(合并入 #79) | Session 113 progress 记录 | langchain 默认用 tiktoken 预编码,oollama 不接受 → `check_embedding_ctx_length=False` |

> 后续 bug 修复完成后,可往这个表追加范例,沉淀经验。
