# 计划:复合查询会话(Fan-out + Synthesize 模式)

> 对应 feature_list.json 的 `id`: `composite-chat`
> 状态: not_started(2026-07-28 立项,PRD 草案)
> 优先级: 72(当前 feature_list 最高为 71 = principal-scope-doc-alignment,已 passing;新设 72 占最高位)
> 前置: 无(独立增量模块);**与 `multi-agent-orchestration`(priority 58 ✅ 已 passing)共存互补**,不改其契约
> 总纲: 本计划是独立 feature,不隶属 plan-mvp-completion-overview.md(后者已收口)

---

## 一、背景:Supervisor 解决「问对人」,缺「综合多人见解」

### 现状(2026-07-28 取证,已核实)

- `app/agents/graph.py` 已实现 **Supervisor 模式**(`build_orchestrator` / `stream_orchestrator`,priority 58 passing):`START → supervisor(LLM 路由) → 选中【一个】specialist → END`,单轮不循环
- 单 agent 会话管线成熟:`stream_agent` + `/chat/stream`(SSE 流式)+ `ConversationService`(持久化)+ `BillingService`(N+1 笔 `UsageEvent` 计费)+ `permission_service.require`(权限门控)
- 知识库 RAG(`retrieve_knowledge` 工具,租户级)、LLM 配置解析(`llm_config_service.get_effective`,tenant>platform>env)、wallet 余额门控(`has_balance` + super_admin 旁路)均已就绪
- `Conversation` / `Message` 表已稳定,`Message.role` 联合类型在前端 `types.ts` 收紧为 `'user'|'assistant'`

### 缺口(用户场景驱动)

连锁门店 SaaS 场景存在「跨领域综合调研」需求——例:总部要做「本月各门店服务复盘」,需同时获取健康顾问/预约专员/产品专家三方面见解再综合。Supervisor 只能选**一个** specialist,无法并行问**全部**再综合。

### 设计溯源

本计划借鉴 StorePilot 项目验证过的「三 pass 流水线」(Pass1 解析+权限门控 → Pass2 并行 fan-out 全部 agent → Pass3 synthesize 综合),落到本项目复用现有基建,与 Supervisor 共存。

### 目标

1. **复合查询会话**:用户多选 N 个 agent + 一个问题 → 并行问全部 → synthesize 综合答案
2. **持久化为新类型会话**:`Conversation.kind=composite`,可查看历史、可续问(对齐本项目「会话=持久化」惯例)
3. **与 Supervisor 互补共存**:Supervisor 走 `/chat/stream`(单 agent 路由),Composite 走新 endpoint(并行 fan-out),两者独立、互不污染
4. **向后兼容**:`Conversation.kind` 默认 `single`,现有单 agent 会话零回归

---

## 二、技术可行性(已 grep 现有代码核实)

| 复用项 | 现有位置 | 复用方式 |
|---|---|---|
| 单 agent 执行(非流式) | `stream_agent`(`app/agents/graph.py:183`) | 并行调 N 次,**只取末尾 `{"usage", "model"}` dict 前的 str 拼接结果**,不消费 SSE 流 |
| 权限门控 | `permission_service.require` | 逐 agent `require(conversations:chat)`,fail-fast |
| 多租户隔离 | `AgentRepository.get_for_tenant` | 解析阶段每 agent 必走,跨租户 404 |
| LLM 配置 | `llm_config_service.get_effective` | synthesize 复用首个 agent 的 model |
| 计费 | `BillingService.charge` + `_record_usage` | N+1 笔照搬 `/chat/stream` 模式 |
| wallet 门控 | `has_balance` + super_admin 旁路 | 开跑前预检,不足 403(非 SSE error) |
| 会话持久化 | `ConversationService` | 复用 `create_or_get` / `append_message`,加 `kind` 区分 |

**新增**:1 个 alembic migration(2 字段)+ 1 个 `composite_query` 编排函数 + 1 个 endpoint + 1 个前端模式切换组件。

### 关键技术决策(2026-07-28 AskUserQuestion 锁定)

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| 1 | 会话建模 | 复用 `Conversation` + `kind` 字段 + `Message.fragments` JSONB | 铁律第 6 条:按需加表,不预建空架子;向后兼容 |
| 2 | 并行编排 | `asyncio.gather` + 新 `composite_query` 函数 | Fan-out 无路由分支,StateGraph 过度设计;不污染 `stream_agent` |
| 3 | synthesize LLM | 首个 agent 的 model + 请求体可选覆盖 | 对齐 StorePilot + 租户级配置天然合理 |
| 4 | 权限门控 | 逐 agent `require(conversations:chat)` fail-fast | 项目铁律 + 复用现有权限对象 |
| 5 | 计费 | N+1 笔 UsageEvent + 预检 wallet + super_admin 旁路 | 照搬 `/chat/stream` 模式 |
| 6 | 前端形态 | `chat-page.tsx` 加模式切换 | 复用 Conversation 建模 → 不割裂体验 |
| 7 | 错误隔离 | per-agent try/except,失败仍返回 fragment | 对齐 StorePilot + Message.status 语义 |
| 8 | fragments 存储 | Message 加 `fragments` JSONB 字段 | 不破现有 `role: user\|assistant` 联合类型 |
| 9 | 返回形态 | 纯 JSON 一次性返回 | 简单、可预测、计费清晰;N 流交错 SSE 复杂 |
| 10 | 知识库 | 维持租户级,不引入用户私有层 | 范围控制;复用现有 `retrieve_knowledge` |

---

## 三、实施步骤(5 阶段,拟拆 4 切片)

### 阶段 1:后端数据层(切片 01)

#### Step 1:`Conversation` 模型加 `kind` 字段(`app/models/agent.py`)

- `kind: Mapped[str] = mapped_column(String(16), default="single", server_default="single")`
- 取值:`single`(默认,向后兼容)| `composite`
- **不加索引**:`kind` 过滤场景未定(如"只看复合会话"),按"按需加索引"铁律不预建;若日后有按 kind 过滤的需求再补(参照 partial index 惯例)
- **`Conversation.agent_id` 语义(关键决策)**:`agent_id` 是 NOT NULL FK,**不改 nullable**。Composite 会话【新建时】填**首个 agent_id**(`agents[0].id`)作为"主 agent / 会话归属";【续接时】保留原 conv.agent_id(create_or_get 续接分支不读此参数)。理由:
  1. 不破坏现有 NOT NULL 约束。**注意:全仓库 grep 无任何 `agent_id` GROUP BY 统计**(核实 `conversation.py`/`usage_event.py`/`dashboard.py` 均无),`dashboard_service` 不按 agent 维度聚合,故填 agents[0] 对现有 dashboard **零影响**;若未来引入 per-agent 统计,需改用 fragments 聚合(超范围)
  2. 全部 N 个 agent 记录在 `Message.fragments`(每 fragment 含 `agent_id`+`agent_name`+token 三项),`Conversation.agent_id` 只是"会话归属点",不是"参与 agent 全集"
  3. 与现有单 agent 会话语义一致(`agent_id` = 归属),前端会话列表点击进对话时,复合会话用 `conversation.kind=="composite"` 切换模式,不依赖 `agent_id` 选单
- 无需改 `__table_args__`(已有 tenant_created_at 索引,与新字段无冲突)

#### Step 2:`Message` 模型加 `fragments` 字段(`app/models/message.py`)

- `fragments: Mapped[list | None] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=True, default=None)`
- 结构(复合查询的 assistant 消息才填充,普通消息恒 None):
  ```json
  [{
    "agent_id": "abc123",
    "agent_name": "健康顾问",
    "snippet": "该 agent 的原始回答全文",
    "status": "completed",   // completed | failed
    "error": null,            // failed 时填错误文本
    "model": "deepseek-chat",
    "input_tokens": 50,       // 切片 03 计费读取,见 M3 契约
    "output_tokens": 73,
    "total_tokens": 123
  }]
  ```
- 复用 `Conversation.tags` 同款 `JSONB().with_variant(JSON, "sqlite")` 双 DB 惯例(已在 `agent.py:120-124` 验证);fragment 含 input/output/total 三项 token 是切片 03 计费契约(否则 prompt/completion 列全零)

#### Step 3:Alembic 迁移

- 文件:`alembic/versions/2026_07_28_HHMM_<12hex>_add_composite_chat.py`
- **模板照本项目实际写法**(`2026_07_26_1100_5565cf1e81bd_*.py` 已核实):
  ```python
  from collections.abc import Sequence
  from alembic import op
  import sqlalchemy as sa

  revision: str = "<12hex>"
  down_revision: str | Sequence[str] | None = "5565cf1e81bd"  # 当前 head
  branch_labels: str | Sequence[str] | None = None
  depends_on: str | Sequence[str] | None = None
  ```
- `up`:
  ① `op.add_column("conversations", sa.Column("kind", sa.String(16), server_default="single", nullable=False))`
  ② `op.add_column("messages", sa.Column("fragments", postgresql.JSONB(astext_type=sa.Text()), nullable=True))` — **migration 层用 `postgresql.JSONB` 无 variant**,与既有 `b2c3d4e5f6a7_add_conversation_management_columns`(conversations.tags 迁移)写法一致;SQLite 兼容性由模型层 `with_variant(JSON,"sqlite")` 在 `create_all` 测试路径覆盖(本项目测试不跑 alembic upgrade,见 `conftest.py:175` 的 `create_all`);`alembic check` 在 PG 上比对,variant 只影响 SQLite 故 PG 端不 drift
  ③ **backfill 旧行(防御性 no-op)**:`op.execute("UPDATE conversations SET kind='single' WHERE kind IS NULL")` — 注:`add_column` 带 `server_default='single'` 在 PG/SQLite 上**已自动回填旧行**(标准 SQL `ALTER TABLE ADD COLUMN NOT NULL DEFAULT` 行为),此 UPDATE 仅作双保险(防 server_default 被遗漏或未来 schema 演进),实际为 no-op
- `down`:对称反向 — `op.drop_column("messages","fragments")` + `op.drop_column("conversations","kind")`
- **同步注册**:`tests/conftest.py` 无需改(未新增 model,仅加字段);`alembic/env.py` 无需改(模型已在 `agent.py`/`message.py` 导入)

#### Step 4:Schema 层(`app/schemas/conversation.py`)

- `ConversationRead` 加 `kind: Literal["single","composite"] = "single"`(Pydantic 默认值 + Literal 收紧双保险:即便有 NULL 旧数据也能 round-trip,且防写入拼写错误)
- `MessageRead` 加 `fragments: list[dict] | None = None`
- 新建 `CompositeRequest`:
  ```python
  class CompositeRequest(BaseModel):
      agent_ids: list[str] = Field(..., min_length=1, max_length=8)  # 最多 8 agent(重复 id 由 endpoint 去重,见切片 03)
      message: str = Field(..., min_length=1)
      conversation_id: str | None = None  # 续接已有复合会话(切片 03 加 kind 一致性校验)
      customer_id: str | None = None
      synthesize_model: str | None = None  # 可选覆盖综合模型
  ```
- 新建 `CompositeFragment` + `CompositeResponse`(fragment 必须含 input/output/total 三项 token,见 M3 计费契约):
  ```python
  class CompositeFragment(BaseModel):
      agent_id: str; agent_name: str; snippet: str
      status: Literal["completed","failed"]; error: str | None
      model: str | None = Field(None, max_length=64)
      input_tokens: int | None; output_tokens: int | None; total_tokens: int | None

  class CompositeResponse(BaseModel):
      conversation_id: str
      synthesis: str
      fragments: list[CompositeFragment]
  ```

### 阶段 2:后端编排引擎(切片 02 — 核心)

#### Step 5:`composite_query` 函数(`app/agents/graph.py` 新增,与 `stream_agent` 并列)

签名(非 stream,返回 dict):

```python
async def composite_query(
    *, user_id, tenant_id, db, api_key, base_url,
    agents: list[Agent],          # 已解析+权限校验过的 Agent ORM 行
    message: str,
    synthesize_model: str | None = None,
) -> dict:
    """
    Returns: {
        "synthesis": str,
        "fragments": [{agent_id, agent_name, snippet, status, error, model, total_tokens}],
        # synthesize 阶段的独立 usage(用于第 N+1 笔 UsageEvent)
        "synthesize_usage": {"input_tokens": int, "output_tokens": int, "total_tokens": int, "model": str},
        # 全部 N+1 轮累加(用于 assistant Message 的 total_tokens 列)
        "usage_total": {"input_tokens": int, "output_tokens": int, "total_tokens": int},
    }
    """
```

实现要点:
- **db session 并发安全(关键约束)**:SQLAlchemy `AsyncSession` **不是并发安全的**——N 个 agent 的 ReAct 若各自调 `retrieve_knowledge` 工具(查 db),共享同一 session 会报错。
  - **选定方案 A**:fan-out 阶段每 agent 创建**独立 session**(从 `_get_session_factory()()` 新开,见 `database.py:54`),各自独立事务。保留 per-agent RAG 能力(composite 的核心价值)
  - **强约束**:`_invoke_agent_once` 必须用 `session = AsyncSessionLocal()` 新开,并把该 session 传给 `_build_tenant_tools(user_id, tenant_id, session)` —— 不能复用主 session 的工具闭包(否则静默违反并发安全,且测试难抓)
  - **commit 时序**:user message 在 composite_query 前 commit(`append_message` 已 commit);agent 各自独立 session 独立 commit;synthesize 用主 session(单次调用无并发问题)
  - **连接池风险**:N+1 个 session 并发借连接,`create_async_engine`(`database.py:46`)用默认 pool_size=5;8 agent + 主 session 可能 `pool exhausted`。MVP 缓解:测试验证 ≤3 agent 不触池上限;若生产要支持 8 agent 需调 pool_size(超范围,记风险)
- **Pass 2(fan-out + 结果落地外部容器)**:
  ```python
  fragments: list[dict] = []  # 外部容器,task 内部 append,超时也能取
  async def _run_one(a):
      try:
          frag = await _invoke_agent_once(a, ...)  # 成功/失败都返回 fragment dict
          fragments.append(frag)
      except Exception as e:
          fragments.append({"agent_id": a.id, "agent_name": a.name, "snippet": "",
                            "status": "failed", "error": str(e), ...})
  # return_exceptions=False:因内部 try/except 已转成正常返回值,gather 永不见异常;
  # 不用 return_exceptions=True 是因我们要带语义的 fragment dict(含 agent_name/error),非原始 Exception
  ```
  - **为什么 fragment 要 append 到外部 list 而非仅 return**:见 Step 6 超时 fail-open —— 超时会让 gather 抛 TimeoutError,返回值取不到,但外部 list 已 append 的能保留
- `_invoke_agent_once`:**不调 `stream_agent`**(它是 SSE 流式 yield 契约),而是新写 —— 内部**为该 agent 独立 build ChatOpenAI**(用该 agent 自己的 model/temperature/max_tokens,经 `_build_llm_kwargs`)+ create_react_agent + **`astream_events(version="v2")`**(非 `ainvoke`)→ 累加**每一轮** `on_chat_model_end` 的 `usage_metadata`(ReAct 可能 think→tool→think 多轮,`ainvoke` 只返回末轮 usage 会**少计 token**;必须用 `astream_events` 累加全轮,与 `stream_agent` 同款机制)。拼接所有 `on_chat_model_stream` 的 `AIMessageChunk.content` 作 snippet。**复用 `_build_llm_kwargs` / `_system_msg`**(纯函数)+ **`_build_tenant_tools`**(闭包工厂,为每 agent 构建绑定其独立 session 的工具闭包)
  - ⚠️ **不用 `ainvoke` 的原因**:虽然 fan-out 不需要流式给前端,但 ReAct 多轮调用的 token 必须累加——`ainvoke` 只返回最终消息的 `usage_metadata`(末轮),会漏掉中间轮(如 tool-calling 前的 reasoning 轮)。用 `astream_events` 累加每轮 `on_chat_model_end` 是唯一准确方式,代价是 agent 内部仍走流式(但 `_invoke_agent_once` 对外仍是同步返回 dict,不暴露流)
- **Pass 3(synthesize)**:把所有 fragment 的 snippet(失败的填 `[此 agent 失败: {error}]`)拼进 synthesize prompt,调一次 LLM(`synthesize_model or agents[0].model`),`max_tokens=600`(对齐 StorePilot)
- **per-agent token 上限**:`max_tokens` 取值逻辑——`agent.max_tokens`(若已设) else `300`(fallback)。**300 是 fallback 默认值,非硬上限**。**注意行为差异**:同一 agent 在 `/chat/stream`(max_tokens=None → provider 默认,DeepSeek 通常 4096)和在 `/chat/composite`(None → 300)输出长度不一致,这是**有意的**(composite 是 N+1 成本需限长);agent 显式设了 max_tokens 则两者一致

#### Step 6:错误隔离与降级

- 单 agent LLM 失败 → 该 fragment `status="failed"` + `error=str(e)`,其他 agent 继续
- **synthesize 失败降级**:`synthesis` 字段返回 `_fallback_synthesis(fragments)`(纯函数,可单测)+ response 仍 200。降级拼接格式明确定义:
  ```python
  def _fallback_synthesis(fragments: list[dict]) -> str:
      parts = []
      for f in fragments:
          if f["status"] == "completed":
              parts.append(f"## {f['agent_name']}\n{f['snippet']}")
          else:
              parts.append(f"## {f['agent_name']}\n[此 agent 失败: {f['error']}]")
      return "\n\n---\n\n".join(parts)
  ```
  此时 `synthesize_usage` 填 `{"input_tokens":0,"output_tokens":0,"total_tokens":0,"model":synthesize_model or agents[0].model}`(零消耗)
- **超时门控(fail-open 正确实现)**:`asyncio.timeout` + `gather` 组合下,超时会取消所有 task 且 gather 抛 TimeoutError(返回值取不到)。**正确做法**:用外部 list 容器(Step 5 已定义 `fragments`)+ 超时 except 分支取容器内容:
  ```python
  try:
      await asyncio.wait_for(
          asyncio.gather(*[_run_one(a) for a in agents]),
          timeout=N * 30 + 60,
      )
  except asyncio.TimeoutError:
      pass  # 已完成的 task 已 append 到 fragments,未完成的跳过(降级)
  # fragments 此时含所有已完成 agent 的结果,继续 synthesize
  ```
  ⚠️ 不要用裸 `async with asyncio.timeout(...)` 包 gather —— 那会取消所有 task 且无法保留已完成结果

### 阶段 3:后端 API + 计费 + 测试(切片 03)

#### Step 7:新 endpoint(`app/api/v1/chat.py` 加,与 `/chat/stream` 并列)

```python
@router.post(
    "/composite",
    dependencies=[Depends(require_permission("conversations", "chat"))],
)
async def composite_chat(payload: CompositeRequest, user, db):
    # 1. 解析 + 权限门控(Pass 1)
    #    agent_ids 去重(保序,防重复 fan-out 浪费 token + fragments 重复)
    unique_ids = list(dict.fromkeys(payload.agent_ids))
    agents = []
    for aid in unique_ids:
        a = await AgentRepository(db).get_for_tenant(aid, user.tenant_id)
        if a is None: raise HTTPException(404, ...)  # 跨租户或已软删 agent 均 404
        await permission_service.require(user.user_id, user.tenant_id, "conversations", "chat", platform_role=user.platform_role)
        agents.append(a)
    # 2. wallet 预检(super_admin 旁路)
    #    ⚠️ 语义选择:Composite 采用「无钱包=阻止」(对齐 has_balance 注释),
    #    区别于 /chat/stream 的「无钱包=放行」(degrade gracefully)。
    #    理由:Composite 是 N+1 倍 token 消耗的高成本操作,应更严格。
    #    HTTP 402 是项目首例(项目惯例是 BizError→400/403),前端 endpoints.ts
    #    需对 /chat/composite 的 402 单独 catch 展示充值引导(见切片 04)。
    if user.platform_role != "super_admin":
        if not await BillingService(db).has_balance(user.tenant_id):
            raise HTTPException(402, "token 余额不足")
    # 3. 创建/续接 composite 会话
    #    ⚠️ 续接时 kind 一致性校验(H2):create_or_get 续接分支需加校验,
    #    当传入 kind 与已有 conv.kind 不符 → NotFoundError(404,不泄露存在性,
    #    与跨租户 404 一致)。防 single↔composite 串用污染。
    #    agent_id 仅在【新建】时填 agents[0].id;续接时保留原 conv.agent_id。
    conv = await ConversationService(db).create_or_get(
        user_id=user.user_id, tenant_id=user.tenant_id,
        agent_id=agents[0].id,  # 新建时填主 agent;续接时 create_or_get 忽略此参数
        conversation_id=payload.conversation_id, kind="composite",
        platform_role=user.platform_role, first_message=payload.message,
        customer_id=payload.customer_id)
    await conv_service.append_message(conv.tenant_id, conv.id, "user", payload.message)
    # 4. composite_query(Pass 2+3)
    llm_cfg = await llm_config_service.get_effective(db, user.tenant_id)
    result = await composite_query(agents=agents, api_key=llm_cfg.api_key, ...)
    # 5. 持久化 assistant 消息(fragments 存入 Message.fragments)
    msg = await conv_service.append_message(
        conv.tenant_id, conv.id, "assistant", result["synthesis"],
        prompt_tokens=result["usage_total"]["input_tokens"],
        completion_tokens=result["usage_total"]["output_tokens"],
        total_tokens=result["usage_total"]["total_tokens"],
        model=result["synthesize_usage"]["model"],
        fragments=result["fragments"])
    # 6. N+1 笔 UsageEvent + 计费
    #    ⚠️ 不复用现有 _record_usage(签名要 Agent 对象,见 chat.py:56-63);
    #    composite 写专用 _record_composite_usage(直接收 agent_id: str|None)。
    #    每笔 UsageEvent.agent_id:fragment 笔=frag.agent_id;synthesize 笔=None。
    #    全部 N+1 笔的 message_id 都指向同一条综合 Message;customer_id 透传 conv.customer_id。
    #    ⚠️ 事务语义(H4):record + charge 必须【配对原子】—— record commit 后紧跟 charge,
    #    charge 失败 rollback 只影响本笔 WalletTransaction,不影响已 commit 的 UsageEvent;
    #    每笔处理前确保 session 无 pending(用 db.flush() 或每笔独立事务)。
    #    best-effort:每笔 try/except + logger.exception 留审计痕(不裸吞,防静默 bug)。
    for frag in result["fragments"]:
        await _record_composite_usage(
            db, conv, msg, agent_id=frag["agent_id"], user=user,
            prompt_tokens=frag["input_tokens"],
            completion_tokens=frag["output_tokens"],
            total_tokens=frag["total_tokens"], model=frag["model"])
    # synthesize 笔(agent_id=None)
    su = result["synthesize_usage"]
    await _record_composite_usage(
        db, conv, msg, agent_id=None, user=user,
        prompt_tokens=su["input_tokens"], completion_tokens=su["output_tokens"],
        total_tokens=su["total_tokens"], model=su["model"])
    return CompositeResponse(conversation_id=conv.id, synthesis=result["synthesis"], fragments=result["fragments"])
```

- **HTTP 402 Payment Required** 用于余额不足(非 SSE,可用真实 HTTP code;区别于 `/chat/stream` 的 SSE error frame)。**402 是项目首例**(项目惯例是 BizError→400/403),前端 `endpoints.ts` 需对 `/chat/composite` 的 402 单独 catch 展示充值引导(见切片 04)
- `ConversationService.create_or_get` 需加 `kind` 参数(加在末尾 `customer_id` 后,现有调用全用 keyword 传参故零改动)+ **续接分支加 kind 一致性校验**(H2:传入 kind 与 conv.kind 不符 → NotFoundError 404,防 single↔composite 串用)
- `ConversationService.append_message` 需加 `fragments` kwarg(加在现有 `error` 后,保持现有 4 处调用零改动)
- **新写 `_record_composite_usage`**(不复用 `_record_usage`):签名 `(db, conv, msg, *, agent_id: str | None, user, prompt_tokens, completion_tokens, total_tokens, model)` —— 关键差异是接 `agent_id` 而非 `Agent` 对象,且允许 None(synthesize 笔)。逻辑照搬 `_record_usage`,但 except 用 `logger.exception(...)` 留审计痕(不裸吞,N+1 笔放大静默失败概率)
- **扣费事务语义(H4)**:record + charge **配对原子**(record commit → charge,charge 失败 rollback 只影响本笔 WalletTransaction);每笔处理前确保 session 无 pending;N+1 笔串行(不并行,FOR UPDATE 已串行化);整体 best-effort 不阻塞 response

#### Step 8:后端测试(新建 `tests/test_composite_chat.py`,约 14 测)

- **纯函数**:`composite_query` 的 synthesize prompt 拼接 / 失败 fragment 降级 / token 累加
- **测试范式(照 `test_chat.py` 实际写法,非 conftest 预种)**:本项目 `conftest.py` **不预种 conversation/agent**,每个测试在 fixture 内自建 —— `app_client.post("/api/v1/agents/", json={...})` 建 agent,再 mock LLM 调端点。composite 测试照此范式:
  - `monkeypatch.setattr(chat_route, "composite_query", fake_composite)` 替换编排函数(照 `test_chat.py:47` 的 `monkeypatch.setattr(chat_route, "stream_agent", fake_stream)` 范式)
  - 测试内 `app_client.post("/api/v1/agents/", ...)` 建 N 个 agent,再 `POST /chat/composite`
  - happy path:3 agent 全成功 → synthesis + 3 fragments + 4 笔 UsageEvent(3+1)
  - 部分失败:1 agent 抛错 → 该 fragment failed,其他正常,synthesis 降级提示
  - synthesize 失败 → synthesis 降级为 fragments 拼接
  - wallet 不足 → 402(member)/ 旁路(super_admin)
  - 权限:member 无 conversations:chat → 403
  - 跨租户:agent_ids 含别租户 agent → 404
  - **agent_ids 含已软删 agent → 404**(软删过滤在 `get_for_tenant`,与跨租户同 404)
  - **agent_ids 含重复 id → 去重后正常返回**(fragments 不重复,计费不翻倍)
  - agent_ids 超 8 个 → 422
  - agent_ids 为空 → 422
  - **续接 kind 一致性(H2)**:传 single 会话 id 给 /chat/composite → 404(不泄露存在性);composite 会话 id 正常复用
  - 持久化:返回后 GET /conversations/{id}/messages 含 fragments
- **计费**:N+1 笔 UsageEvent 总 token 等于 composite_query 返回的 usage_total
- **计费准确性(多轮 usage)**:mock 的 `_invoke_agent_once` 触发 2 轮 LLM 调用(think→tool→think),验证 fragment 的 total_tokens = 两轮之和(防 ainvoke 漏计回归)
- **customer 透传**:composite 带 customer_id 时,N+1 笔 UsageEvent 的 customer_id 都 = 该 customer(`sum_tokens_for_customer` 验证)
- **扣费容错(H4)**:mock 第 2 笔 `charge` 抛异常,验证第 1/3/4 笔 UsageEvent + WalletTransaction 仍正确持久化(best-effort 不阻塞)

### 阶段 4:前端(切片 04)

#### Step 9:`types.ts` + `endpoints.ts`

- `Conversation` 加 `kind: ConversationKind`(`"single" | "composite"`,默认 `"single"`)
- `Message` 加 `fragments?: CompositeFragment[]` **+ `status?: "completed" | "failed"` + `error?: string | null`**(对齐后端 `MessageRead`,现有前端 Message 缺这俩字段,顺手补——单 agent 失败消息重试提示也依赖它)
- 新增 `CompositeFragment` / `CompositeRequest` / `CompositeResponse` interface
- `endpoints.ts` 加 `compositeChat(payload): Promise<CompositeResponse>`(POST `/chat/composite`,非流式 axios.post);**对 402 单独 catch 展示充值引导**(项目首例 402,与现有 403/422 处理分支不同)

#### Step 10:`chat-page.tsx` 加模式切换 + composite-mode.tsx 独立组件

- **state/逻辑边界(H6)**:`mode` state 由 **chat-page 持有**(Switch 在 header,决定是否渲染 `<CompositeMode>`);composite 的发送/结果渲染/fragments 折叠**全部封装在 composite-mode.tsx**。chat-page 仅加:
  - `const [mode, setMode] = useState<"single"|"composite">("single")`(**H5:默认 single,保 AC5 向后兼容**)
  - header 加 `<Switch checked={mode==="composite"} onChange={...}>` + 条件渲染 `{mode==="composite" && <CompositeMode .../>}`
  - 据此 chat-page **净增目标 ≤ 30 行**(原 50 行上限不现实,因 Switch + state + 条件渲染 + 导入)
- **Switch 组件(M7 已核实)**:`switch.tsx` 已存在,`agents-page.tsx:643` 已用于 orchestrator 开关(非"全项目未用")。chat-page 复用同款;**注意语义区别**:agents-page 的 is_orchestrator 是 Agent 级属性(建 agent 时设),chat-page 的 composite 是**会话级临时态**(不写 Agent 字段)
- `composite-mode.tsx`(文件名 kebab-case,export `CompositeMode`,照 `pages/bookings/` 惯例):
  - 多选 agent(现有 `Checkbox`):本租户非 orchestrator 的 agents
  - 输入框(现有 `Input`)+ 「发起复合查询」按钮 → `compositeChat` → loading(现有 `Skeleton`)→ 结果渲染
  - fragments 折叠:每条带 status badge(现有 `Badge`:✓ completed / ✗ failed)
- **composite 会话续问(M10)**:MVP 默认折叠 agent 多选区(沿用首次 agent_ids,从 fragments 读),只显输入框;用户可展开重选覆盖。或更简:MVP 不支持前端续问(只查看历史),后端 conversation_id 续接仅 API 层支持,明确写进「不做的事」

#### Step 11:会话列表区分 + 自动切模式

- 会话列表项加 `kind` 标识(composite 会话显示「复合」badge)
- `selectConversation` 接入点(chat-page.tsx:234):按 `conversations.find(c=>c.id===id)?.kind` 切 mode;**composite 模式下隐藏 header 的 agent Select + customer Select**(行 645-707),避免无意义的单 agent 下拉误导(后端 agent_id 仅是归属点)

### 阶段 5:验证 + ship-it(收尾)

#### Step 12:标准验证

- `./init.sh` → ruff + pytest 全绿(基线 + 新增 ~18)
- `cd frontend && npm run build` → 0 类型错误
- `cd frontend && npx oxlint src/` → 0 warnings
- `alembic check` → model/DB 同步

#### Step 13:真实 DeepSeek key 端到端验证

- **前置(M9 已核实)**:① `llm_config` 表有 platform/tenant 级行(api_key 非空),或 `.env` 的 `OPENAI_API_KEY` 存在(`get_effective` 从 DB 解析,fallback 到 env);② 若 agent 启用 RAG,需先 `POST /knowledge/documents` 灌测试文档并 index;③ docker aap-postgres + aap-logto-db 在跑
- 创建 3 agent(健康顾问 / 预约专员 / 产品专家,至少 1 个带 RAG)+ 发起复合查询「本月服务复盘建议」
- 验证:① 3 agent 并行回答 ② synthesize 综合 ③ fragments 折叠展示 ④ 计费 4 笔 UsageEvent ⑤ 历史可查看
- 向后兼容:普通单 agent 对话不受影响

### 阶段 5:验证 + ship-it(收尾)

#### Step 12:标准验证

- `./init.sh` → ruff + pytest 全绿(基线 + 新增 ~14)
- `cd frontend && npm run build` → 0 类型错误
- `cd frontend && npx oxlint src/` → 0 warnings
- `alembic check` → model/DB 同步

#### Step 13:真实 DeepSeek key 端到端验证

- `.env` 已有真实 key;docker aap-postgres 在跑
- 创建 3 agent(健康顾问 / 预约专员 / 产品专家)+ 发起复合查询「本月服务复盘建议」
- 验证:① 3 agent 并行回答 ② synthesize 综合 ③ fragments 折叠展示 ④ 计费 4 笔 ⑤ 历史可续问
- 向后兼容:普通单 agent 对话不受影响
- 真实结果写入 evidence

#### Step 14-16:ship-it 收尾

- 清理 + 审查 + commit + PR + CI 守门 + 合并 + 文档(feature_list.json evidence + progress.md Session)+ clean-state checklist 全勾

---

## 四、关键设计决策(基于已核实事实)

1. **不新建 CompositeSession 表**:Conversation 主体属性(tenant/user/title/tags)与复合会话一致,加 `kind` 字段区分即可(铁律第 6 条)
2. **不复用 `stream_agent` 做 fan-out**:`stream_agent` 是 SSE yield 契约,N 路并行流交错送前端会乱;新写 `_invoke_agent_once`(内部用 `astream_events` 累加每轮 usage —— ainvoke 只返回末轮会漏计多轮 token,见 AC2.5),但对外仍是同步返回 dict(不暴露流);复用其依赖的纯函数(`_build_llm_kwargs` / `_system_msg` / `_build_tenant_tools`)
3. **synthesize 复用首个 agent 的 model**:本项目 `llm_config_service` 是租户级解析,所有 agent 共享 provider/key,"首个 agent model" 实际就是租户有效配置;请求体可选覆盖给高级用户
4. **wallet 门控用 HTTP 402 而非 SSE error**:Composite 是 JSON 一次性返回,可用真实 HTTP code(区别于 `/chat/stream` 已发 200 后只能 SSE error)
5. **N+1 笔 UsageEvent 独立计费**:不预扣(预扣需退款逻辑,复杂度高),事后按实际用量扣 —— 与 `/chat/stream` 完全一致
6. **fragments 存 Message JSONB**:不破现有 `role: 'user'|'assistant'` 联合类型(若每 fragment 一条 Message 需扩 role 联合类型,前端 types 连锁改)
7. **复合查询走 `/chat/composite` 而非 `/chat/stream`**:两者契约不同(JSON vs SSE),独立 endpoint 互不污染
8. **前端抽独立组件**:`chat-page.tsx` 已 954 行,继续膨胀违反单文件 ≤500 行隐性规则;复合模式 UI 抽 `composite-mode.tsx`

---

## 五、风险与缓解

| 风险 | 缓解 |
|---|---|
| N 个 agent 并行延迟高 | MVP 接受;`asyncio.gather` 并行而非串行;最多 8 agent 上限 |
| token 消耗 N+1 倍 | 计费系统覆盖;每 agent ≤300 tokens;wallet 余额预检 |
| 并发 LLM 调用打到 provider 限流 | MVP 接受;后续可加 rate limiter(超范围) |
| synthesize 漏掉失败 agent 的维度 | synthesize prompt 显式标注 `[此 agent 失败]`,综合 LLM 诚实反映 |
| asyncio.gather 整体超时杀已完成 | 超时阈值 `N*30+60` 秒(fail-open);已完成的 fragment 仍返回 |
| `Conversation.kind` 旧数据 NULL | migration 含 backfill(`UPDATE ... SET kind='single'`)+ Pydantic `Field(default="single")` 双保险 |
| `Message.fragments` 普通消息负担 | nullable + default None;普通消息恒 None,无序列化开销 |
| `Conversation.agent_id` 对 composite 会话语义模糊 | 明确语义:填 `agent_ids[0]` 作为"主 agent/归属",全部 N agent 在 fragments;不改 NOT NULL 约束 |
| **dashboard 按 agent_id 统计偏差** | **已核实:全仓库无 agent_id GROUP BY 统计**(conversation/usage_event/dashboard repos 均无),填 agents[0] 对现有 dashboard **零影响**;若未来引入 per-agent 统计需改用 fragments 聚合(超范围) |
| **N+1 笔扣费的锁开销** | BillingService.charge 用 SELECT...FOR UPDATE;composite 串行扣 N+1 次(不并行,避免锁竞争);整体 best-effort,单笔失败不阻塞 |
| **方案 A 多 session 的 commit 时序** | agent 各自独立 session 独立 commit;composite_query 返回后主 session 再 append assistant msg + N+1 usage。user message 在 composite_query 前 commit(append_message 已 commit),agent 工具查询能读到租户数据(不依赖本次会话的 user msg) |
| **customer_id 透传到 N+1 笔 UsageEvent** | 若 composite 带 customer_id,综合调用也归属该 customer(`sum_tokens_for_customer` 会计入)。MVP 接受:composite 本就是为该 customer 服务的综合查询,计入合理;后续若需区分可加 `event_type` 列 |
| **ReAct 多轮 usage 漏计** | `_invoke_agent_once` 必须用 `astream_events` 累加每轮 `on_chat_model_end`(非 `ainvoke` 只取末轮);Step 5 已明确 |
| 前端 chat-page 膨胀 | 复合模式 UI 抽独立组件 `composite-mode.tsx`;模式切换用现有 `Switch`(无 tabs.tsx),不新增 shadcn 依赖 |
| 与 Supervisor 共存混淆 | 文档+UI 提示:Supervisor=问对人(单 agent 路由),Composite=综合多人 |
| `has_balance` 注释与 `/chat/stream` 行为既有矛盾 | 已知项目瑕疵:`has_balance` 注释说"无钱包=阻止",但 `/chat/stream` 实际"无钱包=放行"(degrade gracefully)。Composite 采用"阻止"语义(N+1 成本高更应严格),PRD Step 7 已注明,实施时不"修复"`/chat/stream` 的行为(超范围) |

---

## 六、不做的事(边界)

- ❌ Swarm 模式(无中心编排)
- ❌ 改现有 Supervisor(`stream_orchestrator` / `build_orchestrator` 零改动)
- ❌ 改现有单 agent `/chat/stream`(零回归)
- ❌ Fan-out 流式(N 流交错复杂,JSON 一次性返回)
- ❌ 知识库用户私有层(维持租户级)
- ❌ 跨租户 agent 协作(只本租户)
- ❌ Agent 自动生成/进化
- ❌ 复合会话的 specialist 关联表(请求体直接传 agent_ids,无预绑定)
- ❌ 实时 specialist 来源显示改 Supervisor 的 SSE 帧(超范围)

---

## 六点五、切片规划(4 切片,线性依赖无环)

> tracer-bullet 垂直切片:每切透 schema→API→test 所有层,可独立验证。对照 plan-booking-schedule-grid(6 切片)范式。
> EP3 实施从 frontier(切片 01)接 `/implement`,逐切片推进,清 context。

### 切片 01 — 后端数据层 + Schema(frontier)

**What to build**:复合会话的数据承载层就绪 —— `Conversation.kind` + `Message.fragments` 字段落地,migration 含 backfill 保证旧数据 round-trip,Pydantic schema 加字段。这一层完成后数据库能存复合会话,但还没有编排逻辑(无 API、无 composite_query)。

**Blocked by**:无(frontier,可立即开始)

**Status**:ready-for-agent

- [ ] `Conversation.kind` 字段添加(String16,server_default "single",无索引)
- [ ] `Message.fragments` 字段添加(JSONB nullable,模型层 `with_variant(JSON,"sqlite")` 双 DB)
- [ ] alembic migration:模板符合项目写法(`revision: str` 类型注解),up 含 backfill(`UPDATE ... WHERE kind IS NULL`,防御性 no-op),down 对称;**migration 层 `postgresql.JSONB` 无 variant**(照 `b2c3d4e5f6a7` tags 迁移惯例)
- [ ] `ConversationRead.kind` 加 `Literal["single","composite"] = "single"`(默认值 + Literal 收紧)
- [ ] `MessageRead.fragments` 加 `list[dict] | None = None`
- [ ] 新建 `CompositeRequest` / `CompositeFragment` / `CompositeResponse` schema;fragment 必须含 input/output/total 三项 token(切片 03 计费契约)
- [ ] **ConversationService 零改动**(切片 03 才加 kind/fragments kwarg),默认值由模型层 `default+server_default` 保证,不依赖 service 传参
- [ ] `./init.sh` 全绿(零回归,纯加字段)
- [ ] 单测:旧 Conversation(无 kind)经 schema round-trip 后 kind="single"
- [ ] **migration 手动验证(写 evidence)**:docker aap-postgres 上 `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` 幂等无错;`SELECT COUNT(*) FROM conversations WHERE kind IS NULL` = 0(项目无 migration 自动化测试,backfill 正确性靠此手动门)

### 切片 02 — 后端编排引擎 `composite_query`(核心)

**What to build**:复合查询的编排核心 —— `composite_query` 函数 + `_invoke_agent_once`(用 `astream_events` 累加每轮 usage,非 ainvoke)+ synthesize 阶段 + 错误隔离。纯函数 + 单元测试,不接 HTTP。完成后可通过 `await composite_query(...)` 拿到 `{synthesis, fragments, synthesize_usage, usage_total}`,但还没 endpoint 暴露。

**Blocked by**:切片 01(`Message.fragments` 字段就绪,fragment 结构定义稳定)

**Status**:ready-for-agent(blocked)

- [ ] `composite_query` 函数:签名 + 返回 dict 四键(synthesis/fragments/synthesize_usage/usage_total);**fragments 用外部 list 容器,task 内部 append**(超时 fail-open 前提)
- [ ] `_invoke_agent_once`:为每 agent 独立 build ChatOpenAI(用该 agent 自己的 model/temperature/max_tokens)+ `astream_events` 累加每轮 `on_chat_model_end` usage + 拼接 `AIMessageChunk.content`
- [ ] **每 agent 独立 session(方案 A 强约束)**:`session = _get_session_factory()()` 新开,传给 `_build_tenant_tools(user_id, tenant_id, session)`,不复用主 session 工具闭包
- [ ] fan-out 用 `asyncio.gather` 包在 `asyncio.wait_for(timeout=N*30+60)` 内,per-agent try/except 把失败转 fragment **append 到外部 list**(不抛出)
- [ ] synthesize 阶段:复用首个 agent 的 model(或请求体覆盖),失败 fragment 填 `[此 agent 失败]`,max_tokens=600
- [ ] **synthesize 失败降级**:`synthesis` 返回 `_fallback_synthesis(fragments)`(纯函数,格式见 Step 6),synthesize_usage 填零占位
- [ ] **超时 fail-open**:`asyncio.wait_for` 触发 TimeoutError 时 except pass,fragments 外部 list 已 append 的结果保留,继续 synthesize 降级
- [ ] 不调用 `stream_agent`(独立路径 `_invoke_agent_once`);复用 `_build_llm_kwargs`/`_system_msg`/`_build_tenant_tools`
- [ ] 单测覆盖:
  - mock LLM 跑 3 agent fan-out(全成功)
  - 1 agent 失败隔离(其他正常)
  - synthesize 失败降级(断言 `_fallback_synthesis` 输出格式)
  - **多轮(2 轮)usage 累加准确性**(fragment total = 两轮之和)
  - **超时降级**:mock 1 agent `asyncio.sleep` + 极小 timeout,验证已完成 fragment 保留 + synthesis 降级
  - **fan-out 并行性验证**:3 agent 各 `asyncio.sleep(0.1)`,总耗时 < 0.25s(串行会 ≈0.3s)
  - **token 上限三情况**:max_tokens=None → 300;=200 → 200;=1000 → 1000
- [ ] `./init.sh` 全绿

### 切片 03 — 后端 API + 计费 + 集成测试

**What to build**:`POST /chat/composite` endpoint 上线,用户能通过 HTTP 发起复合查询。含权限门控、wallet 预检、ConversationService 加 kind/fragments 参数、`_record_composite_usage`(N+1 笔计费,接 agent_id 非 Agent 对象)。完成后 curl/CLI 能调通,返回 JSON,计费 N+1 笔 UsageEvent。

**Blocked by**:切片 02(需要 `composite_query` 函数)

**Status**:ready-for-agent(blocked)

- [ ] `POST /chat/composite` endpoint,dependencies 复用 `conversations:chat` 权限
- [ ] Pass 1:`agent_ids` **去重保序**(`dict.fromkeys`)+ 逐 agent `get_for_tenant`(跨租户/软删均 404)+ `permission_service.require`,agent_ids 空/超 8 个 422
- [ ] wallet 预检:非 super_admin 且 `has_balance=False` → HTTP 402(项目首例,前端需单独 catch)
- [ ] `ConversationService.create_or_get` 加 `kind` 参数(末尾默认 single)+ **续接分支 kind 一致性校验**(H2:不符 → NotFoundError 404);`append_message` 加 `fragments` kwarg
- [ ] composite 会话新建时 `agent_id` 填 `agents[0].id`(续接保留原值);全部 N agent 在 fragments
- [ ] `_record_composite_usage`:新函数(不复用 `_record_usage`),接 `agent_id: str|None`;synthesize 笔 agent_id=None;except 用 `logger.exception`(不裸吞)
- [ ] **扣费事务语义(H4)**:record + charge 配对原子,charge 失败 rollback 只影响本笔 WalletTransaction;N+1 笔串行;每笔处理前 session 无 pending;customer_id 透传
- [ ] HTTP 集成测试(照 test_chat.py 范式,测试内自建 agent + monkeypatch composite_query):happy path 3 agent / 部分失败 / synthesize 失败 / wallet 402 / member 403 / 跨租户 404 / **软删 agent 404** / **重复 agent_ids 去重** / agent_ids 校验 422 / **续接 kind 不符 404**(single↔composite)/ fragments 持久化可读 / 计费 N+1 笔 / customer 透传 / 多轮 usage 准确 / **扣费容错(第 2 笔 charge 失败,1/3/4 笔仍入库)**
- [ ] `./init.sh` 全绿;`alembic check` 同步

### 切片 04 — 前端模式切换 + 真实验证 + ship-it 收尾

**What to build**:用户能在 chat 页面切换到「复合查询」模式,多选 agent,发起查询,看到综合答案 + 折叠的各 agent 原始回答。含前端类型、API 封装、composite-mode.tsx 独立组件、会话列表 badge。最后跑真实 DeepSeek key 端到端验证 + feature 收尾(feature_list.json evidence + progress.md + 文档影响评估)。

**Blocked by**:切片 03(需要 `/chat/composite` API)

**Status**:ready-for-agent(blocked)

- [ ] `types.ts`:`Conversation.kind` + `Message.fragments` + `Message.status`+`Message.error`(M8 顺手补)+ `CompositeFragment`/`CompositeRequest`/`CompositeResponse`
- [ ] `endpoints.ts`:`compositeChat(payload)`(POST /chat/composite,非流式)+ **402 单独 catch 展示充值引导**(项目首例)
- [ ] **`composite-mode.tsx` 独立组件**(文件 kebab-case,export `CompositeMode`,照 `pages/bookings/` 惯例):发送/结果/fragments 折叠全封装
- [ ] **chat-page 边界(H6)**:`mode` state 由 chat-page 持有 + Switch + 条件渲染 + 导入,**净增 ≤ 30 行**;composite 逻辑全在 composite-mode.tsx
- [ ] **Switch 默认态(H5)**:`useState<"single"|"composite">("single")` 初始化为 single;切会话时按 kind 同步 mode(useEffect 监听 selectedConversationId)
- [ ] Switch 复用现有 `switch.tsx`(M7:非"全项目未用",agents-page:643 已用);**composite 是会话级临时态,不写 Agent 字段**(区别于 agents-page 的 is_orchestrator 属性)
- [ ] 结果消息:fragments 折叠展示,每条带 status badge(复用 Badge:✓ completed / ✗ failed)
- [ ] 会话列表 composite 会话显示「复合」badge
- [ ] `selectConversation` 按 kind 切 mode;**composite 模式隐藏 header 的 agent/customer Select**(避免误导)
- [ ] composite 会话续问(M10 明确):MVP 默认折叠 agent 多选区沿用首次 agent_ids,或仅查看历史(写进「不做的事」)
- [ ] `npm run build` 0 类型错误;`oxlint` 0 warnings
- [ ] 真实 DeepSeek key 端到端(M9 前置:llm_config DB 行或 .env key + 若 RAG 需灌文档):建 3 agent(至少 1 带 RAG)+ 复合查询 → 验证 fan-out + synthesize + fragments 折叠 + 计费 4 笔 UsageEvent + 历史可查看
- [ ] 向后兼容:普通单 agent 对话 + Supervisor orchestrator 路径零回归(依赖 H5 默认态 single)
- [ ] **feature 收尾(对照 clean-state-checklist)**:feature_list.json evidence + status=passing + progress.md Session + 文档影响评估执行 + **ADR-0002 判断(composite 落地后即判,不等 ship-it)** + **`./scripts/sync-active-features.sh` 跑过** + **依赖解锁扫描**(priority 72 最高位,若有 feature 等它需解锁)+ clean-state checklist 9 项全勾

---

## 七、验收标准(AC)

### AC1:数据层
- AC1.1 `Conversation.kind` 字段存在(String16,server_default "single",**无索引**)
- AC1.2 `Message.fragments` 字段存在(JSONB nullable,双 DB variant)
- AC1.3 alembic migration up/down 对称,模板符合本项目写法(类型注解 `revision: str`),`alembic check` model/DB 同步
- AC1.4 migration 含 backfill 步骤(`UPDATE conversations SET kind='single' WHERE kind IS NULL`),旧单 agent 会话 `kind` 非 NULL
- AC1.5 `Conversation.agent_id` 保持 NOT NULL,composite 会话填 `agent_ids[0]`(**首次 agent = 主 agent / 会话归属**),全部 N agent 在 fragments 记录

### AC2:编排引擎
- AC2.1 `composite_query` 函数存在,返回 dict 含 `synthesis` / `fragments` / `synthesize_usage` / `usage_total` 四键;**fragments 用外部 list 容器**(task 内 append)
- AC2.2 单 agent 失败 → 该 fragment `status="failed"`,其他正常
- AC2.3 synthesize 失败 → synthesis 降级为 `_fallback_synthesis(fragments)`(**明确定义格式**,见 Step 6),response 仍 200
- AC2.4 token 累加正确:`usage_total` = Σ(fragments.total_tokens) + synthesize_usage.total_tokens
- AC2.5 `_invoke_agent_once` 基于 `astream_events` 累加每轮 usage(非 ainvoke),对外同步返回 dict;与 `stream_agent` 独立路径
- AC2.6 db session 并发安全:fan-out 每 agent 用 `_get_session_factory()()` 新开独立 session,**传给 `_build_tenant_tools`**(不复用主 session 工具闭包)
- AC2.7 **超时 fail-open 正确实现**:`asyncio.wait_for` 触发 TimeoutError 时 except pass,外部 list 已 append 的 fragment 保留;不用裸 `asyncio.timeout` 包 gather(那会取消所有 task 且回收不到结果)
- AC2.8 **fan-out 并行性**:N agent 各 sleep 时总耗时 < N×单 agent(非串行)

### AC3:API + 计费
- AC3.1 `POST /chat/composite` 端点存在,返回 `CompositeResponse`
- AC3.2 wallet 不足 → HTTP 402(member,项目首例,前端单独 catch)/ 旁路(super_admin)
- AC3.3 member 无 `conversations:chat` → 403
- AC3.4 跨租户 agent_id / **已软删 agent → 404**;**重复 agent_ids 去重后正常返回**
- AC3.5 agent_ids 空 / 超 8 个 → 422
- AC3.6 **续接 kind 一致性(H2)**:single 会话 id 传给 /chat/composite → 404(不泄露存在性);composite 会话 id 正常复用
- AC3.7 **N+1 笔 UsageEvent**:N 笔 fragment(agent_id=对应 agent)+ 1 笔 synthesize(agent_id=NULL);全部 message_id 指向同一条综合 Message;总 token = usage_total
- AC3.8 assistant 消息 `fragments` 字段持久化,GET messages 可读
- AC3.9 composite 带 `customer_id` 时,N+1 笔 UsageEvent 的 `customer_id` 均透传
- AC3.10 **多轮 usage 准确计费**:ReAct 2 轮时 fragment total = 两轮之和(防 ainvoke 漏计)
- AC3.11 **扣费容错(H4)**:任一笔 charge 失败,其他笔 UsageEvent + WalletTransaction 仍正确持久化(best-effort)

### AC4:前端
- AC4.1 `chat-page.tsx` 有模式切换(复用现有 `Switch`;M7 已核实 agents-page:643 已用,非"全项目未用")
- AC4.2 复合模式:多选 agent(Checkbox)+ 输入(Input)+ 发起 → loading → 结果
- AC4.3 结果消息折叠展示 fragments(带 status badge,复用 Badge)
- AC4.4 会话列表 composite 会话显示「复合」badge
- AC4.5 **chat-page 净增 ≤ 30 行**(H6:mode state + Switch + 条件渲染 + 导入);composite 逻辑全在 `composite-mode.tsx`(kebab-case 文件名)
- AC4.6 **Switch 默认态 single(H5)**:`useState("single")` 初始化;切会话按 kind 同步;composite 模式隐藏 header 的 agent/customer Select
- AC4.7 `Message` 类型补 `status`+`error`(M8:对齐后端 MessageRead,单 agent 失败消息重试提示也依赖)
- AC4.8 endpoints.ts 对 402 单独 catch 展示充值引导(项目首例 402)

### AC5:向后兼容 + 验证
- AC5.1 现有单 agent `/chat/stream` 零回归(现有测试全绿)
- AC5.2 现有 Supervisor `/chat/stream`(orchestrator 路径)零回归
- AC5.3 `./init.sh` + `npm run build` + `oxlint` 全绿
- AC5.4 真实 DeepSeek key 端到端:3 agent 复合查询全链路通

---

## 八、参考文件

| 参照 | 路径 |
|---|---|
| `stream_agent`(单 agent 流式,不复用但参考契约) | `app/agents/graph.py:183` |
| `build_orchestrator` / `stream_orchestrator`(Supervisor,**零改动**) | `app/agents/graph.py:325 / :388` |
| `_build_llm_kwargs` / `_system_msg` / `_build_tenant_tools`(纯函数,**复用**) | `app/agents/graph.py:109 / :41 / :52` |
| `/chat/stream`(单 agent SSE,**零改动**) | `app/api/v1/chat.py:130` |
| `_record_usage` / `_charge_usage`(计费,**复用模式**) | `app/api/v1/chat.py:56 / :106` |
| `ConversationService.create_or_get`(加 kind 参数) | `app/services/conversation_service.py:32` |
| `ConversationService.append_message`(加 fragments kwarg) | `app/services/conversation_service.py:145` |
| `BillingService.has_balance` / `charge`(计费,复用) | `app/services/billing_service.py:93 / :136` |
| `permission_service.require`(权限门控) | `app/services/permission_service.py:131` |
| `Conversation` 模型(加 kind) | `app/models/agent.py:80` |
| `Message` 模型(加 fragments) | `app/models/message.py:16` |
| `ChatRequest`(不复用,新建 CompositeRequest) | `app/schemas/conversation.py:85` |
| migration head(down_revision 指向) | `alembic/versions/2026_07_26_1100_5565cf1e81bd_add_bookings_tenant_schedule_index.py` |
| StorePilot composite_chat 参考(外部,设计溯源) | sess_babf29ab-062c-4206-a3fd-1f4a1c1ed2e2 |

---

## 九、文档影响评估(预估,实施时执行)

- `feature_list.json` ✅ 新增 `composite-chat` feature(priority 72,status in_progress → passing)
- `progress.md` ✅ Session 记录
- `CONTEXT.md` ⚠️ 可能加一条「复合查询」架构说明(看是否影响整体架构图)
- `项目指南/02-后端架构/` ⚠️ 若引入新编排模式,可能需在「AI Agent 架构」节补一段(实施时判断)
- **ADR-0002 判断**:项目刚建立 ADR-0001(principal-scope-boundary)。本计划引入「双编排模式共存」(Supervisor + Composite),是架构级决策,实施时评估是否需要 ADR-0002 记录「为何两种模式共存而非统一」(参照 ADR-0001 的 Nygard 五段式)。倾向:若 Composite 落地后与 Supervisor 边界清晰且无歧义,可只在 plan 记录;若边界模糊则提 ADR-0002
- README ❌ 不动(脚手架 README,不细到编排模式)
- 本 plan ✅ 实施过程中 checklist 勾选 + 偏差记录
