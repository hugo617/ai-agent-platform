# 计划:dev 后门与配置静默降级三件套(① /dev/token 显式独立开关 ② LLM/embedding key 启动期 fail-fast ③ scheduler_enabled 显式化)

> **id**: config-startup-guard
> **状态**: passing(EP3 切片 01 完成 2026-08-24,PR #174 merge cb9204f;feature 收官)
> **优先级**: 91(feature_list.json)
> **创建日期**: 2026-08-24
> **最后修订**: 2026-08-24(v3:EP3 收尾,§12 七 AC 全勾 + §4.7-9 实施注记)
> **系列总纲**: [plan-risk-hardening-overview.md](./plan-risk-hardening-overview.md)(R5 🟡,D7 已拍板三件套全修;本 plan 为该 feature 的 EP2 产物)

---

## 0. v1 → v2 变更摘要(对抗式自审回写)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| 开关「开」态用例若依赖 conftest app fixture:fixture 实例化先于测试体内 monkeypatch.setattr,create_app() 读不到 patched 的 dev_auth_enabled → 注册条件失效 | 🟡 | §4.8 修订:开态用例在测试体内 monkeypatch 后**自建** `create_app()`(不经 conftest fixture);关态(默认)用例可正常用 conftest fixture(conftest.py:277-290 实证 fixture 每测试重建 app) |
| CI 全景未核验(② 会不会误炸 Migrations/E2E step) | 🟡 | §4.7 补留痕第 8 条:CI 三处 env 全在豁免域(Backend/Migrations APP_ENV=testing;E2E APP_ENV=development + OPENAI_API_KEY=mock-key),E2E 代码(main-flow.spec.ts)零 dev 端点依赖,alembic env.py 虽 import settings 但运行环境均在白名单 → 全景安全 |
| 前端「零改动」论据缺失败路径实证 | 🟡 | §4.7-2 补:handleDevLogin 失败走 toast.error「开发登录失败」(login-page.tsx 实证),开关关时优雅降级非白屏 |

## 0.1 决策拍板状态说明

**与 super-admin-write-audit 不同:本 feature D1-D8 全部经 AskUserQuestion 获用户逐项拍板(2026-08-24,两轮问询均获回复,无默认采纳项)。** 无需 EP3 开工前复核窗口。

---

## 1. Problem Statement

第 10 次巡检业务风险 R5 🟡:三类「押注部署把配置设对」的静默降级风险:

1. **dev 后门单门押注 APP_ENV**:`/dev/token`(可铸任意 platform_role 含 super_admin 的 RS256 JWT)+ `/dev/bootstrap`(建租户种子权限)+ `/oidc/jwks`(验签公钥)三个端点,唯一门控是 handler 内 `app_env != "development"` → 404。生产误设 `APP_ENV=development`(环境变量拼错/模板复制错/Chart 传错)后门即全开,且 OpenAPI 文档中三端点永远可见。
2. **LLM/embedding key 静默降级**:`openai_api_key` / `embedding_api_key` 默认 `"sk-replace-me"`,启动期不校验。生产忘配时启动完全正常,直到第一次调 LLM/RAG 才运行时报错——故障暴露点从「部署时」推迟到「用户首次使用时」。既有 `_secrets_not_default` validator 只拦 `jwt_secret` / `field_encryption_key`(签名/加密密钥),外部服务凭证(LLM key)不在其列。
3. **scheduler 默认关且无声音**:`scheduler_enabled: bool = False`(为测试安全,正确),但 `.env.example` **没有 SCHEDULER_ENABLED 条目**,关闭时 `init_scheduler` 仅 `logger.debug`。生产忘设 → 低额预警(09:00)+ 计费对账(09:30)两个 job 静默不跑,「少扣费」「余额告警失灵」回到不可见。

## 2. Solution

三件套分别收口为**启动期可见**的形态:① 新增 `DEV_AUTH_ENABLED` 独立开关(默认 False,与 APP_ENV 取 AND 语义),三个 dev 端点改**条件注册**——默认关时路由/OpenAPI 均不存在;② 在既有 `_secrets_not_default` model_validator 内扩两条分支(同一机制,对齐不重复):非 dev/testing 环境 `openai_api_key` 占位一律拒启,`embedding_api_key` 占位仅当 base_url 指向非本地 provider 时拒启(本地 Ollama 无鉴权是文档明示的默认形态);③ `init_scheduler` 关闭分支从 debug 升 WARNING(仅非 testing 环境,点名受影响 job),`.env.example` 补 SCHEDULER_ENABLED 条目注释。

## 3. User Stories

- 作为**平台运维**,我希望生产误设 `APP_ENV=development` 时 dev 后门仍然关闭,以便单个环境变量拼错不变成 super_admin token 铸造机。
- 作为**平台运维**,我希望生产忘配 LLM key 时进程启动即报错退出,以便部署流水线当场失败而不是等用户首次聊天时才炸。
- 作为**平台运维**(自托管 Ollama),我希望本地 embedding 部署不被 key 校验误杀,以便文档明示的默认形态开箱即用。
- 作为**平台运维**,我希望忘开 scheduler 时启动日志有明确 WARNING,以便巡检日志能发现低额预警/对账 job 没在跑。
- 作为**开发者**,我希望本地 `.env` 显式设 `DEV_AUTH_ENABLED=true` 后一键 dev 登录行为与现状完全一致,以便开发工作流零感知切换。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 3 | `app/core/config.py`(+`dev_auth_enabled` 字段 + validator 两分支 + 本地 URL 判定 helper)/ `app/main.py`(三 dev 端点条件注册重组)/ `app/core/scheduler.py`(关闭分支 WARN) |
| 数据库迁移 | 0 | 无 |
| 前端文件改动 | 0 | login-page 的 dev 登录对 404 自然失败,开发者经 .env 开关,前端零改动 |
| 新增测试类 | 1 | `tests/test_startup_config_guard.py`(三件套集中,13 用例) |
| 配置 | 1 | `.env.example`(+DEV_AUTH_ENABLED +SCHEDULER_ENABLED 条目) |
| 文档 | 3 | `README.md`(dev 端点表)/ `docs/LOGTO_SETUP.md` / `项目指南/02-后端架构/05-认证体系.md`(dev 登录提及开关)——EP3 文档影响评估时最终确认 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(纯启动期配置守卫,零业务查询改动)
- 是否引入跨租户访问点? **NO**(反而收紧:/dev/token 是潜在跨租户后门,本 feature 使其默认不可达)
- 验证:不涉及多租户数据用例;① 的开关矩阵用例覆盖「后门不可达」断言。

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 60+ 处 `require_permission` caller? **NO**
- 是否影响 graph.py 工具内 check? **NO**
- scope 闸门:不涉及 API Token。/dev/token 铸的 JWT 走既有验证管线不变(仅注册门控变化)。

### 4.4 数据库表设计 checklist

不适用(零表零迁移)。

### 4.5 核心决策表(D1-D8;**全部经 AskUserQuestion 用户逐项拍板,2026-08-24**)

| # | 决策点 | 拍板结果 | 备注 |
|---|---|---|---|
| D1 | ① 开关命名 | `DEV_AUTH_ENABLED` | 镜像 RATE_LIMIT_ENABLED / SCHEDULER_ENABLED 命名惯例;盖三端点整链(bootstrap 建租户 → token 铸 JWT → jwks 验签),同进退不留半开 |
| D2 | ① 开关语义与默认值 | **AND**:开关=true **且** `app_env=development` 才注册;默认 False;条件注册(默认关时路由与 OpenAPI 均不存在) | 纵深防御:生产误设 APP_ENV 单变量不再开后门;「与 APP_ENV 解耦」= 从单押 APP_ENV 变为双必要条件,非解除 dev 环境约束 |
| D3 | ② LLM key 严格度 | 占位值(`sk-replace-me`)一律 ValueError 拒启 | env 兜底是安全网:DB 行被删/失效时占位值 = 平台 LLM 静默失效;DB-only 部署也应显式设非占位值 |
| D4 | ② embedding 规则 | `embedding_base_url` host 为 localhost/127.0.0.1/::1 时豁免 key 校验;非本地且占位 → 拒启 | 本地 Ollama 无鉴权是文档明示默认形态;helper 仅认回环地址,内网 IP 不算本地(从严) |
| D5 | ② 环境范围 | 镜像既有白名单:`app_env in ("development", "testing")` 豁免,其余(production/staging/未知值)全拒 | 与 `_secrets_not_default` 既有环境判定同构,未知环境名默认从严 |
| D6 | ③ 显式化形态 | **两者**:init_scheduler 关闭分支 debug→WARNING(仅 `app_env != testing`,文案点名 SCHEDULER_ENABLED 与两个 job)+ `.env.example` 补条目注释 | 测试环境(create_app per-test)不刷屏 |
| D7 | /dev/token TTL 1h 硬编码 | **不做,留痕**:rate-limit plan(plan-rate-limit-login-lockout.md §255)划入 R5 域,但系列总纲 D7 三件套未含此项,不越界;归后续巡检/独立小改动处置 | 本 plan §8 记入 Out of Scope |
| D8 | 切片结构 | **1 切片端到端** | 三件套同域(启动期配置守卫)改动集中,总规模小;镜像 super-admin-write-audit 单切片先例 |

### 4.6 各落点实施规格

**① 条件注册(`app/main.py`)**:三个 dev 端点(`jwks`/`dev_token`/`dev_bootstrap`)从「无条件注册 + handler 内 `app_env != "development"` 返 404」重组为 `_register_dev_endpoints(app)` 内聚函数,仅当 `settings.dev_auth_enabled and settings.app_env == "development"` 时调用注册。handler 内原 app_env 检查**删除**(注册条件成为唯一真相源,保留反而误导)。`from app.core.dev_keys import ...` 的函数内 import 维持(懒加载惯例)。模块头「Gated behind development mode」注释块同步改写(DEV_AUTH_ENABLED + development 双条件)。

**② validator 扩展(`app/core/config.py` `_secrets_not_default`)**:在既有两条检查之后追加——

```python
if self.openai_api_key == "sk-replace-me":
    raise ValueError("OPENAI_API_KEY must be set in non-dev environments (LLM env fallback is a safety net, placeholder = silent degradation)")
if not _is_local_base_url(self.embedding_base_url) and self.embedding_api_key == "sk-replace-me":
    raise ValueError("EMBEDDING_API_KEY must be set when EMBEDDING_BASE_URL targets a non-local provider")
```

`_is_local_base_url(url)` 模块级 helper:`urllib.parse.urlsplit` 取 hostname,`in ("localhost", "127.0.0.1", "::1")` 判本地;解析异常从严返回 False(宁可拒启)。检查顺序:jwt → field_encryption → openai → embedding,一次报一条(运维逐个修,既有模式)。

**③ scheduler WARN(`app/core/scheduler.py` `init_scheduler`)**:关闭分支改——

```python
if not _SCHEDULER_ENABLED:
    if settings.app_env != "testing":
        logger.warning(
            "scheduler disabled (SCHEDULER_ENABLED=false) — periodic jobs "
            "scan_balance_warnings (09:00) and reconcile_billing (09:30) will NOT run"
        )
    else:
        logger.debug("scheduler disabled (SCHEDULER_ENABLED=false); not starting")
    return scheduler
```

**.env.example 两处条目**:`DEV_AUTH_ENABLED=true`(注释:仅本地开发一键登录;生产绝不开启;代码默认 false 兜底)与 `SCHEDULER_ENABLED=false`(注释:测试依赖默认关;生产单副本设 true;多副本只在一个副本开)。`.env.example` 给 true 的理由:它本身是 development 模板(APP_ENV=development 同页),新开发者复制即得完整 dev 工作流;安全底线是代码默认 False + AND 语义,不靠模板。

### 4.7 取证发现与留痕(实施必读)

1. **dev 端点零测试覆盖**:tests/ 全目录 grep `/dev/token|dev/bootstrap|oidc/jwks` 零命中;E2E(CI)登录走密码表单(archive:sessions-001-056)。故「现有 dev 流测试零回归」为空命题,① 的行为由本 feature 新测试矩阵建立(openapi paths 断言 + /dev/token 真调)。
2. **前端消费链**:`frontend/src/api/endpoints/dev.ts`(devBootstrap/devToken/devLogin)+ `login-page.tsx` 一键 dev 登录。开关关闭时后端 404,`handleDevLogin` 失败走 `toast.error("开发登录失败", ...)` 优雅降级(login-page.tsx 实证)——前端零改动;开发者恢复工作流 = `.env` 加 `DEV_AUTH_ENABLED=true`(README/LOGTO_SETUP 文档同步,防新开发者踩坑)。
3. **`/dev/bootstrap` 测试边界**:其 handler 内 `from app.core.database import AsyncSessionLocal` 直接用全局 factory,不走 `Depends(get_db)`,测试的 DB override 不生效 → **不为 bootstrap 写功能测试**(它本来就没有覆盖,不越界补),仅以 openapi paths 断言其注册状态。
4. **conftest 既有环境**:`OPENAI_API_KEY=test-key` 已设(testing 本就在豁免白名单,双保险);`SCHEDULER_ENABLED` 未显式设(靠代码默认 False)——③ 的 WARN 条件用 `app_env != testing` 而非 `scheduler_enabled` 的来源判断,测试断言用 monkeypatch。
5. **既有 `_secrets_not_default` 零测试覆盖**:② 的新测试文件顺带建立既有两条(jwt_secret/field_encryption_key)的覆盖——同一 validator 的测试单元,不算越界。
6. **`sk-replace-me` 是唯一 env 占位哨兵**:demo 场景的 `sk-demo-placeholder` 只进 DB 行(seed 脚本),不落 env key,不在校验值域。
7. **`/dev/token` 硬编码 1h TTL**(main.py `exp: now + 3600` / `expires_in: 3600`):rate-limit plan §255 明文划归 R5 域,但总纲 D7 三件套未含 → **不做,留痕**(D7 决策)。
8. **CI 全景核验(② 不会误炸任何 step)**:`.github/workflows/ci.yml` 三处 env——Backend(L83 `APP_ENV: testing` + OPENAI_API_KEY=test-key)/ Migrations(L42 `APP_ENV: testing`)/ E2E(L192 `APP_ENV: development` + L195 OPENAI_API_KEY=mock-key)——全部落在 ② 豁免白名单(development/testing);E2E 代码 `frontend/e2e/main-flow.spec.ts` grep dev/token|dev/bootstrap|devLogin 零命中(登录走密码表单),① 默认关不影响 E2E;`alembic/env.py` 虽 import settings(L13)但 Migrations step 在 testing 豁免域,本地 `alembic upgrade head` 默认 .env 亦为 development 豁免域。
9. **EP3 实施注记(2026-08-24 切片 01 收尾回写)**:① 用例 13→14——§5 ①「默认 openapi 无 + /dev/token 404」拆两条(openapi 断言与真调 404 各自成测,对应 §4.7-1 双形态),Spec 轴判良性超集;② §5 ②-1「production 全默认」在 pytest 进程内不可直接实现——conftest `os.environ.setdefault("JWT_SECRET","test-secret")` / `OPENAI_API_KEY=test-key` 会盖掉代码默认,故测试 kwargs 全显式只留 jwt 占位(§4.8 优先级 init kwargs > env > .env),Spec 轴判必要适配;③ /dev/token 解码断言需带 `audience=settings.logto_audience`(PyJWT 对带 aud claim 的 token 默认验 aud);④ 默认关态用例显式钉死 `dev_auth_enabled=False` 而非真读默认——防开发者本地 `.env` DEV_AUTH_ENABLED=true 泄漏进断言(code-review 双轴共识,docstring 如实描述并更名 `test_dev_endpoints_absent_when_gate_closed`);⑤ Standards 判断项留痕:`sk-replace-me` 字面量 ×4 与 validator 四同形分支不抽象(镜像既有 change-me-in-production 惯例 + §11「只扩分支不改机制」),dev_bootstrap 绕 get_db/裸 dict 随迁(§4.7-3 留痕的原样搬移);⑥ CI 三处 step 实测全绿(§4.7-8 预判兑现),全量 1089 passed(基线 1075 + 14)。

### 4.8 其他实施决策

- **测试落点**:新文件 `tests/test_startup_config_guard.py` 集中三件套(同域集中,不分散到 test_health/test_auth);Settings 校验用例直接 kwargs 构造 `Settings(app_env="production", ...)` 断 ValueError(pydantic v2 构造期即跑 model_validator,无需启动 app)。
- **开关矩阵断言方式**:① 用 `app.openapi()["paths"]` 断言三端点注册状态(比逐个发请求更完备,一次盖三端点),另对 `/dev/token` 真发一次 POST(200 + JWT 可解码出 platform_role claim)与关态 404 各一条;`create_app()` 在测试内重新调用,`settings` 单例经 monkeypatch.setattr 控制两变量(dev_auth_enabled / app_env)。**开态用例必须在测试体内 monkeypatch 后自建 `create_app()`**(conftest 的 app/client fixture 在 fixture 实例化时已调 create_app,早于测试体内的 monkeypatch——conftest.py:277-290 实证;关态默认用例不受此限,可正常用 conftest fixture)。
- **错误文案**:ValueError 消息含 env 变量名大写(OPENAI_API_KEY / EMBEDDING_API_KEY),与既有两条(JWT_SECRET/FIELD_ENCRYPTION_KEY)风格一致,运维可直接按消息改 env。

## 5. Testing Decisions

- 测试金字塔:unit 为主(Settings 构造断言,scheduler caplog 断言)+ integration(app 创建 + openapi/HTTP 断言);无 E2E 新增(零前端改动)。
- 全部 SQLite 内存/无 DB(Settings 校验根本不触 DB;bootstrap 不测功能,见 §4.7-3)。
- 用例清单(13 = ① 6 + ② 5 + ③ 2):
  - ① 开关矩阵 6:默认(不设)三端点 openapi 无 + /dev/token 404 / 开+development:三端点注册 + /dev/token 200 铸 token 可解 + /oidc/jwks 200 返回 JWKS / 开+production:三端点 openapi 无(AND 语义,单开关不足以开)/ 关+development:无(反向)。
  - ② 校验 5:production 全默认 → ValueError(JWT_SECRET 消息,顺带覆盖既有分支)/ production + jwt/encryption 就位 + openai 占位 → ValueError(OPENAI_API_KEY 消息)/ 再 + openai 就位 + embedding 占位 + 默认 localhost base_url → 通过(豁免)/ 再 + base_url=https://api.openai.com → ValueError(EMBEDDING 消息)/ development + testing 全占位 → 通过(白名单豁免)。
  - ③ scheduler 2:monkeypatch `_SCHEDULER_ENABLED=False` + `app_env="production"` → init_scheduler caplog WARNING 含 SCHEDULER_ENABLED 与 job 名 / `app_env="testing"` → 无 WARNING(仅 debug)。
- 多租户隔离:不涉及(§4.2)。

## 6. 切片规划

单切片(D8 拍板)。详见 §12 实施切片。

## 7. 对抗式审查(单模型双轴,v1 → v2)

本 feature 触发条件:涉及安全敏感操作(token/密钥)。自审双轴如下。

**Standards 轴(项目铁律/架构惯例)**:
- 依赖方向:config(core)← main/scheduler 消费,单向 ✅。
- 「多租户过滤在 Repository」不涉及 ✅。
- validator 内 `_is_local_base_url` helper:config.py 模块级私有函数,无依赖引入(urllib 标准库)✅。
- 条件注册 vs handler 404:条件注册使默认态「路由不存在」(更强:OpenAPI/扫描器都看不到),符合 fail-closed ✅。

**Spec 轴(需求忠实度)**:三条 verification(开关关 404+开而不变 / key fail-fast / WARN 日志)均有对应用例;D1-D8 逐项可追溯。

(自审发现的修订项回写 §0。)

## 8. Out of Scope

- ❌ `/dev/token` TTL 1h 硬编码(§4.7-7 留痕,归后续巡检/独立小改动)。
- ❌ Logto 生产配置指引 / 三 token 验证管线重构。
- ❌ scheduler 多副本选主/分布式锁(单副本假设不变,`.env.example` 注释说明)。
- ❌ 生产部署模板/部署文档体系(README:185 checklist 另议)。
- ❌ demo_* 配置族、storage/s3 等其他配置的启动校验扩展(按需再加,不过度设计)。
- ❌ 既有 `_secrets_not_default` 白名单机制重构(只扩分支不改机制)。

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 条件注册改变 app 路由集,某处隐式依赖三端点存在 | 低 | 取证:tests/scripts/frontend 仅 login-page 消费且 404 自然失败;openapi 断言用例锁行为 |
| DB-only LLM 部署(平台级 LlmConfig 行就位、env 不配)被 fail-fast 拒启 | 中 | D3 用户拍板接受(占位=安全网失效);报错消息指导设任意非占位值;README 部署说明同步 |
| validator 顺序导致一次只报一条,运维多轮重启 | 低 | 既有模式如此(可接受);消息互相独立、按依赖排序 |
| 开发者升级后一键登录失效踩坑 | 中 | `.env.example` 默认给 true + README/LOGTO_SETUP/认证体系文档三处同步 |
| monkeypatch settings 单例属性(pydantic v2 赋值)与 lru_cache 的交互 | 低 | 测试内直接 setattr(默认 validate_assignment=False 可赋值);create_app 每次重读同一单例,断言后还原 |

## 10. 验收标准(同步 feature_list.json verification)

1. `DEV_AUTH_ENABLED` 未设/false(任意 app_env):openapi paths 无 `/oidc/jwks`、`/dev/token`、`/dev/bootstrap`,直接请求 404;`true` + development:三端点注册,`/dev/token` 铸 token 200 且 JWT payload 含 platform_role claim;`true` + 非 development:仍不注册(AND 语义)。
2. `app_env` 非 development/testing:`openai_api_key` 占位 → Settings 构造抛 ValueError(OPENAI_API_KEY 消息);`embedding_base_url` 非本地 + key 占位 → ValueError;本地 base_url + 占位 → 通过;key 全就位 → 通过;development/testing 全占位 → 通过。
3. `scheduler_enabled=false` 且 `app_env != testing`:`init_scheduler` 输出 WARNING(含 SCHEDULER_ENABLED 与两个 job 名);testing:无 WARNING。
4. `.env.example` 含 `DEV_AUTH_ENABLED` 与 `SCHEDULER_ENABLED` 条目及注释;README/LOGTO_SETUP dev 端点说明提及开关。
5. `./init.sh full` 全量零回归 + ruff 绿;前端零改动(`npm run build` 收尾确认)。

## 11. 不越界声明

本次改动**只**涉及:`app/core/config.py`、`app/main.py`(三 dev 端点注册段)、`app/core/scheduler.py`(关闭分支日志)、`.env.example`、新测试文件、README/LOGTO_SETUP/认证体系文档的 dev 端点说明段。

**不**触碰:三 token 验证管线(security.py)/ casbin / 任何业务端点行为语义 / LLM/embedding 配置解析链(llm_config_service/embedding_config_service 的 tenant > platform > env 顺序)/ scheduler job 逻辑与注册时间 / 前端任何文件 / demo seed 脚本 / alembic。

## 12. 实施切片(to-tickets 产出)

### 切片依赖图

```
切片 01(唯一 = 末切片)
```

### 切片 01 — 启动期配置守卫三件套(DEV_AUTH_ENABLED 条件注册 + key fail-fast + scheduler WARN)✅

> **完成**:PR #174(merge `cb9204f`,2026-08-24,CI 4/4 绿:Migrations 1m0s/Backend 10m30s/E2E 2m33s/Frontend 29s;commits 529e1bc + 10712aa)。全量 1089 passed 零回归 + ruff 绿 + 前端 build 绿(零前端改动确认)。

- **Blocked by**: 无(frontier,可立即开工)
- **What it delivers**: 默认部署(不设任何新 env)下三个 dev 端点从路由层不存在;生产忘配 LLM/embedding key 启动即报错退出(本地 Ollama 豁免);scheduler 忘开时启动日志 WARNING 点名两个 job。开发者 `.env` 显式 `DEV_AUTH_ENABLED=true` 后一键 dev 登录与现状行为一致。
- **文件清单**: `app/core/config.py`(改)/ `app/main.py`(改)/ `app/core/scheduler.py`(改)/ `.env.example`(改)/ `tests/test_startup_config_guard.py`(新)/ `README.md` + `docs/LOGTO_SETUP.md` + `项目指南/02-后端架构/05-认证体系.md`(dev 端点说明段)
- **Acceptance criteria**:

- [x] `app/core/config.py`:`dev_auth_enabled: bool = False` 字段 + `_is_local_base_url` helper + validator 两条新分支(§4.6 规格,消息含大写 env 名)
- [x] `app/main.py`:三 dev 端点收进条件注册(`dev_auth_enabled and app_env == "development"`),handler 内旧 app_env 检查删除,模块头注释同步
- [x] `app/core/scheduler.py`:关闭分支非 testing 环境 WARNING(文案点名 SCHEDULER_ENABLED + scan_balance_warnings + reconcile_billing),testing 保持 debug
- [x] `.env.example`:DEV_AUTH_ENABLED=true(注释:仅本地开发)+ SCHEDULER_ENABLED=false(注释:生产单副本 true)两段
- [x] `tests/test_startup_config_guard.py`:§5 用例清单全落地(① 6 + ② 5 + ③ 2 = 13,实施拆 14 良性超集,红→绿(开态用例按 §4.8 测试体内自建 create_app)
- [x] README.md / docs/LOGTO_SETUP.md / 认证体系文档 dev 端点说明补开关前提
- [x] `pytest tests/test_startup_config_guard.py` 全绿 + ruff 绿 + `./init.sh full` 全量零回归 + 前端 `npm run build` 零改动确认(定向 14/14 + 全量 1089 passed 8 skipped + build 绿)
