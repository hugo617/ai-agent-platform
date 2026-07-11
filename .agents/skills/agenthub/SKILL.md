---
name: agenthub
description: 通过 agenthub CLI 操作 agenthub 多租户智能体云平台。触发场景：与平台上的智能体（Agent）流式对话，查询/创建/修改/删除智能体配置，查看会话历史或清理会话。适用于用户提到"agenthub 平台"、"和我装的智能体对话"、"列出/创建 Agent"、"查看对话历史"等场景。需要预先颁发的 API token（ahp_ 前缀）通过 `agenthub login` 登录。
metadata:
  requires:
    bins: ["agenthub"]
  cliHelp: "agenthub --help"
---

# agenthub CLI Skill

用 agenthub CLI 让用户通过命令行操作他们的 agenthub 智能体云平台实例。agenthub 是一个多租户 AI 智能体 SaaS 平台,本 CLI 让外部 AI Agent 在授权后调用平台的全部能力(对话 + 配置管理 + 历史读写)。

## 何时用

当用户的请求落在以下场景,且需要操作的是**他们的 agenthub 平台实例**(而非通用聊天):

- 想和平台上已配置好的某个智能体对话(用其 system_prompt + model + tools)
- 想列出、创建、修改、删除智能体配置
- 想查看之前的对话历史(会话 + 消息)
- 想清理 / 删除某个会话

## 新会话检查

首次处理 agenthub 任务时,先轻量确认 CLI 可用且已登录:

```bash
agenthub whoami            # 确认已登录 + token 有效(返回 user_id/tenant)
agenthub agents list --json # 确认能看到智能体(空数组也算成功,只是没建过)
```

- 如果 `agenthub` 命令不存在 → 让用户安装:`pipx install agenthub` 或从源码 `pip install -e .`
- 如果 `whoami` 返回「未登录」(exit 2) → 让用户先 `agenthub login <token>`,token 需从 agenthub 管理后台「设置 → API Token」颁发(`ahp_` 前缀,明文仅显示一次)
- 如果 `whoami` 返回 401(token 过期) → 让用户重新颁发 token 并 `agenthub login`

**不要替用户猜 token**。token 是敏感凭证,只由用户自行颁发并粘贴。

## 登录与认证

```bash
agenthub login <token> [--base-url http://localhost:8000]
```

- token 格式 `ahp_xxxxxxxx`(`ahp_` 前缀),从平台「设置 → API Token」颁发
- 凭证存到 `~/.agenthub/credentials`(权限 0600)
- 也支持环境变量覆盖(容器/CI 场景):`AGENTHUB_TOKEN` + `AGENTHUB_BASE_URL`
- `--base-url` 默认 `http://localhost:8000`,私有部署/远程实例需显式传

## 基础用法

```bash
agenthub --help                       # 顶级帮助
agenthub <group> --help               # 子命令组帮助(agents / conversations)
agenthub <group> <command> --help     # 单命令帮助
```

常用全局选项(**必须放在子命令前**,对齐 typer/click 惯例):

```text
--json               输出 JSON(结构化,便于解析);管道场景自动启用
--no-interactive     跳过所有确认提示(等价于写操作加 --yes)
```

## 核心命令速查

完整命令参考见本目录下 [commands.md](commands.md)。最常用的:

### 对话(核心能力)

```bash
agenthub agents chat --agent <id> "你好"           # 流式对话,回复实时打到终端
agenthub --json agents chat --agent <id> "1+1"     # JSON 模式:累积后一次输出 {reply,...}
agenthub agents chat --agent <id> "续聊" --conversation-id <conv-id>  # 续接历史会话
```

- 默认模式:delta 流式输出到 **stderr**(打字机效果,不污染 stdout)
- `--json` 模式:累积完整回复后输出 `{"reply": "...", "agent_id": "...", "conversation_id": ...}` 到 stdout
- 新建会话时 `conversation_id` 为 null(SSE 帧不含);续聊用 `agenthub conversations list` 拿到 id 再传

### 智能体管理(CRUD)

```bash
agenthub agents list --json                              # 列出全部智能体
agenthub agents get <id>                                 # 查看详情(含 system_prompt)
agenthub agents create --name "助手" --model deepseek-chat --prompt "你是..."  # 创建
agenthub agents update <id> --model deepseek-reasoner --yes    # 改字段(PATCH 语义)
agenthub agents delete <id> --yes                        # 删除(默认会确认)
```

### 会话历史

```bash
agenthub conversations list --json                # 我的会话列表(按最近活跃排序)
agenthub conversations messages <conv-id>         # 某会话的全部消息(时间线格式)
agenthub conversations delete <conv-id> --yes     # 删除会话(消息级联清除)
```

## 使用要点

- **需要解析输出时总是加 `--json`**(在子命令前):`agenthub --json agents list`
- **写操作默认会确认**,批量/自动化场景加 `--yes`;`--no-interactive` 全局跳过所有确认
- **exit code 含义**:0 成功 / 1 一般错误(网络、API 错误、404) / 2 认证失败(未登录、401) / 3 权限不足(403)
- **模型选择**:Agent 配置了 `model` 字段(如 deepseek-chat / deepseek-reasoner),对话时用 Agent 的 model;创建/修改时建议先 `agents list` 看现有 Agent 用什么 model
- **多租户隔离**:token 绑定颁发者的租户 + 角色,只能操作本租户资源、继承颁发者权限(owner/admin/member 能做的不同)

## CLI 事实优先

具体命令、参数、输出以当前 CLI 的 `--help` 为准。如果本 Skill 与 CLI 实际输出不一致,**以 CLI 输出为准执行**,并同步修正本 Skill。

## 常见错误处理

| 现象 | 原因 | 处理 |
|------|------|------|
| `未登录`(exit 2) | 没登录或凭证丢失 | `agenthub login <token>` |
| `token 无效或已过期`(exit 2, 401) | token 过期/被吊销 | 让用户重新颁发 token |
| `权限不足`(exit 3, 403) | 当前角色无此权限 | 换有权限的 token,或让 owner 调整角色权限 |
| `API 错误 (404)` | agent_id / conversation_id 不存在 | 先 `agents list` / `conversations list` 确认 id |
| 流式对话 error 帧 | 后端 LLM 调用失败(model 名错、key 失效、超时) | 看 error 内容;确认 model 名 + LLM 配置 |
