# AtoA:让外部 AI Agent 接入你的平台

> **AtoA = Agent-to-Agent**:让任意外部 AI Agent(Claude Code / Cursor / Codex / VS Code Copilot)在授权后,通过 **CLI + Skill** 使用本平台的全部能力。

## 为什么需要 AtoA

传统 SaaS 平台只服务「人类用户通过 Web UI 操作」。但 2025 年起,AI Agent(Claude Code 等)越来越多地代替人类执行开发/运维任务。如果你的平台只认 Web UI,这些 Agent 就用不了你的能力。

AtoA 让平台对 AI Agent 友好,核心是**四件套**(对标 Apifox CLI + Skill 打法):

| 件 | 作用 | 本仓库实现 |
|----|------|-----------|
| **CLI** | 平台能力的命令行入口(Agent 会调命令,不会点网页) | `agenthub` 命令(`cli/` 目录,typer 框架) |
| **Skill** | 教 Agent「何时用、怎么用」的指令文档(开放标准) | `.agents/skills/agenthub/SKILL.md` |
| **授权** | 让 Agent 安全地证明身份(不暴露用户密码) | API Token(PAT 式,`ahp_` 前缀) |
| **Agent-Ready 约定** | CLI 输出对 Agent 友好(JSON / exit code / 幂等) | `--json` / `--no-interactive` / 0-1-2-3 exit code |

## 能力概览

装上 agenthub CLI + Skill 后,外部 Agent 能:

- **对话**(核心卖点):与平台上的智能体流式对话,用其配置的 system_prompt + model
- **智能体管理**:创建 / 修改 / 删除 / 列出 / 查看智能体配置
- **会话历史**:查看对话历史、删除会话
- **身份确认**:whoami 验证 token

## 快速上手

→ 见 [getting-started.md](getting-started.md):5 分钟从零接入(颁发 token → 装 CLI → 装 Skill → 用)

## 分发:如何让外部 Agent 获取

→ 见 [distribution.md](distribution.md):随仓库分发 / 手动安装 / 后续 npm 包分发

## 文档索引

| 文档 | 内容 |
|------|------|
| [getting-started.md](getting-started.md) | 人类视角快速上手(5 步) |
| [distribution.md](distribution.md) | 分发与安装说明 |
| [.agents/skills/agenthub/SKILL.md](../../.agents/skills/agenthub/SKILL.md) | Skill 本体(Agent 读取的指令文档) |
| [.agents/skills/agenthub/commands.md](../../.agents/skills/agenthub/commands.md) | 完整命令参考(Skill 子文件) |

## 架构设计

AtoA 的技术核心是**鉴权旁路**:

1. 外部 Agent 持 `ahp_` 前缀的 API Token
2. `get_current_user`(后端鉴权管线)识别 `ahp_` 前缀 → 查 ApiToken 表 → 构造 `CurrentUser`
3. `require_permission`(RBAC 权限工厂)**完全不用改** —— token 绑定颁发者 user_id,casbin 查询正常工作
4. 所有现有 API 自动获得对外部 Agent 开放的能力

**多租户隔离天然继承**:token 的 tenant_id 固定,Repository 层过滤照常生效。

> 详细的架构说明文档(`09-外部Agent接入AtoA.md`)将在全部 AtoA 任务完成后补充到 `项目指南/02-后端架构/`。

## 对标项目

- [Apifox CLI + Skill](https://docs.apifox.com/apifox-cli):四件套打法的标杆
- [google/agents-cli](https://github.com/google/agents-cli):workflow/scaffold/eval/deploy 全覆盖 + skills 分发
- [ComposioHQ/awesome-agent-clis](https://github.com/ComposioHQ/awesome-agent-clis):Agent-Ready CLI 6 准则
