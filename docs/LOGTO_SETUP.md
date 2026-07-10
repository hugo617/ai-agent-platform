# 登录方式配置指南

> **现状说明**：平台支持**三种登录方式**，默认即可使用全部功能，**无需配置 Logto**。
>
> 1. **账号密码登录**（推荐，生产可用）—— 后端内置 bcrypt 校验，签发 HS256 JWT
> 2. **一键开发登录**（仅 dev）—— 后端自签 RS256 JWT，走与 Logto 完全相同的验证代码路径
> 3. **Logto OIDC**（可选，社交账号/SSO）—— 见下文配置
>
> 本文档说明三者的关系、何时切换到 Logto、以及如何配置 Logto。

## 一、账号密码登录（默认）

后端 `POST /api/v1/auth/login` 接受 `{username|email, password}`：
1. 按 username/email 查 `users` 表（必须 `status=active` 且有 `password`）
2. `app/core/password.py` 用 bcrypt 校验密码
3. `app/core/local_auth.py` 签发 HS256 JWT（`iss="local"`，含 `sub/tenant_id/email/jti`）
4. 写一条 `user_sessions` 记录（用于「活跃会话」管理与注销）

签发的 token 与开发 token、Logto token **走完全相同的 `get_current_user` 验证管线**——
`app/core/security.py::decode_token` 通过 `iss` 字段分发：

| `iss` | 来源 | 算法 | 验证方式 |
|-------|------|------|----------|
| `"local"` | 账号密码登录 | HS256 | `JWT_SECRET` 对称密钥 |
| `http://localhost:8000/oidc` | 开发 token | RS256 | 内存 RSA dev key |
| Logto issuer URL | Logto | RS256 | Logto JWKS endpoint |

**首次使用**先建管理员账号：

```bash
python scripts/init_admin.py
# 默认 admin / admin@example.com / Admin@123456
# 用环境变量覆盖：ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_TENANT_NAME
```

然后用 `admin / Admin@123456` 在前端登录页登录即可。

> **相关配置**（`.env`）：
> - `JWT_SECRET` —— HS256 签名密钥，**生产环境务必改**
> - `SALT_ROUNDS` —— bcrypt cost factor，默认 12
> - `ACCESS_TOKEN_TTL_MINUTES` —— access token 有效期，默认 60
> - `SESSION_TTL_HOURS` —— 会话有效期，默认 168（7 天）

## 二、一键开发登录（仅 dev）

`APP_ENV=development` 下提供两个端点：
- `POST /dev/bootstrap` —— 创建开发租户 + 用户 + seed casbin 权限
- `POST /dev/token` —— 用内存中的 RSA 密钥签发 RS256 JWT

前端登录页的「🚀 一键开发登录」按钮会依次调用这两个端点，拿到 token 后存入 localStorage。
后端验证 token 时，`app/core/security.py` 走的是**和 Logto 完全相同的 JWKS + RS256 验签逻辑**——
只是密钥源换成内存（避免单 worker 自调用死锁）。

**所以切换到 Logto 时，验证代码零改动**，只改 `.env`。

## 三、何时需要 Logto

满足以下任一需求时，再配 Logto：

- 需要社交账号登录（微信、Google、GitHub …）
- 需要 SSO / 企业身份源（SAML、Azure AD）
- 需要标准 OIDC 第三方应用接入

**否则账号密码登录已经覆盖绝大多数场景**，Logto 是可选增强而非必需。

## 四、Logto 的已知镜像问题

`svhd/logto` 的 `latest` 和 `1.27.0` 标签存在数据库 alteration 问题：
启动时报 `Found undeployed database alterations`。

若要使用 Logto，需手动初始化数据库：

```bash
# 1. 启动 Logto（它会因 alteration 错误退出，但数据库容器已起）
docker compose up -d logto-db

# 2. 用官方 CLI 初始化 schema（替代 svhd/logto 镜像）
docker run --rm --network ai-agent-platform_default \
  -e DB=postgresql \
  -e DB_HOST=logto-db \
  -e DB_PORT=5432 \
  -e DB_USER=logto \
  -e DB_PASSWORD=logto_secret \
  -e DB_NAME=logto \
  svhd/logto:1.27.0 npm run cli db seed -- --swe && \
docker run --rm --network ai-agent-platform_default \
  -e DB=postgresql -e DB_HOST=logto-db -e DB_PORT=5432 \
  -e DB_USER=logto -e DB_PASSWORD=logto_secret -e DB_NAME=logto \
  svhd/logto:1.27.0 npm run cli db alteration deploy latest

# 3. 再启动 Logto 服务
docker compose up -d logto
```

更省事的方式是用 Logto Cloud（托管版，免费额度够 MVP），
或换用 `logto/logto` 官方镜像（带自动迁移）。

## 五、配置 Logto（启动成功后）

1. **初始化管理员**：打开 http://localhost:3002，创建管理员账号

2. **创建 API Resource**（让后端能验 token）：
   - 进 API → API Resources → Create
   - API identifier 填 `http://localhost:8000/api`（和 `.env` 的 `LOGTO_AUDIENCE` 一致）
   - 名称随意，如 `agenthub-api`

3. **创建应用**（让前端能登录）：
   - Applications → Create → Traditional Web
   - Redirect URI 填 `http://localhost:3000/callback`
   - Post sign-out redirect URI 填 `http://localhost:3000`
   - 记下 App ID

4. **切换后端验证源**：编辑 `.env`
   ```bash
   # 从开发模式（指向后端自己）
   LOGTO_ISSUER=http://localhost:8000/oidc
   # 改成指向 Logto
   LOGTO_ISSUER=http://localhost:3001/oidc
   ```
   重启后端即可。

5. **前端接 Logto SDK**（替换 dev 登录）：
   ```bash
   npm install @logto/react
   ```
   在 `login-page.tsx` 的 TODO 标记处接入 `LogtoProvider` + `signIn()`。
   登录回调后从 `logtoClient.getAccessToken()` 拿 token，调 `signIn(token)` 存入。

## 六、多模式共存

三种登录方式可以同时存在，互不影响：

| 场景 | 推荐方式 | 配置 |
|------|----------|------|
| 本地开发快速进入 | 🚀 一键开发登录 | `LOGTO_ISSUER=http://localhost:8000/oidc` |
| 团队 staging / 小团队生产 | 账号密码登录 | 任意 `LOGTO_ISSUER`（账号密码独立于 Logto） |
| 需要社交账号/SSO | Logto OIDC | `LOGTO_ISSUER=https://your-logto/oidc` |

**账号密码登录与 Logto 完全独立**：本地账号的 `users.password` 由后端管理，
Logto 账号的 `users.id` 镜像 JWT `sub`（`password` 为 null，无法用密码登录）。
两套账号体系通过 `user_tenants` 共享同一个租户与 casbin 权限矩阵。

切换登录方式只改 `.env` 和前端按钮，验证逻辑（`decode_token`）自动按 `iss` 分发。
