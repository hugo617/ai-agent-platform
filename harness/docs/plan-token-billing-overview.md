# 计划:Token 费用管理总纲(预付钱包制商业闭环)

> 这是 **Token 费用管理系列的总纲文档**(非可执行任务本身)。
> 具体实施拆成 4 个 WIP=1 子任务,见下方「子任务清单」。
> 对应 feature_list.json 的 `id`: `token-usage-tracking` / `token-wallet-billing` / `token-billing-ui` / `customer-conversation-link`

---

## 背景:为什么要做 Token 费用管理

### 用户需求(2026-07-12 Session 060 提出)

> 「我有想到一个 token 费用管理,这个主要是与门店关联,门店向总部购买 token,这个 token 可以用于门店和门店的客户。」

这是平台从「能跑」到「能卖」的关键拼图——把 AI 能力变成可计费、可分配、可追溯的商业资源。

### 现状缺口(全量代码排查确认)

平台有成熟的组织地基(Group 总部 → Tenant 门店 → Customer 客户),但**整条商业闭环完全缺失**:

| 环节 | 现状 | 后果 |
|---|---|---|
| 用量采集 | `stream_agent` 流式循环只 yield 文本,**丢弃 `chunk.usage_metadata`** | 对话完不知道用了多少 token |
| Message 表 | 只有 role+content,**无 token 列、无 model 名、无 cost** | 无法回溯任何一次消耗 |
| 定价 | `LlmConfig` 只存连接信息(api_key/base_url/model),**无单价字段** | 无法算钱 |
| 余额/额度 | 全项目搜 `quota/credit/balance/wallet` **零命中** | 门店用超了也没有拦截 |
| 购买流程 | 无 RechargeOrder / 转账模型 | 表达不了「门店向总部购买」 |
| 客户↔对话 | Conversation 只绑 (tenant, agent, user),**不绑 Customer** | 无法做客户维度 token 归因 |

**好消息**:组织地基已经完备,token 费用管理不是空中楼阁。`Group(总部) → GroupTenant → Tenant(门店) → CustomerProfile → Customer` 这条链正是「总部卖 token 给门店、门店的 AI 服务门店客户」的天然载体。

---

## 用户拍板的方案(2026-07-12,4 个决策)

| 决策点 | 用户选择 | 理由 |
|---|---|---|
| 计费模式 | **预付钱包制** | 门店先买 token 存余额,对话实时扣减,余额为 0 拒绝对话。现金流好、可控、实现简单 |
| 定价基准 | **模型真实 token + 单价表** | 每个模型有 input/output 单价,总部可加价卖给门店。透明可对账 |
| 采购支付 | **纯额度划拨**(不接支付) | 总部在系统里给门店充值(线下转账后录入),系统只管 token 额度流转。MVP 务实 |
| 客户归因 | **做**(Conversation 绑 customer_id) | 门店能看到「服务张先生本月用了多少 token」,商业价值高 |

---

## 商业模型:额度流转图

```
总部(Group/HQ)                    门店(Tenant)                     客户(Customer)
    │                                  │                                │
    │  ① 充值/采购                       │                                │
    │  (super_admin 给门店划拨额度)       │                                │
    │  ─────────────────────────────▶  │ 门店 Wallet 余额 += N           │
    │  WalletTransaction(recharge)      │                                │
    │                                   │  ② AI 对话消耗                  │
    │                                   │  (门店员工用 Agent 服务客户)    │
    │                                   │  读真实 usage_metadata          │
    │                                   │  Wallet 余额 -= 实际 token ────▶│ 客户被服务
    │                                   │  UsageEvent 记流水              │
    │                                   │  Message 记 token+model         │
    │  ③ 总部看板                        │                                │
    │  (各门店余额/消耗/采购汇总) ◀──────│                                │
    │                                   │                                │
    │  ④ 定价维护                        │                                │
    │  (ModelPricing 单价表 + 加价)      │                                │
```

四条主线:
1. **充值**:总部(super_admin)给门店划拨 token 额度 → WalletTransaction(recharge)
2. **消耗**:门店对话时读真实 usage_metadata → 按单价算 cost → 扣减 Wallet 余额 → 记 UsageEvent 流水
3. **看板**:门店看自己的余额/消耗;总部看所有门店的汇总
4. **定价**:总部维护 ModelPricing 单价表(每个模型的 input/output 单价),可加价

---

## 数据模型设计

### 新增 3 张表

#### 1. `wallets`(门店钱包,一门店一钱包)

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(32) PK | uuid hex |
| tenant_id | FK→tenants.id | **唯一**(一门店一钱包,部分唯一索引 is_deleted=false) |
| balance | Integer | 当前余额(token 数,整数避免浮点) |
| total_recharged | Integer | 累计充值(统计用) |
| total_consumed | Integer | 累计消耗(统计用) |
| low_balance_threshold | Integer | 预警阈值(默认余额 10%) |
| is_active / is_deleted / deleted_at | 标准字段 | 软删除惯例 |
| created_at / updated_at | 时间戳 | |

> 用整数 token 数做余额,不用金额——定价变化时余额不变,只在扣减时按当时单价算 cost。

#### 2. `wallet_transactions`(钱包流水,追加式账本)

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(32) PK | |
| wallet_id | FK→wallets.id | |
| tenant_id | String(32) | 冗余,便于租户过滤 |
| type | String(20) | `recharge`(充值)/`consume`(消耗)/`refund`(退款)/`adjust`(调整) |
| amount | Integer | 变动额(正数充值,负数消耗) |
| balance_after | Integer | 变动后余额(快照,便于审计) |
| usage_event_id | FK→usage_events.id | 可空(消耗型流水关联到具体用量事件) |
| model | String(64) | 可空(消耗型记录是哪个模型) |
| remark | String(255) | 备注(如「总部充值 2026-07」) |
| operator_id | FK→users.id | 操作人(谁充的值/谁触发的消耗) |
| created_at | 时间戳 | |

#### 3. `usage_events`(用量事件,每次对话一条,追加式)

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(32) PK | |
| tenant_id | String(32) | 租户过滤 |
| conversation_id | FK→conversations.id | |
| message_id | FK→messages.id | |
| customer_id | FK→customers.id | **可空**(客户归因,任务 4 填) |
| agent_id | FK→agents.id | |
| user_id | String(128) | 触发用户 |
| model | String(64) | 实际服务的模型(解析后,非 agent.model) |
| prompt_tokens | Integer | 输入 token |
| completion_tokens | Integer | 输出 token |
| total_tokens | Integer | 合计 |
| cost | Numeric(12,6) | 按当时单价算的成本快照 |
| created_at | 时间戳 | |

### 现有表改造

#### 4. `messages` 加列(向后兼容,均可空)

`prompt_tokens` / `completion_tokens` / `total_tokens` / `model`(可空 Integer/String)

#### 5. `model_pricing`(定价表,平台级 + 可选租户覆盖)

| 字段 | 类型 | 说明 |
|---|---|---|
| id | String(32) PK | |
| tenant_id | FK→tenants.id | **可空**(NULL=平台默认,非空=租户覆盖) |
| model | String(64) | 模型名(如 deepseek-chat) |
| input_price_per_1k | Numeric(10,6) | 输入单价(每千 token) |
| output_price_per_1k | Numeric(10,6) | 输出单价 |
| currency | String(8) | 币种(CNY/USD,默认 CNY) |
| is_active | Boolean | |
| created_at / updated_at | | |

#### 6. `conversations` 加列(任务 4 客户归因)

`customer_id` FK→customers.id(**可空**,向后兼容)

---

## 三层职责边界(重要)

```
┌──────────────────────────────────────────────────┐
│  第三层(远期,不做)                                │
│  接支付网关、订阅套餐、对公账单、发票               │
├──────────────────────────────────────────────────┤
│  第二层(增强)                                      │
│  成本分析、用量预警通知、客户 360 token 维度         │
├──────────────────────────────────────────────────┤
│  第一层(MVP 核心,本系列做)                        │
│  ① 用量采集(读真实 usage_metadata)               │
│  ② 钱包余额(门店级预付额度)                       │
│  ③ 消耗扣减(对话实时扣 + 余额不足拦截)            │
│  ④ 充值流程(总部给门店划拨额度 + 流水)            │
│  ⑤ 定价表(模型单价 + 总部加价)                    │
│  ⑥ 客户归因(Conversation 绑 customer_id)         │
│  ⑦ 用量看板(门店/总部两级)                        │
└──────────────────────────────────────────────────┘
```

---

## 子任务清单(WIP=1 顺序执行)

| 顺序 | id | priority | 范围 | 前置 | plan 文档 |
|------|----|----------|------|------|----------|
| 1 | `token-usage-tracking` | 43 | 用量采集:读 usage_metadata + Message 加列 + UsageEvent 表 | 无 | `plan-token-usage-tracking.md` |
| 2 | `token-wallet-billing` | 44 | 钱包计费:Wallet + WalletTransaction + ModelPricing + 扣减/充值/拦截 | 1 | `plan-token-wallet-billing.md` |
| 3 | `customer-conversation-link` | 45 | 客户归因:Conversation 绑 customer_id + 客户 360 token 维度 | 1 | `plan-customer-conversation-link.md` |
| 4 | `token-billing-ui` | 46 | 前端看板:门店/总部两级 + 充值操作 + 用量明细 | 1,2,3 | `plan-token-billing-ui.md` |

> 依赖关系:任务 1(用量采集)是地基;任务 2(钱包)和任务 3(客户归因)都依赖 1,但 WIP=1 仍顺序执行;任务 4(前端)依赖前三者。
> 执行顺序:**1 → 2 → 3 → 4**(后端先、前端后,遵循项目惯例)。

---

## 关键实现细节(已精确到行)

| 改动点 | 文件:位置 | 说明 |
|---|---|---|
| 用量采集插入 | `app/agents/graph.py` L172-177 事件循环 | 加 `on_chat_model_end` 分支累积 usage_metadata |
| 流式 usage 开关 | `app/agents/graph.py` L81-87 `_build_llm_kwargs` | 加 `stream_usage: True`(DeepSeek 流式末尾才返回 usage) |
| 用量消费 | `app/api/v1/chat.py` L107-122 event_source | 消费 stream_agent 的 usage,传给 append_message |
| 实际服务 model | `app/api/v1/chat.py` L102-106 | 记录解析后的 `model` 变量(非 agent.model,可能 fallback) |
| append_message 扩展 | `app/services/conversation_service.py` L92-109 | 加可选参数接收 token 数据 |
| 扣减事务 | `conversation_service.append_message` L108 commit 前 | 插入 wallet 扣减,用 `with_for_update()` 锁行防并发双扣(PG 生效,SQLite no-op) |
| 余额预检 | `app/api/v1/chat.py` event_source 开头 | 余额不足返回 402 Payment Required |
| wallet 初始化 | `app/services/tenant_service.py` L65-67 之间 | create_tenant 同事务初始化零余额钱包 |
| 新模型注册 | `alembic/env.py` L18-28 import 列表 | 加 wallet/usage_event/model_pricing 模块 |

---

## 不做的事(系列边界)

- **不接在线支付网关**(纯额度划拨,支付留后期)
- **不做订阅套餐/月度配额自动发放**(纯手动充值)
- **不做对公账单/发票**
- **不做 token 退款**(消耗即扣除,充值可冲正但不撤单笔消耗)
- **不做实时计费中间件**(扣减在对话同事务,简单可靠)
- **不动 stream_agent 的 ReAct 工具链**(只加 usage 采集,不改工具调用逻辑)
- **不做多币种汇率**(定价表有 currency 字段但 MVP 只用 CNY)

---

## 参考文件(系列实施时对照)

| 参照 | 路径 |
|------|------|
| 对话流式入口 | `app/api/v1/chat.py` `event_source` |
| Agent 流式实现 | `app/agents/graph.py` `stream_agent` |
| 会话持久化 | `app/services/conversation_service.py` `append_message` |
| Message 模型(待加列) | `app/models/message.py` |
| Conversation 模型(待加 customer_id) | `app/models/agent.py` |
| LLM 配置(待加 pricing) | `app/models/llm_config.py` + `app/services/llm_config_service.py` |
| 租户创建(待加 wallet 初始化) | `app/services/tenant_service.py` `create_tenant` |
| Repository 基类模式 | `app/repositories/base.py` `TenantScopedRepository` |
| 客户双层模型(归因参照) | `app/models/customer.py` |
| 迁移注册点 | `alembic/env.py` L18-28 |
| 多租户隔离文档 | `项目指南/02-后端架构/04-多租户隔离.md` |

## 行业实践参考

- [RBAC + 计费 SaaS 设计 — WorkOS](https://workos.com/blog/rbac-best-practices)
- [Token / Credit 计费模式(预付 vs 后付)— Stripe Billing 文档](https://stripe.com/docs/billing)
- [用量计费数据模型(ledger/usage event)— AWS Marketplace 计费模型](https://docs.aws.amazon.com/marketplace/)
