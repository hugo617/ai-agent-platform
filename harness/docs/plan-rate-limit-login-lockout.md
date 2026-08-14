# 计划:全局限流 + 登录防爆破 + token TTL 收口(rate-limit-login-lockout)

> **id**: rate-limit-login-lockout
> **状态**: not_started(EP2 已完成:plan draft v2 经对抗式审查双轴回写,3🔴 + 10🟡 全部处理,见 §0;EP3 未开始,开工翻 in_progress)
> **优先级**: 96(feature_list.json,第 10 次巡检业务风险 R1 🔴)
> **创建日期**: 2026-08-14
> **最后修订**: 2026-08-14(v2:对抗式审查回写)
> **来源**: [plan-risk-hardening-overview.md](./plan-risk-hardening-overview.md) §1(D4 已拍板形态:slowapi 全局 API 限流 + 登录失败锁定 + TTL 降小时级)
> **EP2 回环**: grill(2026-08-14,**11 项决策全部用户逐项拍板**,AskUserQuestion 3 轮,无「按推荐默认采纳」——系列铁律,见 §4.5 D1-D11)→ to-spec(v1)→ 对抗式审查(双轴并行)→ to-tickets(v2,§6)

---

## 0. v1 → v2 变更摘要(对抗式审查回写)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| §4.6「豁免路径经 Limiter 的 exempt 机制」——slowapi 0.1.10 **无 `exempt_paths` 构造参数**,豁免只有 `@limiter.exempt` 装饰器(且 /docs /health 等路由无模块级函数可装饰),按字面实施必卡住 | 🔴 | 改为**自写路径短路**:限流装配处(~10 行)先判 `request.url.path` 命中豁免清单(settings 可调)直接放行,不进 slowapi;不依赖私有 API |
| 切片 03「client.ts 拦 429 → toast」——项目 toast 是**自研 Context+hook**(`useToast` 仅 Provider 内可用),axios 拦截器在 React 树外调不到,按字面实施必做错 | 🔴 | 改为**事件桥**(仿既有 `AUTH_EXPIRED_EVENT` 先例):client.ts dispatch `CustomEvent("aap:rate-limited")` → 挂在 ToastProvider 层的 listener 调 `t.error(...)`;前端文件从 1 个改 2 个 |
| 失败计数未规定原子性——ORM read-modify-write 下并发爆破同读旧值各写回 1,计数永远到不了 5,防爆破主力在核心场景失效 | 🟡 | §4.6 + 切片 01 AC 明确:原子 `UPDATE users SET failed_attempts = failed_attempts + 1`(SQLAlchemy `update().values(failed_attempts=User.failed_attempts + 1)`),不经 read-modify-write |
| 失败路径持久化未定义——现状 login 仅成功路径末尾 commit,计数写在失败路径上不显式 commit 即静默丢弃,锁定永不触发 | 🟡 | §4.6 + 切片 01 AC 明确:计数/锁定写必须在 raise AuthError 前 flush+commit(Repository 方法内提交) |
| Limiter「工厂」与 login `@limiter.limit` 实例一致性矛盾——装饰器 import 时绑定实例,每 create_app 新建则两套 storage 计数分裂 | 🟡 | §4.6 收敛:**模块级单例 limiter** + create_app 挂同一实例;测试靠 `enabled=False` 短路、显式限流测试用 `limiter.reset()` 隔离;严档字符串 import 时固化 → 测试调配额走 env(conftest `os.environ.setdefault` 先例),默认档用 callable 保留运行时可调 |
| 锁定语义三个边界未定义:OIDC-only(password=None)账号会被计数成纯 DoS 面(锁对 Logto 无效);锁定期内既有 token/Logto 路径不受影响未写明;锁定期内继续失败会无限续锁 | 🟡 | §4.6 补**锁定作用域框**:locked_until 仅作用于本地 /auth/login;OIDC-only 账号**不计数**(攻击面交 IP 严档);Logto 路径/已签发 token/PAT 不受锁定影响;**锁定期内继续失败一律 401 不计数不续期**(切片 01 补测试) |
| 「create_access_token 是唯一读 TTL 配置的签发点」断言可证伪——`auth.py` login 响应 `expires_in` 也读同一键 | 🟡 | 措辞改「TTL 仅由 settings 派生,local_auth(exp)与 login(expires_in)两处读同一键,改默认值即全生效」 |
| `.env.example` 现状 `ACCESS_TOKEN_TTL_MINUTES=60`(与 config.py 默认 10080 已经分歧),切片 03 只说「注释同步」会留下 60 vs 480 静默分歧 | 🟡 | 切片 03 AC 明确两行目标值:`ACCESS_TOKEN_TTL_MINUTES=480` / `SESSION_TTL_HOURS=8`;§1 补现状分歧半句 |
| 锁定计数写路径归属含糊(service 直改 ORM vs Repository 方法),且切片 01 文件清单漏 `app/repositories/tenant.py` | 🟡 | §4.6 明确:对齐 `update_last_login` 惯例,写走 **UserRepository 新方法**(`record_failed_attempt` 原子自增 / `reset_failed_attempts` / `set_locked_until`);文件清单补 repositories/tenant.py |
| D6 论据部分失真——`SessionRepository.list_active_for_user` 已按 `expires_at > now` 过滤,会话页本就不显示过期行 | 🟡(打磨升级) | D6 论据改述:吊销载体与会话数据源时效粒度一致,DB 内 active=True 但已过期的行缩短 |
| 打磨项(不展开):§7 引用的 §0 当时未建(v2 已建)/ key_func 导入源定为 `app.core.security.decode_token`(避开 conftest 对 deps 命名空间的 mock)/ 三种 token 全覆盖措辞(铁律 3)/ 自定义 429 handler 需手动注入 `Retry-After`(复用 slowapi `_inject_headers`)/ SystemLog action 定死 `login_locked` / §5 补覆盖率目标 / §10 补 SystemLog 对应条 / 影响面补 conftest.py 与前端测试文件 / 风险表补 JWKS 冷启动同步阻塞与 slowapi 自读 .env 双源 | 🟢 | 全部吸收进正文对应章节 |

> 审查另报 1🔴 流程项:EP2 收尾须回填 feature_list.json 的 `plan` 字段指向本文档(three-tier §3)。v2 交付时执行;`status` 按**用户本次会话明确指令保持 `not_started`**(用户选择「已规划待实施」态,EP3 切片 01 开工时再翻 `in_progress`),该待办记 progress.md,不留静默断裂。

## 1. Problem Statement

平台当前认证面对生产环境有三层裸奔(第 10 次巡检 R1 🔴):

1. **登录可无限爆破**:`POST /auth/login` 无失败计数、无锁定、无限流。虽有 dummy-hash 时序防枚举,但攻击者可以不限次试密码。弱密码租户账号必然被穷举。
2. **全库无任何限流**:slowapi/limiter/ratelimit 在 requirements 与 app 内 grep 零命中。任何单用户/单 IP 可无限速打任意端点(聊天、导出、搜索),服务可被滥用拖垮。
3. **token 可用期 7 天**:`access_token_ttl_minutes` 默认 10080(config.py)。token 一旦泄露(浏览器残留、日志误记、XSS),攻击者横向可用窗口长达一周;被爆破成功的账号同理。(现状 `.env.example` 示例值已是 60 分钟,与代码默认值本就分歧——本 feature 一并统一到 480。)

作为「新 SaaS 产品的脚手架」,这是拿到生产前必须堵上的基本盘。

## 2. Solution

三层防御,各自独立可验证:

1. **登录失败锁定**(防爆破主力):User 表加 `failed_attempts` + `locked_until` 两列(DB 持久,重启不丢),连续失败 5 次锁 15 分钟自动解锁,账号维度,原子计数防并发绕过;IP 维度不锁(NAT 连坐)交给限流层。
2. **slowapi 全局 API 限流**(滥用第二层):进程内存存储,两档配额——认证端点 5 次/分/IP,其余端点 120 次/分(已登录按用户,匿名按 IP);探针/文档路径自写短路豁免;429 带 `Retry-After`,前端经事件桥 toast 提示。
3. **TTL 收口**(缩小泄露窗口):`access_token_ttl_minutes` 10080 → 480(8 小时),`session_ttl_hours` 168 → 8 对齐;存量旧 token 自然过期,零强制重登。

## 3. User Stories

1. 作为任意租户用户,我希望账号被连续爆破尝试时自动锁定一段时间,以免弱密码被穷举成功。
2. 作为任意租户用户,我希望锁定 15 分钟后自动解锁,以便不必找管理员即可恢复登录。
3. 作为任意租户用户,我输错密码 4 次后第 5 次输对,我希望账号不被锁(成功登录清零计数)。
4. 作为平台运维,我希望登录端点按 IP 限流,使单 IP 换账号横行扫靶的攻击也被拦住。
5. 作为平台运维,我希望所有业务端点有全局限流,以免任何单用户/单 IP 滥用 API 拖垮服务。
6. 作为平台运维,我希望 /health /ready 等探针与 /docs 不受限流,以免 K8s 探针 429 引发误重启。
7. 作为任意租户用户,我希望 token 8 小时过期,使泄露 token 的可用窗口从 7 天缩到 8 小时。
8. 作为前端用户,我触发限流时希望看到「请求过于频繁」的友好提示而非裸报错,知道稍后重试即可,不被踢出登录。
9. 作为平台运维,我希望限流配额与锁定阈值全部进 settings(env 可调),以便按部署形态调优无需改代码。
10. 作为管理员,我手动设置的 `status="locked"` 永久锁语义不希望被自动锁定机制干扰——两套锁各自独立。
11. 作为 Logto(OIDC)用户,我不使用本地密码登录,不希望本地登录的爆破防护机制能把我的账号锁死(锁定对我的登录路径无副作用)。
12. 作为开发者,我希望测试套件默认不受两层防护干扰(可显式开启/调整),既有 1012 条测试零回归。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | ~8 | `app/models/tenant.py`(User +2 列)/ 新迁移 ×1 / `app/repositories/tenant.py`(锁定写方法)/ `app/services/auth_service.py`(计数+锁定判定)/ `app/api/v1/auth.py`(login 挂严档 limit)/ `app/core/config.py`(新配置键 + TTL 默认值改)/ `app/main.py`(limiter 装配 + 429 handler + 豁免短路)/ 新增 `app/core/rate_limit.py`(单例 limiter + key_func) |
| 数据库迁移 | 1 | alembic 新版本:users 表加 `failed_attempts` int + `locked_until` datetime |
| 前端文件改动 | 2 | `frontend/src/api/client.ts`(429 拦截 → 事件桥)/ toast 监听挂载点(ToastProvider 层 listener,文件实施时定:toast.tsx 或 App 层) |
| 新增/扩展测试 | 3 | `tests/test_rate_limit.py`(新)/ `tests/test_auth_local.py`(扩展锁定用例)/ `tests/conftest.py`(测试环境限流开关)/ 前端 1 处(429 事件→toast 用例) |
| 配置 | 2 | `requirements.txt`(+slowapi)/ `.env.example`(新键注释 + TTL 两行统一 480/8) |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(User 是全局身份表,加列非租户数据;无新表)
- 是否修改现有租户隔离逻辑? **NO**(锁定在登录前、限流在鉴权前,都不触租户过滤路径)
- 是否引入跨租户访问点? **NO**(限流 key 是用户身份/IP,不跨租户读数据)
- 验证:多租户行为不变,既有 1012 测试零回归即为证据

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(限流是 HTTP 层前置防线,429 在权限判定之前返回,不区分角色)
- 是否影响 graph.py 工具内 check? **NO**
- scope 闸门(API Token)? 不涉及(PAT 请求限流按 IP 键,不解析 scope)

### 4.4 数据库表设计 checklist(AGENTS.md 铁律 6:不新增表,仅加列)

- [x] 无新表:User 加 `failed_attempts: int, default 0, not null` + `locked_until: datetime, nullable`(按 id 单行读写,无新索引需求;计数走原子 UPDATE,见 §4.6)
- [x] 双库兼容:普通列,无 PG 专有类型,SQLite 测试(create_all)/ PostgreSQL 生产(alembic)均直跑
- [x] timestamp:复用 User 既有 updated_at 审计列机制
- [x] 软删除:不涉及(锁定列跟随用户行生命周期;软删账号经 `get_by_login_identifier` 过滤落 user None 路径,天然不计数)
- [x] 历史维度:锁定触发写 SystemLog(auth 模块,复用 `LoggingService.record` 的 `action="login"` 先例,新 action 值定 `login_locked`)——不新建审计面(R4 域)

### 4.5 用户拍板决策(D1-D11,2026-08-14 AskUserQuestion 3 轮逐项拍板,无默认采纳)

**锁定机制(D1-D4)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D1 | 失败几次触发锁定 | **5 次**(连续失败;成功登录清零;触发锁定后计数重置) |
| D2 | 锁多久 | **15 分钟自动解锁**(期间正确密码也拒绝;短锁抑制自动化爆破 ≈480 次/天,真人可等) |
| D3 | 计数维度 | **账号锁定 + IP 限流双轨**:锁定只看账号(同账号任意来源 5 败即锁);IP 维度不锁账号(NAT 连坐)交给限流层登录档兜底 |
| D4 | 锁定数据形态 | **DB 字段持久化**:User 加 `failed_attempts` + `locked_until`(alembic 迁移),重启不丢、多 worker 共享;**不动 `status="locked"` 的管理员手动永久锁语义**,两套锁并存互不干扰 |

**TTL(D5-D7)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D5 | access_token TTL | **10080 → 480 分钟(8 小时)**:一个工作日重登一次;接受无 refresh 端点的 UX 成本(用户知情拍板);Logto 签发 token 不受此值控制 |
| D6 | session_ttl_hours | **168 → 8,与 token TTL 对齐**:session 行是吊销载体 + 会话列表数据源,对齐使时效粒度一致(DB 内 active=True 但已过期的行缩短;`list_active_for_user` 虽已过滤过期行,粒度一致仍让数据不撒谎) |
| D7 | 存量 7 天 token | **自然过期**:TTL 改配置只影响新签发,存量继续用到 exp;平台未上生产无真实存量风险,零迁移零强制重登 |

**限流(D8-D11)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D8 | 存储后端 | **slowapi 进程内存**:零新基建;单副本前提(与 scheduler_enabled 注释同一假设);多 worker 下计数分片(阈值等效放宽)+ 重启清零——已知情接受,防爆破主力是 D4 的 DB 锁定不受影响;将来上 Redis 只换 storage 参数 |
| D9 | 配额分级 | **两档**:认证类端点(/auth/login)5 次/分/IP;其余全部端点 120 次/分(已登录按用户、匿名按 IP)。默认值进 settings 可调;chat 端点不单独设档(LLM 成本另有钱包门 R3a 把关) |
| D10 | 豁免端点 | **{ /metrics, /health, /ready, /openapi.json, /docs, /redoc }**(复用 main.py 既有中间件豁免先例):探针误 429 会引发 K8s 误重启;业务端点零豁免不留口子 |
| D11 | 429 格式与前端 | 后端 `{"detail": "..."}` + `Retry-After` 头(与项目错误体惯例一致);前端 client.ts 拦 429 → **事件桥**(仿 `AUTH_EXPIRED_EVENT` 先例,自研 toast 是 Context 模式,拦截器在 React 树外)→ toast「请求过于频繁,请稍后再试」,不踢登录、不自动重试 |

### 4.6 技术设计细节(实施层约定)

**锁定判定与写路径**

- **判定位置**:`AuthService.login` 内、bcrypt verify **之后**(与既有 account-state 检查同序,保住 dummy-hash 时序防枚举):`locked_until > now` → 401 "account temporarily locked, try again later";密码失败且账号存在 → 计数 +1(原子);达到阈值 → 置 `locked_until` 且计数归零;成功登录 → 计数清零、锁残留清除。
- **写路径归属(依赖单向)**:对齐 `update_last_login` 惯例,三组写全走 **UserRepository 新方法**——`record_failed_attempt(user_id) -> int`(原子 UPDATE 自增:`update().values(failed_attempts=User.failed_attempts + 1)`,返回新值供阈值判定,杜绝并发 read-modify-write 同读旧值绕过计数)/ `reset_failed_attempts(user_id)`(清零 + locked_until 置空)/ `set_locked_until(user_id, until)`;Repository 方法内提交,**计数/锁定写必须在 raise AuthError 前 flush+commit**(现状 login 仅成功路径末尾 commit,失败路径不落库即静默失效)。
- **锁定作用域(边界语义)**:`locked_until` **仅作用于本地 `/auth/login`**——Logto 登录路径(`get_current_user` 只看 status)、已签发有效 token、PAT 均不受锁定影响;**OIDC-only 账号(`user.password is None`)不计数**(否则知其 username 即可纯 DoS:锁得了本地入口、对 Logto 入口无效);**锁定期内继续失败一律 401 不计数不续期**(防「每 15 分钟喂 5 次失败无限续锁」的 DoS 放大);`status="locked"/"inactive"` 的拒绝发生在密码判定之前,天然不计数;密码正确但无租户(memberships 空)不算成功登录、不清零。
- **不存在的账号不计数**(无行可计),该路径由登录端点 IP 限流(D9 严档)兜底。

**限流装配**

- **单例 limiter**:`app/core/rate_limit.py` 提供**模块级单例** `limiter = Limiter(...)`(不是每 create_app 新建的工厂——login 路由的 `@limiter.limit` 装饰器在模块 import 时绑定实例,工厂会造成装饰器与 `app.state.limiter` 两套 storage 计数分裂);`default_limits` 用 callable(`[lambda: settings.rate_limit_default]`)保留运行时可调;`headers_enabled=True`。
- **key_func 链**:验签 bearer(复用 `app.core.security` 的统一验证 helper——本地 HS256 无 DB 依赖 / Logto RS256 走模块级缓存 JWKS;**导入源必须是 `app.core.security`,不能从 `app.api.deps` 导入**,否则 conftest 对 deps 命名空间的 mock 会让测试 bearer 全解析成同一 fake sub)取 `sub` 作为 key → 验不过 / 无 token / PAT(`ahp_` 前缀,不做 DB 反查)→ client IP。**必须验签而非裸解码 JWT payload**——裸解码下攻击者轮换伪造 sub 即可彻底绕过限流。三种 token(本地/Logto/开发)统一管线全覆盖。
- **login 严档独立 key**:`@limiter.limit(settings.rate_limit_login)` 装饰 login 路由(该端点匿名,key 直接用 IP,不走「先验 token 取 sub」链——带合法 token 的登录请求不该按 sub 计数);严档字符串 import 时固化,测试调严档配额走 env(conftest `os.environ.setdefault` 先例);login 现有顶层 `request: Request` 参数满足装饰器要求。
- **豁免 = 自写路径短路**(审查确认 slowapi **没有** `exempt_paths` 构造参数,`@limiter.exempt` 装饰器又够不到 /docs /health 这类非模块级路由):限流装配处 ~10 行路径短路,`request.url.path` 命中 `settings.rate_limit_exempt_paths` 清单直接放行不进 slowapi;不碰 slowapi 私有 API(`_exempt_routes` 等)。
- **全局默认档**:`SlowAPIMiddleware` 把 default_limits 应用到所有未短路、未装饰路由(与既有 `metrics_middleware` 同为 BaseHTTPMiddleware 机制,chat 流式端点已在该机制下运行,无新增风险)。
- **429 handler**:`app.add_exception_handler(RateLimitExceeded, ...)` 自定义返回 `{"detail": "..."}`——slowapi 内置 handler 返回 `{"error": ...}` 且经 `_inject_headers` 注 `Retry-After`,自定义后须复用该机制或手动设置头(AC 已要求 `Retry-After` 存在)。
- **slowapi 配置双源注意**:Limiter 构造会自读 cwd `.env` 的 `RATELIMIT_*` 键(可能覆盖 `enabled` 等)——部署 `.env` **不应**写 `RATELIMIT_*` 键,配置唯一入口是项目 settings 的 `rate_limit_*` 键。

**TTL**

- TTL 仅由 `settings.access_token_ttl_minutes` 派生:`local_auth.create_access_token`(exp)与 login 响应 `expires_in` 两处读同一键,改默认值即全生效,零代码改动。/dev/token 硬编码 1h 不动(归 R5 config-startup-guard 域)。
- **配置键**(全部带默认值 + 注释,`.env.example` 同步):`rate_limit_enabled: bool = True` / `rate_limit_default: str = "120/minute"` / `rate_limit_login: str = "5/minute"` / `rate_limit_exempt_paths: str = "/metrics,/health,/ready,/openapi.json,/docs,/redoc"` / `login_lockout_threshold: int = 5` / `login_lockout_minutes: int = 15`;既有 `access_token_ttl_minutes` 默认值改 480、`session_ttl_hours` 默认值改 8(`.env.example` 两行同值统一,消除现状 60 分钟分歧)。
- **CONTEXT.md 术语**(EP3 落地时结晶,末切片):「临时锁定(Temporary Lockout)」= failed_attempts 触发、locked_until 自动解锁的自动锁,仅作用本地登录;区别于「管理员锁定」= status="locked" 手动永久锁。

## 5. Testing Decisions

- **测试 seam**:全部走既有 HTTP 层集成 seam(`TestClient` + 内存库 conftest),不新开 seam;key_func 单测走函数直调。既有先例:`tests/test_auth_local.py`(登录失败路径)、`tests/test_permission_backfill.py`(parametrize 风格)。
- **锁定用例**(切片 01):5 连败 → 第 6 次(正确密码)401 且 message 含 locked;`locked_until` 过期后(直接回写 DB 行时间,不 monkeypatch 时钟)正确密码可登录;4 败 + 第 5 次成功 → 计数清零再 4 败不锁;**锁定期内继续失败不计数不续期**(回写 locked_until 推后验证未变);`status="locked"` 手动锁行为不变(既有用例);不存在账号连打 10 次不产生任何 DB 计数;**OIDC-only 账号(password=None)连打不计数不锁定**;并发原子性(两并发失败后计数 == 2,可选异步任务直测 repo 方法)。
- **限流用例**(切片 02):严档 6 连打登录 → 第 6 次 429 + `Retry-After` 头 + `{"detail"}` 体;默认档配额 override 成小值(如 "3/minute")打任意业务端点 → 429;豁免路径(/health)连打 20 次不限;key_func 直调:合法本地 token → sub 键 / 垃圾 token、无 token、PAT → IP 键(**伪造 sub 的裸 token 必须落 IP 档**);`rate_limit_enabled=False` 整套不生效。
- **两层不打架**:锁定测试(01)先于限流(02)落地,天然无干扰;02 落地后既有锁定测试需继续绿——测试环境 `RATE_LIMIT_ENABLED=false`(conftest `os.environ.setdefault`,settings import 前注入),显式限流测试内开启 + 小配额 + `limiter.reset()` 隔离(单例 limiter 跨测试共享计数),保证默认装配仍被显式构造的 app 覆盖到。
- **TTL 用例**(切片 03):登录响应 `expires_in == 480*60`;UserSession 行 `expires_at ≈ now+8h`;既有 token 过期相关测试同步核对新值。
- **前端用例**(切片 03):429 → `aap:rate-limited` 事件 → toast 出现;401 既有行为不回归;token 不被清除、不跳登录。
- **覆盖率目标**:不低于项目基线 93%;新增 `app/core/rate_limit.py` 与 auth_service 锁定分支全覆盖(每分支至少一正一反用例)。
- **回归基线**:`./init.sh full` 全量(当前 1012 passed)零回归是硬门槛。

## 6. 实施切片(to-tickets 产出,EP2 单回环)

### 切片依赖图

```
01 登录失败锁定(迁移+repo+service+测试)──→ 02 slowapi 全局限流(单例+两档+豁免+429+key_func)──→ 03 TTL 收口 + 前端 429 事件桥 + feature 收尾(末切片)
```

> 顺序理由:01 先行是**测试互斥**需求——锁定测试本身要连打登录 5-6 次,若 02 的登录严档(5/分/IP)先在,锁定测试会先吃 429;01 先落地锁定测试干净,02 再处理两层共存(测试环境限流开关 + 显式限流测试自行隔离)。03 无技术依赖,但作为收尾片放最后(全量验证 + feature 收尾仪式)。

### 切片 01 — 登录失败锁定:User 加列迁移 + UserRepository 写方法 + AuthService 判定 + 集成测试

**What it delivers**:攻击者对某账号连续输错 5 次密码后,该账号被锁 15 分钟——期间即使密码正确也 401 并提示稍后再试;15 分钟后自动恢复;正常用户输错 4 次后登录成功则计数清零;锁定期内继续失败不会续期;OIDC-only 账号与不存在的账号连打无副作用;管理员手动永久锁(status="locked")行为不变;重启服务锁定状态不丢(DB 持久);并发失败计数不丢(原子 UPDATE)。

**Blocked by**: 无(frontier,可立即开工)

**文件清单**:`app/models/tenant.py`(改)+ `alembic/versions/`(新迁移)+ `app/core/config.py`(login_lockout_threshold/login_lockout_minutes 两键)+ `app/repositories/tenant.py`(三个写方法)+ `app/services/auth_service.py`(改)+ `tests/test_auth_local.py`(扩展)

**验证命令**:`pytest tests/test_auth_local.py tests/test_auth.py -q` + `alembic upgrade head && alembic check`(需 docker PG)+ `./init.sh`(冒烟)

**Acceptance criteria**:

- [ ] User 模型新增 `failed_attempts`(int,server_default "0",not null)+ `locked_until`(datetime,nullable);alembic 迁移双库兼容(SQLite 测试 create_all / PG 生产迁移均直跑,风格对齐现有 `YYYY_MM_DD_HHMM_<rev>_<slug>`)
- [ ] `UserRepository` 新增三方法(方法内 flush+commit):`record_failed_attempt(user_id) -> int`(原子 `UPDATE ... SET failed_attempts = failed_attempts + 1`,杜绝 read-modify-write 并发绕过)/ `reset_failed_attempts(user_id)`(计数清零 + locked_until 置空)/ `set_locked_until(user_id, until)`
- [ ] `AuthService.login`:bcrypt verify 后、密码判定前查 `locked_until > now` → 401 "account temporarily locked, try again later";插入点不破坏既有 401 语义(user None / status locked / inactive / 无租户分支)与 dummy-hash 时序防护
- [ ] 密码失败且账号存在且 `user.password` 非 None(本地密码账号)→ `record_failed_attempt`;新值达到 `login_lockout_threshold`(5)→ `set_locked_until(now + login_lockout_minutes)` 且 `reset_failed_attempts`(计数归零,解锁后重新累计);**计数/锁定写在 raise AuthError 前已持久化**
- [ ] 锁定期内(`locked_until > now`)继续失败:一律 401 locked,**不计数不续期**
- [ ] 成功登录 → `reset_failed_attempts`(清零含锁残留)
- [ ] OIDC-only 账号(`user.password is None`)失败不计数;不存在账号连败无任何 DB 写;软删账号经 `get_by_login_identifier` 过滤同不存在路径
- [ ] `status="locked"` 管理员永久锁既有行为与测试零变化(两套锁互不干扰)
- [ ] 锁定触发写一条 SystemLog(复用 LoggingService.record,`action="login_locked"`,auth 模块)
- [ ] `settings` 新键 `login_lockout_threshold=5` / `login_lockout_minutes=15` 带注释,`.env.example` 同步
- [ ] 新增集成测试覆盖:5 连败触发锁(第 6 次正确密码 401 含 locked 提示)/ locked_until 过期后自动恢复 / 4 败+成功清零再 4 败不锁 / **锁定期内继续失败不续期** / 手动锁不受影响 / 不存在账号 10 连败无副作用 / **OIDC-only 账号连打不锁定** / repo 原子性直测(两次 record 后计数 == 2)
- [ ] `pytest tests/test_auth_local.py tests/test_auth.py` 全绿;`./init.sh` 冒烟绿;全量 pytest 零回归

### 切片 02 — slowapi 全局限流:单例装配 + 两档配额 + 路径短路豁免 + 429 + key_func + 测试

**What it delivers**:任意业务端点被同一用户(已登录,验签取 sub)或同一 IP(匿名/垃圾 token/PAT)以超过 120 次/分钟持续调用时,返回 429 + `Retry-After` 头 + `{"detail"}` 体;登录端点更严(同 IP 5 次/分钟,独立 IP key);探针与文档路径完全不受限(自写路径短路,清单 env 可调);配额与豁免全部 env 可调;`rate_limit_enabled=False` 一键关闭整套;重启后计数清零(已接受);伪造 sub 的裸 token 无法绕过(必须验签)。

**Blocked by**: 切片 01

**文件清单**:`requirements.txt`(+slowapi,精确 pin)+ `app/core/rate_limit.py`(新:模块级单例 limiter + key_func)+ `app/core/config.py`(4 个 rate_limit_* 键)+ `app/main.py`(装配 middleware + 429 handler + 路径短路)+ `app/api/v1/auth.py`(login 挂严档)+ `tests/test_rate_limit.py`(新)+ `tests/conftest.py`(测试环境 `RATE_LIMIT_ENABLED=false` 注入)

**验证命令**:`pytest tests/test_rate_limit.py tests/test_auth_local.py -q`(新测试绿 + 切片 01 锁定测试不回归)+ `./init.sh`(冒烟)

**Acceptance criteria**:

- [ ] `requirements.txt` 加 slowapi(精确 pin,与既有依赖风格一致);`app/core/rate_limit.py` 提供**模块级单例 limiter**(default_limits 用 callable 读 settings、headers_enabled=True)+ key_func;不是每 create_app 新建的工厂(装饰器 import 期绑定实例,工厂会分裂计数)
- [ ] key_func:验签 bearer(导入源 `app.core.security`,本地 HS256 无 DB / Logto RS256 缓存 JWKS,三种 token 统一管线)取 sub → 用户键;无 token / 验不过 / PAT(`ahp_` 前缀)→ client IP 键;**直测证明伪造 sub 的裸 token 落 IP 档**(验签失败不得产出用户键)
- [ ] `create_app` 装配:`app.state.limiter` 挂单例 + 路径短路(`request.url.path` 命中 `rate_limit_exempt_paths` 直接放行,不进 slowapi,不碰私有 API)+ `SlowAPIMiddleware`(默认档覆盖所有未短路未装饰路由)+ `RateLimitExceeded` handler 返回 `{"detail": "..."}` 且**带 `Retry-After` 头**(复用 slowapi `_inject_headers` 或手动注入)
- [ ] login 路由显式挂严档 `@limiter.limit(settings.rate_limit_login)`(5/minute,key 为 IP,不走验签链);覆盖默认档
- [ ] 豁免 6 路径(/metrics /health /ready /openapi.json /docs /redoc)不受限(测试连打证明);豁免清单读 settings(env 可调)
- [ ] settings 新键 `rate_limit_enabled=True` / `rate_limit_default="120/minute"` / `rate_limit_login="5/minute"` / `rate_limit_exempt_paths`;`.env.example` 同步(含「不写 RATELIMIT_* 键」注释);`rate_limit_enabled=False` 时整套不生效(测试证明)
- [ ] 新增测试:严档 6 连打登录第 6 次 429(体含 detail + Retry-After)/ 默认档小配额打业务端点 429 / 豁免路径连打不限 / key_func 四分支直测(sub / 垃圾 token / 无 token / PAT)/ enabled=False 不生效 / 限流与切片 01 锁定共存(锁定测试场景在限流关闭下照常绿 + 显式开启的小配额下各自独立触发)
- [ ] conftest:`os.environ.setdefault("RATE_LIMIT_ENABLED", "false")`(settings import 前),既有全部测试(含切片 01 锁定测试)零回归
- [ ] `./init.sh` 冒烟绿;全量 pytest 零回归

### 切片 03 — TTL 收口 + 前端 429 事件桥 + feature 收尾(末切片)

**What it delivers**:新签发的本地 token 8 小时过期(登录响应 `expires_in=28800`),session 行与 token 时效对齐;用户触到限流时前端弹「请求过于频繁,请稍后再试」toast 而非裸报错、不被踢出登录、token 不被清;存量旧 token 不受影响自然过期;全量验证收官。

**Blocked by**: 切片 02

**文件清单**:`app/core/config.py`(两默认值改)+ `.env.example`(TTL 两行统一 480/8 + 新键注释收尾)+ `frontend/src/api/client.ts`(429 拦截 → 事件桥)+ 前端 listener(新 ~15 行小组件,挂载点约束:**必须在 ToastProvider 子树内**才能调 `useToast`,具体文件看 ToastProvider 挂载层级后定,行为已钉死:监听 `aap:rate-limited` → `t.error`)+ 前端测试 1 处 + `CONTEXT.md`(术语条目)

**验证命令**:`./init.sh full` + `alembic upgrade head && alembic check` + `cd frontend && npm run build && npm test && npx oxlint`

**Acceptance criteria**:

- [ ] `access_token_ttl_minutes` 默认值 10080 → 480;`session_ttl_hours` 默认值 168 → 8;`.env.example` 两行显式改 `ACCESS_TOKEN_TTL_MINUTES=480` / `SESSION_TTL_HOURS=8` + 过渡注释(存量 token 自然过期;**消除现状示例 60 分钟与代码默认的分歧**)
- [ ] 登录集成测试断言 `expires_in == 28800`;UserSession `expires_at ≈ now+8h`;grep `10080`/`"168"` 旧字面量在 app/ 下归零(auth_service 的 `settings.session_ttl_hours` 符号引用不算;/dev/token 的 3600 不属于本片)
- [ ] `frontend/src/api/client.ts` 拦截 429 → `window.dispatchEvent(new CustomEvent("aap:rate-limited"))`(仿 `AUTH_EXPIRED_EVENT` 先例);ToastProvider 层 listener 收到事件 → `t.error("请求过于频繁,请稍后再试")`;不清 token、不跳登录、不自动重试
- [ ] vitest 用例锁定:429 → 事件发出 → toast 渲染;401 既有行为不回归;token 不被清除
- [ ] `CONTEXT.md` 新增术语:「临时锁定(Temporary Lockout)」与「管理员锁定」的区分条目(按 §4.6 措辞,glossary 格式对齐「判定链(Decision Chain)」先例)
- [ ] 全量验证:`./init.sh full` 全绿零回归 + alembic 迁移链干净 + 前端 build/test/oxlint 全绿
- [ ] feature 收尾仪式(three-tier §4 第 1-8 步):feature_list.json `not_started → passing` + evidence + sync-active + progress.md + 文档影响评估 + 分支清理

## 7. 对抗式审查段(复杂任务:鉴权 + token 安全敏感 → 已执行)

**审查方式**:单模型双轴(Standards + Spec)并行,2026-08-14 执行;产出 3🔴 + 10🟡 + 12🟢(含 1🔴 流程项:feature_list 回填),全部回写 §0 变更摘要,v1 → v2。

## 8. Out of Scope

- ❌ refresh token 端点(D5 已知情接受每 8 小时重登;将来需求独立立项)
- ❌ Redis / 多副本共享限流存储(D8 拍板进程内存;换后端只动 storage 参数,届时再说)
- ❌ Logto 侧 token TTL(Logto 租户配置域,非本项目代码)
- ❌ /dev/token 独立硬编码 1h(归 R5 `config-startup-guard`)
- ❌ 存量 7 天 token 批量吊销脚本(D7 自然过期)
- ❌ 网关层限流 / WAF / CDN(总纲系列边界,部署侧能力)
- ❌ chat/LLM 端点单独严档(D9 拍板两档;LLM 成本由 R3a 钱包门把关)
- ❌ 429 自动重试 / 指数退避(D11 拍板仅提示不重试)
- ❌ 限流/锁定状态的管理员可见面板(锁定短暂自动恢复,无需管理面;将来需要独立立项)
- ❌ TurnAccountant 等架构重构(总纲边界)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 既有 auth 测试与锁定/限流交互:某些测试连打登录失败路径,意外触发锁定(改测试预期)或 429 | 中 | 切片顺序 01→02 隔离;全量跑发现即修;测试环境限流可关(conftest `RATE_LIMIT_ENABLED=false`);锁定测试用独立账号计数天然隔离 |
| key_func 每请求验签成本(本地 HS256 便宜;Logto JWKS 有 600s 缓存;PAT 落 IP 不查库) | 低 | 复用现有验证 helper;不新增 DB 查询路径;JWKS 冷启动同步阻塞与既有 get_current_user 行为相同,非新增风险 |
| SSE 流式端点(chat)被默认档误伤 | 低 | 限流按请求数而非流时长;120/分远超正常 UI 触发频率;SlowAPIMiddleware 与既有 metrics_middleware 同机制,chat 已在其下运行;配额 env 可调 |
| 多 worker 部署限流计数分片(阈值等效放宽 N 倍)+ 重启清零 | 低 | D8 已知情接受(单副本前提,与 scheduler_enabled 同一假设);防爆破主力 D4 是 DB 持久不受影响 |
| 锁定被武器化(恶意第三方故意锁受害者账号做 DoS) | 中 | D2 选 15 分钟短锁自动恢复 + 锁定期内失败不续期(§4.6);OIDC-only 账号不计数(堵「锁了也没用」的纯 DoS 面);账号锁 + IP 限流双层下攻击者自身先被 IP 限流拦 |
| 严档(5/分)与锁定阈值(5 次)同值,测试里两层叠加互相干扰判定 | 中 | 切片 02 AC 明确「两层共存各自独立触发」用例;测试中限流可独立开关 |
| slowapi 自读 `.env` 的 `RATELIMIT_*` 键,与项目 settings 双源冲突 | 低 | §4.6 明确部署 .env 不写 RATELIMIT_* 键;`.env.example` 注释声明;配置唯一入口是 rate_limit_* |
| TTL 缩短对长时挂机用户的影响(8 小时后被踢回登录页) | 低 | D5 用户知情拍板;前端 401 处理器已有优雅登出路径 |

## 10. 验收标准(同步 feature_list.json verification)

1. 登录连败 5 次 → 账号锁 15 分钟(正确密码也拒;锁定期内失败不续期);过期自动恢复;OIDC-only/不存在账号无副作用——测试常驻 CI(切片 01)
2. 锁定计数原子(并发不丢)且失败路径持久化(重启可复现锁定)——repo 直测常驻 CI(切片 01)
3. 锁定触发写 SystemLog(`action="login_locked"`)——测试断言(切片 01)
4. 全局默认档 120/分(用户/IP 键)+ 登录严档 5/分/IP 生效;429 = `{"detail"}` + `Retry-After`;豁免 6 探针/文档路径不受限;enabled=False 一键关——测试常驻 CI(切片 02)
5. key_func 验签防绕过:伪造 sub 的裸 token 落 IP 档——直测(切片 02)
6. `access_token_ttl_minutes=480` / `session_ttl_hours=8` 生效:`expires_in=28800` + session 行 8h;`.env.example` 统一 480/8——测试断言(切片 03)
7. 前端 429 → 事件桥 → toast,不踢登录不清 token 不重试——vitest(切片 03)
8. `./init.sh full` 全量零回归(基线 1012 passed)+ `alembic check` + 前端 build/test/oxlint 全绿(切片 03)
9. 全部新配置键有默认值 + 注释 + `.env.example` 同步;grep 确认 slowapi 入 requirements(切片 02)

## 11. 不越界声明

本次改动**只**涉及:登录失败锁定(User 加列 + UserRepository 写方法 + AuthService 判定)、slowapi 全局限流(单例装配 + 两档 + 路径短路豁免 + 429)、token TTL 两个默认值与 `.env.example` 统一、前端 429 事件桥 toast、配套测试与配置。

**不**触碰:权限判定链 / RBAC / casbin / 多租户隔离逻辑 / 任何业务端点的行为语义 / 计费与钱包(R3a 域)/ 审计埋点扩展(R4 域,仅 auth 模块既有先例内加一条 login_locked)/ /dev/token 与配置守卫(R5 域)/ refresh 端点 / Redis / auth_service 既有结构重构。
