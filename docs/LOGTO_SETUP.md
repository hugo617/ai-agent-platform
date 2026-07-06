# Logto 配置指南（可选）

> **现状说明**：MVP 阶段已内置"一键开发登录"（后端自签 RS256 JWT，走与 Logto 完全相同的验证代码路径）。
> 你**不需要配置 Logto** 就能登录和使用全部功能。
>
> 本文档供将来需要真实 OIDC 登录（社交账号、SSO 等）时参考。

## 一、为什么现在不必配 Logto

后端在 `APP_ENV=development` 下提供两个端点：
- `POST /dev/bootstrap` —— 创建开发租户 + 用户 + seed casbin 权限
- `POST /dev/token` —— 用内存中的 RSA 密钥签发 RS256 JWT

前端登录页的"🚀 一键开发登录"按钮会依次调用这两个端点，拿到 token 后存入 localStorage。
后端验证 token 时，`app/core/security.py` 走的是**和 Logto 完全相同的 JWKS + RS256 验签逻辑**——
只是密钥源换成内存（避免单 worker 自调用死锁）。

**所以切换到 Logto 时，验证代码零改动**，只改 `.env`。

## 二、Logto 的已知镜像问题

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

## 三、配置 Logto（启动成功后）

1. **初始化管理员**：打开 http://localhost:3002，创建管理员账号

2. **创建 API Resource**（让后端能验 token）：
   - 进 API → API Resources → Create
   - API identifier 填 `http://localhost:8000/api`（和 `.env` 的 `LOGTO_AUDIENCE` 一致）
   - 名称随意，如 `ai-agent-platform-api`

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

## 四、双模式共存

两套登录方式可以共存：
- 开发环境用"一键开发登录"（`.env` 里 `LOGTO_ISSUER=http://localhost:8000/oidc`）
- 生产/staging 用 Logto（`LOGTO_ISSUER=https://your-logto/oidc`）

切换只改一行环境变量，验证逻辑自动适配。
