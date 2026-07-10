# 计划:对话后端(DeepSeek 接入 + 会话历史 API)

> 对应 feature_list.json 的 `id`: `chat-conversation-api`
> 状态: not_started
> 优先级: 12
> 前置: `agents-api-hardening`(Agent 是对话的目标)
> 参考文档: https://api-docs.deepseek.com/zh-cn/

---

## 背景:为什么不是"从零搭建"

对话主线的**后端核心已实现**:SSE 流式(`POST /chat/stream`)、消息持久化(user/assistant 都存)、历史加载、租户隔离都在 `chat.py` + `conversation_service.py` 里。本任务的真实工作是**两件补全**:

1. **LLM 切换为 DeepSeek**:当前 `graph.py` 用 `ChatOpenAI` 接 OpenAI,DeepSeek 用 OpenAI 兼容格式,只改配置不改代码结构
2. **暴露会话历史 API**:`conversation_service` 已有 `list_for_user`/`history` 方法,但**没暴露成 HTTP 端点**——前端无法列表/查看历史。还要补"删除会话"

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| SSE 流式对话 | ✅ 已完成 | `app/api/v1/chat.py` `POST /chat/stream`(含持久化+历史加载) |
| LLM 初始化 | ✅ 结构就绪 | `app/agents/graph.py` `ChatOpenAI`(L50,83),读 `settings.openai_*` |
| 会话列表 Service | ✅ 已完成 | `conversation_service.list_for_user`(L49) |
| 历史消息 Service | ✅ 已完成 | `conversation_service.history`(L56) |
| 消息追加 Service | ✅ 已完成 | `conversation_service.append_message`(L63) |
| 会话列表 API | ❌ 缺端点 | Service 有,未暴露 HTTP |
| 历史消息 API | ❌ 缺端点 | Service 有,未暴露 HTTP |
| 删除会话 | ❌ 全缺 | Service/Repository/端点都没有 |
| LLM 配置 | ⚠️ 是 OpenAI | `config.py` L58-60 + `.env.example` L46-48,默认 OpenAI |
| Conversation model | ⚠️ 缺 updated_at | `app/models/agent.py` Conversation 只有 created_at |
| 测试 | ⚠️ 仅 2 个 | `tests/test_chat.py`(持久化 + 跨租户拒绝)|

---

## 目标

让对话主线后端完整可用:
1. LLM 切换为 DeepSeek(配置层改动,代码结构不变)
2. 会话历史 API 补齐(列表/历史/删除三个端点)
3. 测试覆盖完整(流式、列表、历史、删除、隔离)

---

## 前置条件

- `agents-api-hardening` 完成(Agent 是对话目标,要保证 Agent CRUD 稳健)
- **DeepSeek API Key**:需用户提供有效的 `sk-...` key 填入 `.env`(测试用 monkeypatch 不需要真 key)

---

## 实施步骤

### 第一阶段:LLM 切换为 DeepSeek(配置层)

#### Step 1:改 LLM 配置默认值

DeepSeek 用 OpenAI 兼容格式,`ChatOpenAI` 调用方式完全不变,只改三处配置默认值。

- **改什么**:
  - `app/core/config.py` L58-60:
    ```python
    # 旧
    openai_api_key: str = "sk-replace-me"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    # 新(默认值改为 DeepSeek)
    openai_api_key: str = "sk-replace-me"
    openai_base_url: str = "https://api.deepseek.com"
    openai_model: str = "deepseek-chat"
    ```
  - `.env.example` L46-48(同步):
    ```ini
    OPENAI_API_KEY=sk-replace-me
    OPENAI_BASE_URL=https://api.deepseek.com
    OPENAI_MODEL=deepseek-chat
    ```
  - `.env`(L29-31,同步)
- **不改什么**:`app/agents/graph.py` 的 `ChatOpenAI(...)` 调用结构完全不动(DeepSeek 兼容 OpenAI 格式)。
- **检查**:`graph.py` 两处 ChatOpenAI(L50,83)读的是 `settings.openai_*`,改完 config 默认值即生效。变量名仍叫 `openai_*`(语义上是"OpenAI 兼容"接口,不改名以减少改动面)。

> **关于变量命名**:config 字段仍叫 `openai_api_key`/`openai_base_url`/`openai_model`,因为 langchain 的类就叫 `ChatOpenAI`,DeepSeek 走的就是 OpenAI 兼容协议。若想语义更准,可加注释说明"支持任何 OpenAI 兼容端点(含 DeepSeek)"。**不建议改名**(改动面大,无功能收益)。

### 第二阶段:会话历史 API 补齐

#### Step 2:Conversation model 加 updated_at(排序用)

对话列表需按"最近活跃"排序,当前 `Conversation` 只有 `created_at`。

- **改什么**(`app/models/agent.py` Conversation 类,L50 后):
  - 加 `updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)`
  - 参照同文件 Agent 表的 created_at 写法
- **迁移**:生成 Alembic 迁移 `alembic revision --autogenerate -m "add updated_at to conversation"`
- **更新 Service**:`conversation_service.append_message` 里更新 `conv.updated_at`(新消息时刷新)

#### Step 3:新建 conversations.py API(列表/历史/删除)

`conversation_service` 的 `list_for_user`/`history` 方法已就绪,缺 HTTP 端点。新建 `app/api/v1/conversations.py` 暴露它们 + 补删除。

- **新建文件** `app/api/v1/conversations.py`(参照 `agents.py` 的结构):
  ```python
  router = APIRouter(prefix="/conversations", tags=["conversations"])

  @router.get("/", dependencies=[Depends(require_permission("conversations", "read"))])
  async def list_conversations(user, db):
      # 调 conversation_service.list_for_user
      # 返回 list[ConversationRead],按 updated_at desc 排序

  @router.get("/{conversation_id}/messages", dependencies=[...("read")])
  async def list_messages(conversation_id, user, db):
      # 调 conversation_service.history

  @router.delete("/{conversation_id}", status_code=204, dependencies=[...("delete")])
  async def delete_conversation(conversation_id, user, db):
      # 新增 Service 方法 delete(软删除或硬删除,见下)
  ```
- **Service 补 delete 方法**(`conversation_service.py`):
  - 加 `async def delete(self, user_id, tenant_id, conversation_id)`:
    - `permission_service.require(..., "conversations", "delete")`
    - `get_for_tenant` 取 conv,不存在抛 `NotFoundError`
    - 删除(决策见下)
- **删除策略决策**(需实施时确认):
  - **方案 A(推荐):硬删除**——Conversation/Message 表无 `is_deleted` 字段,加软删除要改 schema。对话属用户私有数据,硬删除合理
  - 方案 B:软删除——需给 Conversation/Message 加 `is_deleted`,改动大,不推荐
- **路由注册**(`app/main.py` L12 + L55 区域):
  - import 加 `conversations`
  - `app.include_router(conversations.router, prefix=prefix)`
- **检查**:`GET /api/v1/conversations/` 返回当前用户会话列表;`GET /api/v1/conversations/{id}/messages` 返回历史;`DELETE` 返回 204。

#### Step 4:ConversationService 异常对齐

趁此机会把 `conversation_service.create_or_get` 的裸 `ValueError`(L34)改为 `NotFoundError`,对齐其他 Service。

- **改什么**(`app/services/conversation_service.py`):
  - import `from app.services.errors import NotFoundError`
  - L34 `raise ValueError(...)` → `raise NotFoundError(...)`
  - 新增 `delete` 方法里 not found 也抛 `NotFoundError`
- **chat.py 同步**(L59):`except ValueError → 404` 可改为 `isinstance` 模式(参照 agents-api-hardening 的 `_http_exc`)

### 第三阶段:测试补全

#### Step 5:补 test_chat.py

当前 2 个测试(持久化 + 跨租户拒绝)。补会话历史端点 + 删除覆盖。

- **保留**:现有 2 个测试
- **新增测试用例**:
  - **会话列表**:发起对话后 `GET /conversations/` → 含该会话
  - **历史消息**:`GET /conversations/{id}/messages` → 含 user + assistant 消息(需 monkeypatch stream_agent,避免依赖真实 LLM)
  - **删除会话**:`DELETE /conversations/{id}` → 204;再 GET 列表不再出现
  - **跨租户隔离**:租户 B 的 client GET 租户 A 的会话 → 列表不出现 / GET messages → 404
  - **权限边界**:`member_client` DELETE → 403(member 无 `conversations:delete`)
- **LLM mock**:流式对话测试用 `monkeypatch` 替换 `stream_agent`(返回固定 chunk),不依赖真实 DeepSeek API。参照现有 `test_chat.py` 的 mock 方式。
- **检查**:`pytest tests/test_chat.py -v` 全过。

### 第四阶段:总验证

#### Step 6:全栈验证

- **命令**:
  ```bash
  ./init.sh   # ruff + pytest 全绿(含新增测试)
  ```
- **手动验证**(启动后,需真实 DeepSeek key):
  - `.env` 填入 DeepSeek key → `uvicorn app.main:app --reload`
  - `POST /api/v1/chat/stream`(带 token + agent_id + message)→ SSE 流式返回中文回复
  - `GET /api/v1/conversations/` → 看到刚的会话
  - `GET /api/v1/conversations/{id}/messages` → 看到 user + assistant 消息
- **通过标准**:
  - `./init.sh` 全绿
  - 手动 SSE 对话能收到 DeepSeek 的流式回复
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. LLM 配置默认值切到 DeepSeek(`base_url=https://api.deepseek.com`、`model=deepseek-chat`),`.env.example` 同步
2. 新增端点:`GET /conversations/`、`GET /conversations/{id}/messages`、`DELETE /conversations/{id}`
3. `./init.sh` 全绿(ruff + pytest,含新增会话/删除/隔离测试)
4. ConversationService 异常用 `NotFoundError`(类型化)
5. (手动)真实 DeepSeek key 下,SSE 流式对话能正常返回

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| DeepSeek API 与 OpenAI 有细微差异(如 tool calling) | DeepSeek 官方声明兼容 OpenAI 格式;`stream_agent` 的 `astream_events` + `AIMessageChunk` 是标准 LangChain 协议,兼容。测试用 mock,手动验证才用真实 key |
| 加 `updated_at` 需要 Alembic 迁移 | 生成迁移后,本地 `alembic upgrade head` 验证;CI migrations job 会守门 |
| 删除会话用硬删除丢失数据 | 对话是用户私有数据,硬删除符合预期;若未来要审计,再加软删除(按需) |
| `ChatRequest` 当前无 title 字段 | 创建会话时 title 可选;列表显示用 title 或 fallback 到首条消息摘要(前端处理) |
| 测试覆盖流式需 mock | 现有 `test_chat.py` 已有 monkeypatch stream_agent 的范例,照搬 |

### 不做的事(边界)

- 不改前端(那是 `chat-frontend` 任务)
- 不做向量检索/pgvector(对话历史用普通 SQL 查询;RAG 是更后续的事)
- 不做多模型路由(Agent.model 字段保留,但 stream_agent 暂用全局 settings;per-agent model 是后续增强)
- 不改 config 字段名(仍叫 `openai_*`,语义为"OpenAI 兼容接口")

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| SSE 流式对话(已有) | `app/api/v1/chat.py` `POST /chat/stream` |
| 会话 Service(已有方法) | `app/services/conversation_service.py` |
| 会话 Repository(已有) | `app/repositories/conversation.py` |
| conversation schema(已有) | `app/schemas/conversation.py` |
| Agent model + Conversation model | `app/models/agent.py` |
| API 端点结构模板 | `app/api/v1/agents.py`(CRUD 结构) |
| 错误映射模板 | `app/api/v1/users.py:29` `_http_exc` |
| 异常定义 | `app/services/errors.py` |
| 现有 chat 测试 | `tests/test_chat.py`(含 monkeypatch stream_agent 范例) |
| DeepSeek 文档 | https://api-docs.deepseek.com/zh-cn/ |
| LLM 配置位置 | `app/core/config.py` L58-60 |
