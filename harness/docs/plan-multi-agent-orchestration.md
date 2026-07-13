# 计划:多 Agent 编排(LangGraph 多节点图,Agent 协作/转交)

> 对应 feature_list.json 的 `id`: `multi-agent-orchestration`
> 状态: not_started
> 优先级: 58(V2 大投入)
> 前置: 无(独立模块)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:单 ReAct agent,无法协作

### 现状(2026-07-12 取证)

- `app/agents/graph.py`:用 `langgraph.prebuilt.create_react_agent`——**单个** ReAct agent
- 工具只有 `get_my_agents`(列租户 Agent)
- 无多 agent 图、无编排、无转交、无 sub-agent 委派
- 搜 `multi.?agent|workflow|orchestrat|pipeline|sub.?agent|delegate` **零命中**

### 目标

从单 agent 升级到智能体协作:
1. **编排 Agent**(orchestrator):路由/分派用户请求到合适的专业 Agent
2. **转交**(handoff):Agent A 遇专业问题转 Agent B,保留对话上下文
3. **Agent 可声明可调用的子 agent + 转交条件**

---

## 前置条件

- 无(独立模块)。建议在 RAG(57)之后做(Agent 能力更完整)。

---

## 实施步骤

### 第一阶段:设计编排模型

#### Step 1:编排模式选型

- **选项 A:Supervisor 编排器**(推荐 MVP):
  - 一个 supervisor agent 接收所有请求 → 决定路由到哪个 specialist agent → 收集结果 → 回复
  - LangGraph 的 `create_supervisor` 或自建 supervisor 节点
- **选项 B:Swarm 转交**(LangGraph swarm):
  - 无中心编排;Agent 之间直接 handoff(转交控制权)
  - 更灵活但调试难
- **推荐 A**(supervisor)做 MVP,后续可加 B
- **检查**:模式确定;画状态机图

### 第二阶段:多 Agent 图实现

#### Step 2:编排器 + 专业 Agent 注册

- **改什么**(`app/agents/graph.py`):
  ```python
  from langgraph.graph import StateGraph, MessagesState, START, END

  def build_orchestrator(specialists: list[Agent], db, tenant_id):
      graph = StateGraph(MessagesState)
      # specialist 各为一个节点
      for sp in specialists:
          graph.add_node(sp.code, make_specialist_node(sp, db, tenant_id))
      # supervisor 节点:决定路由
      graph.add_node("supervisor", make_supervisor_node(specialists))
      # 边:START → supervisor → specialist → supervisor → END
      graph.add_edge(START, "supervisor")
      graph.add_conditional_edges("supervisor", route_to_specialist)
      ...
  ```
- **supervisor 逻辑**:用 LLM 判断用户问题属于哪个 specialist 的职责 → 路由
- **specialist 节点**:各自有 system_prompt + 工具(含 retrieve_knowledge 若有 57)
- **检查**:多 agent 图能跑;请求路由到正确 specialist

#### Step 3:handoff 转交

- **改什么**(specialist 遇到不属于自己职责的问题时转交):
  ```python
  def make_specialist_node(sp, db, tenant_id):
      async def node(state):
          result = await run_agent(sp, state["messages"])
          if needs_handoff(result):  # LLM 判断或规则
              return {"next": "supervisor", "messages": [HandoffMessage(...)]}
          return {"messages": [result]}
      return node
  ```
- **上下文保留**:转交时把对话历史带上(MessagesState 自动)
- **检查**:转交后上下文连续;用户无感

#### Step 4:stream_agent 改造支持编排

- **改什么**(`stream_agent` L125):
  - 当前是单 agent 流;改为支持编排图
  - 若 Agent 配置了 `orchestrator_for`(关联的 specialists)→ 用编排图;否则用单 agent(向后兼容)
- **检查**:单 agent 对话不受影响;编排对话走新图

### 第三阶段:Agent 配置

#### Step 5:Agent 模型加编排字段

- **改**(`app/models/agent.py` Agent 加字段):
  ```python
  is_orchestrator: Mapped[bool] = mapped_column(Boolean, default=False)
  specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 职责描述(supervisor 路由依据)
  ```
- **AgentCreate/Edit schema** 加这些字段
- **检查**:Agent 可标记为 orchestrator / 声明 specialty

#### Step 6:orchestrator 关联 specialists

- **新建** `agent_specialists` 关联表(orchestrator_id, specialist_id)或 orchestrator 配置 JSON
- **或**:orchestrator 自动包含本租户所有 `is_orchestrator=False` 的 Agent 作为 specialists
- **检查**:orchestrator 能找到它的 specialists

### 第四阶段:前端

#### Step 7:Agent 编辑页加编排配置

- **改**(`frontend/src/pages/agents-page.tsx`):
  - Agent 编辑 form 加「是否编排器」开关
  - 若是编排器:显示「可调度的专业 Agent」多选(specialists)
  - 专业 Agent:显示「职责描述」输入(供 supervisor 路由)
- **检查**:配置生效

#### Step 8:对话中显示 Agent 切换

- **改**(`chat-page.tsx`):
  - 编排对话中,显示当前服务的 specialist(如「当前由:健康顾问 Agent 服务」)
  - 转交时显示提示(「已转接给:预约专员 Agent」)
- **检查**:用户能看到 agent 切换

### 第五阶段:验证

#### Step 9:测试 + 总验证

- **后端**(`tests/test_multi_agent.py`):
  - supervisor 路由正确(健康问题 → 健康顾问;预约 → 预约专员)
  - handoff 上下文保留
  - 单 agent 模式不受影响(向后兼容)
  - 租户隔离(编排只用本租户 Agent)
- **端到端**:用户问多领域问题 → 编排器分派 → 各 specialist 回答 → 转交连续
- **命令**:`./init.sh` + `npm run build` + 真实 LLM 验证路由
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. Supervisor 编排模式实现(LangGraph 多节点图)
2. specialist 路由(supervisor 用 LLM 判断路由到正确 specialist)
3. handoff 转交 + 上下文保留
4. Agent 加 is_orchestrator/specialty 字段 + 关联 specialists
5. 前端:Agent 编辑加编排配置;对话显示 agent 切换
6. 向后兼容(单 agent 不受影响)
7. `./init.sh` + `npm run build` 全绿;真实 LLM 路由验证

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 路由准确率 | supervisor 用清晰 specialty 描述;few-shot 示例;fallback 到默认 specialist |
| 多 agent 延迟(多次 LLM 调用) | 接受(编排场景容忍延迟);或并行 specialist |
| 调试困难 | LangGraph studio 可视化;日志记录路由决策 |
| token 消耗大(编排多次调用) | 计费系统(43-46)自然覆盖;预警阈值 |
| 向后兼容 | stream_agent 判断 is_orchestrator,是则走编排图,否则原单 agent 路径 |

### 不做的事(边界)

- 不做 Swarm 模式(无中心编排,后续)
- 不做 Agent 自动生成/进化
- 不做跨租户 Agent 协作(只本租户)
- 不做 Agent 市场/共享

---

## 参考文件

| 参照 | 路径 |
|------|------|
| stream_agent(待改造) | `app/agents/graph.py` L125-178 |
| create_react_agent(当前单 agent) | `app/agents/graph.py` L159 |
| Agent 模型(待加字段) | `app/models/agent.py` |
| LangGraph 文档 | [LangGraph Multi-Agent](https://langchain-ai.github.io/langgraph/agent_architecture/) |
| Agent 编辑页 | `frontend/src/pages/agents-page.tsx` |
