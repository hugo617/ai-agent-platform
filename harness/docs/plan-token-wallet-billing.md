# 计划:Token 钱包计费(预付钱包 + 扣减 + 充值 + 拦截)(Token 费用管理系列 2/4)

> 对应 feature_list.json 的 `id`: `token-wallet-billing`
> 状态: not_started
> 优先级: 44
> 前置: `token-usage-tracking`(用量采集就绪,UsageEvent 表有 token 数据)
> 系列总纲: [`plan-token-billing-overview.md`](plan-token-billing-overview.md)

---

## 背景:有用量但没计费

### 现状(前置任务 1 完成后)

任务 1 让系统「知道用了多少 token」(UsageEvent 表有数据)。但:
- 没有「余额」概念 —— 门店用超了也没有任何拦截
- 没有「充值」流程 —— 表达不了「门店向总部购买 token」
- 没有「定价」—— 无法把 token 换算成钱

### 目标(用户决策:预付钱包制 + 模型真实 token 定价 + 纯额度划拨)

1. **Wallet 表**:一门店一钱包,记录余额(整数 token 数)
2. **WalletTransaction 流水**:充值/消耗/调整的追加式账本
3. **ModelPricing 定价表**:每个模型的 input/output 单价(平台级 + 租户覆盖)
4. **BillingService**:扣减(charge,SELECT FOR UPDATE 防并发双扣)、充值(recharge)、定价计算(calc_cost)
5. **对话拦截**:event_source 开头查余额,不足返回 402;成功后在同事务扣减
6. **wallet 初始化**:create_tenant 末尾同事务建零余额钱包
7. **权限**:新增 wallet:read/wallet:recharge/billing:read/pricing:manage

### 关键设计决策

1. **余额用整数 token 数,不用金额**:定价变化时余额不变,只在扣减时按当时单价算 cost 快照。避免「改了单价,历史余额含义变了」。
2. **扣减用 SELECT FOR UPDATE**:`with_for_update()` 锁 wallet 行,防止同门店并发对话双扣(PG 生效,SQLite no-op 但测试够用)。
3. **扣减在 append_message 同事务**:对话成功 → 扣减 → commit,原子性保证(要么都成功要么都回滚)。
4. **定价快照**:扣减时按当时 ModelPricing 算 cost,写进 UsageEvent.cost 和 WalletTransaction(不依赖未来单价)。

---

## 前置条件

- `token-usage-tracking` 完成(UsageEvent 表有 token 数据,append_message 能接收 usage)

---

## 实施步骤

### 第一阶段:数据模型

#### Step 1:Wallet 模型 + 迁移

- **新建**(`app/models/wallet.py`):
  ```python
  class Wallet(Base):
      __tablename__ = "wallets"
      __table_args__ = (
          # 一门店一钱包(部分唯一索引,软删除惯例)
          Index("uq_wallets_tenant_active", "tenant_id", unique=True,
                postgresql_where=text("is_deleted = false"),
                sqlite_where=text("is_deleted = 0")),
      )
      id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
      tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"))
      balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # token 数
      total_recharged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      total_consumed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      low_balance_threshold: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
      is_active: Mapped[bool] = mapped_column(Boolean, default=True)
      is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
      deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
      created_at / updated_at
  ```
- **新建** `WalletTransaction`:
  ```python
  class WalletTransaction(Base):
      __tablename__ = "wallet_transactions"
      id, wallet_id (FK), tenant_id, type (recharge/consume/refund/adjust),
      amount (Integer, 正充值负消耗), balance_after (Integer), usage_event_id (FK nullable),
      model (String nullable), remark (String), operator_id (FK users),
      created_at
  ```
- **注册**(`alembic/env.py` import 加 `wallet`)
- **迁移**:`alembic revision --autogenerate`
- **检查**:`alembic upgrade head && alembic check`

#### Step 2:ModelPricing 模型 + 迁移

- **新建**(`app/models/model_pricing.py`):
  ```python
  class ModelPricing(Base):
      __tablename__ = "model_pricing"
      __table_args__ = (
          UniqueConstraint("tenant_id", "model", name="uq_pricing_tenant_model"),  # tenant_id 可空时需部分索引
      )
      id, tenant_id (FK nullable, NULL=平台默认), model (String),
      input_price_per_1k (Numeric(10,6)), output_price_per_1k (Numeric(10,6)),
      currency (String(8), default "CNY"), is_active (Boolean),
      created_at, updated_at
  ```
  - tenant_id 可空:NULL = 平台默认定价;非空 = 租户覆盖(总部给特定门店加价)
- **注册** + **迁移**
- **检查**:同上

### 第二阶段:Service 层(核心)

#### Step 3:BillingService —— 扣减/充值/定价

- **新建**(`app/services/billing_service.py`):
  ```python
  class BillingService:
      async def get_wallet(self, tenant_id) -> Wallet | None
      async def has_balance(self, tenant_id) -> bool          # 余额 > 0
      async def calc_cost(self, model, prompt_tokens, completion_tokens, tenant_id) -> Decimal
          # 查 ModelPricing(租户覆盖 > 平台默认);算 (prompt/1000*in_price + completion/1000*out_price)
      async def charge(self, tenant_id, usage_event, db) -> WalletTransaction
          # SELECT wallet FOR UPDATE; 算 cost; balance -= total_tokens; total_consumed += total_tokens;
          # 写 WalletTransaction(consume, balance_after); 更新 usage_event.cost; commit
      async def recharge(self, tenant_id, amount, operator_id, remark, db) -> WalletTransaction
          # super_admin 调用; balance += amount; total_recharged += amount; 写 WalletTransaction(recharge)
  ```
- **并发防双扣**:`charge` 用 `select(Wallet).where(...).with_for_update()`(PG 行锁;SQLite no-op 但单线程测试够用)
- **定价解析**:`calc_cost` 先查 `tenant_id=X AND model=Y`(租户覆盖),无则查 `tenant_id IS NULL AND model=Y`(平台默认),无则返回 0(免费/未配置,允许对话但记 cost=0)
- **检查**:单元测试 charge 原子性、recharge 流水、calc_cost 覆盖优先级

#### Step 4:WalletRepository

- **新建**(`app/repositories/wallet.py`):
  ```python
  class WalletRepository(TenantScopedRepository[Wallet]):
      model = Wallet
      async def get_for_tenant_for_update(self, tenant_id) -> Wallet | None:
          # SELECT ... FOR UPDATE
          stmt = select(Wallet).where(Wallet.tenant_id == tenant_id, Wallet.is_deleted == False).with_for_update()
          ...
  ```
- **检查**:Repository 只做数据访问,业务逻辑在 Service

### 第三阶段:对话集成

#### Step 5:event_source 余额预检 + 扣减

- **改什么**(`app/api/v1/chat.py` event_source):
  ```python
  # 余额预检(对话前)
  wallet = await billing_service.get_wallet(user.tenant_id)
  if wallet and not await billing_service.has_balance(user.tenant_id):
      yield f"data: {json.dumps({'error': 'token 余额不足,请联系总部充值'}, ensure_ascii=False)}\n\n"
      return
  ...
  # 对话成功后,在 append_message 之后扣减(同事务)
  if usage_data:
      usage_event = await usage_service.create_event(...)  # 任务1的 UsageEvent
      await billing_service.charge(user.tenant_id, usage_event, db)
  ```
- **余额不足语义**:返回 SSE error 事件(前端显示「余额不足」),不用 HTTP 402(SSE 已开始流,改 HTTP 状态码不友好;用 error 事件)
- **注意**:扣减失败(如并发冲突)的处理 —— 记日志 + 放行(宁可少扣不可阻断已完成的对话,差异靠对账补)
- **检查**:余额为 0 时对话被拦截;有余额时对话后余额减少

#### Step 6:create_tenant 初始化 wallet

- **改什么**(`app/services/tenant_service.py` L65-67 `create_tenant`,在 commit 前加):
  ```python
  # 6. 初始化门店钱包(零余额,同事务)
  wallet = Wallet(tenant_id=tenant.id)
  await self.db.add(wallet)  # 或调 wallet_service
  ```
- **检查**:新建租户后 wallets 表有对应零余额记录

### 第四阶段:API 端点 + 权限

#### Step 7:Wallet / Pricing 端点

- **新建**(`app/api/v1/billing.py`):
  - `GET /billing/wallet` —— 查当前租户钱包余额(`wallet:read`)
  - `GET /billing/wallet/{tenant_id}` —— super_admin 查指定门店钱包(`require_super_admin`)
  - `GET /billing/transactions` —— 当前租户流水(`wallet:read`)
  - `POST /billing/recharge` —— super_admin 给门店充值(`require_super_admin` + body: tenant_id, amount, remark)
  - `GET /billing/usage` —— 用量明细查询(`billing:read`,支持按 customer/agent/时间段过滤)
  - `GET /billing/pricing` —— 查定价表(`billing:read`)
  - `POST/PUT/DELETE /billing/pricing` —— 维护定价(`require_super_admin`)
- **路由注册**(`app/main.py`):import billing + include_router
- **权限**:在 `permission_service.py` 的 DEFAULT_*_PERMS 加 `("wallet", "read")`/`("billing", "read")`(owner/admin 持有);`wallet:recharge`/`pricing:manage` 仅 super_admin(平台级,不进租户 seed)
- **检查**:端点权限正确;member 能查自己门店余额但不能充值

### 第五阶段:测试 + 总验证

#### Step 8:补测试

- **新建** `tests/test_billing.py`:
  - **扣减原子性**:charge 后 balance 减少、total_consumed 增加、WalletTransaction 有 consume 记录、UsageEvent.cost 填充
  - **并发双扣**:两个协程同时 charge 同一 wallet → 用 with_for_update 保证不超扣(PG;SQLite 标注 skip)
  - **余额不足拦截**:balance=0 → has_balance False → 对话被拦
  - **充值**:recharge → balance/total_recharged 增加、WalletTransaction 有 recharge 记录
  - **定价计算**:calc_cost 租户覆盖 > 平台默认;未配置模型 cost=0
  - **租户隔离**:门店 A 查不到门店 B 的 wallet/transaction
  - **wallet 初始化**:create_tenant 后有零余额 wallet
- **检查**:`pytest tests/test_billing.py -v` 全过

#### Step 9:总验证

- **命令**:
  ```bash
  ./init.sh
  alembic upgrade head && alembic check
  ```
- **通过标准**:
  - 全绿;对话消耗后 wallet 余额减少;余额为 0 对话被拦;充值生效;定价正确
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. Wallet + WalletTransaction + ModelPricing 三表建立,迁移无 drift
2. BillingService 实现 charge(扣减,FOR UPDATE 防双扣)/recharge(充值)/calc_cost(定价,租户覆盖>平台默认)
3. event_source 余额预检(不足拦截)+ 对话成功后扣减(同事务)
4. create_tenant 初始化零余额 wallet(同事务,原子性)
5. API:wallet 查询/充值/流水/用量/定价 端点,权限正确(wallet:read 门店级;recharge/pricing super_admin)
6. 新增权限项 wallet:read/billing:read(owner/admin),wallet:recharge/pricing:manage(super_admin)
7. `./init.sh` 全绿;并发双扣防护测试通过

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 并发对话双扣 | charge 用 SELECT FOR UPDATE(PG);SQLite no-op 但单线程测试可验证逻辑;生产 PG 行锁生效 |
| 扣减失败阻断对话 | 扣减放 append_message 后,try/except 包裹,失败记日志不阻断(差异靠对账补) |
| 定价表未配置模型 | calc_cost 返回 0(免费/未配置),允许对话,cost 记 0;不阻断业务 |
| with_for_update 在 SQLite 报错 | SQLAlchemy 的 with_for_update 在 SQLite 是 no-op(不报错),测试可跑;PG 生效 |
| 余额用 token 数 vs 金额 | 用整数 token 数;cost 是金额快照(算完写死),余额和 cost 解耦 |
| wallet 初始化失败导致建租户失败 | wallet 创建在 create_tenant 同事务,失败整体回滚(符合原子性) |

### 不做的事(边界)

- 不做前端看板(任务 4 `token-billing-ui`)
- 不做客户归因扣减(UsageEvent.customer_id 留空,任务 3 填)
- 不接支付网关(纯额度划拨)
- 不做退款(消耗即扣除;充值可冲正但不撤单笔消耗)
- 不做预警通知(前端看板显示余额,不做主动通知)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-token-billing-overview.md` |
| 任务 1(前置) | `harness/docs/plan-token-usage-tracking.md` |
| event_source(待改) | `app/api/v1/chat.py` L93-147 |
| create_tenant(待改) | `app/services/tenant_service.py` L27-68 |
| Repository 基类 | `app/repositories/base.py` |
| 客户模型(部分唯一索引参照) | `app/models/customer.py` |
| 权限 seed | `app/services/permission_service.py` `DEFAULT_*_PERMS` |
| 声明式校验 | `app/api/deps.py` `require_permission`/`require_super_admin` |
