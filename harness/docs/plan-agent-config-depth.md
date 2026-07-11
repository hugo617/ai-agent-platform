# 计划:Agent 配置深度(推理参数 + prompt 变量 + 元信息)

> 对应 feature_list.json 的 `id`: `agent-config-depth`
> 状态: not_started
> 优先级: 27
> 前置: `real-chat-llm-config` ✅(Agent.model 已生效;本任务把 Agent 从"只能配名字+模型+prompt"升级为"可配推理参数")

---

## 背景:为什么需要这个任务

Agent 模型当前只有 **4 个有效字段**:`name`、`system_prompt`、`model`、时间戳。而 LLM 的核心推理参数——temperature、max_tokens、top_p——**全部硬编码在 `graph.py`**(写死 `temperature=0.3`,无 max_tokens/top_p 配置)。这意味着:

- 用户无法给"创意写作 Agent"设高 temperature(0.9),也无法给"代码生成 Agent"设低 temperature(0.1)——所有 Agent 行为同质化
- 无法控制输出长度(max_tokens),长回复可能耗尽预算
- Agent 没有任何"描述/分类/标签"元信息,列表页只显示名字,用户管理多个 Agent 时无法区分

这是一个"AI 平台"最基础的配置能力缺失。

### 问题根因(代码佐证)

- **Agent 模型字段极少**:`app/models/agent.py:16-33` 只有 `id/tenant_id/name/system_prompt/model/created_at`,无 `temperature`/`max_tokens`/`top_p`/`description`。
- **Schema 同样单薄**:`app/schemas/agent.py:8-11` `AgentBase` 只有 `name/system_prompt/model`。
- **temperature 硬编码**:`app/agents/graph.py:76` `temperature=0.3`(build_agent)、`graph.py:109` `temperature=0.3`(stream_agent)——**两处写死**。
- **无 max_tokens / top_p**:`ChatOpenAI(...)` 调用未传这些参数,用 LangChain 默认。
- **前端表单字段单薄**:`agents-page.tsx:44-48` zod schema 只有 `name/system_prompt/model`,表单只有名称/模型/系统提示词三个字段。

### 后果

1. **Agent 行为不可调**:所有 Agent 用同一套推理参数,无法按场景优化
2. **输出长度失控**:无法限制 max_tokens,长回复消耗成本
3. **Agent 管理困难**:无描述/标签,列表页只有名字,租户内 Agent 多了无法区分

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| Agent.temperature | ❌ 硬编码 0.3 | `app/agents/graph.py:76,109` |
| Agent.max_tokens | ❌ 未配置 | `ChatOpenAI` 未传 |
| Agent.top_p | ❌ 未配置 | `ChatOpenAI` 未传 |
| Agent.description | ❌ 无字段 | `app/models/agent.py` |
| 前端推理参数表单 | ❌ 无 | `agents-page.tsx:44-48` |
| stream_agent 签名 | ⚠️ 已解耦 model/api_key/base_url | `graph.py:84`(real-chat 任务已改),但无推理参数 |

---

## 目标

1. **Agent 模型加推理参数字段**:`temperature`(浮点,0-2)、`max_tokens`(整数,可选)、`top_p`(浮点,可选,0-1)、`description`(文本,可选)
2. **graph.py 使用 Agent 配置**:stream_agent / build_agent 的 `ChatOpenAI` 用传入的推理参数,移除硬编码 temperature
3. **chat.py 传递推理参数**:解析 agent 配置传给 stream_agent
4. **前端表单加推理参数**:Sliders/Inputs 让用户调 temperature/max_tokens/top_p;加 description 字段;列表显示 description

### 已确认的决策(与用户对齐)

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 加哪些字段 | **temperature + max_tokens + top_p + description** | 这 4 个覆盖 90% 调参需求;frequency_penalty/presence_penalty 等边缘参数暂不加(避免表单过载) |
| 字段默认值 | temperature=0.7(LLM 通用默认)/ max_tokens=None(不限)/ top_p=None(不限)/ description="" | None 表示"不传给 LLM",用 provider 默认;temperature 必有值 |
| 默认值如何作用于现有数据 | **迁移加字段带 server_default**(temperature=0.7),现有 agent 自动获得默认值 | 无需数据回填 |
| 前端控件 | **Slider + 数字输入**(temperature/top_p 用 Slider,max_tokens 用 Input) | Slider 直观(拖拽即见变化),Input 精确 |
| 高级参数折叠 | **"高级设置"折叠区**(Collapsible),默认收起 | 避免新手被参数吓到;temperature 放显眼处 |

---

## 前置条件

- `real-chat-llm-config` ✅(stream_agent 已解耦 model/api_key/base_url,本任务加推理参数)
- 迁移链 head:`c4d5e6f7a8b9`(`add_api_tokens_table`)

---

## 实施步骤

### 第一阶段:数据模型 + 迁移

#### Step 1:Agent model 加字段

- **改什么**(`app/models/agent.py` `Agent` 类,L16-33):
  ```python
  description: Mapped[str] = mapped_column(Text, default="")
  temperature: Mapped[float] = mapped_column(Float, default=0.7, server_default="0.7")
  max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
  top_p: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
  ```
- **import**:`Float, Integer` from sqlalchemy
- **server_default**:迁移时给现有行填默认值(temperature=0.7)

#### Step 2:Alembic 迁移

- `alembic revision --autogenerate -m "add agent inference params and description"`
- **down_revision = 'c4d5e6f7a8b9'**(当前 head)
- **确认迁移内容**:`ALTER TABLE agents ADD COLUMN temperature FLOAT DEFAULT 0.7; ADD COLUMN max_tokens INTEGER; ADD COLUMN top_p FLOAT; ADD COLUMN description TEXT DEFAULT '';`
- **alembic check**:确保 autogenerate 无 drift(对齐 real-chat 任务踩过的坑:env.py 的 model import 列表要含 agent——已含,无需改)
- **conftest.py**:agent model 已注册(`tests/conftest.py:85-93` 已 import agent),无需改

---

### 第二阶段:Schema + graph.py + chat.py

#### Step 3:Schema 加字段

- **改什么**(`app/schemas/agent.py`):
  - `AgentBase` 加:
    - `description: str = ""`
    - `temperature: float = Field(0.7, ge=0.0, le=2.0)`
    - `max_tokens: int | None = Field(None, ge=1, le=32768)`(上限按 DeepSeek 32k 输出)
    - `top_p: float | None = Field(None, ge=0.0, le=1.0)`
  - `AgentUpdate` 对应加 Optional 版本(`temperature: float | None = Field(None, ge=0, le=2)` 等)
- **Pydantic 校验**:`ge`/`le` 约束范围;422 中文化已在 validation-error-i18n 任务完成

#### Step 4:graph.py stream_agent 加推理参数

- **改什么**(`app/agents/graph.py`):
  - `stream_agent` 签名加:`temperature: float = 0.7`、`max_tokens: int | None = None`、`top_p: float | None = None`
  - `ChatOpenAI(...)` 实例化:用传入的 `temperature`(替代硬编码 0.3);`max_tokens` 和 `top_p` 仅在非 None 时传入(避免覆盖 provider 默认)
    ```python
    kwargs = {"model": model, "api_key": api_key, "base_url": base_url, "streaming": True, "temperature": temperature}
    if max_tokens is not None: kwargs["max_tokens"] = max_tokens
    if top_p is not None: kwargs["top_p"] = top_p
    llm = ChatOpenAI(**kwargs)
    ```
  - `build_agent`(L58)同步改造(虽然 build_agent 目前是死代码,但保持一致性)

#### Step 5:chat.py 传推理参数

- **改什么**(`app/api/v1/chat.py` `event_source`,L98-108 的 stream_agent 调用):
  ```python
  async for chunk in stream_agent(
      ..., model=model, api_key=..., base_url=...,
      system_prompt=agent.system_prompt,
      temperature=agent.temperature,
      max_tokens=agent.max_tokens,
      top_p=agent.top_p,
      history=history, user_message=payload.message,
  ):
  ```
- **效果**:Agent 的推理参数真正传递到 LLM

---

### 第三阶段:前端

#### Step 6:types.ts 加字段

- **改什么**(`frontend/src/api/types.ts` 的 `Agent` interface):
  ```typescript
  description: string;
  temperature: number;
  max_tokens: number | null;
  top_p: number | null;
  ```
- `AgentCreate` / `AgentUpdate` 对应加(Update 全 optional)

#### Step 7:agents-page.tsx 表单加推理参数 + description

- **改什么**(`agents-page.tsx`):
  - zod schema(L44-48)加:
    ```typescript
    description: z.string().default(""),
    temperature: z.number().min(0).max(2).default(0.7),
    max_tokens: z.number().int().min(1).max(32768).optional().or(z.literal("")),
    top_p: z.number().min(0).max(1).optional().or(z.literal("")),
    ```
  - 表单加:
    - **description**:Input(普通文本框,"用于区分智能体用途")
    - **temperature**:用 `<input type="range" min=0 max=2 step=0.1>` + 数字显示;或用项目已有的 UI 组件(若无 Slider 组件,用原生 range + 样式)
    - **max_tokens / top_p**:放"高级设置"折叠区(用 `<details>` 或 Collapsible);Input 留空=不设(传 null)
  - **defaultValues**(L71):加 `description: "", temperature: 0.7, max_tokens: "", top_p: ""`
  - **openEdit**(L82):加 `description: agent.description, temperature: agent.temperature, max_tokens: agent.max_tokens ?? "", top_p: agent.top_p ?? ""`
  - **列表表格**(L148-155):加一列"描述"(显示 description,截断);或在名称下用小字显示 description
- **register valueAsNumber**:temperature/max_tokens/top_p 用 `register("temperature", { valueAsNumber: true })` 确保数字类型(对齐 roles-crud 的 sort_order 处理)

#### Step 8:列表显示 description

- **改什么**(agents-page 列表表格):
  - 名称列下方加 description 小字(若非空):`{agent.description && <p className="text-xs text-muted-foreground">{agent.description}</p>}`
  - 或新增一列"描述"

---

### 第四阶段:测试 + 验证

#### Step 9:更新 test_agents_api.py

- 现有 14 个测试因 schema 加字段(有默认值)不会全部崩溃,但需补:
  - **create agent with inference params**:POST 带 temperature/max_tokens/top_p → 200 + 断言返回值
  - **create agent with invalid temperature**:temperature=3.0(超 2.0)→ 422
  - **update agent temperature**:PUT 改 temperature → 200 + 断言
  - **default values**:POST 不传 temperature → 返回 0.7

#### Step 10:更新 test_chat.py

- 加 `test_agent_inference_params_passed_to_stream_agent`:建 agent(temperature=0.1)→ 对话 → 断言 fake_stream 收到的 temperature == 0.1(验证 Step 4-5)

#### Step 11:总验证

- `./init.sh` 全绿(ruff + pytest,含新/更新测试)
- `APP_ENV=testing alembic upgrade head` 迁移链通过(CI migrations job 守门)
- `cd frontend && npm run build` 通过 + oxlint 0 warning
- (可选,真实)真实 DeepSeek 对话验证:建两个 agent(temperature=0.1 vs 0.9),问同一问题,验证回复风格不同

---

## 验收标准

1. **Agent 模型加 4 字段**:temperature/max_tokens/top_p/description,migration 通过
2. **推理参数生效**:stream_agent 的 ChatOpenAI 用 agent.temperature(非硬编码 0.3);max_tokens/top_p 在非 None 时传入
3. **前端可配**:表单可设 temperature(max_tokens/top_p 在高级区);列表显示 description
4. **Pydantic 校验**:temperature 超范围 → 422
5. `./init.sh` 全绿 + `cd frontend && npm run build` 通过 + oxlint 0 warning
6. `alembic upgrade head` + `alembic check` 无 drift
7. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 迁移加字段(server_default)在 SQLite 测试环境的行为 | SQLite 支持 `DEFAULT` 子句;server_default 在 alembic 生成的 ALTER 里体现;现有测试用 create_all 不走迁移,需确认 model 定义与迁移一致 |
| max_tokens 上限 per-model 不同(DeepSeek 8k 输出 vs GPT 4k) | 本任务用固定上限 32768(保守);不做 per-model 动态上限(查 /models context_length 是后续增强) |
| 前端无现成 Slider 组件 | 用原生 `<input type="range">` + Tailwind 样式;或后续抽 Slider UI 组件(shadcn 风格)。本任务先用原生 range 保证可用 |
| temperature 默认值变更(0.3→0.7) | 现有 agent 迁移后获得 0.7;之前硬编码 0.3 的行为变了——这是预期改进(0.7 是更通用的默认值),用户可按需调 |
| AgentUpdate schema 全 optional 与默认值冲突 | Update 用 `None` 表示"不改",与 AgentBase 的默认值(0.7)语义不同;service 层 update 时用 `model_dump(exclude_unset=True)` 只更新传入字段(对齐现有 users/roles update 模式) |
| build_agent 死代码改不改 | 同步改参数(保持一致性),但 PR 标注它是既有死代码(对齐 real-chat 任务的处理) |

### 不做的事(边界)

- **不做工具配置**(Agent.tools 字段):工具是代码硬编码的(1 个示范工具),让用户在 UI 配工具属"工具体系"任务,本任务只做推理参数
- **不做知识库关联**(Agent.knowledge_base_id):RAG 能力属另一任务
- **不做 prompt 变量/模板**(system_prompt 的 {{variable}} 插值):复杂度高,属另一任务
- **不做 per-model 参数上限**:max_tokens 用固定 32768 上限
- **不做 Agent 分类/标签系统**:只加 description 文本字段,不做 tag 多对多
- **不改 Agent 表的删除策略**(仍是硬删除,对齐 agents-api-hardening 任务的现状)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| Agent 模型(加字段) | `app/models/agent.py:16-33` |
| temperature 硬编码 | `app/agents/graph.py:76,109` |
| stream_agent 签名 | `app/agents/graph.py:84-95`(已解耦 model/key/base_url) |
| chat.py 调 stream_agent | `app/api/v1/chat.py:98-108` |
| Agent schema | `app/schemas/agent.py:8-22` |
| 前端 Agent 类型 | `frontend/src/api/types.ts` |
| 前端 agents-page 表单 | `frontend/src/pages/agents-page.tsx:44-48,69-88` |
| 前端 valueAsNumber 范式 | `frontend/src/pages/roles-page.tsx`(sort_order 处理) |
| 迁移链 head | `c4d5e6f7a8b9`(`alembic/versions/2026_07_11_1000_..._add_api_tokens_table.py`) |
| env.py model import 列表 | `alembic/env.py`(确保含 agent——已含) |
| conftest 模型注册 | `tests/conftest.py:85-93`(agent 已注册) |
| Agent 测试范式 | `tests/test_agents_api.py`(14 测试) |
| chat mock 范式 | `tests/test_chat.py:33-52`(_mock_chat + fake_stream) |
| Service update 范式 | `app/services/agent_service.py` + `user_service.py`(exclude_unset) |
| LLM 推理参数说明 | https://platform.openai.com/docs/api-reference/chat(temperature/top_p/max_tokens) |
| DeepSeek 参数说明 | https://api-docs.deepseek.com/zh-cn/quick_reference/pricing |
