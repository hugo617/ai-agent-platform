# 计划:AtoA Skill 编写 —— 让任意 Agent 装上就能用（开放标准）

> 对应 feature_list.json 的 `id`: `atoa-skill`
> 状态: not_started
> 优先级: 22
> 前置: `atoa-cli-chat-admin` ✅（CLI 全部能力就绪后，Skill 才有内容可教 Agent）

---

## 背景:为什么需要这个任务

CLI 全部能力就绪后，外部 Agent 理论上能用 `agenthub` 命令操作平台了。但 Agent 不会自动知道这些命令的存在——它需要一份**指令文档**告诉它「何时用、怎么装、怎么认证、常用命令是什么」。这份文档就是 **Skill**。

这是 Apifox 打法四件套（CLI + Skill + 授权 + agentHints）里的 **Skill 层**，也是让「任意 Agent」能用的关键——只要 Agent 支持 Agent Skills 开放标准（Claude Code / Cursor / Codex / VS Code Copilot 都支持），装上这份 Skill 就自动学会用你的平台。

### 什么是 Agent Skills 开放标准

一个**事实上的行业标准**（2025 年由 VS Code Copilot / Claude Code / Cursor / Codex 共同采纳）：

- 每个 Skill 是一个目录，含 `SKILL.md`
- `SKILL.md` 用 **YAML frontmatter**（`name` + `description`）+ **Markdown 正文**（详细指令）
- **渐进式加载**（核心设计）：
  1. Agent 启动时扫描所有 Skill 的 frontmatter（每个约 100 token）→ 建立「有什么能力」索引
  2. 用户任务命中某个 Skill 的 description → Agent 加载该 Skill 的完整正文
  3. 正文里若引用了子文件 → Agent 按需读取
- **目录约定**：`.github/skills/`、`.claude/skills/`、`.agents/skills/`、`~/.agents/skills/`

### 行业对标

- **Apifox**：官方 GitHub org 发布 "AI Agent Skills for Apifox CLI"，含 `SKILL.md`
- **google/agents-cli**：每个能力（workflow/scaffold/eval/deploy）配一份 Skill，`npx skills add` 分发
- **本仓库现有 skills**：`~/.agents/skills/` 下已有大量 Skill（lark-*、obsedit-* 等），可参照格式

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| CLI 全部命令 | ✅ 前置任务交付 | `cli/`（login/whoami/agents/chat/conversations） |
| API Token 鉴权 | ✅ 前置任务交付 | `app/api/deps.py`（旁路） |
| agenthub Skill | ❌ 缺失 | 无 `.agents/skills/agenthub/` |
| 使用文档 | ❌ 缺失 | 无 `docs/atoa/` |

---

## 目标

1. **编写 `SKILL.md`**：符合 Agent Skills 开放标准，教 Agent 用 agenthub CLI
2. **放对位置**：`.agents/skills/agenthub/SKILL.md`（跨 Agent 通用目录）
3. **写使用文档**：`docs/atoa/` 供人类参考 + 分发说明
4. **实测验证**：至少一个真实 Agent（Claude Code）装上后能被识别并执行命令

### 已确认的决策（与用户对齐）

| 决策点 | 选择 |
|--------|------|
| Skill 标准 | **Agent Skills 开放标准**（YAML frontmatter + 渐进式加载） |
| Skill 位置 | `.agents/skills/agenthub/`（项目内，跨 Agent 通用） |
| 分发方式 | 本版：随仓库分发 + 手动安装；后续可做 `npx skills add agenthub` 或 npm 包 |
| 目标 Agent | Claude Code（实测）；兼容 Cursor / Codex / VS Code Copilot |

---

## 前置条件

- `atoa-cli-chat-admin` ✅（CLI 全部能力就绪）
- 至少一个已颁发并验证可用的 API Token

---

## 实施步骤

### 第一阶段:Skill 编写

#### Step 1:`.agents/skills/agenthub/SKILL.md`（新建）

**结构**（符合开放标准）：

```markdown
---
name: agenthub
description: |
  Operate the agenthub multi-tenant AI agent platform via CLI.
  Use when the user wants to chat with agents, manage agent configs,
  or work with conversation history on an agenthub instance.
  Requires a pre-issued API token (agenthub login).
---

# agenthub CLI Skill

## When to use
- User wants to chat with an agent on their agenthub platform
- User wants to list/create/update/delete agents
- User wants to read conversation history

## Prerequisites
1. Install: `pipx install agenthub` (or `pip install -e .` from source)
2. Login: `agenthub login <token> --base-url <url>`
   - Get token from agenthub admin UI (Settings → API Tokens)

## Common commands

### Chat with an agent
`agenthub agents chat --agent <id> "your message"`
- Streams the reply in real-time
- Add `--conversation-id <id>` to continue a conversation

### List agents
`agenthub agents list --json`

### Create an agent
`agenthub agents create --name "助手" --model deepseek-chat --prompt "..."

## Tips
- Always add `--json` when you need to parse output programmatically
- Add `--yes` to skip confirmations on write operations
- If you get a 401, the token expired — ask the user to re-login
```

**编写要点**：
- **description 精准**（决定 Agent 何时命中）：包含「做什么」+「何时用」+「前置条件」
- **正文简洁**（Agent 上下文宝贵）：命令 + 一句话说明，不写长篇
- **包含认证流程**：Agent 必须知道怎么 login
- **包含错误处理提示**：401 → 重新 login 等常见情况

#### Step 2:可选子文件

若 SKILL.md 太长，拆分子文件按需引用：
- `.agents/skills/agenthub/commands.md`（完整命令参考）
- `.agents/skills/agenthub/examples.md`（常见任务示例）

> 原则：SKILL.md 保持精简（加载成本低），细节放子文件（按需加载）

---

### 第二阶段:使用文档

#### Step 3:`docs/atoa/`（新建）

- `docs/atoa/README.md`：AtoA 功能总览（CLI + Skill + 授权 三件套）
- `docs/atoa/getting-started.md`：人类视角的快速上手（颁发 token → 装 CLI → 装 Skill → 用）
- `docs/atoa/distribution.md`：分发说明（如何让外部 Agent 获取 Skill）

#### Step 4:更新项目文档

- `项目指南/02-后端架构/`：考虑新增 `09-外部Agent接入AtoA.md`（架构说明）
- `README.md`：加「AtoA：让外部 Agent 接入」章节（简述 + 链接到 docs/atoa/）

> 注：架构文档可在功能全部实现后补；本任务先写 Skill + 使用文档

---

### 第三阶段:验证

#### Step 5:Claude Code 实测

- 将 `.agents/skills/agenthub/` 放到 Claude Code 能扫描的位置（项目内或 `~/.agents/skills/`）
- 启动 Claude Code，提问「帮我用 agenthub 列出所有 agent」
- 验证：Claude Code 识别到 Skill → 执行 `agenthub agents list` → 返回结果
- 记录验证证据（截图/日志）

#### Step 6:回归 + 总验证

- `./init.sh` 全绿（Skill 是纯文档，不影响后端）
- Skill 文件格式校验（YAML frontmatter 合法 + Markdown 正文完整）

---

## 验收标准

1. `.agents/skills/agenthub/SKILL.md` 符合开放标准（YAML frontmatter + 正文）
2. `docs/atoa/` 使用文档完整（README + getting-started + distribution）
3. **(真实)Claude Code 实测**：装上 Skill 后能被识别并执行 agenthub 命令
4. `./init.sh` 全绿（纯文档，不影响后端）
5. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| Skill 不被 Agent 识别 | 确认 frontmatter 格式（name + description 必填）；放在正确目录（`.agents/skills/`）；实测验证 |
| description 不够精准导致不命中 | description 写清「做什么 + 何时用」；包含关键词（agent/chat/platform） |
| 正文太长加载成本高 | 保持精简，细节拆子文件；SKILL.md 控制在 200 行内 |
| 命令变更后 Skill 过时 | Skill 与 CLI 命令同步维护；CI 可加一致性检查（后续） |

### 不做的事（边界）

- 不做 npm 包分发（`npx skills add agenthub`）——后续按需
- 不做 Skill 版本管理
- 不写完整的架构文档（`09-外部Agent接入AtoA.md` 在全部 AtoA 任务完成后补）
- 不改 CLI 任何代码（纯文档任务）

---

## 参考文件（实施时对照）

| 参照 | 路径 / 链接 |
|------|------------|
| Agent Skills 开放标准 | https://code.visualstudio.com/docs/agent-customization/agent-skills |
| 本仓库现有 Skill 范本 | `~/.agents/skills/`（lark-* / obsidian-* 等） |
| Apifox 官方 Skill | https://github.com/apifox |
| google/agents-cli Skills | https://github.com/google/agents-cli |
| CLI 命令清单（Skill 内容来源） | `cli/` 全部子命令（前置任务交付） |
| AtoA 架构总览 | `progress.md` 任务规划表 + 本系列 5 份 plan |
