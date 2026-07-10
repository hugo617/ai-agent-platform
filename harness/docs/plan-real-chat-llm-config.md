# 计划:真实智能体对话 + LLM 配置管理 + bug 修复

> 对应 feature_list.json 的 `id`: `real-chat-llm-config`
> 状态: not_started
> 优先级: 18
> 前置: `chat-conversation-api` ✅ + `chat-frontend` ✅(对话前后端已纳管 passing,本任务把"离线测试通过"推进到"真实可用"并补配置管理)

---

## 背景:为什么需要这个任务

对话主线的三个前置任务(agents-api-hardening / chat-conversation-api / chat-frontend)虽标 passing,但 progress.md 反复承认「手动 SSE 验证从未真正跑通」——因为 `.env` 里 `OPENAI_API_KEY=sk-replace-me` 是占位符,对话根本调不通。探勘代码发现 3 个真实 bug/缺口:

### 发现的 bug 与缺口

- **Bug 1(致命):Agent.model 字段被完全忽略。**
  `chat.py` 调 `stream_agent` 时只传了 `system_prompt`,而 `stream_agent`(graph.py)硬用全局 `settings.openai_model` 实例化 `ChatOpenAI`。用户在智能体页面选什么模型,实际对话**永远用全局配置的那个模型**,Agent.model 形同虚设。
- **Bug 2(致命):前端模型列表与后端完全脱节。**
  `agents-page.tsx:43` 硬编码 `["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "claude-3-5-sonnet"]`,后端配的是 DeepSeek(只有 `deepseek-chat`/`deepseek-reasoner`)。用户选 `gpt-4o-mini` 建 agent 后调 DeepSeek API 直接 model not found。前端默认值 `gpt-4o-mini` 也与后端默认 `deepseek-chat` 矛盾。
- **Bug 3:LLM 配置只能改 .env,无 UI 管理。**
  用户要求「API key 和模型选择功能需要进一步完善」—— 当前 LLM key/base_url/model 全在 `config.py` 读环境变量,既无数据库持久化,也无前端管理页。多租户场景下无法每租户配 key、无法在线切换 provider。

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| SSE 流式对话 | ✅ 已完成 | `app/api/v1/chat.py` `POST /chat/stream` |
| LLM 实例化 | ⚠️ 用全局配置 | `app/agents/graph.py` `ChatOpenAI` 读 `settings.openai_*`,**未用 agent.model** |
| chat.py 调 stream_agent | ⚠️ 未传 model | `chat.py:86-93` 只传 system_prompt |
| Agent.model 字段 | ⚠️ CRUD 正常但对话不用 | model/schema/service 都正常,**bug 在 graph/chat 链路** |
| 前端模型选择 | ❌ 硬编码错误 | `agents-page.tsx:43` MODELS 列表是 GPT/Claude,后端是 DeepSeek |
| LLM 配置管理 | ❌ 全缺 | 仅 env 变量,无 DB 表、无 API、无 UI |
| 加密工具 | ❌ 无 | `cryptography==44.0.0` 已装但无封装,Fernet 未用 |
| 真实对话验证 | ❌ 从未跑通 | progress.md 多处承认「手动 SSE 未跑」 |

---

## 目标

1. **修复 Bug 1+2**:让 Agent.model 在对话中真正生效(前端选什么模型,后端用什么模型);前端模型列表与后端配置对齐
2. **新增 LLM 配置管理(全栈)**:数据库持久化 + API key 加密存储 + 平台级(超管)/租户级两层配置 + 前端设置页
3. **真实跑通对话**:用户提供真实 DeepSeek key,端到端验证 SSE 流式对话真实可用,修运行时 bug

### 已确认的决策(与用户对齐)

| 决策点 | 选择 |
|--------|------|
| 配置粒度 | **平台级(tenant_id=NULL,超管配)+ 租户级(tenant_id 具体)** |
| 取值优先级 | **租户级 > 平台级 > .env**(三级 fallback) |
| API key 回显 | **掩码不回显**(后端返回 `sk-***abcd`,GET 不解密;更新时留空=不改) |
| 任务插队 | 本任务 priority 18,插队 `tenant-org-admin-ui`(WIP=1 暂停那个) |

---

## 前置条件

- `chat-conversation-api` ✅(对话后端已就绪)
- `chat-frontend` ✅(对话前端已就绪)
- **DeepSeek API Key**:用户提供有效的 `sk-...` key(阶段 6 真实验证用;阶段 1-5 用离线测试/monkeypatch 不需要真 key)
- Docker 环境中 `aap-postgres` 运行中(真实跑通用;离线测试用内存 SQLite 不依赖)

---

## 实施步骤

### 第一阶段:加密 + 数据模型

#### Step 1:加密工具 `app/core/crypto.py`(新建)

`cryptography==44.0.0` 已在 requirements.txt(无需新增依赖),Fernet 已验证可用。

- **新建 `app/core/crypto.py`**:
  - `encrypt(plaintext: str) -> str`:Fernet 加密,返回 token 字符串
  - `decrypt(ciphertext: str) -> str`:Fernet 解密
  - `mask_api_key(key: str) -> str`:返回掩码 `sk-***后4位`(如 `sk-abcd1234...` → `sk-***1234`)
  - 密钥来源:`settings.field_encryption_key`(见 Step 2)
- **不改什么**:`app/core/dev_keys.py`(那是 RSA 签名密钥,与字段加密无关)

#### Step 2:config.py 加加密密钥字段

- **改什么**(`app/core/config.py`):
  - 加 `field_encryption_key: str`(Fernet key,base64 urlsafe 32 字节)
  - 复用现有 `model_validator` 模式(L65-81):非 dev/test 环境拒绝默认值(防生产用弱密钥)
  - dev/test 给固定默认值(方便 init.sh 离线测试)
  - **不复用 jwt_secret**(Fernet 需特定格式 key)
- **.env.example / .env**:`FIELD_ENCRYPTION_KEY=<注释生成命令>`,给出 Fernet key 生成方式
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

#### Step 3:LlmConfig model + 迁移

- **新建 `app/models/llm_config.py`**:

  | 列 | 类型 | 说明 |
  |---|---|---|
  | `id` | String(32) PK | uuid hex |
  | `tenant_id` | String(32) FK→tenants, **nullable, index** | NULL=平台级;非空=租户级 |
  | `api_key_encrypted` | Text | Fernet 密文 |
  | `api_key_hint` | String(32) | 明文掩码 `sk-***abcd`,供 GET 回显 |
  | `base_url` | String(255) | 如 `https://api.deepseek.com` |
  | `default_model` | String(64) | 默认模型 |
  | `available_models` | JSON | 可选模型数组 `["deepseek-chat","deepseek-reasoner"]` |
  | `is_active` | Boolean | 默认 True |
  | `created_at` / `updated_at` | DateTime | 时间戳 |

- **单行约束**:靠 service 层 upsert 保证(平台级查 `tenant_id IS NULL`,租户级查 `tenant_id=?`),**不做 DB 唯一约束**(避免 NULL 唯一性的跨库兼容问题,对齐 AGENTS.md「双库兼容」原则)
- **迁移**:`alembic revision --autogenerate -m "add llm_config table"`,`down_revision = 'a2b3c4d5e6f7'`(当前 head)
- **conftest.py 注册**:`tests/conftest.py:85-93` import 列表加 `llm_config`,否则 `create_all` 不建表(最易漏的一步)

#### Step 4:Schema + Repository

- **新建 `app/schemas/llm_config.py`**:
  - `LlmConfigUpdate`:`api_key: str | None`(可选)、`base_url | None`、`default_model | None`、`available_models: list[str] | None`
  - `LlmConfigRead`:`api_key_hint: str`(掩码)、`base_url`、`default_model`、`available_models`、`is_active`(无明文 key、无密文)
  - `EffectiveLlmConfig`(内部用,含解密 api_key,不暴露给 API)
- **新建 `app/repositories/llm_config.py`**:照 `app/repositories/agent.py`(8 行)最小写法;继承 `BaseRepository`;加 `get_platform()` / `get_for_tenant(tenant_id)` / `upsert_platform()` / `upsert_for_tenant()` 方法

---

### 第二阶段:后端 Service + API

#### Step 5:LlmConfigService `app/services/llm_config_service.py`(新建)

- `OBJECT = "settings"`,方法首行 `permission_service.require(...)`(对齐 agent_service 范式)
- **核心方法**:
  - `get_effective(db, tenant_id) -> EffectiveLlmConfig`:**三级 fallback 解析** —— 查租户级 active 配置 → 平台级 active 配置 → env(`settings.openai_*`)。返回**解密后**的 `{api_key, base_url, default_model, available_models}`
  - `get_platform(db) -> LlmConfigRead`(掩码)
  - `upsert_platform(db, payload) -> LlmConfigRead`:加密 key → 存 `api_key_encrypted` + 更新 `api_key_hint`;若 payload.api_key 为空则保留原值
  - `get_tenant(db, tenant_id) -> LlmConfigRead`(掩码)
  - `upsert_tenant(db, tenant_id, payload) -> LlmConfigRead`
  - `list_models(db, tenant_id) -> list[str]`:resolve 到生效配置的 available_models(供 agents 下拉)
- **加解密边界**:只在 `get_effective`(内部)+ `upsert_*` 写入时加密,**Read schema 永远不返回明文/密文**

#### Step 6:settings.py API(新建)+ main.py 注册

- **新建 `app/api/v1/settings.py`**:

  | 方法 | 路径 | 守卫 | 说明 |
  |---|---|---|---|
  | GET | `/settings/llm/platform` | super_admin | 平台级配置(掩码) |
  | PUT | `/settings/llm/platform` | super_admin | 写平台级 |
  | GET | `/settings/llm/tenant` | `settings:manage`(owner/admin) | 本租户配置(掩码) |
  | PUT | `/settings/llm/tenant` | `settings:manage` | 写本租户 |
  | GET | `/settings/models` | 登录即可 | 当前生效可用模型列表 |

- **super_admin 守卫机制**:`permission_service.check` 对 `platform_role=="super_admin"` 直接返回 True(`permission_service.py:63`),平台级端点用 `Depends(require_permission("settings","manage"))` 即可,super_admin 自动放行,普通租户用户需 owner/admin 有此权限

- **main.py 注册**:import `settings` + `app.include_router(settings.router, prefix=prefix)`(import 按字母序,settings 在 roles 与 tenants 之间)

#### Step 7:权限 seed

- **生产侧** `permission_service.py:373-391`:`DEFAULT_OWNER_PERMS` / `DEFAULT_ADMIN_PERMS` 加 `("settings","manage")`
- **测试侧** `tests/conftest.py:40-50` `_make_casbin`:owner/admin policy 列表加 `("settings","manage")`
- **幂等 seed**:`scripts/init_admin.py` 重跑一次即可给老租户补权限(对齐现有 seed 机制)

---

### 第三阶段:修复核心 bug(graph + chat)

#### Step 8:graph.py stream_agent 解耦全局配置

- **改什么**(`app/agents/graph.py`):
  - `stream_agent` 签名加 `api_key: str`、`base_url: str`、`model: str` 三个**必传**参数(由 chat.py 解析好传入)
  - `ChatOpenAI` 实例化改用传入参数,移除对 `settings.openai_*` 的直接依赖 → 变成纯函数(更可测)
  - `build_agent`(L48)同步改造
- **效果**:stream_agent 不再硬绑全局配置,模型/key 由调用方决定

#### Step 9:chat.py 解析配置 + 传 model

- **改什么**(`app/api/v1/chat.py` `chat_stream`):
  ```python
  config = await llm_config_service.get_effective(db, user.tenant_id)
  model = agent.model if agent.model in config.available_models else config.default_model
  async for chunk in stream_agent(
      ..., model=model, api_key=config.api_key, base_url=config.base_url,
      system_prompt=agent.system_prompt, ...
  ):
  ```
- **兜底**:agent.model 不在可用列表时用 default_model(防止脏数据导致 400)
- **效果**:Bug 1 修复 —— Agent.model 真正生效

---

### 第四阶段:后端测试

#### Step 10:test_llm_config.py(新建)

参照 `test_permissions_api.py` HTTP 集成模式。用例:
- **crypto 单测**:encrypt→decrypt 往返、mask_api_key 格式
- **平台级 CRUD**:super_admin 写读;普通租户用户 GET 平台级 → 403
- **租户级 CRUD**:owner/admin 写读;member → 403
- **get_effective 解析优先级**:租户级存在 → 用租户级;不存在 → 用平台级;都不存在 → env 兜底
- **key 掩码**:GET 返回 hint 不返回明文/密文;PUT 留空 key → 不改
- **跨租户隔离**:租户 A 看不到租户 B 的配置(用 db_session 直插 + 断言,参照 test_permissions_api 跨租户写法)

#### Step 11:更新 test_chat.py

- `fake_stream` 改成显式接收 `model/api_key/base_url` 并记录,补断言 `model` == agent.model(**验证 Bug 1 修复**)
- mock `llm_config_service.get_effective` 返回固定配置(避免依赖真实 DB 配置)
- 现有 9 个测试因 `fake_stream` 用 `**kwargs` 不会因签名变更崩溃,但补强断言

#### Step 12:后端总验证

- `./init.sh` 全绿(ruff + pytest,含新测试,无回归)
- `APP_ENV=testing alembic upgrade head` 迁移链通过(CI migrations job 守门)

---

### 第五阶段:前端

#### Step 13:前端 API 层

- **types.ts**:`LlmConfig`(api_key_hint/base_url/default_model/available_models/is_active)、`LlmConfigUpdate`、`ModelList`
- **endpoints.ts**:加 `// ---------- llm settings ----------` 区,`fetchPlatformLlmConfig`/`updatePlatformLlmConfig`/`fetchTenantLlmConfig`/`updateTenantLlmConfig`/`fetchEffectiveModels`
- **queries.ts**:`qk.llmConfigPlatform`/`qk.llmConfigTenant`/`qk.effectiveModels`,对应 5 个 hook(useQuery/useMutation,onSuccess invalidate)

#### Step 14:新建 settings-page.tsx

- RHF + zod + **Card 内联表单**(非 Dialog,设置页是常驻页)
- **平台级 Card**:仅 `me.platform_role==="super_admin"` 可见可编辑
- **租户级 Card**:`canManageUsers(me)`(owner/admin/super_admin)可见可编辑
- **API key 输入框**:`type="password"` + Eye/EyeOff 切换(lucide-react 已有图标);占位符显示当前掩码 hint(如 `sk-***abcd`),留空=不改
- **available_models 编辑器**:可增删标签(输入框 + 回车添加 + × 删除)
- 保存:`useUpdate*LlmConfig`,toast 反馈

#### Step 15:修复 agents-page.tsx

- 删除硬编码 `MODELS`(L43),改成 `useEffectiveModels()` 动态加载
- 默认值 `gpt-4o-mini`(L49,65,70)改成生效配置的 `default_model`
- 模型下拉从 `<select>` 硬编码遍历改成动态遍历

#### Step 16:路由 + 导航

- **App.tsx**:`/settings` 放进 `RequireUserManagement` 块(与 users/roles/permissions 并列)
- **dashboard-layout.tsx**:NAV_ITEMS 加 `{ to:"/settings", label:"设置", icon:Settings, needsUserManagement:true }`(import `Settings` from lucide-react)

#### Step 17:前端总验证

- `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)
- `npx oxlint src/` 改动文件 0 warning

---

### 第六阶段:真实对话验证(用户参与)

#### Step 18:配置真实 key + 启动

- 用户在对话中提供真实 DeepSeek key → 配进 `.env`(`OPENAI_API_KEY=真实key`,不入 git)作 env 兜底
- 后端连 `aap-postgres` docker(已确认在跑),`alembic upgrade head` 建新表
- `scripts/init_admin.py` 建超管(若已有则跳过),本地密码登录

#### Step 19:端到端真实跑通

- 前端 dev server 启动,登录,进设置页配 LLM(或直接走 .env 兜底)
- 建 agent(选 deepseek-chat)→ 进对话页发消息 → **验证 SSE 流式打字机真实输出**
- 验证:切换不同 model 的 agent 对话行为不同
- 修任何运行时 bug(SSE 真实 DeepSeek API 下可能有超时/错误帧边界情况)

#### Step 20:记录证据

- 验证结果写入 `feature_list.json` 的 `evidence` 字段
- `progress.md` 记会话(Session 014)

---

## 验收标准

1. **Bug 1 修复**:Agent.model 在对话中真正生效(测试断言 stream_agent 收到的 model == agent.model)
2. **Bug 2 修复**:前端模型列表动态来自后端,无硬编码 GPT/Claude
3. **Bug 3 完成**:LLM 配置数据库持久化 + 加密存储 + 三级 fallback + 前端设置页
4. `./init.sh` 全绿(ruff + pytest,含新测试 test_llm_config.py + 更新的 test_chat.py)
5. `cd frontend && npm run build` 通过 + oxlint 0 warning
6. **(真实)DeepSeek key 下,SSE 流式对话端到端跑通**,运行时 bug 已修
7. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 真实验证暴露运行时 bug(SSE 真实 API 边界) | 预留阶段 6 修;若 key 受阻,阶段 1-5 可独立完成(离线测试验证逻辑),阶段 6 待 key 到位再跑 |
| field_encryption_key 首次部署 | 生产需生成 Fernet key 配置,否则 model_validator 拦截启动;.env.example 加注释 + 生成命令 |
| 平台级 vs 租户级 UI 复杂度 | 设置页两个 Card + 权限分层,比单一表单复杂,但符合「超管 + 租户级」需求 |
| stream_agent 改签名影响现有测试 | fake_stream 用 `**kwargs` 不会因签名变更崩溃;但建议补强断言显式验证 model 传递 |
| conftest.py 漏注册新模型 | create_all 不建表会报 "no such table";conftest.py:85-93 import 列表必须加 llm_config |
| super_admin 权限守卫 | 平台级端点用 `require_permission("settings","manage")`,super_admin 自动放行(check() 对 platform_role=="super_admin" 返回 True);无需额外守卫逻辑 |

### 不做的事(边界)

- 不动 `tenant-org-admin-ui`(暂停,WIP=1)
- 不加 LLM provider 多选 UI(只支持 OpenAI 兼容接口,DeepSeek/OpenAI/Moonshot 等都能用,改 base_url 即可)
- 不加用量计费 / token 统计 / 调用日志
- 不改现有权限矩阵数据结构(只加 settings 对象的 seed)
- 不改 Conversation/Message schema(已在上个任务加 updated_at)
- 不做多 LLM 并发路由 / 负载均衡

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| bug 根因 1(stream_agent 用全局 model) | `app/agents/graph.py:67-89` |
| bug 根因 2(chat 调用未传 agent.model) | `app/api/v1/chat.py:86-93` |
| 前端硬编码模型列表(待删) | `frontend/src/pages/agents-page.tsx:43` |
| Repository 基类 | `app/repositories/base.py`(BaseRepository / TenantScopedRepository) |
| 最小 repository 范例 | `app/repositories/agent.py`(8 行) |
| Service 范式 | `app/services/agent_service.py`(OBJECT 常量 + require_permission) |
| API 端点结构模板 | `app/api/v1/agents.py` / `permissions.py` |
| 权限 seed 唯一真源 | `app/services/permission_service.py:373-391`(DEFAULT_*_PERMS) |
| require_permission 工厂 | `app/api/deps.py:151-170` |
| 加密依赖(已装) | `requirements.txt:22` cryptography==44.0.0 |
| config model_validator 范本 | `app/core/config.py:65-81` |
| 迁移链 head | `a2b3c4d5e6f7`(`alembic/versions/2026_07_10_1200_...`) |
| conftest 模型注册 | `tests/conftest.py:85-93` |
| conftest casbin seed | `tests/conftest.py:40-50`(owner policy 列表) |
| HTTP 集成测试范式 | `tests/test_permissions_api.py` |
| chat mock 范式 | `tests/test_chat.py:33-52`(_mock_chat + fake_stream) |
| 前端表单范式 | `frontend/src/pages/agents-page.tsx`(RHF+zod+Dialog) |
| 前端 API 层 | `frontend/src/api/client.ts` + `endpoints.ts` + `types.ts` |
| 前端权限 helper | `frontend/src/lib/permission.ts`(canManageUsers) |
| 路由守卫 | `frontend/src/components/auth/require-permission.tsx` + `App.tsx:51-55` |
| 导航注册 | `frontend/src/components/layout/dashboard-layout.tsx:21-36`(NAV_ITEMS) |
| DeepSeek 文档 | https://api-docs.deepseek.com/zh-cn/ |
