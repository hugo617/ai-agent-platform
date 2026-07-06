# ai-agent-platform

多租户 AI 智能体 SaaS 平台后端 —— FastAPI + pycasbin + LangGraph。

> Phase 1：后端骨架 + 多租户权限系统 + 最简 LangGraph 智能体（前后端分离，前端在 Phase 3）。

## 技术栈

| 层 | 选型 |
|----|------|
| Web 框架 | FastAPI + Uvicorn |
| ORM / 迁移 | SQLAlchemy 2.0（async）+ Alembic |
| 认证 | Logto（OIDC，FastAPI 只验 JWT）|
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

### 2. 配置 Logto（首次）

1. 打开 Logto 管理台 http://localhost:3002，完成初始化（创建账号）
2. 创建一个 **Traditional Web** 应用，记下 App ID
3. 在 API 设置里创建一个 API resource，identifier 填 `http://localhost:8000/api`
4. 在 Custom JWT 配置里，把用户的 `tenant_id` 加进 access token claims
5. 把 `.env` 里的 `LOGTO_AUDIENCE` 对齐到上面的 identifier

### 3. 安装后端依赖 & 初始化数据库

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head          # 建表
uvicorn app.main:app --reload # 启动后端，访问 http://localhost:8000/docs
```

### 4. 创建第一个租户

通过 `/api/v1/tenants/` 接口（带 Logto 签发的 access token）创建租户，系统会自动 seed 该租户的 owner 角色与默认权限策略。

## 测试

```bash
pytest                        # 全部测试（SQLite 内存库，无需外部服务）
pytest --cov=app              # 带覆盖率
```

测试矩阵：认证（缺/错 token、/me）· Agent CRUD · **多租户隔离**（跨租户不可见、无权限拒绝、member 不能删除）· Chat（SSE 流式、消息持久化、跨租户 Agent 拒绝）。

## 主要 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/health` | 健康检查 | 公开 |
| GET | `/api/v1/auth/me` | 当前用户 + 租户 + 角色 | 已认证 |
| POST | `/api/v1/tenants/` | 创建租户（自动 seed 权限） | 已认证 |
| GET/POST | `/api/v1/agents/` | Agent 列表 / 创建 | agents:read / agents:create |
| GET/PATCH/DELETE | `/api/v1/agents/{id}` | Agent 详情 / 改 / 删 | read / update / delete |
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
