# 计划:Token 用量采集(用量事件层)(Token 费用管理系列 1/4)

> 对应 feature_list.json 的 `id`: `token-usage-tracking`
> 状态: not_started
> 优先级: 43
> 前置: 无(本系列地基)
> 系列总纲: [`plan-token-billing-overview.md`](plan-token-billing-overview.md)

---

## 背景:对话消耗的 token 完全没被采集

### 现状(2026-07-12 精确取证)

`app/agents/graph.py` 的 `stream_agent`(L125-178)事件循环**只处理 `on_chat_model_stream`**,只 yield `chunk.content`(文本)。它**从不读 `chunk.usage_metadata`**——这正是 LangChain 在流末尾暴露 provider 真实用量(`input_tokens`/`output_tokens`/`total_tokens`)的地方。真实用量被完全丢弃。

`app/api/v1/chat.py` 的 `event_source`(L93-147)只把文本累积到 `full_reply: list[str]`,然后调 `append_message(..., "assistant", text)`。**不传任何 token 数据**。

`app/models/message.py` 的 Message 模型只有 5 列(id/conversation_id/tenant_id/role/content/created_at),**无 token 列、无 model 列**。

**结论**:平台对「每次对话用了多少 token、哪个模型服务的」一无所知。这是整个商业闭环的第一道缺口——连用量都不知道,后续计费无从谈起。

### 关键技术点

1. **DeepSeek 流式 usage 的特殊性**:OpenAI 兼容 API 在流式模式下,usage 只在**最后一个 SSE chunk** 返回。LangChain 的 `ChatOpenAI` 需要显式传 `stream_usage: True` 才会在流中聚合并交付 usage(否则流式下 usage 不返回)。
2. **ReAct agent 多轮调用**:`create_react_agent` 可能在一轮对话里多次调 LLM(思考→工具→再思考)。`on_chat_model_end` 会在每次模型调用结束时触发,需要**累加**所有调用的 usage,而非只取最后一次。
3. **yield 契约变更**:`stream_agent` 现在是 `AsyncIterator[str]`。要传 usage 给调用方,需改为带类型的结构(如 `AsyncIterator[str | UsagePayload]` 或 discriminated union)。

### 目标

让系统「知道每次对话用了多少 token、哪个模型服务的」:
1. `stream_agent` 采集真实 `usage_metadata`(累加多轮)+ 开启 `stream_usage`
2. `event_source` 接收 usage,记录实际服务的 model 名
3. Message 加 token 列(向后兼容)
4. 新建 UsageEvent 追加式账本(每次对话一条,为后续计费/归因打基础)
5. 本任务**不做扣费、不做余额拦截**(那是任务 2),只做「采集 + 落库」

---

## 前置条件

- 无。本系列第一棒,所有改动在现有对话流内,不依赖钱包/定价。

---

## 实施步骤

### 第一阶段:开启流式 usage + 采集

#### Step 1:`_build_llm_kwargs` 开启 stream_usage

- **改什么**(`app/agents/graph.py` L81-87 `_build_llm_kwargs`):
  ```python
  kwargs: dict[str, Any] = {
      "model": model,
      "api_key": api_key,
      "base_url": base_url,
      "streaming": True,
      "stream_usage": True,   # ← 新增:流式聚合 usage(DeepSeek 末尾 chunk 返回)
      "temperature": temperature,
  }
  ```
- **检查**:确认 `ChatOpenAI` 接受 `stream_usage` 参数(langchain-openai 支持);确认非流式路径不受影响

#### Step 2:stream_agent 采集并累加 usage_metadata

- **改什么**(`app/agents/graph.py` L125-178 `stream_agent`):
  - 改返回类型注解:从 `AsyncIterator[str]` 改为 `AsyncIterator[str | dict]`(或定义 `UsagePayload` TypedDict)
  - 事件循环(L172-177)加分支:
    ```python
    usage_acc = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    async for event in agent.astream_events(inputs, version="v2"):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield chunk.content
        elif kind == "on_chat_model_end":
            # ReAct 可能多次调 LLM,累加所有调用的 usage
            output = event["data"].get("output")
            if hasattr(output, "usage_metadata") and output.usage_metadata:
                um = output.usage_metadata
                usage_acc["input_tokens"] += um.get("input_tokens", 0)
                usage_acc["output_tokens"] += um.get("output_tokens", 0)
                usage_acc["total_tokens"] += um.get("total_tokens", 0)
    # 流结束后 yield usage 汇总(调用方据此落库)
    yield {"usage": usage_acc, "model": model}
    ```
  - **注意**:`on_chat_model_end` 在 ReAct 多轮里会触发多次(每次 LLM 调用一次),必须累加而非覆盖
- **检查**:单元测试模拟 astream_events 产出含 usage 的 on_chat_model_end 事件,验证累加正确

### 第二阶段:Message 加列 + 持久化

#### Step 3:Message 模型加 token 列

- **改什么**(`app/models/message.py` Message 模型,加 4 个可空列):
  ```python
  prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
  completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
  total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
  model: Mapped[str | None] = mapped_column(String(64), nullable=True)
  ```
  - 全部可空(向后兼容:user 消息和旧 assistant 消息这些列为 NULL)
- **迁移**(`alembic revision --autogenerate`):加 4 列
- **检查**:`alembic upgrade head && alembic check` 无 drift;现有消息查询不受影响(NULL 不影响)

#### Step 4:append_message 扩展接收 token 数据

- **改什么**(`app/services/conversation_service.py` L92-109 `append_message`):
  ```python
  async def append_message(
      self, tenant_id: str, conversation_id: str, role: str, content: str,
      *,
      prompt_tokens: int | None = None,
      completion_tokens: int | None = None,
      total_tokens: int | None = None,
      model: str | None = None,
  ) -> Message:
      msg = Message(
          conversation_id=conversation_id, tenant_id=tenant_id,
          role=role, content=content,
          prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
          total_tokens=total_tokens, model=model,
      )
      ...
  ```
  - 关键字参数(向后兼容:现有调用方不传这些参数也不报错)
- **检查**:现有调用方(`chat.py` L132/141)不传新参数也能工作

#### Step 5:chat.py event_source 消费 usage 并传给 append_message

- **改什么**(`app/api/v1/chat.py` L107-146 event_source):
  ```python
  usage_data = None
  async for item in stream_agent(...):
      if isinstance(item, str):
          full_reply.append(item)
          yield f"data: {json.dumps({'delta': item}, ensure_ascii=False)}\n\n"
      elif isinstance(item, dict) and "usage" in item:
          usage_data = item  # 流末尾的 usage 汇总
  # 成功路径:带 usage 落库
  await conv_service.append_message(
      conv.tenant_id, conv.id, "assistant", "".join(full_reply),
      prompt_tokens=usage_data["usage"]["input_tokens"] if usage_data else None,
      completion_tokens=usage_data["usage"]["output_tokens"] if usage_data else None,
      total_tokens=usage_data["usage"]["total_tokens"] if usage_data else None,
      model=model,   # ← L102-106 解析后的实际服务 model,非 agent.model
  )
  ```
  - 中断路径(L130-138)同样记录 partial usage(若有)
- **检查**:对话完成后查 Message 表,assistant 消息的 token 列和 model 列有值

### 第三阶段:UsageEvent 账本表

#### Step 6:新建 UsageEvent 模型 + Repository

- **新建**(`app/models/usage_event.py`):
  ```python
  class UsageEvent(Base):
      __tablename__ = "usage_events"
      __table_args__ = (Index("idx_usage_events_tenant_created", "tenant_id", "created_at"),)

      id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
      tenant_id: Mapped[str] = mapped_column(String(32), index=True)
      conversation_id: Mapped[str] = mapped_column(String(32), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
      message_id: Mapped[str] = mapped_column(String(32), ForeignKey("messages.id", ondelete="CASCADE"), index=True)
      agent_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
      customer_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 任务4 填
      user_id: Mapped[str] = mapped_column(String(128))
      model: Mapped[str] = mapped_column(String(64))
      prompt_tokens: Mapped[int] = mapped_column(Integer)
      completion_tokens: Mapped[int] = mapped_column(Integer)
      total_tokens: Mapped[int] = mapped_column(Integer)
      cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)  # 任务2 填
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  ```
  - `customer_id`/`cost` 本任务可空(任务 2/4 填),为后续打基础
- **新建**(`app/repositories/usage_event.py`):
  ```python
  class UsageEventRepository(TenantScopedRepository[UsageEvent]):
      model = UsageEvent
      # 加聚合查询:按 tenant/按 customer/按 agent/按时间段汇总 tokens
  ```
- **注册模型**(`alembic/env.py` L18-28 import 列表加 `usage_event`)
- **迁移**:`alembic revision --autogenerate`
- **检查**:`alembic upgrade head && alembic check` 无 drift

#### Step 7:对话成功后写 UsageEvent

- **改什么**(`app/services/conversation_service.py` 或新建 `app/services/usage_service.py`):
  - append_message 成功后(或 event_source 里),若 assistant 消息有 token 数据,创建一条 UsageEvent
  - 字段:`tenant_id`/`conversation_id`/`message_id`(刚创建的 msg.id)/`agent_id`/`user_id`/`model`/3 个 token 列;`customer_id`/`cost` 暂 None
- **检查**:对话后查 usage_events 表有对应记录

### 第四阶段:测试 + 总验证

#### Step 8:补测试

- **新建/追加**(`tests/test_usage_tracking.py`):
  - **采集正确性**:模拟 astream_events 产出 on_chat_model_end 含 usage → stream_agent yield 的 usage dict 正确累加
  - **多轮累加**:ReAct 多次 on_chat_model_end → usage 累加(非覆盖)
  - **落库**:对话后 Message 有 token 列 + model;usage_events 有记录
  - **向后兼容**:不传 token 参数的 append_message 调用(Message token 列为 NULL,不报错)
  - **中断路径**:流中断时 partial usage 也记录
  - **跨租户隔离**:usage_events 查询带 tenant_id 过滤
- **检查**:`pytest tests/test_usage_tracking.py -v` 全过

#### Step 9:总验证

- **命令**:
  ```bash
  ./init.sh   # ruff + pytest 全绿
  alembic upgrade head && alembic check   # 迁移无 drift(需 PG/SQLite)
  ```
- **通过标准**:
  - `./init.sh` 全绿(含用量采集测试)
  - 对话后 Message 和 usage_events 表有真实 token 数据
  - 向后兼容(旧调用不崩)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `_build_llm_kwargs` 开启 `stream_usage: True`
2. `stream_agent` 累加 `on_chat_model_end` 的 usage_metadata,流末尾 yield usage 汇总(含实际 model 名)
3. Message 加 4 列(prompt_tokens/completion_tokens/total_tokens/model,均可空,向后兼容)
4. `append_message` 扩展关键字参数接收 token 数据
5. `event_source` 消费 usage 传给 append_message,记录实际服务的 model(非 agent.model)
6. 新建 UsageEvent 表 + Repository(追加式账本,customer_id/cost 暂可空)
7. 对话成功后写一条 UsageEvent
8. `./init.sh` 全绿;`alembic check` 无 drift;向后兼容

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| DeepSeek 流式不返回 usage(即使 stream_usage=True) | 先用真实 DeepSeek key 验证 stream_usage 是否生效;若不生效,降级为非流式取 usage 再流式(两步)或用 token_budget 近似 + 标注 estimated |
| ReAct 多轮 usage 累加出错 | on_chat_model_end 累加(非覆盖);单元测试覆盖多轮场景 |
| yield 契约变更(str → str|dict)影响调用方 | 只有两个调用方(chat.py event_source + AtoA CLI chat);同步改;类型注解 + isinstance 分发 |
| UsageEvent 写入失败导致对话失败 | UsageEvent 写入放在 append_message 之后、用 try/except 包裹,失败只记日志不阻断对话(用量丢失 < 对话失败) |
| 迁移加列导致旧数据问题 | 全部可空,server_default 不设;旧消息 token 列 NULL 是正确语义 |

### 不做的事(边界)

- 不做钱包扣费/余额拦截(任务 2 `token-wallet-billing`)
- 不做客户归因(UsageEvent.customer_id 留空,任务 4 `customer-conversation-link` 填)
- 不做定价计算(UsageEvent.cost 留空,任务 2 填)
- 不改 ReAct 工具链(只加 usage 采集,不改工具调用)
- 不做用量看板(任务 4 前端)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-token-billing-overview.md` |
| stream_agent(待改) | `app/agents/graph.py` L125-178 |
| _build_llm_kwargs(待改) | `app/agents/graph.py` L66-92 |
| event_source(待改) | `app/api/v1/chat.py` L93-147 |
| append_message(待改) | `app/services/conversation_service.py` L92-109 |
| Message 模型(待加列) | `app/models/message.py` |
| Repository 基类 | `app/repositories/base.py` `TenantScopedRepository` |
| 迁移注册点 | `alembic/env.py` L18-28 |
