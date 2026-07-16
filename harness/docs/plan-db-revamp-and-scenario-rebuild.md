# 计划:数据库设计修复 + 清空重建大健康连锁场景

> **状态**:已审查 + 已修订(挑刺复核发现 7 处问题,已于 Session 110 修订),待执行
> **创建**:Session 109(2026-07-16)
> **修订**:Session 110(2026-07-16)——按挑刺审查结论修订 S3/S2/L2/M5/§3/L3/§2.3 共 7 处(见文末「§8 修订日志」)
> **决策来源**:Session 109 深度审查 25 张表 + 26 个迁移 + 种子脚本 + 4 轮 AskUserQuestion 对齐
> **前置**:无(独立工作单元,WIP=1)
> **关联**:`progress.md` Session 109/110、`feature_list.json`(执行时登记新任务)

---

## 0. 背景与用户决策(为什么做这件事)

用户诉求原话:"对项目具体的业务场景还是有困惑,需要把所有数据先恢复到空置状态,基于一个业务场景,这个系统真实用户应该有几个人,有哪些数据,哪些配置,给出一个足够让我对外分享的具体说明"。

经 4 轮 AskUserQuestion 对齐,锁定 4 项决策:

| 维度 | 决策 |
|------|------|
| **修复范围** | 全修(3 严重 + 6 中等死字段 + 3 轻微 = 12 项),但 **不加新表** |
| **行业方向** | 保留大健康连锁(颐和堂),优化现有数据让它真实可对外讲 |
| **对话能力** | 用户提供真实 LLM key 进种子(系统启动即可现场聊天演示) |
| **超管预填** | `.env` 驱动 + 登录页默认值(开发/测试环境预填,生产环境不预填) |

**不做的**:不加新表(Agent.tools / 邀请表 / 附件表)——这些是新功能,登记为后续任务;不改 RBAC/认证管线;不改前端 UI 框架。

---

## 1. 数据库设计审查报告(完整发现)

审查范围:`app/models/` 全部 25 张表源码逐字段读过 + `alembic/versions/` 26 个迁移 + `scripts/seed_demo.py`/`init_admin.py` + 交叉验证 `app/schemas/`、`app/services/`、`app/repositories/`、`frontend/src/` 实际读写。

### 1.1 整体健康度:B+

**好的部分**:
- ✅ 迁移链单链无分叉,1 个 head(`a3b4c5d6e7f8`),26 个迁移线性递进
- ✅ 所有 `upgrade()` 无破坏性 drop(只有 downgrade 回滚才 drop),从空库 `alembic upgrade head` 绝对安全
- ✅ 双库兼容到位(JSONB↔JSON、Vector↔JSON、partial unique index 双写 PG/SQLite)
- ✅ SCD2 设计干净(`user_tenants`/`role_permissions` 的时间维度)
- ✅ 软删除+部分唯一索引约定一致

### 1.2 严重问题(影响功能正确性,必修)

#### S1. `Wallet.is_active` 是"假开关"——写了不读,设 False 照样能用
- **字段**:`wallets.is_active`(`app/models/wallet.py:91`)
- **问题**:写入点存在(`app/services/billing_service.py:88`),但**所有查询都不过滤 `is_active`**。已 grep 确认 `Wallet.is_active` 在所有 query 语句中零命中。把钱包设为 inactive 后,对话照扣费、余额照显示。
- **修法**:`app/repositories/wallet.py` 的 `get_for_tenant` + 任何 list 查询加 `.where(Wallet.is_active.is_(True))`,让"停用钱包"真正生效。加测试验证"停用钱包后对话被拦截"。
- **文件**:改 `app/repositories/wallet.py`;测试 `tests/test_billing*.py` 新增 1 个用例。

#### S2. `CustomerProfile.status` 前后端枚举不一致——统计计数只认 active(修订:列表不过滤)
- **字段**:`customer_profiles.status`(`app/models/customer.py:135`)
- **问题(核实后重新定义)**:前端 `frontend/src/pages/customers-page.tsx:89` 定义了 `["active","inactive","vip","blacklist"]` 4 个值并让用户填。**之前的判断"列表把 vip 过滤掉看不见"是误判**——实际核实:
  - 列表查询 `list_for_tenant`(customer.py:155)和 `list_for_scope`(customer.py:288,后者由 `customer_service.py:147` 实际调用)**完全不按 status 过滤**,返回所有 `is_deleted=False` 的 profile(vip/inactive/blacklist 在列表里都看得见)
  - 真正只认 `status == "active"` 的是 **`statistics_for_tenant`(customer.py:110/354)的 active 计数**——它只统计真 active 数,这是合理的(语义本就是"活跃身份计数")
  - 真实的不一致是:**前端让用户填 4 态,但后端无任何业务分支消费 vip/inactive/blacklist 的区分**(列表全显示、统计只数 active、无 vip 专属视图/筛选器),4 态枚举名存实亡
- **修法(修订)**:**不改动 list_for_scope / list_for_tenant 的过滤逻辑**(它们当前行为正确:全显示)。改为:
  1. 在前端 customers-page 增加按 status 的**筛选器**(让 4 态真正可被消费),或
  2. 后端 list 端点支持 `?status=vip` 等可选过滤参数(让前端筛选器有数据支撑),统计计数逻辑保持不变
  - 这样新加的 4 态才不是摆设。**不再按原计划"改 list 为 notin_(inactive,blacklist)"**——那会错误地把 inactive/blacklist 从列表移除,改变现有正确行为。
- **文件**:改 `app/repositories/customer.py`(加可选 status 过滤参数)+ `app/api/v1/customers.py`(透传 query param)+ `frontend/src/pages/customers-page.tsx`(加筛选器);测试 `tests/test_customers_api.py` 新增用例覆盖 4 态过滤行为。
- **注意**:这条从"必修 bug"降级为"体验增强"——不修也不影响功能正确性,4 态只是没被充分利用。执行时优先级可排在 S1/S3 之后。

#### S3. `Agent` 没有软删除——硬删除连对话一起删(后果比预估更严重)
- **问题**:`app/models/agent.py` 无 `is_deleted`,`app/services/agent_service.py:175-187 delete()` 走 `repo.delete(agent)` 硬删除。对比同级的 Customer/Role/Document/Wallet 都软删除。**核实后的真实后果(修订)**:删一个 Agent 触发两类 FK 级联,且方向不同——
  - `Conversation.agent_id`(`agent.py:90`)是 `ondelete="CASCADE"` → **整条对话(含全部历史消息)被级联删除**,而非之前误判的 SET NULL
  - `UsageEvent.agent_id`(`usage_event.py:61`)是 `ondelete="SET NULL"` → 该 Agent 的用量统计行 `agent_id` 置空,统计归因丢失
  - 两类合起来:**删除一个 Agent = 该 Agent 名下的所有历史对话记录彻底消失 + 用量统计无法归因,且不可恢复**。
- **修法**:`app/models/agent.py` 加 `is_deleted: Mapped[bool]` + `deleted_at: Mapped[datetime | None]`(镜像 Customer 模式);`agent_service.delete()` 改软删(`is_deleted=True`);`AgentRepository` 所有查询加 `is_deleted=False` 过滤;新迁移加列(`server_default=text("false")` 免 backfill)。
- **文件**:改 `app/models/agent.py` + `app/services/agent_service.py` + `app/repositories/agent.py`;新迁移;测试 `tests/test_agents_api.py` 验证软删除行为(删除后 Agent 不在列表、对话仍可查、agent_id 仍指向该 Agent)。

### 1.3 中等问题(死字段/死表清理)

| # | 对象 | 位置 | 处理 | 连带改动 |
|---|------|------|------|---------|
| **M1** | `User.info_json`(DB列名 `metadata`) | `app/models/tenant.py:111` | **删列**(零读写,全仓 `info_json` 只在定义处出现) | 无 schema/service/前端引用,纯删 |
| **M2** | `Permission.sort_order`/`status`/`description` | `app/models/rbac.py:97-99` | **删三列**(纯 seed 只读表,查询按 `code` 排序、不过滤 status、不展示 description;`PermissionItem` schema 故意不带这三列) | 检查 `permission_service.py` seed 是否填了这三列,填了则移除赋值 |
| **M3** | `verification_codes` 整表 | `app/models/security.py:97` | **删表 + 删模型**(建了从未启用,整个 `VerificationCode` 在 app/ 中从未实例化,无 SMS 端点,无对应 repository) | 删 `app/models/security.py` 的 `VerificationCode` 类;确认无 import |
| **M4** | `ModelPricing.currency` | `app/models/model_pricing.py:73` | **删列**(MVP 只 CNY,写但不读不过滤不分支;前端 `billing-admin-page.tsx` 把输入框 disabled) | 改 `app/api/v1/billing.py` 创建/更新端点移除 currency 字段;前端表单移除该输入框 |
| **M5** | `Role.status` | `app/models/rbac.py:59` | **删列**(修订:经核实通过 schema 透传且可被 API 写入,但无 query 过滤、无 UI 展示、无业务分支消费,属"名存实亡"字段) | 连带改动比原估略大:`app/services/rbac_service.py:117` update 循环移除 `"status"`;**`app/schemas/rbac.py:20` RoleRead 移除 status 字段**;**`app/schemas/rbac.py:45` RoleUpdate 移除 status 可选字段**;`frontend/src/api/types.ts:138,161` Role/RoleUpdate interface 移除 status;前端 roles-page 无引用(已核实零命中) |
| **M6** | `UserSession.token_hash` | `app/models/security.py:49` | **删列**(写但 token 校验/注销实际走 `session_id` 即 JWT 的 jti,这列悬空) | `app/services/auth_service.py:136` 移除 `token_hash=_sha256(token)` 赋值 |

### 1.4 轻微问题(补齐,不含加表)

#### L1. `User.avatar` 默认值是"死 URL"
- **问题**:`app/models/tenant.py:92` 默认 `/avatars/default.jpg`,但后端 `app/api/v1/uploads.py` 没挂载 `/avatars/` 路由。前端 `frontend/src/components/ui/avatar.tsx:43-47` 注释承认这点,回退到 initials 首字母。
- **修法**:改默认为 `""`(空字符串),让前端 avatar.tsx 自然走 initials 分支(当前已是这个回退逻辑)。同时改 `app/services/user_service.py:207` 的 fallback 逻辑。
- **文件**:改 `app/models/tenant.py` + `app/services/user_service.py`。

#### L2. 关键 FK 缺失(引用完整性弱)—— 二次核实后类型一致,可安全加 FK
- **问题**:
  - `Conversation.user_id`(`app/models/agent.py:92`)无 FK,列类型 `String(128)`
  - `UsageEvent.tenant_id`/`user_id`(`app/models/usage_event.py:48,67`)无 FK
  - (`Tenant.created_by` 无 FK 是有意例外,bootstrap 需要,保留并补注释)
- **类型核实(Session 110 执行时二次确认,推翻审查阶段误判)**:审查阶段曾误以为 `User.id` 是 String(32) 导致类型不匹配陷阱——**那是 `Tenant.id`(tenant.py:29 String(32))**。实际 `User.id`(tenant.py:86)是 **`String(128)`**,与所有 `*_user_id` 列(String(128))**类型完全一致**。且项目已有多个 String(128)→users.id 的 FK 先例(`Role.created_by/updated_by`、`User.created_by/updated_by`、`UserSession.user_id`、`UserLoginMethod.user_id`)。**结论:user_id 和 tenant_id 都可直接加 FK,无类型陷阱。**
- **修法**:
  - `Conversation.user_id` 加 `ForeignKey("users.id", ondelete="SET NULL")`(用户删,历史对话保留)+ nullable(因 SET NULL 需要列可空——当前是 NOT NULL,需同时改 nullable=True)。
  - `UsageEvent.tenant_id` 加 `ForeignKey("tenants.id", ondelete="CASCADE")`;`UsageEvent.user_id` 加 `ForeignKey("users.id", ondelete="SET NULL")` + nullable=True。
  - 因为马上彻底清空数据库,**无存量数据风险**,直接加 FK 安全。
- **文件**:改 `app/models/agent.py`(user_id 加 FK + nullable)+ `app/models/usage_event.py`(tenant_id + user_id 加 FK);新迁移加约束。
- **注意**:加 FK 后,`UserTenant.assign_role` 等 SCD2 写入路径要确认不破坏(应该不破坏,只是加引用约束)。

#### L3. `Message` 无失败/错误状态字段
- **问题**:`app/api/v1/chat.py:184`(余额不足)和 `:256-257`(生成失败)两个失败分支都只发 SSE error 事件、**不落库**(修订:原计划只点 184 行号不精确,256 才是生成失败主分支)。失败的回复无审计、前端无法重试展示。
- **修法**:`app/models/message.py` 加 `error: Mapped[str | None]` + `status: Mapped[str]`(default `"completed"`,可选 `"failed"`);`chat.py` 生成失败分支(256)落库一条 `status="failed"` 的 Message 行。
- **文件**:改 `app/models/message.py` + `app/api/v1/chat.py` + `app/services/conversation_service.py`;新迁移加列。

### 1.5 确认没问题的(原本怀疑,核实后是好的)

| 原疑点 | 核实结论 |
|--------|---------|
| Conversation.is_pinned/is_starred/tags | ✅ 前后端全用,chat-page 右键菜单+列表排序都在用 |
| Agent.specialty | ✅ 活字段,supervisor 路由 LLM 用它分派(`graph.py:293`),前端可填 |
| Tenant.address/description/status | ✅ tenants-page 展示+编辑都在用(更新走 setattr 动态赋值) |
| LlmConfig vs EmbeddingConfig 不对称 | ✅ 合理(embedding 用单一模型,LLM 需多选) |
| created_by/updated_by 处理 | ✅ 基本一致,Tenant 无 FK 是有意例外 |
| 软删除不一致 | ✅ append-only 表(Message/日志/账本)无软删除合理 |
| 迁移数据回填 | ✅ 只 1 处 `op.execute`(`d1e2f3a4b5c6`),空库重建是 no-op |

---

## 2. 执行阶段(5 阶段,每阶段独立验证)

### 阶段 1:数据库设计修复(后端)

#### 1.1 迁移策略
- **聚合为 1 个新迁移** `XXXX_YYYY_db_design_cleanup`(down_revision = 当前 head `a3b4c5d6e7f8`),内含所有 add/drop column + drop table + add FK + add Agent 软删除列。
- **FK 加什么(二次核实明确)**:`Conversation.user_id`(String(128)→users.id,SET NULL)、`UsageEvent.tenant_id`(String(32)→tenants.id,CASCADE)、`UsageEvent.user_id`(String(128)→users.id,SET NULL)。**user_id 类型经二次核实与 User.id(String(128))一致,可安全加 FK**(推翻审查阶段"类型不匹配"误判)。**无顺序依赖**:add column(Agent.is_deleted)、drop column(6 处死列)、drop table(verification_codes)、add FK(user_id/tenant_id)四类操作互不依赖,同迁移安全。
- 双库方言(PG/SQLite)兼容写法沿用现有惯例(`postgresql_where` + `sqlite_where` 双写、`JSONB().with_variant(JSON, "sqlite")`)。
- **不需要 backfill 脚本**(马上彻底清空,新列 server_default / 旧列直接 drop)。

#### 1.2 代码改动清单(按文件)
| 文件 | 改动 |
|------|------|
| `app/models/wallet.py` | 无需改(查询逻辑在 repository) |
| `app/repositories/wallet.py` | S1:查询加 `is_active` 过滤 |
| `app/repositories/customer.py` | S2(修订):list 加**可选** status 过滤参数(不改默认全显示) |
| `app/api/v1/customers.py` | S2(修订):透传 `?status=` query 参数 |
| `frontend/src/pages/customers-page.tsx` | S2(修订):加 status 筛选器(原计划 M4 移 currency 输入框也在此类) |
| `app/models/agent.py` | S3:加 `is_deleted`/`deleted_at`;L2(二次核实):`user_id` 加 FK(SET NULL)+ 改 nullable=True(类型 String(128)=User.id,一致) |
| `app/services/agent_service.py` | S3:delete() 改软删 |
| `app/repositories/agent.py` | S3:查询加 `is_deleted=False` |
| `app/models/tenant.py` | M1:删 `info_json`;L1:avatar 默认改 `""` |
| `app/services/user_service.py` | L1:avatar fallback 改 `""` |
| `app/models/rbac.py` | M2:删 Permission 三列;M5:删 Role.status |
| `app/schemas/rbac.py` | M5(修订):RoleRead(L20)/RoleUpdate(L45) 移除 status 字段 |
| `app/services/permission_service.py` | M2:seed 移除三列赋值(如有) |
| `app/services/rbac_service.py` | M5:update 循环移除 `"status"` |
| `app/models/security.py` | M3:删 `VerificationCode`;M6:删 `token_hash` |
| `app/services/auth_service.py` | M6:移除 `token_hash` 赋值 |
| `app/models/model_pricing.py` | M4:删 `currency` |
| `app/schemas/billing.py` | M4:移除 currency 字段(L87,L104) |
| `app/api/v1/billing.py` | M4:创建/更新端点移除 currency |
| `frontend/src/api/types.ts` | M4:移除 currency;M5:移除 Role.status(L138,L161) |
| `frontend/src/pages/billing-admin-page.tsx` | M4:移除 currency 输入框 |
| `app/models/usage_event.py` | L2(二次核实):`tenant_id` 加 FK(CASCADE)、`user_id` 加 FK(SET NULL)+ nullable=True |
| `app/models/message.py` | L3:加 `error`/`status` |
| `app/api/v1/chat.py` | L3:生成失败分支(256)落库 |
| `app/services/conversation_service.py` | L3:append_message 支持 status/error |
| `alembic/versions/XXXX_db_design_cleanup.py` | **新迁移** |
| `tests/conftest.py` | 同步移除被删字段的 fixture 引用 |
| 各 `tests/test_*.py` | 新增 S1/S3 测试用例(S2 降为体验增强,可选) |

#### 1.3 验证
- `./init.sh` → ruff `All checks passed!` + pytest 全绿(含新增测试)
- `alembic upgrade head && alembic check`(PG,需 docker)→ 无 drift

---

### 阶段 2:清空数据库 + 真实 LLM key 集成

#### 2.1 彻底清空(用户已确认)
```bash
docker-compose down -v          # 删 volume aap_pgdata,最干净
docker-compose up -d            # 起空 PG(pgvector) + Logto
alembic upgrade head            # 跑全链(含阶段1新迁移)
python scripts/init_admin.py    # 建超管(admin/Admin@123456)
```

#### 2.2 真 key 集成(用户提供,不进 git)
- **安全铁律:真 key 只进 `.env`(已被 `.gitignore` 忽略),绝不硬编码进 `seed_demo.py`(会进 git 历史)。**
- 方案:
  1. `.env.example` 加 `DEMO_LLM_API_KEY=` / `DEMO_EMBEDDING_API_KEY=`(空值占位 + 注释说明)
  2. `app/core/config.py` 加对应字段(`demo_llm_api_key: str = ""` / `demo_embedding_api_key: str = ""`)
  3. `scripts/seed_demo.py` 读 `settings.demo_llm_api_key`,有值则用真 key 灌 LlmConfig/EmbeddingConfig,无值则用占位符 `sk-demo-placeholder`(保持向后兼容)
  4. 种子灌入时:平台级 LlmConfig 用真 key(DeepSeek),平台级 EmbeddingConfig 用真 key(OpenAI)
- **保留保护逻辑**:seed_demo 现有的"检测已有真配置不覆盖"逻辑(`seed_demo.py:629`)保留,防止重跑覆盖用户手动配置。
- **用户操作**:把真 DeepSeek key + OpenAI key 写进本地 `.env`,跑 seed 时自动读取。

#### 2.3 已知坑(清空重建路径)
1. **顺序强约束**:`init_admin` 必须先于 `seed_demo`(后者找不到 super_admin 直接退出 1)
2. **`field_encryption_key` 默认是公开 dev key**(`config.py:81-83`)——dev/test 无所谓,生产必须先生成 key 再灌数据。本任务在 dev 环境,用默认 key 即可。
3. ~~SQLite 跑迁移会炸~~ **(修订:此条原为误报)**——核实迁移 `f2b3c4d5e6f7` L43-47 已有方言守卫 `if bind.dialect.name != 'sqlite': op.execute("CREATE EXTENSION...")`,SQLite 跑该迁移不会炸。本项目仍全程用 PG(因 pgvector 真实向量检索只在 PG 可用),但不存在的坑不列入。
4. **`backfill_permissions.py` 不需要跑**——从空库重建时 `init_admin`/`seed_demo` 调的 `seed_tenant_defaults` 已灌最新权限目录。

---

### 阶段 3:重写大健康连锁种子数据(优化现有)

基于现有 `scripts/seed_demo.py` 框架,**保留架构(3 门店+总部+跨店客户+多角色),重写内容让它更真实可对外讲**。

#### 3.1 业务设定(对外讲得清)
- **品牌**:颐和堂大健康连锁(保留,认知度高)
- **3 门店**:朝阳理疗中心 / 海淀中医门诊 / 王府井理疗馆(保留,真实地名组合)
- **1 总部**:平台 super_admin(品牌运营总部)
- **业务范围**:中医诊疗、推拿理疗、艾灸养生、健康咨询、会员管理
- **2 组织(Group)**:颐和堂中医馆(挂朝阳+海淀,连锁品牌)/ 独立养生馆(挂王府井,加盟店)

#### 3.2 人员清单(8 账号 + 1 超管,覆盖全角色)
| 用户名 | 角色 | 身份 | 所属 | 能干什么(剧本锚点) |
|--------|------|------|------|------|
| `admin` | super_admin | 平台运营总部 | 总部 | 开门店/充值/配定价/看全局 |
| `chen_guanzhang` | owner | 朝阳店·馆长 | 朝阳 | 管店全权+配 Agent+管客户+看账 |
| `li_shifu` | senior_therapist(自定义) | 朝阳店·资深理疗师 | 朝阳 | 读改客户+对话(不能删/建客户) |
| `wang_shifu` | member | 朝阳店·理疗师 | 朝阳 | 只读 Agent+对话 |
| `zhao_guanzhang` | owner | 海淀店·馆长 | 海淀 | 同朝阳 owner |
| `sun_shifu` | member | 海淀店·针灸师 | 海淀 | 同朝阳 member |
| `wu_guanzhang` | owner | 王府井店·馆长 | 王府井 | 同朝阳 owner |
| `hq_dudao` | hq_staff | 总部·运营督导 | 总部(跨店只读) | 跨店看数据/客户/用量 |

统一密码 `Demo@123456`(seed 常量,注释标明仅演示用)。

#### 3.3 数据补强(相比现有 seed 的增量)
- **客户**:从 3 扩到 6-8 个(含跨店复用张先生/刘女士、新客、VIP、黑名单各 1,**演示 status 4 态——这正好验证 S2 修复**)
- **对话**:每门店 2-3 段真实话术(中医问诊/理疗方案/艾灸注意事项),assistant 文本硬编码不依赖 LLM(演示历史)
- **知识库文档**:**新增!** 每个门店灌 1-2 份 RAG 文档(理疗操作规范/中药禁忌/艾灸注意事项),用 EmbeddingConfig 真 key 做真实 embedding 入库,**演示 RAG 检索能力**
- **钱包/定价**:每门店钱包给真实余额(如 50000 token),ModelPricing 配 DeepSeek 真实单价(input/output per 1k)
- **审计日志/通知**:Service 调用自然产生(角色创建/权限授予/充值等),体现真实运营痕迹
- **多智能体编排(orchestrator)**:可在总部建 1 个 orchestrator Agent,挂 2-3 个 specialist(中医/理疗/养生各 1),**演示 priority 58 的多 Agent 路由能力**(现有 seed 没演示这个)

#### 3.4 脚本健壮性
- 保留 `--reset` 白名单清理逻辑,**同步适配阶段1的表结构变更**(Agent 软删除的清理、删掉的列不写、Message 加 status/error)
- 保留幂等设计(查重跳过)
- 保留"不覆盖用户真实 LLM key"的保护逻辑
- 新增知识库灌入函数(调 `KnowledgeService.create_document`,它内部走 `_ingest` 做真实 embedding——**修订:原计划写的 `ingest_document` 方法不存在**)

#### 3.5 验证
- `python scripts/seed_demo.py --reset` → 一键清空演示数据 + 全量重建,无报错
- `python scripts/seed_demo.py`(无参数)→ 幂等重跑,全部打印 exists 跳过
- 各表计数验证:3 门店 + 9 用户 + 2 组织 + 6-8 客户身份 + N 档案 + 5+ Agent + 8+ 对话 + N 消息 + LLM/Embedding 配置 + 钱包/定价 + 知识库文档+chunks
- 真实 RAG embedding 入库验证(若有真 key,document_chunks.embedding 非空)
- 跨店客户复用验证(张先生 profile_count=2)

---

### 阶段 4:超管预填登录页(.env 驱动)

#### 4.1 后端:暴露预填配置
- `.env.example` 加 `DEMO_LOGIN_USERNAME=admin` / `DEMO_LOGIN_PASSWORD=Admin@123456`(注释说明仅开发演示)
- `app/core/config.py` 加字段:`demo_login_username: str = "admin"` / `demo_login_password: str = "Admin@123456"`
- 新增公开端点 `GET /api/v1/auth/login-hint` 返回 `{username, password}`:
  - **仅当 `app_env in ("development","testing")` 才返回真值**
  - 生产环境(`app_env=production`)返回 `{username: null, password: null}`——**无安全风险**
- 文件:改 `app/core/config.py` + `app/api/v1/auth.py`;`.env.example`

#### 4.2 前端:登录页预填
- `frontend/src/pages/login-page.tsx` 启动时调 `/auth/login-hint`,有值则作为 identifier/password 的 defaultValue(非受控,用户可改)
- 生产环境端点返 null,登录页空白
- 保留现有 3 种登录路径(密码/dev/token)不变
- 文件:改 `frontend/src/pages/login-page.tsx` + `frontend/src/api/endpoints.ts`(加 fetchLoginHint)

#### 4.3 验证
- `cd frontend && npm run build` → tsc + vite build 成功
- `npx oxlint src/` → 0 warnings 0 errors
- 手动验证:开发环境登录页预填 admin/Admin@123456;生产环境端点返 null

---

### 阶段 5:4 份对外交付物(文档)

全部放在 `docs/demo-scenario/` 新目录(对外分享用,与 `harness/docs/` 内部计划区分):

#### 5.1 `docs/demo-scenario/01-业务场景说明.md`(对外分享主文档)
- 行业背景(大健康连锁数字化转型痛点:会员分散、服务标准难统一、健康数据无法跨店)
- 颐和堂场景设定(3 门店+总部组织架构图)
- 平台核心能力(多租户隔离/跨店客户身份复用/RAG 知识库/预付钱包计费/三级权限/白标)
- 商业价值(为什么用这个平台:统一服务标准、会员跨店识别、AI 辅助诊疗、按量计费透明)
- 系统架构图(mermaid,复用现有 `docs/db-schema.mmd`)

#### 5.2 `docs/demo-scenario/02-演示账号清单.md`
- 9 个账号表格(用户名/密码/角色/所属门店/能干什么)
- 每个账号的"登录后第一眼看到什么"
- 不同角色的权限差异说明(对照权限矩阵)
- 平台级 vs 租户级 vs 跨租户只读三种身份对比

#### 5.3 `docs/demo-scenario/03-日常使用剧本.md`(分角色 walk-through)
- **周一早晨陈馆长(朝阳 owner)**:看 dashboard → 管客户 → 配 Agent system_prompt → 看本月 token 消耗
- **李师傅接待颈椎理疗客户(朝阳 senior_therapist)**:选 Agent → 关联客户张先生 → 对话(颈椎理疗方案)→ 查历史对话 → 更新客户备注
- **总部督导员巡查 3 门店(hq_staff)**:跨店看数据/客户/用量 → 导出报表
- **平台运营给门店充值(super_admin)**:tenants 页 → billing/admin 充值 → 配模型定价
- 每个剧本标注:用哪个账号、点什么菜单、看到什么数据、体现什么能力

#### 5.4 `docs/demo-scenario/04-种子数据复现指南.md`
- 一键复现命令序列(docker → alembic → init_admin → seed_demo)
- `.env` 配置说明(真 key 放哪、各字段含义)
- 数据全景表(每张表灌了多少行、关键字段示例)
- 重置/清理命令(`seed_demo.py --reset`)
- 常见问题(对话 401 怎么办/如何换行业/如何加新门店)

#### 5.5 验证
- 4 份文档完整,mermaid 图渲染正常
- 账号清单与 seed_demo.py 实际种的一致(交叉核对)
- 剧本里的操作路径与前端实际路由一致

---

## 3. 全局验证清单

| 阶段 | 验证命令 | 预期 |
|------|---------|------|
| 1 | `./init.sh` | ruff + pytest 全绿(含新增 S1/S2/S3 测试) |
| 1 | `alembic upgrade head && alembic check`(PG) | 无 drift |
| 2 | docker 清空 + init_admin | 无报错,超管创建成功 |
| 3 | `python scripts/seed_demo.py --reset` | 一键重建,各表计数符合预期 |
| 3 | `python scripts/seed_demo.py`(幂等) | 全部 exists 跳过 |
| 4 | `cd frontend && npm run build` | tsc + vite 成功 |
| 4 | `npx oxlint src/` | 0 warnings 0 errors |
| 4 | 手动浏览器 | 登录页预填 admin,登录成功进 dashboard |
| 5 | 文档审阅 | 4 份完整,账号/路径与实际一致 |

---

## 4. 收尾(会话结束前)

- 对照 `harness/clean-state-checklist.md` 逐项打勾
- 更新 `progress.md` Session 109 记录
- 更新 `feature_list.json`:本任务作为新 feature 登记(evidence 字段填验证证据)
- `项目指南/附录/关系图.md` 第十一章(演示案例数据全景表)同步更新
- 文档影响评估(按 AGENTS.md 约定)

---

## 5. 不做的事(边界)

- ❌ **不加新表**:Agent.tools / 邀请表 / 附件表 —— 登记为后续 feature_list 任务(执行时写 notes)
- ❌ 不改 RBAC 权限模型 / 认证管线
- ❌ 不改前端 UI 框架(只改 login-page 预填 + billing-admin 移除 currency 输入框)
- ❌ **不把真 key 写进 git**(只进 .gitignore 忽略的 .env)
- ❌ 不破坏现有 58 个 passing 功能(改动窄范围,每步验证不回归)

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 删列/删表迁移在已有数据的库上跑会丢数据 | 用户已确认彻底清空重来,清空在新迁移之前;且现有数据本就要重建 |
| 真 key 泄露 | 只进 .gitignore 忽略的 .env,seed 脚本不硬编码;`.env.example` 只放空值占位 |
| seed_demo 适配新表结构有遗漏 | `--reset` 跑通 + 各表计数验证 + 幂等重跑验证 |
| FK 新增后 SCD2 写入路径破坏 | 加 FK 后跑 `init_admin` + `seed_demo` 全流程验证;SCD2 表(user_tenants/role_permissions)本身不动 |
| 删 VerificationCode 表后某处隐式依赖 | 已 grep 确认 app/ 中从未实例化、无 repository、无端点;conftest 无引用 |
| L3 Message 加 status 影响现有对话流 | status 默认 "completed",现有 append_message 路径不传则用默认值,向后兼容 |

---

## 7. 关键文件路径索引

- 本计划:`harness/docs/plan-db-revamp-and-scenario-rebuild.md`
- 数据模型:`app/models/{tenant,rbac,agent,message,customer,group,wallet,usage_event,model_pricing,api_token,llm_config,embedding_config,document,log,notification,security,tenant_config,agent_specialist}.py`
- 迁移目录:`alembic/versions/`(26 个,head = `a3b4c5d6e7f8`)
- 种子脚本:`scripts/seed_demo.py`、`scripts/init_admin.py`
- 配置:`app/core/config.py`、`.env.example`
- 登录页:`frontend/src/pages/login-page.tsx`
- 审查报告完整版:本文件 §1
- 演示案例现有文档:`项目指南/附录/关系图.md` 第十章/十一章

---

## 附:本会话审查产出的证据链(供新会话复核用)

本计划的每一条发现都有代码证据支撑,复核时按此索引:

1. **S1 Wallet.is_active**:grep `Wallet.is_active` / `w.is_active` 在 query 语句零命中;写入在 `billing_service.py:88`
2. **S2 CustomerProfile.status**:`repositories/customer.py:110` 只 `== "active"`;前端 `customers-page.tsx:91-94` 4 态
3. **S3 Agent 无软删除**:`agent.py` 无 `is_deleted`;`agent_service.py:175-187` 走 `repo.delete`
4. **M1 User.info_json**:全仓 `info_json` 仅 `tenant.py:109,111`(定义处)
5. **M2 Permission 三列**:无 CRUD 端点(`api/v1/permissions.py` 只有 2 个 GET);`PermissionItem` schema 故意不带
6. **M3 verification_codes**:`VerificationCode(` 仅 `security.py:97`(类定义);无 repository、无端点
7. **M4 currency**:grep `currency ==` 零命中;前端 `billing-admin-page.tsx:~604` disabled
8. **M5 Role.status**:`repositories/rbac.py` list 不按 status 过滤;前端 roles-page 不展示
9. **M6 token_hash**:写 `auth_service.py:136`;校验走 `session_id`(`deps.py:152`)
10. **L1 avatar 默认死 URL**:`uploads.py` 无 `/avatars/` 路由;`avatar.tsx:43-47` 注释承认回退 initials
11. **L2 FK 缺失**:`agent.py:92` Conversation.user_id 无 FK;`usage_event.py:48,67` 无 FK
12. **L3 Message 无 error**:`chat.py:184` 失败只发 SSE,不落库

---

## 8. 修订日志(Session 110 —— 挑刺复核后的修订)

挑刺审查(对照源码逐条核实)发现 7 处问题,已于 Session 110 修订,执行前应基于修订版。修订明细:

| # | 条目 | 原计划问题 | 修订后 |
|---|------|-----------|--------|
| R1 | **S3 级联方向** | 称 Conversation.agent_id 被 SET NULL | 实为 `ondelete="CASCADE"`,删 Agent **级联删对话**;UsageEvent 才是 SET NULL。后果比原估更严重 |
| R2 | **S2 因果** | 称 list 把 vip 过滤掉看不见 | 误判:list 全显示;真只认 active 的是 statistics 统计。bug 重定义为"4 态枚举名存实亡",修法改为加筛选器(不再改 list 过滤),降为体验增强 |
| R3 | **§2.3 坑3** | 称 SQLite 跑迁移会炸(vector 无守卫) | 误报:迁移已有 `if dialect != sqlite` 守卫。划掉 |
| R4 | **L2 类型陷阱(又二次推翻)** | 原计划称 user_id 直接加 FK 安全 | 挑刺审查阶段误判为"String(128)≠User.id String(32) 类型不匹配";**执行阶段二次核实发现 User.id 实为 String(128)(tenant.py:86,误读成 Tenant.id),类型一致,可安全加 FK**。最终定案:user_id + tenant_id 全部加 FK,沿用 SET NULL/CASCADE。教训:挑刺结论也需复核 |
| R5 | **M5 连带** | 称前端无引用,纯删 | 经核实 RoleRead/RoleUpdate schema 带 status 且可写,连带面更大,补全 schema + 前端 types 改动 |
| R6 | **§3 方法名** | 称调 `KnowledgeService.ingest_document` | 该方法不存在,改为 `create_document`(内部走 `_ingest`) |
| R7 | **L3 行号** | 点 184 为生成失败 | 184 是余额不足;256 才是生成失败主分支。补全两个失败分支 |

**未修订(核实确认准确)**:S1 Wallet.is_active 假开关、M1/M2/M3/M4/M6 死字段/死表、L1 avatar、§4 登录预填安全模型、§7 证据链、1.5 节"确认没问题"项。

**执行风险提示**:R4(L2 类型陷阱)是阶段 1 唯一可能导致迁移直接报错的硬阻塞,务必按方案A处理,切勿对 user_id 加 FK。
