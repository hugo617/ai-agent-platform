# 计划:客户维度 Token 归因(Conversation 绑 customer_id)(Token 费用管理系列 3/4)

> 对应 feature_list.json 的 `id`: `customer-conversation-link`
> 状态: not_started
> 优先级: 45
> 前置: `token-usage-tracking`(UsageEvent 表就绪,有 customer_id 可空列)
> 系列总纲: [`plan-token-billing-overview.md`](plan-token-billing-overview.md)

---

## 背景:消耗无法归因到客户

### 现状

Conversation 只绑 `(tenant_id, agent_id, user_id)`,**不绑 Customer**。即使用户在服务某客户时发起对话,系统也不知道「这次对话是服务张先生的」。

后果:
- 无法回答「服务张先生这个月用了多少 token」
- 客户 360 视图缺「AI 服务」维度
- 总部无法做「哪个客户最耗费 AI 资源」的分析

前置任务 1 的 UsageEvent 表已预留 `customer_id` 可空列,本任务填上它。

### 目标(用户决策:做客户归因)

1. Conversation 加 `customer_id`(可空 FK→customers.id,向后兼容)
2. 发起对话时可选关联客户(门店员工服务某客户时选「为张先生咨询」)
3. UsageEvent.customer_id 从 Conversation 透传 → 聚合出客户维度用量
4. 客户 360 卡片加「AI 服务」维度(对话次数 + token 消耗 + 最近活跃)

### 关键设计

1. **customer_id 可空**:不是所有对话都关联客户(员工可能自己内部咨询)。可空 = 向后兼容。
2. **对话级关联,非消息级**:一个对话关联一个客户(不在每条消息上配)。简单够用。
3. **前端入口**:聊天页发起对话时,加「关联客户」下拉(可选);或在客户详情页「为客户咨询」按钮直达带 customer_id 的新对话。
4. **跨店归因**:Customer 是全局身份(identity_key),同一个人在不同门店的对话,token 可按 Customer 全局汇总(总部视角)或按 CustomerProfile 分店(门店视角)。

---

## 前置条件

- `token-usage-tracking` 完成(UsageEvent 有 customer_id 可空列)
- `customers-api` 完成(Customer/CustomerProfile 模型 + 查询)✅

---

## 实施步骤

### 第一阶段:模型 + 迁移

#### Step 1:Conversation 加 customer_id

- **改什么**(`app/models/agent.py` Conversation 模型,加 1 列):
  ```python
  customer_id: Mapped[str | None] = mapped_column(
      String(32), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
  )
  ```
  - 可空 + SET NULL:客户被删时对话不级联删,只置 NULL(历史对话保留)
- **迁移**:`alembic revision --autogenerate`(加列)
- **检查**:`alembic upgrade head && alembic check`;旧对话 customer_id = NULL(正确)

#### Step 2:UsageEvent.customer_id 透传

- **改什么**(任务 1 建的 UsageEvent 已有 customer_id 列,本步骤确保**填充逻辑**):
  - 创建 UsageEvent 时,从 Conversation 取 customer_id 透传
  - `usage_service.create_event(...)` 加参数 `customer_id`(从 conv.customer_id 取)
- **检查**:关联客户的对话,UsageEvent.customer_id 有值

### 第二阶段:后端 API

#### Step 3:对话创建/查询支持 customer_id

- **改什么**(`app/schemas/conversation.py`):
  - `ConversationCreate` 加 `customer_id: str | None = None`
  - `ConversationRead` 加 `customer_id: str | None`
- **改什么**(`app/api/v1/conversations.py`):
  - 创建对话端点接受 customer_id(可选)
  - 列表端点支持 `?customer_id=xxx` 过滤(查某客户的全部对话)
- **检查**:带 customer_id 创建对话 → 查回来 customer_id 有值

#### Step 4:客户维度用量聚合端点

- **改什么**(`app/api/v1/billing.py` 或 `customers.py`):
  - `GET /customers/{id}/usage` —— 某客户的 token 用量汇总(对话次数 + 总 token + 总 cost + 最近活跃时间)
  - 聚合查询:`SELECT COUNT(*), SUM(total_tokens), SUM(cost), MAX(created_at) FROM usage_events WHERE customer_id=? [AND tenant_id=?]`
  - 门店视角加 tenant_id 过滤(只看本店服务的);总部视角不加(super_admin/hq_staff 看全局)
- **检查**:有归因对话的客户查到用量;无归因的用量为 0

### 第三阶段:前端

#### Step 5:聊天页加「关联客户」

- **改什么**(`frontend/src/pages/chat-page.tsx`):
  - 新建对话时,加「关联客户(可选)」下拉 —— 复用 `useCustomers()`(门店客户列表)
  - 对话标题区显示关联的客户名(若有),如「💬 健康咨询 · 张先生」
  - 创建对话调 `createConversation({agent_id, customer_id})`
- **改什么**(`frontend/src/api/endpoints.ts` + `types.ts`):
  - `createConversation` 接受 customer_id
  - `Conversation` 类型加 customer_id
- **检查**:聊天页能选客户关联;对话区显示客户名

#### Step 6:客户详情页加「AI 服务」维度

- **改什么**(`frontend/src/pages/customers-page.tsx` 客户详情卡片):
  - 加「AI 服务」区块:本月对话次数 / token 消耗 / 最近 AI 咨询时间
  - 调 `GET /customers/{id}/usage` 或 `useCustomerUsage(id)`
  - 加「为客户咨询」按钮 → 跳转聊天页,预填该客户
- **检查**:客户详情显示 AI 服务数据;按钮跳转到带 customer_id 的新对话

### 第四阶段:测试 + 总验证

#### Step 7:补测试

- **后端**(`tests/test_customer_conversation.py`):
  - 创建带 customer_id 的对话 → 查回有值
  - UsageEvent.customer_id 从 Conversation 透传
  - 客户用量聚合:关联 2 次对话 → 汇总 token 正确
  - 跨店:同客户在 2 门店对话 → 总部视角汇总,门店视角各算各
  - 向后兼容:旧对话 customer_id = NULL 不报错;无归因客户用量为 0
  - 客户删除(软删)→ 对话 customer_id 置 NULL(SET NULL,FK ondelete)
- **前端**:`npm run build`

#### Step 8:总验证

- **命令**:
  ```bash
  ./init.sh
  cd frontend && npm run build
  ```
- **通过标准**:
  - 对话能关联客户;UsageEvent.customer_id 填充;客户 360 显示 AI 服务数据
  - 向后兼容;跨店归因正确
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. Conversation 加 customer_id(可空 FK→customers.id,SET NULL,向后兼容)
2. 创建对话接受可选 customer_id;列表支持按 customer_id 过滤
3. UsageEvent.customer_id 从 Conversation 透传填充
4. `GET /customers/{id}/usage` 聚合(对话次数/token/cost/最近活跃),支持门店/总部双视角
5. 聊天页能关联客户;客户详情显示 AI 服务维度 + 「为客户咨询」入口
6. 向后兼容(旧对话 NULL);跨店归因正确
7. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| customer_id 加列迁移影响大 | 可空 + SET NULL,旧数据 NULL 是正确语义;测试向后兼容 |
| 客户被软删后对话悬空 | FK ondelete=SET NULL,软删用 is_deleted 不触发 FK;需确保软删路径把 conversation.customer_id 置 NULL 或保留(保留更合理,历史可追溯) |
| 聚合查询性能 | usage_events 有 (tenant_id, created_at) 索引(任务1建);加 (customer_id) 索引;客户量级内可接受 |
| 前端关联客户增加操作步骤 | 设为可选;提供「为客户咨询」快捷入口(客户详情直达) |

### 不做的事(边界)

- 不做消息级客户关联(只对话级)
- 不做自动客户识别(对话内容里自动提取客户)——AI 能力,后续
- 不做前端看板(任务 4)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-token-billing-overview.md` |
| Conversation 模型(待改) | `app/models/agent.py` Conversation |
| UsageEvent(任务1建) | `app/models/usage_event.py` |
| 客户模型 | `app/models/customer.py` |
| 对话端点 | `app/api/v1/conversations.py` |
| 聊天页(待改) | `frontend/src/pages/chat-page.tsx` |
| 客户页(待改) | `frontend/src/pages/customers-page.tsx` |
