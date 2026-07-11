# agenthub CLI 完整命令参考

> 本文件是 SKILL.md 的子文件,按需加载。所有命令的权威信息以 `agenthub --help` / `<cmd> --help` 为准。

## 全局选项

放在子命令**前面**(typer/click 惯例):

```text
agenthub [--json] [--no-interactive] <group> <command> [args]
```

| 选项 | 作用 |
|------|------|
| `--json` | 输出 JSON(结构化);管道场景(stdout 非 TTY)自动启用 |
| `--no-interactive` | 跳过所有确认提示(等价于写操作加 `--yes`) |

## 顶级命令

### `agenthub login`

登录并保存凭证。

```bash
agenthub login <token> [--base-url http://localhost:8000]
```

- `token`:`ahp_` 前缀的 API token,从平台「设置 → API Token」颁发
- `--base-url`:平台 API 地址,默认 `http://localhost:8000`;远程/私有部署需显式传
- 登录前会调 `/api-tokens/verify` 验证 token 有效,无效则不保存(exit 2)
- 凭证存到 `~/.agenthub/credentials`(权限 0600)

### `agenthub whoami`

显示当前登录身份。

```bash
agenthub whoami [--json]
```

- 默认输出:`user_id` / `tenant` / `valid`
- `--json` 输出原始 verify 响应

## `agents` 子命令组

### `agenthub agents list`

列出当前租户的全部智能体。

```bash
agenthub agents list [--json]
```

- 默认输出 rich 表格(ID / 名称 / 模型)
- `--json` 输出原始数组:`[{id, name, model, system_prompt, ...}]`

### `agenthub agents get`

查看某个智能体的详情(含完整 system_prompt)。

```bash
agenthub agents get <id> [--json]
```

### `agenthub agents create`

创建一个新智能体(非破坏性,无需确认)。

```bash
agenthub agents create --name "助手" [--model deepseek-chat] [--prompt "你是..."] [--json]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--name` | 是 | 智能体名称 |
| `--model` | 否 | 模型(如 deepseek-chat / deepseek-reasoner);不传用平台默认 |
| `--prompt` | 否 | 系统提示词(system_prompt) |

### `agenthub agents update`

修改智能体配置(只传要改的字段,PATCH 语义)。

```bash
agenthub agents update <id> [--name "..."] [--model "..."] [--prompt "..."] [--yes]
```

- 至少传一个 `--name` / `--model` / `--prompt`,否则报参数错误
- 默认会 `typer.confirm` 确认;`--yes` 跳过;`--no-interactive` 全局跳过

### `agenthub agents delete`

删除一个智能体。

```bash
agenthub agents delete <id> [--yes]
```

- 默认会确认;`--yes` 跳过;`--no-interactive` 全局跳过

### `agenthub agents chat`(核心能力)

与智能体对话,SSE 流式输出。

```bash
agenthub agents chat --agent <id> <message> [--conversation-id <conv-id>] [--json]
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `--agent` | 是 | 目标智能体 ID |
| `<message>` | 是(位置参数) | 要发送的消息 |
| `--conversation-id` | 否 | 续接已有会话;不传则后端自动新建 |

**输出模式**:

- **默认模式**:delta 逐字输出到 **stderr**(打字机效果,stdout 保持干净便于管道)
- **`--json` 模式**:累积完整回复后,输出 `{"reply": "...", "agent_id": "...", "conversation_id": <传入值或null>}` 到 stdout

**SSE 帧格式**(供调试参考):

- `data: {"delta": "chunk"}` → 增量内容
- `data: {"error": "msg"}` → 错误(exit 1)
- `data: [DONE]` → 流结束

**续聊**:`--json` 输出的 `conversation_id` 在新建会话时为 null(SSE 帧不含);要续聊先 `agenthub conversations list` 拿到 id,再用 `--conversation-id` 传入。

## `conversations` 子命令组

### `agenthub conversations list`

列出当前用户的会话(按最近活跃排序)。

```bash
agenthub conversations list [--json]
```

- 默认输出 rich 表格(ID / Agent / 标题 / 更新时间)
- `--json` 输出原始数组:`[{id, agent_id, title, created_at, updated_at, ...}]`

### `agenthub conversations messages`

查看某个会话的历史消息(按时间升序)。

```bash
agenthub conversations messages <conv-id> [--json]
```

- 默认输出时间线格式:`[user] xxx` / `[assistant] xxx`(带时间戳)
- `--json` 输出原始数组:`[{id, role, content, created_at}]`

### `agenthub conversations delete`

删除一个会话(硬删除,消息随之级联清除)。

```bash
agenthub conversations delete <conv-id> [--yes]
```

- 默认会确认;`--yes` 跳过;`--no-interactive` 全局跳过
- `--json` 输出 `{"deleted": true, "conversation_id": "..."}`

## Exit Code 含义

| Code | 含义 | 触发场景 |
|------|------|---------|
| 0 | 成功 | 命令正常完成(含用户在确认提示选「否」) |
| 1 | 一般错误 | 网络错误、API 错误(4xx/5xx 除 401/403)、SSE error 帧 |
| 2 | 认证失败 | 未登录、token 无效/过期(401) |
| 3 | 权限不足 | 当前 token 角色无此权限(403) |

## 权限矩阵(决定 token 能做什么)

token 继承颁发者在租户内的角色权限:

| 操作 | owner | admin | member |
|------|-------|-------|--------|
| agents list/get | ✅ | ✅ | ✅ |
| agents chat | ✅ | ✅ | ✅ |
| conversations list/messages(自己的) | ✅ | ✅ | ✅ |
| agents create/update/delete | ✅ | ✅(无 delete) | ❌ |
| conversations delete(自己的) | ✅ | ✅ | ✅ |

> member 主要受限在写操作;对话 + 读历史对三个角色都开放。具体以平台 RBAC 配置为准。
