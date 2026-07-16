# 计划:多 Agent 编排(Supervisor 模式,LangGraph 多节点图)

> 对应 feature_list.json 的 `id`: `multi-agent-orchestration`
> 状态: in_progress(2026-07-16 开工)
> 优先级: 58(V2 大投入,项目最后一个 not_started)
> 前置: 无(独立模块);建议在 RAG(57 ✅ 已并入)之后做 —— specialist 可共享 `retrieve_knowledge` 工具
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 一、背景:单 ReAct agent,无法协作

### 现状(2026-07-16 取证,已核实)

- `app/agents/graph.py`:用 `langgraph.prebuilt.create_react_agent` —— **单个** ReAct agent
- 工具有 `get_my_agents`(列租户 Agent)+ `retrieve_knowledge`(57 RAG 已加)
- 无多 agent 图、无编排、无 supervisor、无 sub-agent 委派
- Agent 模型(`app/models/agent.py:29`)无 `is_orchestrator`/`specialty` 字段
- 全项目 grep `orchestrat|supervisor|handoff` 零命中(仅注释提及)

### 用户决策(2026-07-16 AskUserQuestion 4 问)

1. **范围**:细化 plan + 实现 + ship-it 全程
2. **编排模式**:Supervisor 编排器(中心化路由,可调试)
3. **specialist 关联**:新建 `agent_specialists` 关联表(M2M)
4. **真实 LLM 验证**:需要真实 DeepSeek key 端到端验证 supervisor 路由

### 目标

从单 agent 升级到智能体协作:
1. **编排 Agent**(orchestrator):接收用户请求 → LLM 判断路由到哪个 specialist → specialist 回答
2. **specialist 关联**:orchestrator 显式 attach 一组本租户的非编排 Agent 作 specialist
3. **向后兼容**:普通 agent(is_orchestrator=False)走原 ReAct 路径,零回归

---

## 二、技术可行性(已 grep LangGraph 0.2.61 源码核实)

| API | 状态 | 位置 |
|------|------|------|
| `StateGraph` / `MessagesState` / `START` / `END` | ✅ 存在 | `langgraph/graph/__init__.py` |
| `Command(goto=..., update=...)` | ✅ 存在 | `langgraph/types.py:254`,被 `_control_branch`(`graph/state.py:842`)消费作路由指令 |
| `create_react_agent(llm, tools, messages_modifier)` | ✅ 存在 | `prebuilt/chat_agent_executor.py:197`,`messages_modifier` 在 0.3.0 才移除 |
| `CompiledStateGraph.astream_events(version="v2")` | ✅ 存在 | 继承链 `CompiledStateGraph → CompiledGraph → Pregel → Runnable`,astream_events 在 langchain_core 基类 |
| `HandoffMessage` / `create_supervisor` / swarm | ❌ 不存在 | 0.2.61 无,需 0.4+ |

**关键结论**:自建 `StateGraph(MessagesState).compile()` 出来的图与 `create_react_agent` 返回的图同属 `Pregel` 子类,**都支持 `.astream_events(version="v2")`** —— 现有 `on_chat_model_stream`/`on_chat_model_end` usage 捕获契约(`graph.py:231-248`)可完整保留。

**事件冒泡机制**:specialist 节点用 `create_react_agent` 包装,作为外层图的节点被 Pregel 调度时,其内部 ChatOpenAI 的 `on_chat_model_stream` 事件经 child callback manager 冒泡到外层 `astream_events`(langchain_core `Runnable.astream_events` v2 标准机制)。

---

## 三、实施步骤(5 阶段,22 步)

### 阶段 1:后端数据层(模型 + 迁移 + Repository + Service)

#### Step 1:Agent 模型加字段(`app/models/agent.py`)

- `is_orchestrator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")`
- `specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)`(职责描述,supervisor 路由依据)
- Agent 模型无 `__table_args__` 无软删除(已核实),加字段简单

#### Step 2:新建 `agent_specialists` 关联表(照 GroupTenant 范式 `app/models/group.py:84-110`)

- 文件:`app/models/agent_specialist.py`
- 字段:`id`(String32 主键 uuid)/ `orchestrator_id`(FK agents.id CASCADE)/ `specialist_id`(FK agents.id CASCADE)/ `created_at`(server_default now)
- `__table_args__`:`UniqueConstraint("orchestrator_id", "specialist_id", name="uq_agent_specialists")` + `Index("idx_agent_specialists_specialist_id", "specialist_id")`
- **无软删除**(挂载/卸载 = insert/delete,语义同 GroupTenant)
- **自引用 FK**:两 FK 都指向 agents.id,Agent 删除时 CASCADE 自动清理

#### Step 3:Alembic 迁移

- 文件:`alembic/versions/2026_07_16_HHMM_<12hex>_add_agent_orchestration.py`
- `down_revision = 'f2b3c4d5e6f7'`(当前 head)
- `up`:① add_column is_orchestrator(Boolean server_default "false") ② add_column specialty(String255 nullable) ③ create_table agent_specialists + UniqueConstraint + Index
- `down`:对称反向
- **同步注册**:`alembic/env.py` + `tests/conftest.py` 两处 model import 加 `agent_specialist`(漏 conftest 会 NoReferencedTableError)

#### Step 4:Repository 层

- 新建 `app/repositories/agent_specialist.py`(`BaseRepository` 非 TenantScoped,因 Agent 已带 tenant_id):
  - `list_for_orchestrator(orchestrator_id) -> list[AgentSpecialist]`
  - `list_specialist_agents(orchestrator_id, tenant_id) -> list[Agent]`(JOIN agents,带 tenant_id 守卫)
  - `exists(orchestrator_id, specialist_id) -> bool`
  - `attach(orchestrator_id, specialist_id)` / `detach(...) -> int`(照 `app/repositories/group.py:63-103`)
- `AgentRepository` 加 `list_orchestrators_for_tenant` / `list_specialists_for_tenant`(按 is_orchestrator 过滤)

#### Step 5:Service 层(`app/services/agent_service.py`)

- `list_specialists(orchestrator_id, tenant_id)`(读)
- `attach_specialist(user_id, tenant_id, orchestrator_id, specialist_id, platform_role)`:权限 agents:update + 校验(同租户 / specialist 非 orchestrator / 非自挂 / 未重复)
- `detach_specialist(...)`(对称)
- `create`/`update` 写入 `is_orchestrator`/`specialty`(update 已用 exclude_unset,加字段自动生效)
- `AgentRead` schema 加 `specialist_ids: list[str]`(读时 Repository JOIN 聚合)

### 阶段 2:后端编排引擎(graph.py 改造 — 核心)

#### Step 6:supervisor 路由 LLM(`app/agents/graph.py` 新增)

- supervisor 用同一 ChatOpenAI(复用 `_build_llm_kwargs`),`with_structured_output` 返回 `{specialist_code: str, reason: str}`
- 路由 prompt 动态拼接 specialist 的 `name + specialty`
- **降级**:LLM 解析失败或返回未知 specialist → fallback 第一个 specialist

#### Step 7:build_orchestrator(新增,LangGraph 0.2.61 StateGraph + Command 范式)

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Command

def build_orchestrator(*, supervisor_llm, specialists: list[tuple[str, Any]]):
    graph = StateGraph(MessagesState)
    async def supervisor_node(state):
        decision = await supervisor_llm.ainvoke(...)  # 结构化路由
        target = match_specialist(decision.specialist_code, specialists) or specialists[0][0]
        return Command(goto=target)
    graph.add_node("supervisor", supervisor_node)
    for code, react_agent in specialists:
        graph.add_node(code, react_agent)  # create_react_agent 是 Runnable,可直接作节点
    graph.add_edge(START, "supervisor")
    for code, _ in specialists:
        graph.add_edge(code, END)  # MVP 单轮,specialist 回答后 END
    return graph.compile()
```

#### Step 8:stream_orchestrator(新增,保持 yield 契约)

- 签名同 `stream_agent` + `specialists: list[Agent]` 参数
- 内部 build_orchestrator → astream_events(version="v2") → 同样的 on_chat_model_stream yield str / on_chat_model_end 累加 usage / 末尾 yield `{usage, model}` dict

#### Step 9:chat.py 接入(`app/api/v1/chat.py:202`)

- `event_source` 内判断 `agent.is_orchestrator`:
  - 是 → 查 specialists + 若有 specialist 调 `stream_orchestrator`,无 specialist 降级普通 agent
  - 否 → 原 `stream_agent`(零回归)

### 阶段 3:后端 API + 权限 + 测试

#### Step 10:Schema + API 端点

- `app/schemas/agent.py`:AgentBase/Create/Update/Read 加 is_orchestrator/specialty;AgentRead 加 specialist_ids
- `app/api/v1/agents.py` 加(照 groups attach/detach):
  - `GET /agents/{orchestrator_id}/specialists`(agents:read)
  - `POST /agents/{orchestrator_id}/specialists/{specialist_id}`(agents:update)
  - `DELETE /agents/{orchestrator_id}/specialists/{specialist_id}`(agents:update)

#### Step 11:权限 seed

- **无新权限**:复用 agents:update/read(已 seed 给 owner/admin/member)
- 仅 AgentRead 暴露新字段供前端消费

#### Step 12:后端测试(新建 `tests/test_multi_agent.py`,约 12 测)

- **纯函数**:supervisor 路由 prompt / 路由降级 / build_orchestrator 图结构
- **mock stream_orchestrator**(照 `test_chat.py:41-47` 的 `chat_route.stream_agent` 替换范式):orchestrator 走新路径 / 普通 agent 走旧路径 / 无 specialist 降级
- **CRUD + 权限**(HTTP):attach/detach(同租户/跨租户 404/自挂 400/重复 400/specialist 是 orchestrator 400)+ AgentRead 含新字段 + member 403 + 删除级联清理

### 阶段 4:前端

#### Step 13:types.ts

- `Agent`/`AgentCreate`/`AgentUpdate` 加 `is_orchestrator` + `specialty`;`Agent` 加 `specialist_ids: string[]`

#### Step 14:endpoints.ts + queries.ts

- `fetchOrchestratorSpecialists` / `attachSpecialist` / `detachSpecialist`
- `useOrchestratorSpecialists` / `useAttachSpecialist` / `useDetachSpecialist`(照 `useAttachTenant`/`useDetachTenant` 范式)

#### Step 15:agents-page.tsx 加编排配置

- `agentSchema` 加 `is_orchestrator: z.boolean().default(false)` + `specialty: z.string().default("")`
- **首次启用 Switch 组件**(`components/ui/switch.tsx` 存在但全项目未用):
  - 「编排器」Switch → 开启时显示「职责描述」Input + specialist 多选区
- specialist 多选照 groups-page 双模式:
  - 创建态:原生 checkbox 列表(本租户非 orchestrator 的 agents)
  - 编辑态:Badge + dropdown attach/detach
- 列表加「类型」列(编排器 Badge / 普通)

#### Step 16:chat-page.tsx 提示

- `CardHeader`(agent 选择器旁 `chat-page.tsx:644-661`)加:选中 orchestrator 时显示「编排器:将路由到 N 个 specialist」
- **MVP 不做实时 specialist 来源显示**(SSE 帧不带 specialist 字段,改 schema 超范围)

### 阶段 5:验证 + ship-it + 真实 LLM

#### Step 17:标准验证

- `./init.sh` → ruff + pytest 全绿(基线 514 + 新增 ~12)
- `cd frontend && npm run build` → 0 类型错误
- `cd frontend && npx oxlint src/` → 0 warnings

#### Step 18:真实 DeepSeek key 端到端验证

- `.env` 已有真实 key(已核实);docker aap-postgres(pgvector)在跑
- 起 docker-compose + alembic upgrade head + uvicorn + npm run dev
- 创建 2 specialist(健康顾问 specialty=理疗/针灸 + 预约专员 specialty=预约/排班)+ 1 orchestrator attach specialists
- 对 orchestrator 问多领域问题 → 验证 supervisor 路由(健康问题 → 健康顾问;预约 → 预约专员)
- 向后兼容:普通 agent 对话不受影响
- 真实路由结果写入 evidence

#### Step 19-22:ship-it 收尾

- 清理 + 审查 + commit + PR + CI 守门 + 合并 + 文档(feature_list.json evidence + progress.md Session)+ clean-state checklist 全勾

---

## 四、关键设计决策(基于已核实事实)

1. **Supervisor 节点不进 ReAct**:supervisor 只做一次 LLM 路由决策(结构化输出),不用 create_react_agent。specialist 才用 create_react_agent(保留 retrieve_knowledge 工具能力)
2. **单轮 MVP 不做 supervisor 回收循环**:specialist 回答完直接 END,避免 token 爆炸 + 延迟
3. **事件冒泡靠 child callback**:specialist 的 create_react_agent 作为图节点被调度时,内部 ChatOpenAI 的 on_chat_model_stream 事件冒泡到外层 astream_events —— LangGraph + langchain_core 标准机制(已核实源码)
4. **agent_specialists 照 GroupTenant 范式**:无软删除 + UniqueConstraint + CASCADE + id 主键。不照 SCD2(编排关系无历史维度需求)
5. **降级三重保险**:① orchestrator 无 specialist → 降级普通 agent ② supervisor 路由 LLM 失败 → fallback 第一个 specialist ③ specialist 是 orchestrator → attach 时拒绝(防环)
6. **前端 MVP 不做实时 specialist 来源显示**:SSE 帧不带 specialist 字段,改 ChatStreamChunk + Message schema 超范围

---

## 五、风险与缓解

| 风险 | 缓解 |
|------|------|
| supervisor 路由准确率 | 结构化输出 + 清晰 specialty 描述 + fallback 第一个 |
| 多 LLM 调用延迟 | MVP 接受;supervisor 低 temperature |
| token 消耗翻倍 | 计费系统(43-46)覆盖;UsageEvent 累加多轮 on_chat_model_end 已支持 |
| 自引用 FK 环 | attach 校验 specialist 非 orchestrator;删除 CASCADE 清理 |
| LangGraph 0.2.61 API 边界 | 全部已 grep 源码核实;Command/StateGraph/MessagesState 真实存在 |
| 事件冒泡失败 | 真实 LLM 端到端验证(Step 18)覆盖;如失败降级 specialist 节点直接 yield |

---

## 六、不做的事(边界)

- ❌ Swarm 模式(无中心编排,后续)
- ❌ supervisor 回收循环(specialist 回答后回 supervisor 检查是否再转交)
- ❌ Agent 自动生成/进化
- ❌ 跨租户 Agent 协作(只本租户)
- ❌ 实时 specialist 来源显示(改 SSE 帧 + Message schema,超范围)
- ❌ Agent 市场/共享

---

## 七、验收标准

1. Supervisor 编排模式实现(LangGraph StateGraph + Command)
2. specialist 路由(supervisor LLM 结构化输出判断)
3. Agent 加 is_orchestrator/specialty 字段 + agent_specialists 关联表
4. 前端:Agent 编辑加编排配置(Switch + specialist 多选);对话页编排器提示
5. 向后兼容(单 agent 不受影响)
6. `./init.sh` + `npm run build` 全绿
7. 真实 DeepSeek key 端到端验证 supervisor 路由

---

## 八、参考文件

| 参照 | 路径 |
|------|------|
| stream_agent(待改造,加分支) | `app/agents/graph.py` |
| chat.py event_source(接入点) | `app/api/v1/chat.py:202` |
| Agent 模型(加字段) | `app/models/agent.py:29` |
| GroupTenant(M2M 范式) | `app/models/group.py:84-110` |
| GroupTenantRepository(attach/detach 范式) | `app/repositories/group.py:63-103` |
| groups-page(Badge+dropdown 多选) | `frontend/src/pages/groups-page.tsx:435-489` |
| LangGraph 多 agent 文档 | https://langchain-ai.github.io/langgraph/agent_architecture/ |
