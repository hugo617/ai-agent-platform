# 计划:API Token 细粒度 Scope(scope 收敛闭环)

> **状态**:草案 v2(经一轮对抗式审查重写,待二轮审查)
> **不在 feature_list.json 登记**:用户尚未决定立项,本文档仅为审查与讨论而生
> **前置**:`atoa-api-token-auth`(已 passing)—— `ApiToken` 表已存在,`scopes` 字段已预留
> **同类先例**:`plan-permission-data-scope.md`(Role.data_scope 四档)、`plan-atoa-api-token-auth.md`(PAT 地地)

---

## v1 → v2 变更摘要(为什么重写)

v1 经一轮对抗式审查发现 3 个致命问题,本版针对性重写:

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| **范式 B + 工具内 check 的 scope 注入盲区**:v1 只改 `require_permission` 闭包,但 `permission_service.check/require` 直调点共 30+ 处(`agent_service` 9 / `conversation_service` 7 / `api_token_service` 3 / `knowledge_service` 3 / `customers`·`logs`·`exports` 多处 / `graph.py` 工具内 2 处),这些点拿不到 scopes,token 调最常用 Agent API 时 scope 闸门全失效 | 🔴 | **改用 contextvar 注入**:`check()` 内部读 `current_token_ctx` 取 scopes,所有 caller 零改动 |
| **super_admin 颁发 token 收敛后变空集**:`get_implicit_permissions_for_user` 对 super_admin 返回 `[]`(casbin 无 policy),交集=空集,token 无法使用 | 🔴 | **issue() 收敛时特判 super_admin**:grantor_perms 用全集(动态拼 `DEFAULT_OWNER_PERMS` 等四份常量)而非查 casbin |
| **backfill "restricted + 全集" 不等价且有越权风险**:admin/member 颁发的旧 token backfill 成 owner 全集=越权;授予者权限时点无法还原 | 🔴 | **backfill 改 `scope_mode="full"`**:真正的行为等价,不做 scopes 求交集 |
| MVP 一次性打包 scope+budget+model+RPM 违反「不过度设计」铁律 | 🟡 | **砍到只做 scope 收敛**:budget/model/RPM 推迟到独立后续任务 |
| `/api-tokens/scopes` 与已有 `/permissions/catalogue?type=api` 重复 | 🟡 | **砍掉新端点**,前端直接复用 catalogue |
| v1 称 `customer_id` 是 "nullable + 无 FK + index" 范式 | 🟡 | **事实更正**:`usage_event.py:68` 的 `customer_id` 实际**无 index**;v2 砍掉 budget 维度,此问题随项消失 |
| v1 称 `sum_tokens_for_customer` 可直接克隆 | 🟡 | v2 砍 budget,不再克隆 |
| v1 称 `get_implicit_permissions_for_user` "已有缓存机制" | 🟢 | **事实更正**:无缓存,每次走 `run_in_threadpool`;v2 收敛逻辑会明确这一点 |
| v1 写 "DEFAULT_OWNER_PERMS 约 33 项" | 🟢 | **事实更正**:实际 35 项(见下「全量权限码」) |

---

## ⚠️ 调研诚信声明(必读)

| 项 | 实情 |
|---|---|
| **网络工具状态** | 会话期间 `WebSearch`/`WebFetch`/`webReader` 三个 MCP 工具全部返回 **429 配额超限**,重置时间 **2026-08-05 22:54 UTC**。 |
| **竞品信息来源** | GitHub fine-grained PAT / Stripe Restricted key / AWS STS Session Policy 等设计模式**完全基于训练数据**(约 2024 中~2025 初),2025 下半年至 2026 各产品功能迭代频繁,**可能已变化**。 |
| **项目现状来源** | **逐字读取源码**取证,覆盖 `app/models/api_token.py` / `app/services/api_token_service.py` / `app/api/deps.py` / `app/services/permission_service.py` / `app/repositories/api_token.py` / `app/repositories/usage_event.py` / `app/api/v1/chat.py` / 前端 `settings-page.tsx` / `permissions-page.tsx`。**所有"现状"段落都有源码出处**。 |
| **建议后续动作** | 等 2026-08-05 后用 web access skill 复核竞品设计是否仍成立。 |

---

## 背景:为什么需要这个任务(只做 scope 收敛)

平台 AtoA 系列已完成 `atoa-api-token-auth`:外部 AI Agent 持 `ahp_` 前缀 token 即可访问平台全部 API。但当前实现存在**安全风险**:

> **任何 API Token 都 100% 继承颁发者的全部权限** —— `scopes` 字段虽已建模并持久化,但 `verify()` 解析时**主动丢弃**,鉴权链路从未读取。

**威胁模型(已核实,成立):**
- Agent 是 7×24 运行的机器身份,token 泄漏路径多于人类账号(日志、配置文件、环境变量、第三方框架回传);
- 当前一个 token 等于"全权代表你操作",一旦泄漏=全部数据可读写;
- Agent 数量会爆炸(每个 Agent 都要 token),不能每个都全权。

**本任务边界(只做这一件事):** ①权限收敛(token 只能调用显式授权的 API 子集)+ ②强制迁移旧 token 到新模型。**不做** budget / model_allowlist / RPM(见「不做的事」)。

### 为什么砍掉 AI 风控维度

对照项目铁律(AGENTS.md):「**按需加表,不预建空架子,不过度设计**」。本平台定位是**脚手架**(README.md),不是生产级 AI 网关。budget/model/RPM 是面向 C 端商业化 AI API(Anthropic/OpenAI 范式)的运维/商业优化,在脚手架阶段:
- 没有真实计费(`Wallet.balance` 是 demo 数据);
- 模型清单还在频繁迭代(`2026_07_17` 刚改完向量维度),现在加 model_allowlist 字段=空架子;
- RPM 内存计数在多 worker 下默认失效,是 bug 不是限制。

**安全 > 优化**。先把 scope 收敛闭环做扎实,budget/model/RPM 等有真实生产数据再独立立项。

---

## 现状取证(源码精确证据,逐条核实过)

### 数据通道已就绪,鉴权链路完全不读 scopes

| 层 | 状态 | 源码位置 |
|---|---|---|
| `ApiToken.scopes` JSONB 列 | ✅ 已存在,`NOT NULL`,default `[]` | `app/models/api_token.py:61-66` |
| `ApiTokenCreate.scopes` / `ApiTokenRead.scopes` / `ApiTokenCreated.scopes` | ✅ 三个 DTO 全含 `scopes: list[str]` | `app/schemas/api_token.py` |
| `issue()` 写入 scopes 到 DB 并回显 | ✅ `payload.scopes → row.scopes → response.scopes` | `api_token_service.py:83-105` |
| 前端类型 + 颁发表单提交 scopes | ❌ `handleIssue`(settings-page:778)不下发 scopes;列表无 scope 列 | `frontend/src/pages/settings-page.tsx:778,943` |

### 鉴权链路的三个致命断点(逐字核实)

| 断点 | 源码 | 后果 |
|---|---|---|
| ① `verify()` 丢弃 scopes | `ResolvedToken` 只有 `user_id/tenant_id` 两字段(`api_token_service.py:41-46`),`api_token_service.py:136` `return ResolvedToken(user_id=..., tenant_id=...)` | token 携带的 scopes 在认证时丢失 |
| ② `CurrentUser` 无 scopes 字段 | `app/api/deps.py:45-62` 只有 `user_id/tenant_id/email/jti/platform_role` | 拿到 scopes 也无处透出 |
| ③ `check()` 无 scope 入口 | `permission_service.py:50-77` 五参数 `check(user_id, tenant_id, obj, act, platform_role)` | 鉴权汇聚点没有 scope 闸门 |

### scope 注入点:不只 `require_permission`,还有 30+ 直调 caller(关键证据)

`permission_service.check/require` 的全量 caller(grep 核实):

| 位置 | 数量 | 调用形式 |
|---|---|---|
| `app/api/deps.py` `require_permission` 闭包 | ~60+ 处 router 依赖 | `check(user_id, tenant_id, obj, act, platform_role=...)` |
| `app/services/agent_service.py` | **9 处** 直调 `require` | service 层 |
| `app/services/conversation_service.py` | **7 处** 直调 `require` | service 层 |
| `app/services/api_token_service.py` | 3 处 直调 `require` | service 层 |
| `app/services/knowledge_service.py` | 3 处 直调 `require` | service 层 |
| `app/api/v1/customers.py` / `logs.py` / `exports.py` | 多处 直调 `require/check` | router 层范式 B |
| `app/agents/graph.py:66,86` | **2 处** 工具内直调 `check` | **Agent 工具内,只持有 user_id/tenant_id,拿不到 CurrentUser** |

**v1 的错误**:只改 `require_permission` 闭包注入 scopes,会让 service 层直调(对话/智能体/知识库这些 Agent 最常用的 API)和工具内 check **完全读不到 scopes**,scope 闸门对核心场景失效。

**v2 的解法**:用 **contextvar** 在请求入口写入 token 上下文,`check()` 内部主动读取,所有 caller 零改动。详见「核心设计」。

### verify() 已正确处理 revoke(撤回 v1 的错误断言)

v1 曾怀疑 `verify()` 不查 `is_active`,revoke 失效。**核实更正**:`api_token.py:28-29` 的 `find_by_prefix` 显式带 `is_active.is_(True)` 和 `is_deleted.is_(False)`,**revoke 是即时生效的**。本任务不碰这块。

---

## 用户决策清单(v2 调整后)

| 决策点 | v1 选择 | v2 选择 | 变更理由 |
|---|---|---|---|
| MVP 范围 | 完整(scope+budget+model+RPM) | **只做 scope 收敛** | 违反「不过度设计」铁律;安全闭环优先 |
| AI 维度 | 现在做 | **推迟** | 独立后续任务 |
| 迁移策略 | restricted + 全集 | **`scope_mode="full"` + scopes=全集** | 真正的行为等价,避免越权 |
| 超管语义 | token 受 scope 约束 | **不变,但 issue() 收敛要特判 super_admin** | 否则 super_admin token 收敛后变空集无法使用 |
| scope 矩阵 | 4 类核心 | **不变**(customers/agents/conversations/knowledge × 核心动词) | — |
| budget 模型 | 聚合阈值 | **不做** | 推迟 |
| scope 数据源 | 新建 `/api-tokens/scopes` | **复用 `GET /permissions/catalogue?type=api`** | 已有端点,避免重复 |
| 注入机制 | 改 `check()` 签名 + require_permission 闭包 | **contextvar + `check()` 内部读取** | 解决 30+ 直调 caller 盲区 |

---

## 核心设计

### 安全铁律(抄 AWS STS 的交集代数)

```
effective_scopes = token.scopes ∩ grantor_current_permissions
```
- 颁发时收敛(`payload.scopes ∩ 颁发者权限`)存 DB
- 调用时实时再算交集(颁发者权限可能在 token 生命周期内被 revoke/降级)
- token 永不超授予者(GitHub 铁律)
- 写蕴含读(`customers:update` 自动满足 `customers:read`)

### scope_mode 三态

| mode | 行为 | 来源 |
|---|---|---|
| `full` | **继承授予者当前全部权限**(运行时动态求 grantor perms,不读 scopes) | 旧 token 强制迁移到此(行为等价);新建可选 |
| `restricted` | **仅 token.scopes ∩ grantor 当前权限 内**(强制要求 scopes 非空) | 新建 token 默认值 |

**注意:`full` 模式不等于"v1 的 legacy"**。v1 把旧 token 标 restricted+全集是想"行为等价",但 restricted+全集要求 scopes 是静态快照,授予者权限变更后行为会漂移。v2 的 `full` 模式在每次请求时动态求 grantor 当前权限,这才是真正的行为等价(授予者降级,token 自动跟着降)。

### 注入机制:contextvar(解决 30+ caller 盲区)

**新增** `app/api/token_context.py`(项目首次引入 contextvar,需评审是否接受新范式):

```python
from contextvars import ContextVar
from dataclasses import dataclass

@dataclass
class TokenCtx:
    token_id: str
    scopes: list[str]
    scope_mode: str  # "full" | "restricted"

# None = 当前请求是 JWT 路径(或测试),不走 token scope 闸门。
current_token_ctx: ContextVar[TokenCtx | None] = ContextVar("current_token_ctx", default=None)
```

**写入点**:`deps._resolve_api_token` 末尾(已核实此函数是 ahp_ 路径唯一入口,`deps.py:168-221`):
```python
# _resolve_api_token 末尾,return CurrentUser(...) 之前
current_token_ctx.set(TokenCtx(token_id=resolved.token_id, scopes=resolved.scopes, scope_mode=resolved.scope_mode))
```

**读取点**:`permission_service.check()` 开头(JWT 路径 ctx=None 自动短路,零回归):
```python
async def check(self, user_id, tenant_id, obj, act, platform_role=None):
    ctx = current_token_ctx.get()  # None for JWT path → skip scope gate
    if ctx is not None and ctx.scope_mode == "restricted":
        # scope 闸门在前,super_admin bypass 在后(实现"超管 token 也受约束")
        required = {f"{obj}:{act}", f"{obj}:manage"}
        if act in ("update", "delete", "create", "chat", "export"):
            required.add(f"{obj}:read")  # 写/对话/导出蕴含读
        if not (set(ctx.scopes) & required):
            return False
    # 现有 super_admin / hq_staff 旁路保留
    if platform_role == "super_admin":
        return True
    if platform_role == "hq_staff" and act == "read":
        return True
    # 走原 casbin
    ...
```

**为什么 contextvar 比改签名好:**
1. **零 caller 改动**:30+ 个直调点、graph.py 工具内 check,全部自动生效;
2. **graph.py 工具内 check 也能拿到 scope**:工具只持有 user_id,但 contextvar 是请求级上下文,工具内 `permission_service.check` 自然读得到;
3. **JWT 路径零回归**:JWT 不 set ctx,`get()` 返回默认 None,短路;
4. **测试友好**:测试里不 set ctx,所有现有测试不受影响。

**contextvar 的已知风险(必须在测试覆盖):**
- **asyncio 任务边界**:FastAPI 每个请求独立 task,contextvar 不会跨请求泄漏。但若有 `asyncio.create_task` 派生子任务,子任务**会继承**父任务 ctx —— 需确认 chat.py SSE 流、orchestrator 派生 specialist 调用是否安全(初步看 stream_agent 在同 task 内,但需测试覆盖)。
- **线程池**:`check()` 内部 `run_in_threadpool` 调 casbin,但 contextvar 读取在 `run_in_threadpool` **之前**(scope 检查是纯 Python set 操作,不开线程),不受影响。

### super_admin 收敛特判(修 v1 致命问题 #2)

`issue()` 收敛逻辑:
```python
# grantor_perms 计算
if platform_role == "super_admin":
    # super_admin 在 casbin 里没有 policy(靠 platform_role bypass 全权),
    # get_implicit_permissions_for_user 对 super_admin 返回 []。
    # 不能直接交集,否则 token scopes 永远为空。
    grantor_perms = _all_known_scope_codes()  # 动态拼 DEFAULT_OWNER/ADMIN/MEMBER/MENU
else:
    implicit = await permission_service.get_implicit_permissions_for_user(user_id, tenant_id)
    grantor_perms = {f"{p[0]}:{p[1]}" for p in implicit}  # casbin 返回 [sub,dom,obj,act]
effective = [s for s in payload.scopes if s in grantor_perms]
if scope_mode == "restricted" and not effective:
    raise ValueError("restricted token must retain ≥1 scope after intersection")
row.scopes = effective
```

`_all_known_scope_codes()` = `DEFAULT_OWNER_PERMS ∪ DEFAULT_ADMIN_PERMS ∪ DEFAULT_MEMBER_PERMS ∪ menu scopes` 的 `"<obj>:<act>"` 字符串集合(去重)。

### 全量权限码(实际核实,非 v1 的"约 33 项")

`permission_service.py:452-469` 的 `DEFAULT_OWNER_PERMS` 逐条数:
- `agents`: read/create/update/delete/export = **5**
- `conversations`: read/create/update/delete/chat = **5**
- `users`: read/create/update/delete = **4**
- `roles`: read/create/update/delete = **4**
- `settings`: read/update = **2**
- `api_tokens`: read/create/delete = **3**
- `customers`: read/create/update/delete/export = **5**
- `wallet`: read/update = **2**
- `billing`: read = **1**
- `logs`: read = **1**
- `knowledge`: read/create/delete = **3**

**OWNER 合计 = 35 项**(v1 写 33 是错的)。

**menu:tenants 的归属问题(v1 没识别):**
`menu:tenants` 是 super_admin 专属,**不在任何 `DEFAULT_*_PERMS` 里**(`permission_service.py:502-505` 注释明确)。所以:
- 普通租户 backfill 到 `full` 模式:**不需要 menu:tenants**(本来也没有);
- super_admin 的旧 token backfill 到 `full` 模式:**运行时动态求 grantor perms,super_admin 走 `_all_known_scope_codes()`,自动包含 menu:tenants**(只要 `_all_known_scope_codes()` 把 `MENU_CN` 的 key 也拼进去)。

`_all_known_scope_codes()` 必须显式包含 `menu:tenants` 等 MENU 字典里的全部 key,否则 super_admin 旧 token 会丢菜单权限。**这是 v2 必须覆盖的测试点。**

### backfill 策略(修 v1 致命问题 #3)

**v2:`scope_mode="full"` + `scopes=全集`**。
- `full` 模式运行时动态求 grantor 当前权限,**不读 scopes 字段**,所以 backfill 时 scopes 写什么不影响行为(写全集只为可读性/未来切 restricted 时有兜底);
- 不做"按 owner 当时权限求交集",**避免越权风险**(admin/member 颁发的旧 token backfill 成 owner 全集 = 越权);
- 真正的行为等价:旧 token 全权 → `full` 模式全权(动态 grantor perms),授予者降级时 token 自动跟着降。

**backfill 可重入性(修 v1 问题):**
```sql
-- server_default 让新列加完后所有旧行 scope_mode='restricted'(不是 NULL),
-- 所以用 scopes IS NULL 或空判断行不通。改用迁移标记列或版本号:
UPDATE api_tokens
SET scope_mode='full', scopes='<全集 JSON>'
WHERE scope_mode='restricted' AND scopes='[]';
```
- 第一行执行后,scopes 不再是 `[]`,**重入时 WHERE 不命中**,幂等 ✅;
- 但若迁移中途失败(部分行已更新),**已更新行 scopes=全集,未更新行 scopes=[]** —— 状态不一致。缓解:`alembic` 迁移是单事务,失败整体回滚;若担心大表超时,改用独立脚本 `scripts/backfill_api_token_scopes.py` 带 `--dry-run` + 分批 + 进度文件。

---

## 影响面(7 后端 + 1 迁移 + 3 前端 + 2 测试,比 v1 瘦一半)

### 后端(7 文件)

1. **`app/models/api_token.py`** —— 加 1 列 `scope_mode: Mapped[str]`(default `"restricted"`,server_default `"restricted"`)。**不加** budget/model/RPM 列(已砍)。
2. **`app/api/token_context.py`**(新建)—— `TokenCtx` dataclass + `current_token_ctx: ContextVar`。
3. **`app/schemas/api_token.py`** —— `ApiTokenCreate` / `ApiTokenRead` / `ApiTokenCreated` 三 DTO 加 `scope_mode` 字段(默认 `"restricted"`)。
4. **`app/services/api_token_service.py`** ——
   - `ResolvedToken` 加 `token_id` / `scopes` / `scope_mode` 三字段;
   - `verify()`(`api_token_service.py:136`)回填这三字段;
   - `issue()` 加 scope 收敛逻辑(**含 super_admin 特判**)。
5. **`app/services/permission_service.py`** —— `check()` 开头插 contextvar 读取 + scope 闸门(JWT 短路)。**不改签名**,所有 caller 零改动。
6. **`app/api/deps.py`** ——
   - `CurrentUser` 加 `api_token_id`(可选,仅用于 UsageEvent 透传预留;v2 不写入 UsageEvent);
   - `_resolve_api_token` 末尾 `current_token_ctx.set(...)`。
7. **`app/api/v1/api_tokens.py`** —— `issue` 接收 `scope_mode`;`GET /verify` 回显 scopes + scope_mode。**不新建 `/scopes` 端点**(复用 `/permissions/catalogue`)。

### 迁移(1 文件)

8. **`alembic/versions/2026_07_XX_add_api_token_scope_mode.py`** ——
   - 加 1 列(`api_token.scope_mode`,带 server_default);
   - backfill 旧 token(`scope_mode='full'`, `scopes=全集`);
   - `down_revision` 接当前 head `2026_07_17_0100_c5d6e7f8a9b0`(change_embedding_dimension)。
   - **可选独立脚本** `scripts/backfill_api_token_scopes.py`(`--dry-run` + 分批,大表保险)。

### 前端(3 文件)

9. **`frontend/src/api/types.ts`** —— `ApiToken` / `ApiTokenCreate` 加 `scope_mode`。
10. **`frontend/src/pages/settings-page.tsx`** —— 颁发 Dialog 重构:
    - scope 矩阵(复用 permissions-page 的 PermCell 范式:绿/灰 button + Check/Minus + pendingCell 防双击,`permissions-page.tsx:332-369` 已核实);
    - scope 数据源调 `GET /permissions/catalogue?type=api`,前端按 obj 过滤出 4 类核心(customers/agents/conversations/knowledge);
    - `scope_mode` 单选(默认 restricted,可选 full);
    - 表格加 scope 列(展示已选 scope 数量 + tooltip 列表);
    - 删除 `settings-page.tsx:943` 占位提示(已核实行号)。
11. **`frontend/src/hooks/queries.ts`** —— 复用已有 `usePermissionsCatalogue`(若无则新增,但优先复用)。

### 测试(2 文件)

12. **`tests/test_api_token_scopes.py`**(新建)——
    - scope 收敛(颁发时 ∩ 颁发者权限);
    - **super_admin 颁发 token 不变空集**(关键回归点);
    - 实时交集(颁发者 revoke 权限后 token 失效);
    - migration 兼容(旧 token backfill 到 full,行为不变);
    - **超管 token 也受 scope 约束**(restricted token 调用非授权 scope 被 403);
    - **范式 B 直调 caller 也读 scope**(调 `conversation_service.create` 时 token scope 闸门生效);
    - **graph.py 工具内 check 也读 scope**(Agent 工具调用时 scope 闸门生效);
    - 空边界(restricted + scopes=[] → 全拒);
    - 写蕴含读(`customers:update` 满足 `customers:read`);
    - **chat/export 动作的蕴含规则**(v1 漏的);
    - **contextvar 跨 task 不泄漏**(模拟 `asyncio.create_task` 派生);
    - JWT 路径零回归(ctx=None,现有 super_admin bypass 测试全过)。
13. **`tests/test_permission_service.py`**(扩展)—— `check()` contextvar 读取的边界用例。

### 砍掉的(v1 有 v2 无)

- ❌ `app/models/usage_event.py` 加 `api_token_id`(budget 砍)
- ❌ `app/repositories/usage_event.py` 加 `sum_tokens_for_api_token`(budget 砍)
- ❌ `app/api/v1/chat.py` 改造(budget/model/RPM 砍)
- ❌ `app/repositories/api_token.py` 加 `get_for_update`(RPM 砍)
- ❌ `app/services/api_token_service.py` 加 `check_budget()`(budget 砍)

---

## 实施步骤(按依赖顺序,分 4 阶段)

### 阶段 1:Schema 层(地基)

**Step 1.1** `app/models/api_token.py` 加 `scope_mode` 列:
```python
scope_mode: Mapped[str] = mapped_column(
    String(16), default="restricted", server_default="restricted"
)
```

**Step 1.2** 写迁移 `2026_07_XX_add_api_token_scope_mode.py`:
- 加 1 列(带 server_default);
- backfill:`UPDATE api_tokens SET scope_mode='full', scopes='<全集 JSON>' WHERE scope_mode='restricted' AND scopes='[]'`;
- 全集 JSON 硬编码(从 `_all_known_scope_codes()` 派生,OWNER 35 项 ∪ MENU keys,去重);
- `down_revision` 接 `2026_07_17_0100_c5d6e7f8a9b0`。

**Step 1.3** `app/schemas/api_token.py`:
- `ApiTokenCreate` 加 `scope_mode: Literal["full","restricted"] = "restricted"` + `scopes: list[str] = []`;
- `ApiTokenRead` / `ApiTokenCreated` 同步;
- restricted 模式下 scopes 非空校验(validator)。

### 阶段 2:鉴权链路(scope 闸门核心)

**Step 2.1** 新建 `app/api/token_context.py`:`TokenCtx` + `current_token_ctx`。

**Step 2.2** `app/services/api_token_service.py`:
- `ResolvedToken` 加 `token_id` / `scopes` / `scope_mode` 三字段;
- `verify()`(`api_token_service.py:136`)回填:`ResolvedToken(user_id=..., tenant_id=..., token_id=row.id, scopes=list(row.scopes), scope_mode=row.scope_mode)`;
- `issue()` 加 scope 收敛(**含 super_admin 特判**,见「核心设计」)。

**Step 2.3** `app/api/deps.py`:
- `_resolve_api_token` 末尾 `current_token_ctx.set(TokenCtx(...))`;
- **JWT 路径不 set**(零回归)。

**Step 2.4** `app/services/permission_service.py` `check()` 开头插 scope 闸门:
- 读取 `current_token_ctx.get()`;
- ctx is None 或 `scope_mode == "full"` → 短路(走原逻辑);
- `scope_mode == "restricted"` → 计算 required codes(含 chat/export 蕴含读),set 交集为空返回 False;
- **scope 闸门在前,super_admin bypass 在后**(实现"超管 token 也受约束")。

### 阶段 3:API 端点

**Step 3.1** `app/api/v1/api_tokens.py`:
- `POST ""` 接收 `scope_mode` + `scopes` 透传 service;
- `GET "/verify"` 回显 scopes + scope_mode(让外部 Agent 可 introspect)。

### 阶段 4:前端 + 测试

**Step 4.1** `frontend/src/api/types.ts` + `settings-page.tsx`:
- 类型扩展;
- 颁发 Dialog 加 scope 矩阵(复用 PermCell)+ scope_mode 单选;
- 数据源 `GET /permissions/catalogue?type=api`;
- 表格加 scope 列;
- 删 `settings-page.tsx:943` 占位提示。

**Step 4.2** 新建 `tests/test_api_token_scopes.py`(见「影响面」测试列表,12 类用例)。

**Step 4.3** 总验证:
```bash
./init.sh  # ruff + pytest 全绿(含新增 12 类用例)
cd frontend && npm run build  # tsc + vite
cd frontend && npx oxlint src/  # 0 warnings
alembic upgrade head && alembic check  # 无 drift
```

---

## 验收标准

1. ✅ 新建 token 默认 `scope_mode="restricted"`,必须选至少 1 个 scope(restricted 模式下收敛后非空)
2. ✅ 旧 token 强制迁移为 `scope_mode="full"`,**行为完全不变**(运行时动态求 grantor perms)
3. ✅ `token.scopes ∩ 颁发者权限` 实时生效(颁发者 revoke/降级权限后 token 立即跟着失效)
4. ✅ **super_admin 颁发的 restricted token 收敛后非空,仍可用选中 scope**(v1 致命问题 #2 修复验证)
5. ✅ **super_admin 颁发的 restricted token 调用未授权 scope 时被 403**(超管 token 也受约束)
6. ✅ **范式 B 直调 caller 也读 scope**:`conversation_service.create` / `agent_service.*` / `knowledge_service.*` 在 token restricted 模式下 scope 闸门生效(v1 盲区修复验证)
7. ✅ **graph.py 工具内 check 也读 scope**:Agent 工具调用在 token restricted 模式下 scope 闸门生效
8. ✅ contextvar 不跨请求泄漏(模拟并发请求 + `asyncio.create_task` 派生)
9. ✅ JWT 路径零回归(ctx=None,现有 super_admin bypass / hq_staff 测试全过)
10. ✅ 写/对话/导出蕴含读:`customers:update` / `conversations:chat` / `customers:export` 自动满足 `customers:read`
11. ✅ 前端颁发 Dialog 含 scope 矩阵(4 类核心)+ scope_mode 单选
12. ✅ 前端 token 列表展示 scope 信息
13. ✅ `./init.sh` + `npm run build` + `oxlint` 全绿
14. ✅ alembic check 无 drift

---

## 风险与注意事项

| 风险 | 缓解 |
|---|---|
| **contextvar 是项目首次引入的新范式** | 评审确认;测试覆盖 asyncio task 边界;`token_context.py` 加详细注释解释为什么不用改签名 |
| **contextvar 在 `asyncio.create_task` 派生子任务时会继承** | chat.py SSE / orchestrator specialist 调用需确认是否安全(初步看同 task 内);测试显式覆盖派生场景 |
| `check()` 改动破坏现有调用 | ctx=None 时短路(JWT 路径零回归),所有现有 caller 不感知 contextvar |
| 旧 token 迁移后语义变化 | `full` 模式运行时动态求 grantor perms,**真正行为等价**;可在 dashboard 标黄建议用户重新颁发为更窄 restricted scope |
| 超管 token 受约束与现有测试冲突 | 现有 super_admin bypass 测试用的是 JWT 路径(ctx=None),不受影响;新增专项测试覆盖 super_admin + restricted token |
| backfill 中途失败状态不一致 | alembic 单事务整体回滚;大表用独立脚本 `--dry-run` + 分批 + 进度文件 |
| scope 收敛需查颁发者权限(每次 issue 成本) | `issue()` 是低频操作(颁发 token),不是热路径;无需缓存 |
| **`full` 模式每次 check 都要动态求 grantor perms?** | **不需要**。`full` 模式 ctx.scope_mode=="full" → check 短路跳过 scope 闸门,直接走原 casbin/bypass 逻辑。grantor perms 只在 `issue()` 颁发时求一次,用于 restricted 模式收敛 |

---

## 不做的事(边界)

- ❌ **不做 budget / model_allowlist / RPM**(推迟到独立后续任务 `plan-api-token-ai-risk-controls`,等有真实生产数据)
- ❌ 不做资源级 scope("特定 customer token")—— schema 不预留 resource_bindings
- ❌ 不做 TTL 平台上限 + 未使用提醒(治理层,后续任务)
- ❌ 不做 OAuth Client Credentials(`token_type="oauth_client"` 字段已预留但不实现)
- ❌ 不做 token 编辑(不支持改 scope,只能 revoke + 重发)
- ❌ 不做 Redis RPM 计数(随 budget/RPM 一起推迟)

---

## 参考文件(已取证,源码出处)

| 文件 | 关键证据 |
|---|---|
| `app/models/api_token.py:61-66` | scopes JSONB 字段已存在但未被鉴权链读取 |
| `app/services/api_token_service.py:41-46,136` | `ResolvedToken` 丢弃 scopes/token_id;`verify()` 回填点 |
| `app/api/deps.py:45-62,168-221` | `CurrentUser` 无 scopes;`_resolve_api_token` 是 contextvar 写入点 |
| `app/services/permission_service.py:50-77,145` | `check()` 五参数无 scope 入口;`get_implicit_permissions_for_user` 无缓存 |
| `app/services/permission_service.py:452-469` | `DEFAULT_OWNER_PERMS` 实际 35 项(非 v1 的 33) |
| `app/services/permission_service.py:502-505` | `menu:tenants` super_admin 专属,不在任何 DEFAULT_*_PERMS |
| `app/repositories/api_token.py:28-29` | `find_by_prefix` 显式查 is_active + is_deleted(revoke 即时生效) |
| `app/agents/graph.py:66,86` | 工具内直调 check,只持有 user_id/tenant_id(论证 contextvar 必要性) |
| `frontend/src/pages/permissions-page.tsx:332-369` | PermCell 是 scope 矩阵的视觉模板 |
| `frontend/src/pages/settings-page.tsx:778,943` | `handleIssue` 不下发 scopes;占位提示实际行号 |
| `app/api/v1/permissions.py:39-59` | 已有 `GET /permissions/catalogue?type=api`,复用不新建端点 |
| `harness/docs/plan-permission-data-scope.md` | DataScopeService 是 scope 闸门设计的同类先例 |
