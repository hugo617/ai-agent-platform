# 计划:AtoA CLI 对话 + CRUD —— 核心卖点与完整能力

> 对应 feature_list.json 的 `id`: `atoa-cli-chat-admin`
> 状态: not_started
> 优先级: 21
> 前置: `atoa-cli-core` ✅（CLI 骨架 + 登录 + 只读命令就绪）

---

## 背景:为什么需要这个任务

CLI 骨架（atoa-cli-core）交付后，Agent 能登录 + 跑只读命令。但**核心价值还没实现**——外部 Agent 用你平台最大的诉求是「调用你的 LLM+Agent 能力」，即对话。本任务把 CLI 从「只读查看器」推进到「完整能力」：

1. **对话**（核心卖点）：`agenthub agents chat` 对接 SSE 流式，终端实时输出
2. **会话历史读写**：让外部 Agent 读/写会话，做上下文衔接
3. **Agent CRUD**：让外部 Agent 能创建/修改平台资源（带确认机制）

这是 Apifox 打法里「CLI 覆盖平台核心能力」的阶段。对话涉及 SSE 流式（技术难点），CRUD 涉及写操作（风险点），所以独立成任务。

### 行业对标

- **Apifox CLI**：覆盖测试执行 + API 文档管理 + 数据模型全生命周期
- **google/agents-cli**：workflow / scaffold / eval / deploy / publish 全覆盖
- **Composio CLI**：`composio execute <ACTION>` 执行任意操作

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| 后端 SSE 对话端点 | ✅ 已完成 | `app/api/v1/chat.py` `POST /chat/stream` |
| 后端会话历史 API | ✅ 已完成 | `app/api/v1/conversations.py` |
| 后端 Agent CRUD | ✅ 已完成 | `app/api/v1/agents.py` |
| CLI 骨架 + 登录 | ✅ 前置任务交付 | `cli/`（typer） |
| CLI 对话命令 | ❌ 缺失 | 需对接 SSE 流 |
| CLI CRUD 命令 | ❌ 缺失 | 需对接写端点 |

---

## 目标

1. **对话命令**：`agenthub agents chat --agent <id> "message"`，终端流式输出（打字机效果）
2. **会话历史命令**：`conversations list` / `conversations messages <id>`
3. **Agent CRUD 命令**：`agents create/update/delete`，带 `--confirm` / `--yes` 确认机制
4. **错误处理完善**：SSE 中断、网络错误、权限不足的友好提示

### 已确认的决策（与用户对齐）

| 决策点 | 选择 |
|--------|------|
| 首发能力范围 | **对话 + 只读 + 历史读写 + CRUD**（全选，本任务覆盖除只读外的三项，只读在上个任务） |
| 对话输出方式 | **终端流式**（逐字输出，打字机效果），`--json` 时收完整回复后一次输出 |
| CRUD 确认机制 | 写操作默认要确认；`--yes` 跳过；`--no-interactive` 自动 `--yes` |
| 会话续接 | `--conversation-id <id>` 指定历史会话续聊 |

---

## 前置条件

- `atoa-cli-core` ✅（CLI 骨架 + 登录 + client 就绪）
- 后端 SSE 端点 + 会话 API + Agent CRUD 全部就绪（已 passing）
- 一个有 `conversations:chat` + `agents:create/update/delete` 权限的 API Token

---

## 实施步骤

### 第一阶段:对话命令（核心卖点）

#### Step 1:`cli/commands/chat.py` —— SSE 流式对接

```bash
agenthub agents chat --agent <agent-id> "你好" [--conversation-id <id>] [--json]
```

- **对接**：`POST /chat/stream`，body `{agent_id, conversation_id?, message}`
- **SSE 解析**（复用后端 `chat.py` 的帧格式）：
  - `data: {"delta": "chunk"}\n\n` → 逐字输出到 stderr（不污染 stdout 便于管道）
  - `data: {"error": "msg"}\n\n` → 报错 exit 1
  - `data: [DONE]\n\n` → 结束
- **流式实现**：`httpx.Client.stream()`，逐行读、解析、yield
- **打字机效果**：每个 chunk 直接 `sys.stderr.write(chunk)` + flush（不缓冲）
- **`--json` 模式**：累积所有 delta，结束后一次输出 `{"reply": "...", "conversation_id": "..."}` 到 stdout
- **会话续接**：`--conversation-id` 指定历史会话；不指定则后端自动新建

#### Step 2:对话测试

- mock SSE 流（用 `httpx.MockTransport` 模拟 `data:` 帧）
- 测试：正常流式 / error 帧 / [DONE] / `--json` 输出格式
- 可选：真实端到端（需后端 + 真实 LLM key）

---

### 第二阶段:会话历史命令

#### Step 3:`cli/commands/conversations.py`

```bash
agenthub conversations list [--json]
agenthub conversations messages <id> [--json]
agenthub conversations delete <id> [--yes]
```

- **对接**：`GET /conversations`（列表）/ `GET /conversations/{id}/messages`（历史）/ `DELETE /conversations/{id}`
- **list 默认输出**：表格（id / agent / 更新时间 / 消息数）
- **messages 默认输出**：时间线格式（`[user] xxx` / `[assistant] xxx`，带时间戳）
- **delete**：默认确认，`--yes` 跳过

#### Step 4:会话测试

- mock httpx，测 list / messages / delete 三个命令的输出格式 + 确认逻辑

---

### 第三阶段:Agent CRUD 命令

#### Step 5:`cli/commands/agents.py` 扩展（写操作）

```bash
agenthub agents create --name "助手" --model deepseek-chat [--prompt "..."] [--json]
agenthub agents update <id> [--name "..."] [--model "..."] [--prompt "..."]
agenthub agents delete <id> [--yes]
```

- **对接**：`POST /agents` / `PUT /agents/{id}` / `DELETE /agents/{id}`
- **create**：name + model 必填，prompt 可选；输出新建的 agent 详情
- **update**：只传要改的字段（PATCH 语义，后端是 PUT 但接受 partial）
- **delete**：确认机制（同 conversations delete）
- **`--no-interactive`**：自动 `--yes`

#### Step 6:CRUD 测试

- mock httpx，测 create / update / delete 的参数构造 + 确认逻辑 + 错误处理

---

### 第四阶段:验证

#### Step 7:端到端验证

- 起后端 → 颁发 token → CLI 登录
- **对话真实跑通**：`agenthub agents chat --agent <id> "1+1"` → 流式输出 "2"
- **CRUD 全流程**：create → list（含新建的）→ update → delete → list（不含）
- **会话历史**：对话后 `conversations list` 含新会话 → `messages <id>` 含对话内容

#### Step 8:回归 + 总验证

- `./init.sh` 全绿（后端不回归）
- CLI 测试全过（`cli/tests/`）

---

## 验收标准

1. `agenthub agents chat` 终端流式输出正常（对接 SSE 成功）
2. `agenthub conversations list/messages/delete` 工作正常
3. `agenthub agents create/update/delete` 工作正常，带确认机制
4. `--json` / `--yes` / `--no-interactive` 全部生效
5. CLI 测试通过（`cli/tests/`）
6. `./init.sh` 全绿（后端不回归）
7. **(真实)端到端对话跑通**（需 LLM key）
8. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| SSE 流式中断（网络抖动） | 优雅退出 + 已收到的内容保留；错误帧清晰提示 |
| 对话输出污染 stdout（影响管道） | 流式 chunk 输出到 stderr，`--json` 完整 reply 输出到 stdout |
| CRUD 误操作（Agent 乱删资源） | 写操作默认确认；`--yes` 需显式传；权限由后端 RBAC 守（member 无 delete 权限） |
| 会话历史 API 分页 | 当前 API 无分页（limit 100），CLI 先不支持分页，后续按需 |
| 真实 SSE 需 LLM key | 离线测试用 mock；真实验证需用户提供 key（参照 real-chat-llm-config 模式） |

### 不做的事（边界）

- 不实现流式对话的中途取消（Ctrl+C 优雅退出即可，不做 resume）
- 不实现交互式 REPL（多轮连续对话）——每条 `chat` 命令一次请求；多轮靠 `--conversation-id`
- 不实现文件上传 / 多模态
- 不实现 Skill（atoa-skill 任务）
- 不改后端任何端点（只对接现有 API）

---

## 参考文件（实施时对照）

| 参照 | 路径 / 链接 |
|------|------------|
| SSE 对话端点 | `app/api/v1/chat.py` `POST /chat/stream` |
| SSE 帧格式 | `chat.py:84-119`（`data:{delta}` / `[DONE]` / `{error}`） |
| 前端 SSE 解析参照 | `frontend/src/api/endpoints.ts` `sendChatStream`（async generator） |
| 会话历史 API | `app/api/v1/conversations.py` |
| Agent CRUD API | `app/api/v1/agents.py` |
| CLI 骨架（前置任务） | `cli/main.py` / `cli/client.py` |
| 行业对标 Apifox CLI | https://docs.apifox.com/apifox-cli |
