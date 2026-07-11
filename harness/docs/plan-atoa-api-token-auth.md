# 计划:AtoA 地基 —— API Token 鉴权机制（PAT 式）

> 对应 feature_list.json 的 `id`: `atoa-api-token-auth`
> 状态: not_started
> 优先级: 19
> 前置: 无（地基任务，所有后续 AtoA 任务依赖它）
> AtoA 系列总览见 `progress.md` 任务规划表

---

## 背景:为什么需要这个任务

平台要让任意外部 AI Agent（Claude Code / Cursor / Codex / 任意）在授权后，通过 CLI 操作本平台。当前 `get_current_user`(`app/api/deps.py:57`) 只认**用户态** Bearer JWT（本地 HS256 / Logto RS256 / 开发 RS256），**没有任何长效 API Token / 机器身份机制**。外部 Agent 不是「人登录浏览器」，需要一套全新的「长效凭证 + 机器身份」机制。

本任务是 AtoA 系列的**地基**：建立 API Token 鉴权后，所有现有 API（`/agents` `/chat/stream` `/conversations` ...）自动获得「对外部 Agent 开放」的能力，后续 CLI / Skill / 管理前端都依赖它。

### 行业对标

- GitHub Personal Access Token（PAT）：`ghp_xxx` 前缀，长效，绑用户+scope
- Composio API key：`composio login <key>`，CLI 持有
- Apifox 访问令牌：管理后台颁发，Agent 拿到后调 CLI

本任务实现 PAT 式（Personal Access Token）方案；OAuth Client Credentials 作为后续独立任务（预留扩展点）。

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| 用户态 JWT 鉴权 | ✅ 已完成 | `app/api/deps.py:57` `get_current_user` |
| 三类 token（local/dev/logto） | ✅ 已完成 | `app/core/security.py` `decode_token` |
| 权限守卫工厂 | ✅ 可复用 | `app/api/deps.py:151` `require_permission(obj, act)` |
| Fernet 加密 | ✅ 已完成 | `app/core/crypto.py` `encrypt/decrypt/mask_api_key` |
| API Token / PAT 机制 | ❌ 完全缺失 | 无表、无端点、无鉴权旁路 |
| 机器身份 | ❌ 完全缺失 | 外部 Agent 无法接入 |

---

## 目标

1. **新增 ApiToken 表**：绑租户 + 颁发者 user_id，token hash 存储（不存明文），软删除，预留 OAuth 扩展点
2. **改造 `get_current_user` 加旁路**：识别 `ahp_` 前缀 token → 查表 → 构造 `CurrentUser`，`require_permission` 完全不用改（user_id 真实，casbin 查询正常）
3. **新增颁发/验证/吊销端点**：明文 token 颁发时仅显示一次，掩码回显
4. **多租户隔离天然继承**：Token 固定 tenant_id，Repository 层过滤照常生效

### 已确认的决策（与用户对齐）

| 决策点 | 选择 |
|--------|------|
| 鉴权模型 | **PAT 先做，OAuth 后续**（本任务只做 PAT，ApiToken 表预留 `token_type` 字段） |
| token 存储方式 | **存 hash（Fernet encrypt），不存明文**；颁发时明文仅返回一次 |
| token 前缀 | `ahp_`（agenthub platform），便于 deps.py 识别分流 |
| 绑定身份 | **绑定颁发者 user_id + 固定 tenant_id**（复用现有 casbin RBAC，token 继承用户的角色权限） |
| 多租户隔离 | Token 绑定 tenant_id，不可切换租户（安全：防止跨租户越权） |
| 权限范围（scope） | 表预留 `scopes` JSON 字段（本任务不实现细粒度 scope，全部继承用户权限；后续可加） |

---

## 前置条件

- 无功能前置（地基任务）
- `app/core/crypto.py` 的 Fernet 加密已就绪（real-chat-llm-config 任务交付）
- 迁移链 head = `b3c4d5e6f7a8`

---

## 实施步骤

### 第一阶段:数据模型

#### Step 1:ApiToken model `app/models/api_token.py`（新建）

遵循 AGENTS.md「新增表 8 条 checklist」。

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | String(32) PK | uuid hex（`_uuid()` 模式，对齐 tenant.py） |
| `tenant_id` | String(32) FK→tenants, index | 固定租户，不可切换 |
| `created_by_user_id` | String(128) FK→users, index | **绑定颁发者**（鉴权旁路用它构造 CurrentUser） |
| `name` | String(128) | 人类可读名称（如 "my-cursor-agent"） |
| `token_type` | String(16), default="pat" | `"pat"` / 预留 `"oauth_client"` |
| `token_hash` | Text | Fernet 密文（encrypt 原文 token） |
| `token_prefix` | String(16) | 回显用掩码 `ahp_***wxyz` |
| `scopes` | JSON / JSONB | 预留 scope 列表，本任务空数组 |
| `last_used_at` | DateTime, nullable | 最后使用时间（鉴权时刷新） |
| `expires_at` | DateTime, nullable | 过期时间（null=永不过期） |
| `is_active` | Boolean, default=True | 吊销=false |
| `is_deleted` | Boolean, default=False | 软删除（对齐项目惯例） |
| `created_at` / `updated_at` | DateTime | 时间戳 |

- **双库兼容**：`scopes` 用 `JSONB().with_variant(JSON, "sqlite")` 模式（对齐 `User.info_json`）
- **不存明文**：`token_hash` 存 `crypto.encrypt(plaintext)`，验证时 `crypto.decrypt(hash) == input`
- **软删除 + 部分唯一索引**：本表无业务唯一约束（token_hash 用查询校验，不做 DB 唯一索引避免性能问题）

#### Step 2:Alembic 迁移

- `alembic revision --autogenerate -m "add api_tokens table"`
- `down_revision = 'b3c4d5e6f7a8'`（当前 head）
- **⚠️ 必须同步两处 import**（Session 018 血泪教训）：
  - `alembic/env.py:17-26` import 列表加 `api_token`
  - `tests/conftest.py:87-96` import 列表加 `api_token`
- 迁移链验证：`APP_ENV=testing alembic upgrade head` + `alembic check`（CI migrations job 守门）

#### Step 3:Schema + Repository

- **新建 `app/schemas/api_token.py`**：
  - `ApiTokenCreate`:`name: str`、`expires_at: datetime | None`、`scopes: list[str] = []`
  - `ApiTokenCreateResponse`:含 `token: str`（**明文，仅此一次**）+ `token_id` + `token_prefix` + `name` + `expires_at` + `created_at`
  - `ApiTokenRead`:`id` / `name` / `token_prefix`（掩码）/ `scopes` / `last_used_at` / `expires_at` / `is_active` / `created_at`（**无明文、无 hash**）
- **新建 `app/repositories/api_token.py`**：继承 `TenantScopedRepository`；方法 `get_by_token_hash` / `list_for_tenant` / `get_for_tenant` / `update_last_used`

---

### 第二阶段:鉴权旁路（核心改造）

#### Step 4:改造 `app/api/deps.py` `get_current_user`

**这是整个 AtoA 的技术核心**：在 `decode_token` 前加 API Token 检测旁路。

```python
# 伪代码（实际实现对齐 deps.py 风格）
async def get_current_user(credentials, db):
    if credentials is None:
        raise 401
    token = credentials.credentials
    # 旁路：API Token（ahp_ 前缀）
    if token.startswith("ahp_"):
        return await _resolve_api_token(token, db)
    # 原有路径：用户态 JWT
    claims = await decode_token(token)
    ...  # 现有逻辑不变
```

- **`_resolve_api_token(token, db)`**:
  1. 遍历 active + 未过期的 ApiToken 行（token_hash 查询；或解密比对）
  2. `crypto.decrypt(row.token_hash) == token` → 命中
  3. 验证 `is_active=True` + `is_deleted=False` + 未过期
  4. 刷新 `last_used_at`
  5. 构造 `CurrentUser(user_id=row.created_by_user_id, tenant_id=row.tenant_id)`
- **关键**:`CurrentUser` 构造后，`require_permission` 完全不用改——user_id 是真实的，casbin 查询正常工作，token 继承用户的角色权限（owner/admin/member）
- **多租户隔离**：token 的 tenant_id 固定，Repository 层的 tenant_id 过滤照常生效
- **不改什么**:`require_permission`(`deps.py:151`) / `require_super_admin`(`deps.py:173`) / `permission_service.check` 全部不动

#### Step 5:性能考量（token 验证）

- **朴素方案**：每请求遍历所有 active token 解密比对 → token 多时慢
- **优化方案**（本任务采用）：token 结构 `ahp_<random>`，`token_prefix` 存前 12 位（`ahp_xxxx`），用 `token_prefix` 索引缩小范围到极少数行，再解密比对 → O(1) 级
- 加 `token_prefix` 的普通索引（非唯一，因软删除后前缀可复用）

---

### 第三阶段:Service + API

#### Step 6:ApiTokenService `app/services/api_token_service.py`（新建）

- `OBJECT = "api_tokens"`，方法首行 `permission_service.require(...)`（对齐 agent_service 范式）
- **核心方法**:
  - `issue(db, user_id, tenant_id, payload) -> ApiTokenCreateResponse`:生成 `ahp_<secrets.token_urlsafe(32)>` → encrypt 存 hash → 存 prefix → 返回明文（**仅此一次**）
  - `list_for_tenant(db, user_id, tenant_id) -> list[ApiTokenRead]`:掩码列表
  - `revoke(db, user_id, tenant_id, token_id)`:软删除（`is_active=False` + `is_deleted=True`）
  - `verify(db, token) -> CurrentUser | None`:供 deps.py 调用（查表 + 解密比对 + 刷新 last_used）
- **加解密边界**:`issue` 加密写入，`verify` 解密比对，`list` 永远返回掩码

#### Step 7:`app/api/v1/api_tokens.py`（新建）+ main.py 注册

| 方法 | 路径 | 守卫 | 说明 |
|---|---|---|---|
| POST | `/api-tokens` | `api_tokens:manage`(owner/admin) | 颁发，返回明文 token **仅此一次** |
| GET | `/api-tokens` | `api_tokens:manage` | 列表（掩码） |
| DELETE | `/api-tokens/{id}` | `api_tokens:manage` | 吊销（软删除） |
| GET | `/api-tokens/verify` | 登录即可（API Token 通过旁路） | 验证当前 token 有效（CLI `whoami` 用） |

- **main.py 注册**:import `api_tokens` + `app.include_router(api_tokens.router, prefix=prefix)`（import 按字母序）

#### Step 8:权限 seed

- **生产侧** `permission_service.py` 行 373-391:`DEFAULT_OWNER_PERMS` / `DEFAULT_ADMIN_PERMS` 加 `("api_tokens", "manage")`
- **测试侧** `tests/conftest.py:40-50` `_make_casbin`:owner/admin policy 列表加 `("api_tokens", "manage")`
- **幂等 seed**:`scripts/init_admin.py` 重跑一次给老租户补权限

---

### 第四阶段:测试

#### Step 9:`tests/test_api_tokens.py`（新建）

参照 `tests/test_permissions_api.py` HTTP 集成模式。用例:
- **crypto 复用**:encrypt→decrypt 往返（已在 test_llm_config 覆盖，此处不重复）
- **颁发 + 验证**:POST 颁发 → 拿明文 token → 用 token 访问 `/agents`（验证旁路生效）→ 返回数据
- **掩码回显**:GET 列表返回 token_prefix，无明文无 hash
- **吊销**:DELETE → 再用该 token 访问 → 401
- **过期**:db_session 直插过期 token → 访问 → 401
- **跨租户隔离**:租户 A 颁发的 token 不能访问租户 B 数据（token tenant_id 固定）
- **权限边界**:member 颁发 token → 403（无 `api_tokens:manage`）
- **deps 旁路不破坏现有 JWT**:app_client（JWT）访问正常（回归）

#### Step 10:后端总验证

- `./init.sh` 全绿（ruff + pytest，含新测试，无回归）
- `APP_ENV=testing alembic upgrade head` 迁移链通过（CI migrations job 守门）
- `alembic check` 无 drift（env.py import 对齐）

---

## 验收标准

1. ApiToken 表 + 迁移链通过（含 env.py / conftest.py 两处 import 同步）
2. `get_current_user` 旁路：`ahp_` 前缀 token 能构造 CurrentUser，非 `ahp_` 走原 JWT 路径（零回归）
3. 颁发/验证/吊销端点工作正常，明文 token 颁发仅显示一次
4. **核心价值**:用颁发的 API Token 能访问现有 `/agents` 端点（验证整个鉴权链路端到端）
5. 多租户隔离：token 绑定 tenant_id，不可跨租户
6. `./init.sh` 全绿（ruff + pytest，含新测试 test_api_tokens.py）
7. `alembic check` 无 drift
8. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| deps.py 改动影响现有鉴权（回归） | 旁路用前缀分流（`ahp_` vs 其他），非 `ahp_` 走原路径；回归测试覆盖 app_client（JWT）正常访问 |
| conftest.py 漏注册新模型 | `create_all` 不建表报 "no such table"；conftest.py:87-96 import 列表必须加 api_token（Session 018 教训） |
| alembic/env.py 漏注册导致 CI migrations 红 | env.py:17-26 import 列表同步加 api_token（Session 018 血泪教训） |
| token 验证性能 | 用 token_prefix 索引缩小查询范围，再解密比对（非全表遍历） |
| token 泄露风险 | 明文仅颁发时返回一次；存 hash 不存明文；支持吊销（is_active=false）+ 过期 |
| super_admin token 权限 | token 继承颁发者权限；若颁发者是 super_admin，token 也有 super_admin 权限（符合预期，但 UI 需提示风险） |

### 不做的事（边界）

- 不实现 OAuth Client Credentials（预留 token_type 字段，后续独立任务）
- 不实现细粒度 scope 限制（scopes 字段预留，本任务全部继承用户权限）
- 不实现 token 旋转 / 自动续期
- 不实现调用日志 / 审计（system_logs 已有基建，后续按需）
- 不实现 IP 白名单 / 来源限制
- 不改前端（atoa-admin-ui 任务做）

---

## 参考文件（实施时对照）

| 参照 | 路径 |
|------|------|
| 鉴权管线（改造点） | `app/api/deps.py:57` `get_current_user` |
| 权限守卫工厂（不动） | `app/api/deps.py:151` `require_permission` |
| CurrentUser 值对象 | `app/api/deps.py:37` |
| Fernet 加密（复用） | `app/core/crypto.py` `encrypt/decrypt/mask_api_key` |
| 迁移链 head | `b3c4d5e6f7a8`(`alembic/versions/2026_07_11_0900_...`) |
| env.py model import（必同步） | `alembic/env.py:17-26` |
| conftest model 注册（必同步） | `tests/conftest.py:87-96` |
| conftest casbin seed | `tests/conftest.py:40-67` `_make_casbin` |
| 权限 seed 唯一真源 | `app/services/permission_service.py:373-391`(DEFAULT_*_PERMS) |
| Repository 基类 | `app/repositories/base.py`(BaseRepository / TenantScopedRepository) |
| Service 范式 | `app/services/agent_service.py`(OBJECT 常量 + require_permission) |
| LLM config 范式（掩码模式参照） | `app/services/llm_config_service.py`(upsert + 加密边界) |
| API 端点结构模板 | `app/api/v1/settings.py`(5 端点 + 权限分层) |
| HTTP 集成测试范式 | `tests/test_permissions_api.py` |
| 新增表 8 条 checklist | `项目指南/02-后端架构/03-数据库与ORM.md`「新增表的设计原则」 |
| 行业对标 | GitHub PAT / Composio API key / Apifox 访问令牌 |
