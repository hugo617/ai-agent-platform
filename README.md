# ai-agent-platform

多租户 AI 智能体 SaaS 平台后端 —— FastAPI + pycasbin + LangGraph。

> Phase 1：后端骨架 + 多租户权限系统 + 最简 LangGraph 智能体（前后端分离，前端在 Phase 3）。

## 技术栈

| 层 | 选型 |
|----|------|
| Web 框架 | FastAPI + Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic |
| 认证 | Logto（OIDC，FastAPI 只验 JWT）+ **本地账号密码（bcrypt）** |
| 授权 | **pycasbin**（RBAC + domain，多租户隔离）|
| 智能体 | LangGraph（ReAct agent，SSE 流式）|
| 数据库 | PostgreSQL 16 + pgvector |
| 测试 | pytest + pytest-asyncio + httpx |

## 架构（经典四层分层）

```
app/
├── api/        【Controller 层】HTTP 路由 + 依赖注入（认证/租户/权限）
│   ├── deps.py       公共依赖：get_current_user / require_permission
│   └── v1/           auth / tenants / agents / chat
├── services/   【Service 层】业务逻辑（含 permission_service 封装 casbin）
├── repositories/【Repository 层】数据访问，BaseRepository 统一注入 tenant_id 隔离
├── models/     【Model 层】SQLAlchemy ORM 实体
├── schemas/    【Model 层】Pydantic DTO（请求/响应）
├── core/       基础设施：config / database / security / casbin_enforcer
└── agents/     LangGraph 智能体（独立于四层，工具调用受 casbin 约束）
```

**依赖方向严格单向**：`api → services → repositories → models`。权限校验通过 `Depends(require_permission(...))` 在 Controller 层声明，工具调用在执行前再次校验。

## 多租户与权限模型

- **数据隔离**：共享 PostgreSQL，所有租户表带 `tenant_id`，`TenantScopedRepository` 在数据层统一加 `WHERE tenant_id = :current`。
- **权限模型**（`casbin_model.conf`，RBAC + domain）：
  ```
  r = sub, dom, obj, act
  m = g(r.sub, p.sub, r.dom) && r.dom == p.dom && keyMatch(r.obj, p.obj) && r.act == p.act
  ```
- **默认角色策略**（创建租户时自动 seed）：
  - `owner`：agents 全权限 + conversations 全权限
  - `member`：agents 只读 + conversations 读写/对话

## 快速开始

### 1. 启动基础设施

```bash
cp .env.example .env       # 按需修改（DATABASE_URL / OPENAI_API_KEY 等）
docker-compose up -d       # 起 PostgreSQL(pgvector) + Logto
```

### 2. 安装后端依赖 & 初始化数据库

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head          # 建表
uvicorn app.main:app --reload # 启动后端，访问 http://localhost:8000/docs
```

### 3. 创建管理员账号（首次）

```bash
python scripts/init_admin.py
# 默认：admin / admin@example.com / Admin@123456
# 可用环境变量覆盖：ADMIN_USERNAME / ADMIN_EMAIL / ADMIN_PASSWORD
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev                   # 访问 http://localhost:3000
```

### 5. 登录

打开 http://localhost:3000，三种方式任选：

- **账号密码**（推荐）—— 用上一步创建的 `admin / Admin@123456` 登录。
- **🚀 一键开发登录** —— 无需任何账号，直接用内置 dev-user 进入。
- **粘贴 Token** —— 直接粘贴已有 access token。

> **认证机制**：账号密码登录走 `POST /api/v1/auth/login`（bcrypt 校验 → 签发 HS256 JWT，`iss=local`）；
> 开发登录走 `/dev/token`（内存 RSA 密钥，RS256）。两种 JWT 都通过同一条
> `get_current_user` 验证管线，下游代码无感知差异。需要真实 Logto/OIDC 登录时见
> [docs/LOGTO_SETUP.md](docs/LOGTO_SETUP.md)。

## 功能模块

### 用户管理（完整 CRUD）

参考 health_admin 实现，与多租户 casbin RBAC 深度集成：

- **用户表**：`username / email / phone / avatar / real_name / status(active|inactive|locked) / 软删除 / 审计字段`
- **分页 + 搜索 + 筛选 + 排序**：`GET /api/v1/users`（search/status/role/sort_by/sort_order/page/limit）
- **统计卡片**：`GET /api/v1/users/statistics`（总数/活跃/锁定/本月新增/近30天登录）
- **完整生命周期**：创建（bcrypt 哈希）/更新/删除（软删除）/改状态/重置密码
- **角色同步**：改角色时实时同步到 casbin，权限立即生效
- **审计日志**：每次增删改写入 `system_logs`（含 before/after 快照）

### 配套数据模型（对齐 health_admin）

| 表 | 用途 |
|----|------|
| `users` | 扩展为完整用户档案（含密码、状态、软删除、审计） |
| `roles` / `permissions` / `role_permissions` | RBAC 显示层（casbin 之上） |
| `organizations` / `user_organizations` | 组织架构树 + 用户多组织 |
| `user_sessions` | 登录会话（设备/IP/过期），支持「活跃会话」管理 |
| `user_login_methods` | 多种登录方式（email/phone/wechat/oauth） |
| `system_logs` | 操作审计日志 |

## 测试

```bash
pytest                        # 全部测试（SQLite 内存库，无需外部服务）
pytest --cov=app              # 带覆盖率
```

测试矩阵（44 passed）：认证（缺/错 token、/me、**账号密码登录成功/失败/锁定/邮箱登录/token 往返**、会话/注销）· Agent CRUD · **多租户隔离**（跨租户不可见、无权限拒绝、member 不能删除）· **用户 CRUD**（分页/搜索/筛选/排序、创建/更新/删除/改状态/重置密码/统计/重复校验）· **角色 CRUD**（创建/列表/重复校验/系统角色保护）· **组织树 CRUD**（父子/重父级/删除）· 租户成员 CRUD · Chat（SSE 流式、消息持久化、跨租户 Agent 拒绝）。

## 主要 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/health` | 健康检查 | 公开 |
| POST | `/dev/bootstrap` | 创建开发租户+用户（仅 dev） | 公开 |
| POST | `/dev/token` | 签发开发 JWT（仅 dev） | 公开 |
| GET | `/oidc/jwks` | 开发模式 JWKS（仅 dev） | 公开 |
| **POST** | **`/api/v1/auth/login`** | **账号密码登录 → access_token** | **公开** |
| GET | `/api/v1/auth/me` | 当前用户 + 租户 + 角色 | 已认证 |
| GET | `/api/v1/auth/sessions` | 当前用户活跃会话列表 | 已认证 |
| POST | `/api/v1/auth/logout` | 注销当前会话 | 已认证 |
| POST | `/api/v1/tenants/` | 创建租户（自动 seed 权限 + 角色） | 已认证 |
| GET/POST | `/api/v1/agents/` | Agent 列表 / 创建 | agents:read / agents:create |
| GET/PATCH/DELETE | `/api/v1/agents/{id}` | Agent 详情 / 改 / 删 | read / update / delete |
| **GET** | **`/api/v1/users/`** | **用户列表（分页/搜索/筛选/排序）** | **users:read** |
| **GET** | **`/api/v1/users/statistics`** | **用户统计** | **users:read** |
| **GET/POST** | **`/api/v1/users/{id}`** | **用户详情 / 创建 / 改 / 删** | **users:*** |
| **PATCH** | **`/api/v1/users/{id}/status`** | **改用户状态** | **users:update** |
| **POST** | **`/api/v1/users/{id}/reset-password`** | **重置密码** | **users:update** |
| GET/POST | `/api/v1/tenants/me/members/` | 租户成员列表 / 添加成员 | users:read / create |
| GET/POST | `/api/v1/roles/` | 角色列表 / 创建 | roles:read / create |
| GET | `/api/v1/roles/label` | 角色下拉选项 | roles:read |
| GET | `/api/v1/organizations/tree` | 组织架构树 | organizations:read |
| POST | `/api/v1/chat/stream` | SSE 流式对话 | conversations:chat |

## 依赖致谢

本项目使用但不包含以下开源项目的源码（通过 pip 引入，各自保留其许可证）：
- [PyCasbin](https://github.com/casbin/pycasbin) — Apache 2.0
- [FastAPI](https://github.com/tiangolo/fastapi) — MIT
- [LangGraph](https://github.com/langchain-ai/langgraph) — MIT
- [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) — MIT

## 后续阶段（Phase 2+）

- [ ] RAG / 向量检索（pgvector）
- [ ] Agent 持久化记忆（Postgres Checkpointer 替换 MemorySaver）
- [ ] 多工具编排（文件解析、代码执行等）
- [ ] 前端 Next.js（Phase 3）
- [ ] 计费、配额、审计日志
- [ ] 生产部署（Docker/K8s）
