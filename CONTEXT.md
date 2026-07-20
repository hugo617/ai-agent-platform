# ai-agent-platform

多租户 AI 智能体 SaaS 平台 —— 可作为新 SaaS 产品的脚手架。本文档是本项目的**领域词汇表**(glossary),只录项目特有的业务概念,不录通用编程概念(JWT / RBAC / SSE / ORM / Pydantic 等协议/库不在此列,见 `项目指南/附录/术语表.md`)。

> 性质:纯 glossary,无实现细节。架构决策见 `docs/adr/`(lazy 创建),任务级规则见 `harness/docs/task-workflow.md`。

## 租户与身份

**Tenant**:
一个独立的客户组织。多租户系统的顶层隔离边界,所有业务数据按 `tenant_id` 隔离。
_Avoid_: organization(已废弃,见 org-cleanup), client, workspace

**User**:
租户内的一个账号。每个 User 属于一个 Tenant,有一个或多个 Role。
_Avoid_: account, member(Member 是 User 在 Group 内的角色概念,不是 User 本身)

**Role**:
权限的载体。User 通过 Role 继承 Permission。每个 Tenant 默认 seed 三个 Role:owner / admin / member。
_Avoid_: profile, group(Group 是业务实体,不是 Role)

**Permission**:
一个 (object, action) 二元组,如 `(users, read)`。Casbin 策略 `(role, obj, act)` 授权给 Role。
_Avoid_: capability, grant

**Platform Role**(super_admin / hq_staff):
**跨租户**的全局身份,不绑定单个 Tenant。super_admin 跨租户写,hq_staff 跨租户只读。
_Avoid_: global role, system role

## AI 智能体与对话

**Agent**:
一个可配置的 AI 智能体(system_prompt + model + tools + 推理参数),由 LangGraph ReAct / Supervisor 编排,绑定到 Tenant。
_Avoid_: bot, assistant, character

**Conversation**:
用户与 Agent 的一次会话,含多条 Message。可关联到 Customer(用于 Token 归因)。
_Avoid_: session(UserSession 是登录会话,不是对话), chat, thread

**Message**:
Conversation 内的一条消息(user / assistant / tool 角色),含 token usage 统计。
_Avoid_: entry, turn

**Orchestration**:
多 Agent 编排模式(Supervisor 路由 + agent_specialists 关联)。区别于单 Agent 的 ReAct 模式。
_Avoid_: workflow, pipeline

**Knowledge Base**:
租户内的文档库,用于 RAG 语义检索。文档 chunk 后用 embedding(本地 Ollama bge-m3,1024 维)写入 pgvector。
_Avoid_: corpus, document store

## 业务实体(大健康连锁演示场景)

**Customer**:
一个终端客户。**全局身份**(跨租户复用,通过手机号去重),在每个 Tenant 有独立的 CustomerProfile。
_Avoid_: patient(本项目演示场景是大健康连锁,但不固化医疗语义), contact

**CustomerProfile**:
Customer 在某个门店(Tenant)的档案,含 4 态状态(active / vip / inactive / blacklist)。受 Role.data_scope 控制。
_Avoid_: record, file

**Group**:
门店的**组织分组**(如「华东大区」「朝阳区门店」),用于层级管理。多对多挂载 Tenant。
_Avoid_: team, department

**Data Scope**:
Role 的数据可见范围(all / tenant / group / self 四档)。CustomerProfile 查询时按 DataScopeService 收敛。
_Avoid_: permission(Permission 是操作权限,DataScope 是数据范围), filter

## Token 计费

**Wallet**:
每个 Tenant 一个钱包,余额预检(余额 ≤0 拦截对话)。充值 / 消费记到 WalletTransaction。
_Avoid_: balance, credit

**WalletTransaction**:
钱包流水(充值 / 消费),双向账户。
_Avoid_: ledger entry, payment

**UsageEvent**:
一次 LLM 调用的 token 账本(prompt / completion / total / model)。可按 Customer 维度归因。
_Avoid_: usage record, token log

**ModelPricing**:
每个 model 的单价(prompt / completion per 1k tokens)。BillingService 算费用时用,租户可覆盖平台默认。
_Avoid_: rate, price

## API Token(AtoA 服务)

**API Token**:
外部 Agent 调用本平台的凭证(`ahp_` 前缀)。绑定颁发者的 Tenant + Role + scopes。
_Avoid_: PAT, access token, api key

**Token Scope**:
细粒度权限收敛。`restricted` 模式按 scopes 列表,`full` 模式继承颁发者全部权限。
_Avoid_: permission(Permission 是 RBAC,Scope 是 Token 上的收敛)

**Token Context**:
`token_context.py` 里的 contextvar,跨 StreamingResponse 子任务传播 Token scope,让 graph.py 工具内 check 拿到 scope。
_Avoid_: session context

## 工程概念(项目特有部分)

**Soft Delete**:
删除时不真删,打 `is_deleted=True` 标记 + 部分唯一索引。查询自动过滤。
_Avoid_: logical delete, trash

**Four-Layer Architecture**:
后端强制的依赖方向 Controller → Service → Repository → Model。**反向 = 技术债**。
_Avoid_: MVC, three-tier

**Tenant-Scoped Repository**:
`TenantScopedRepository` 基类,自动给查询加 `WHERE tenant_id=?`。多租户隔离的**唯一**强制点。
_Avoid_: multi-tenant filter, tenant guard

## 范围外(明确不录)

以下概念虽在项目内使用,但属于**通用编程/协议概念**,不在本 glossary:
JWT / RBAC / OIDC / SSE / ORM / Pydantic / FastAPI / SQLAlchemy / LangGraph / pgvector / bcrypt / Casbin / ReAct / SaaS / DTO / MVP / CORS / venv —— 见 `项目指南/附录/术语表.md`。
