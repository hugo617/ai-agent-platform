# 计划:对话上下文工程(token 计数 + 滑动窗口 + 历史截断)

> 对应 feature_list.json 的 `id`: `context-engineering`
> 状态: not_started
> 优先级: 25
> 前置: `real-chat-llm-config` ✅(对话主链路已跑通,本任务解决"长对话必崩"的结构性缺陷)

---

## 背景:为什么需要这个任务

当前对话主链路把**所有历史消息原样拼进 LLM 上下文**,**零 token 控制、零截断、零滑动窗口**。这是一个确定性的运行时 bug——只要对话足够长(几十轮,或单条消息较长),必然撞 LLM 的 context window 上限直接报错。

### 问题根因(代码佐证)

- **Repository 全量拉取,无 limit**:`app/repositories/conversation.py:32` 的 `MessageRepository.list_for_conversation` 直接 `select(Message).where(...).order_by(Message.created_at)`,**没有 limit / offset**。对话有 100 条消息就拉 100 条。
- **chat.py 原样拼接**:`app/api/v1/chat.py:76-82` 把 `list_for_conversation` 返回的全部历史转成 `HumanMessage`/`AIMessage`,无任何截断/计数。
- **graph.py 全量喂给 agent**:`app/agents/graph.py:118` `inputs = {"messages": [*history, HumanMessage(content=user_message)]}` —— 全量历史 + 新消息一起丢进 ReAct agent。
- **零 token 计数**:全仓 grep `token|truncate|sliding|window|max_history|tiktoken` 在 `app/` 下零命中(仅 message model 里有 `role` 字段值含 "assistant",与 token 无关)。
- **零超时保护**:`stream_agent` 的 `astream_events` 无 `asyncio.wait_for`,LLM 拒绝过长输入时连接挂死。

### 后果

1. **长对话 100% 崩溃**:context window 满了 → DeepSeek/OpenAI 返回 400(max tokens / context length exceeded)→ `event_source` 捕获后 yield error,用户看到"对话出错",**这条 user 消息已存库但 assistant 回复丢失**,下次历史里出现"断档"。
2. **成本失控**:每次请求把全部历史发出去,token 消耗随对话长度**平方级增长**(第 N 轮发 N 条历史)。
3. **无记忆压缩**:没有"早期对话摘要 + 近期原文"的分层,长对话信息密度低。

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| 历史消息拉取 | ❌ 无 limit | `app/repositories/conversation.py:32` `list_for_conversation` |
| 历史拼进 prompt | ❌ 全量拼接 | `app/api/v1/chat.py:76-82` |
| token 计数 | ❌ 无 | 全仓零命中 |
| 滑动窗口/截断 | ❌ 无 | — |
| LLM 调用超时 | ❌ 无 | `app/agents/graph.py:119` `astream_events` 无 wait_for |
| 错误时 user 消息已存/assistant 丢失 | ⚠️ 已知 | `chat.py:72` 先存 user,`chat.py:116` 流结束后才存 assistant |

---

## 目标

1. **防止长对话崩溃**:对话历史超过模型 context window 预算时,自动截断(保留 system + 最近 N 轮)
2. **引入 token 计数**:用 token 数(而非消息条数)作为截断依据,贴近真实 LLM 行为
3. **LLM 调用加超时保护**:agent 流式调用加 `asyncio.wait_for`,防挂死
4. **assistant 回复落库容错**:流式中途失败时也尝试落库已有部分(避免历史断档)

### 已确认的决策(与用户对齐)

| 决策点 | 选择 | 理由 |
|--------|------|------|
| token 计数方式 | **近似估算**(字符数 / 1.5 中文,字符数 / 4 英文,混合取保守值) | 不引入 `tiktoken`(额外依赖 + 仅对 OpenAI 精确,DeepSeek 无官方 tokenizer);近似足够做"防止崩溃"的截断 |
| 截断策略 | **滑动窗口**(system + 最近 N 条,保证在预算内) | 最简单可靠;摘要压缩是后续增强(本任务不做,见边界) |
| context 预算来源 | **配置常量**(默认 24000 token,DeepSeek 32k window 留余量) | 硬编码常量,不做 per-model 动态查询(后续可查 `/models` context_length,本任务不做) |
| 超时策略 | `asyncio.wait_for` 整体超时(默认 60s)+ 单 chunk 间隙超时(默认 30s) | 防 LLM 完全挂死 + 防"半死不活"长时间无输出 |

---

## 前置条件

- `real-chat-llm-config` ✅(对话主链路已真实跑通,SSE 已验证)
- 无新依赖(不引入 tiktoken)

---

## 实施步骤

### 第一阶段:token 估算工具

#### Step 1:新建 `app/agents/token_budget.py`

纯函数模块,无副作用,易测。

- **`estimate_tokens(text: str) -> int`**:近似 token 计数
  - 中文字符(CJK Unicode 范围):约 1 字 ≈ 1 token(保守),计数 `len(cjk_chars)`
  - 英文/ASCII:约 4 字符 ≈ 1 token,计数 `len(ascii_chars) // 4`
  - 混合取两者之和向上取整 + 1(保守偏高,宁可早截断)
- **`estimate_messages_tokens(messages: list) -> int`**:对一组 LangChain message 求 token 总和(含 role 开销,每条 +4 token 固定开销,对齐 OpenAI 官方说明)
- **常量**:`CONTEXT_TOKEN_BUDGET = 24000`(预留 8k 给 system + 新消息 + 输出)、`RESERVE_FOR_REPLY = 4096`、`MIN_HISTORY_MESSAGES = 6`(至少保留最近 3 轮,即使超预算也不少于 6 条)
- **`truncate_history(messages, budget, system_prompt) -> list`**:核心截断函数
  - 计算总 token(system + history + 新消息预估)
  - 若超预算:从最旧的消息开始丢弃,直到 fit;但**永不少于 `MIN_HISTORY_MESSAGES`** 条
  - 返回截断后的 message 列表

### 第二阶段:graph.py + chat.py 接入

#### Step 2:graph.py stream_agent 加超时

- **改什么**(`app/agents/graph.py` `stream_agent`):
  - 在 `agent.astream_events(...)` 外层包 `asyncio.wait_for(..., timeout=60)`,整体超时
  - 更细的做法(可选):用 `asyncio.timeout` + chunk 间隙超时(本次先做整体超时,简单可靠)
  - 超时抛 `TimeoutError`,由 chat.py 的 `except Exception` 捕获,前端收到 `{"error":"LLM 响应超时"}` 而非无限挂起
- **import**:`import asyncio`

#### Step 3:chat.py 用 token_budget 截断历史

- **改什么**(`app/api/v1/chat.py` `chat_stream`,L76-82 的 history 拼接段):
  ```python
  from app.agents.token_budget import truncate_history, estimate_tokens
  history_msgs = await MessageRepository(db).list_for_conversation(conv.id, conv.tenant_id)
  history = [ ... 现有转换 ... ]
  # 按 token 预算截断(保留最近的)
  history = truncate_history(history, CONTEXT_TOKEN_BUDGET, agent.system_prompt)
  ```
- **Repository 加 limit(防御性)**:`list_for_conversation` 加 `limit: int = 200` 参数,默认只拉最近 200 条(避免极端情况一次拉几千条)。这不是截断逻辑(截断靠 token),只是防御性 limit。

#### Step 4:assistant 回复落库容错

- **改什么**(`app/api/v1/chat.py` `event_source`):
  - 当前:异常时 `return`(L113),assistant 回复**完全不落库** → 历史断档
  - 改为:异常分支里,若 `full_reply` 已有内容(部分生成),**仍落库部分回复**(标 role=assistant,content=已生成部分 + 末尾 `[生成中断]`),保证历史连续
  - 空回复则不落库(避免空 assistant 消息)
- **效果**:对话历史不再出现"user 有问 assistant 没答"的断档

---

### 第三阶段:测试

#### Step 5:新建 `tests/test_token_budget.py`(纯函数单测)

参照 `tests/test_validation_errors.py`(纯函数单测模式)。用例:
- **estimate_tokens**:空串=0;纯中文("你好世界"6字)≈ 6;纯英文("hello world"11 字符)≈ 3;混合取保守值
- **estimate_messages_tokens**:多条 message 求和 + 固定开销
- **truncate_history 正常不截断**:预算充足时原样返回
- **truncate_history 截断**:构造超预算历史 → 断言返回的消息数减少、最旧的消息被丢弃、最近的保留
- **truncate_history 最小保留**:即使严重超预算,返回不少于 `MIN_HISTORY_MESSAGES`
- **truncate_history 保留 system**:system_prompt 不计入截断目标(它由 messages_modifier 注入,不在 history 列表里)

#### Step 6:更新 `tests/test_chat.py`

- 加 `test_truncate_history_called_on_long_conversation`:mock `list_for_conversation` 返回 50 条历史,断言 `stream_agent` 收到的 `history` 参数长度 < 50(被截断)
- 加 `test_assistant_partial_reply_persisted_on_error`:mock `stream_agent` 抛异常中途,断言 `append_message("assistant", ...)` 仍被调用(部分回复落库)
- 加 `test_llm_timeout_yields_error_frame`:mock `stream_agent` 挂起,断言 SSE 返回 `{"error": "...超时"}`

#### Step 7:后端总验证

- `./init.sh` 全绿(ruff + pytest,含新测试,无回归)
- 无 schema/migration 改动 → 无需 CI migrations 守门(Repository limit 参数不改 schema)

---

### 第四阶段(可选,用户决定):真实长对话验证

#### Step 8:真实跑通长对话(需 DeepSeek key + docker)

- 用真实 DeepSeek key,构造一个 agent,连续发 40+ 轮消息(每轮内容较长)
- 验证:对话不崩溃(LLM 不返回 context length exceeded);Token 计数日志输出(可选:在 stream_agent 加 debug log)
- 证据写入 evidence

> 此阶段可选。阶段 1-3 用离线测试(monkeypatch stream_agent)已覆盖逻辑,阶段 4 是"真实长对话不崩"的端到端确认。

---

## 验收标准

1. **truncate_history 正确工作**:纯函数单测覆盖(正常/截断/最小保留/system 保留)
2. **长对话不崩**:构造 50 条历史,`stream_agent` 收到的 history 被截断(测试断言)
3. **LLM 超时保护**:stream_agent 超时 → SSE 返回 error frame(不挂死)
4. **assistant 回复容错**:流式中途失败 → 部分回复落库(无历史断档)
5. `./init.sh` 全绿(ruff + pytest,含新测试)
6. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 近似 token 估算不准(偏高/偏低) | 保守偏高(宁可早截断不晚截断);MIN_HISTORY_MESSAGES 兜底保证至少 3 轮;后续可换 tiktoken 精确化 |
| 截断导致丢失早期重要信息 | 滑动窗口是"够用"方案;**对话摘要/压缩**是后续增强(见边界,本任务不做) |
| Repository 加 limit 改签名影响调用方 | `list_for_conversation` 当前 2 个调用点(chat.py + conversation_service.history);history 端点全量返回是 API 契约,limit=200 足够大不影响正常使用 |
| asyncio.wait_for 与 astream_events 协作 | astream_events 是 async generator,wait_for 包整个 for 循环(用 `asyncio.timeout` 上下文管理器更优,Python 3.11+;项目 Python 版本需确认,若 <3.11 用 wait_for) |

### 不做的事(边界)

- **不做对话摘要/压缩**:即"把早期对话用 LLM 摘要成一段,再拼近期原文"——这是更高级的 context 工程,侵入性大(要加 summary 表 + 异步摘要任务),本任务只做滑动窗口
- **不引入 tiktoken**:额外依赖,且 DeepSeek 无官方 tokenizer
- **不做 per-model 动态 context 预算**:不查 `/models` 的 context_length,用固定常量(后续可增强)
- **不改 Message 表结构**:不加 token_count 字段(那是 token 用量计量任务的范围)
- **不改 SSE 协议**:不加分页/游标(历史 API 仍全量返回,截断只在喂给 LLM 时做)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 全量拉取根因 | `app/repositories/conversation.py:32` `list_for_conversation` |
| 全量拼接根因 | `app/api/v1/chat.py:76-82` |
| 全量喂 agent | `app/agents/graph.py:118` |
| 无超时 | `app/agents/graph.py:119` `astream_events` |
| assistant 落库时机 | `app/api/v1/chat.py:115-118`(流结束后才存) |
| user 先存库 | `app/api/v1/chat.py:72` |
| 纯函数单测范式 | `tests/test_validation_errors.py` |
| chat mock 范式 | `tests/test_chat.py:33-52`(_mock_chat + fake_stream) |
| Service 范式 | `app/services/conversation_service.py` |
| LangChain message 类型 | `langchain_core.messages`(HumanMessage/AIMessage/SystemMessage) |
| DeepSeek context window | deepseek-chat 32K(https://api-docs.deepseek.com/) |
