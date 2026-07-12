# plan:demo-seed-full —— 演示数据全量补全(清理重建 + 覆盖所有业务实体)

| 字段 | 值 |
|------|-----|
| **id** | `demo-seed-full` |
| **priority** | 38 |
| **area** | 演示案例 |
| **status** | not_started |
| **depends_on** | `demo-seed`(37,已 passing)—— 在其基础上扩 `scripts/seed_demo.py` |
| **verification** | `python scripts/seed_demo.py --reset` 一键清空+重建;`./init.sh` 全绿(纯脚本,无 app/ 改动) |

---

## 1. 背景与目标

`demo-seed`(priority 37,已 passing)种下了**组织/客户/门店**三大域的基础数据:
3 门店 + 7 用户 + 2 组织 + 5 客户档案 + 4 Agent + RBAC 默认种子。

但用户要求「**所有业务数据都有一份,覆盖全面**」。对照项目的 22 张业务表,
当前种子**只覆盖了 8 张**,以下业务表**完全没有演示数据**:

| 缺口表 | 业务含义 | 为什么该有演示数据 |
|--------|---------|-------------------|
| `Conversation` + `Message` | 对话会话 + 消息 | AI 内核的**核心产物**,没有对话数据 = 演示看不到「智能体在干活」 |
| `LlmConfig` | LLM 配置(平台级 + 租户级) | 三级 fallback(租户>平台>env)是已交付能力,无数据则前端下拉永远走 env,演示不出「租户级覆盖平台级」 |
| `ApiToken` | AtoA 长效 token | AtoA 系列已 passing,无 token 数据 = CLI 登录演示不了 |
| `SystemLog` | 审计日志 | 审计能力已交付,空表演示不出「用户 CRUD 留痕」 |
| 自定义 `Role` / `Permission` / `RolePermission` | RBAC 超出默认三角色 | RBAC「宪法」核心卖点是「自定义角色 + 权限矩阵」,默认三角色演示不出灵活性 |
| `UserLoginMethod` | 多登录方式 | 用户表有这个关联,空表 = 演示不出「一个用户多种登录方式」 |
| Agent 推理参数 | temperature / max_tokens / top_p | 现有 4 个 Agent 全是默认值,演示不出「不同 Agent 不同推理风格」 |

### 目标

把 `scripts/seed_demo.py` 从「基础三域」扩成「**全量业务实体**」,并加 `--reset` 清理重建能力:

1. **清理**:`python scripts/seed_demo.py --reset` 按 FK 反向顺序硬删除全部演示数据,
   再重建。一键、幂等、可复用。
2. **补全**:新增对话历史 / LLM 配置 / API Token / 审计日志 / 自定义角色权限 / 多登录方式 /
   Agent 推理参数差异化,让演示数据**覆盖全部业务表**。

### 为什么不新建脚本而扩现有的

- `seed_demo.py` 已是项目唯一的演示种子入口,且照搬了 `init_admin.py` 的成熟范式
(幂等 select-then-add + 调真实 Service/Repository)。
- 「清理 + 重建」是同一个演示生命周期的两面,放一个脚本 + 一个 `--reset` 开关最自然,
避免维护两个脚本的状态同步。

---

## 2. 数据覆盖矩阵(验收的「全面」标准)

重建后,演示数据应覆盖以下全部业务表(✅ = 已有,🆕 = 本次新增):

### 平台级实体(无 tenant_id)
| 表 | 现有 | 本次增量 |
|----|------|---------|
| `Group` | ✅ 2 个(颐和堂中医馆 / 独立养生馆) | 不变 |
| `GroupTenant` | ✅ 3 条挂载关系 | 不变 |
| `Customer` | ✅ 3 个全局身份(张/刘/周先生女士) | 🆕 +2 个(凑齐更丰富的跨店场景) |

### 租户级实体(有 tenant_id)
| 表 | 现有 | 本次增量 |
|----|------|---------|
| `Tenant` | ✅ 3 门店 | 不变 |
| `User` | ✅ 7(1 超管 + 6 门店员工 + 1 hq_staff) | 不变(账号体系已够) |
| `UserTenant` | ✅ SCD2 成员关系 | 不变 |
| `CustomerProfile` | ✅ 5 个门店档案 | 🆕 +2 个(配合新 Customer) |
| `Agent` | ✅ 4 个 | 🆕 **补推理参数差异化**(temperature/max_tokens/top_p 各不同) |
| `Conversation` | ❌ 0 | 🆕 **每个门店 Agent 1-2 段对话**(含 user/assistant 轮次) |
| `Message` | ❌ 0 | 🆕 **配合 Conversation,每段 4-6 条消息** |
| `LlmConfig` | ❌ 0 | 🆕 **平台级 1 条 + 1 个门店级覆盖**(演示三级 fallback) |
| `ApiToken` | ❌ 0 | 🆕 **2-3 个 token**(门店 owner 颁发,演示 AtoA) |
| `SystemLog` | ❌ 0 | 🆕 **由建数据过程中的 Service 调用自然产生**(用户/角色 CRUD 留痕) |

### RBAC 层(租户级)
| 表 | 现有 | 本次增量 |
|----|------|---------|
| `Role` | ✅ 默认三角色(owner/admin/member) | 🆕 **朝阳店加 1 个自定义角色**(如「资深理疗师」) |
| `Permission` | ✅ 默认权限 | 🆕 配合自定义角色的新权限项 |
| `RolePermission` | ✅ SCD2 默认授权 | 🆕 **给自定义角色授予差异化权限**(演示权限矩阵灵活性) |

### 登录/会话层
| 表 | 现有 | 本次增量 |
|----|------|---------|
| `UserLoginMethod` | ❌ 0(只 users.email) | 🆕 **给 1-2 个用户加手机号登录方式** |
| `UserSession` / `VerificationCode` | — | **不种**(运行时数据,种子不该造假登录态) |

**「全面」= 上述除 UserSession/VerificationCode 外的所有业务表都有演示数据。**
(这两个是运行时态,种子造出来反而误导。)

---

## 3. 交付物

### 3.1 扩展 `scripts/seed_demo.py`

#### A. 新增 `--reset` 清理能力

加 `argparse`,支持两种模式:
- `python scripts/seed_demo.py`(默认,现有行为)—— 幂等 upsert,已有则跳过
- `python scripts/seed_demo.py --reset` —— **先清理全部演示数据,再全量重建**

**清理顺序(按 FK 反向,避免约束冲突)**:
```
Message → Conversation → ApiToken → LlmConfig → CustomerProfile → Customer
→ RolePermission → Permission → Role(只删自定义,is_system=False 的非默认角色)
→ Agent → UserTenant → User(只删演示用户,保留 super_admin)
→ GroupTenant → Group → Tenant(演示门店)
→ SystemLog(演示产生的日志,按 tenant_id IN 演示门店 清理)
→ Casbin 行(policy 表,演示用户/租户的行)
```

**清理边界(铁律:不误伤)**:
- 只删「演示标记范围内」的数据。判定方式:用**演示数据常量清单**
  (门店名/用户名/Group code/Customer identity_key 的白名单)反查要删的行 ID,
  按这些 ID 级联清理,而非 `DELETE FROM ...`(裸删会误伤非演示数据)。
- `super_admin` 及其 casbin 行**不删**(init_admin.py 建的,不属于演示范围)。
- 默认三角色(owner/admin/member,`is_system=True`)及默认权限**不删**(seed_defaults 建的)。

#### B. 新增数据补全(在现有 5 步后追加 Step 6-11)

**Step 6:Agent 推理参数差异化**(改现有 AGENTS 常量 + AgentCreate 调用)
- 现有 4 个 Agent 全用默认 temperature=0.7。改为:
  - 朝阳店健康顾问:temperature=0.3(严谨)/ max_tokens=2048 / top_p=0.9
  - 海淀店健康顾问:temperature=0.7(默认)/ max_tokens=None / top_p=None
  - 王府井店健康顾问:temperature=0.9(发散)/ max_tokens=4096 / top_p=0.95
  - 颐和堂总部督导:temperature=0.2(保守汇总)/ max_tokens=8192 / top_p=0.85
- `AgentCreate` schema 已支持这三个字段(`schemas/agent.py:16-18`),直接传即可。

**Step 7:自定义角色 + 差异化权限**(演示 RBAC 灵活性)
- 朝阳店加 1 个自定义角色:「资深理疗师」(code=`senior_therapist`,非 system)。
- 用 `RbacService.create(actor_id=朝阳owner, tenant_id, RoleCreate(...))`。
- 给该角色授予差异化权限:用 `RbacService.grant_permission(...)` 授
  `customers:read` + `customers:update`(能看能改客户档案,但不能删/建)。
- 把朝阳店「李师傅」从 member 改绑成 senior_therapist(演示「自定义角色真的生效」)。
- 这一步会**自然产生 SystemLog**(role.create / role.grant 审计行)。

**Step 8:LLM 配置**(演示三级 fallback)
- **平台级 1 条**:用 `LlmConfigService.upsert_platform(LlmConfigUpdate(...))`,
  base_url 指 DeepSeek 兼容端点,default_model=deepseek-chat,
  available_models=[deepseek-chat, deepseek-reasoner]。
  api_key 用占位符 `sk-demo-placeholder`(演示用,真实 key 由用户在 settings 页填)。
- **朝阳店级覆盖 1 条**:用 `LlmConfigService.upsert_tenant(朝阳tenant_id, ...)`,
  default_model=deepseek-reasoner(演示「这家门店用更强的推理模型」)。
- 这样演示三级 fallback:海淀/王府井 → 平台级 deepseek-chat;朝阳 → 租户级 deepseek-reasoner。

**Step 9:对话历史**(AI 内核核心产物)
- 为每个门店 Agent 造 1-2 段对话,每段 4-6 条消息(user/assistant 交替)。
- 用 `ConversationService.create_or_get(user_id=门店员工, tenant_id, agent_id, first_message=首条user消息)`
  建会话(title 由 first_message 自动截前 20 字生成)。
- 用 `ConversationService.append_message(tenant_id, conv_id, role, content)` 逐条追加。
- 内容要**贴合大健康场景**:如「我最近颈椎不舒服,有什么理疗建议?」/「根据您的描述,
  建议先做颈椎推拿,配合艾灸...」(assistant 内容直接写死文本,不调真实 LLM)。
- 平台级 Agent(颐和堂总部督导)造 1 段跨店汇总对话,演示总部视角。

**Step 10:API Token**(演示 AtoA)
- 朝阳店 owner 颁发 1 个 token:用 `ApiTokenService.issue(user_id=朝阳owner, tenant_id, ApiTokenCreate(name="朝阳店 AtoA 集成"))`。
- 海淀店 owner 颁发 1 个:同上。
- **注意**:`issue()` 返回明文 token 只展示一次,脚本打印出来供演示用(注释标明仅演示)。

**Step 11:多登录方式**
- 给朝阳店陈馆长加 1 个手机号登录方式:
  用 `UserRepository` / 直接 `UserLoginMethod` 行(login_type=phone, identifier=演示手机号, is_verified=True)。
- 这演示「一个用户多种登录方式」(邮箱 + 手机号)。

**Step 12:汇总打印更新**
- 现有汇总只打印账号清单。扩展为「数据全景表」:
  门店/用户/组织/客户/Agent/对话/消息/LLM 配置/Token/自定义角色/日志的**计数** + 关键演示点标注。

#### C. 幂等设计扩展

`--reset` 模式天然幂等(删完重建)。默认(无 --reset)模式对新加的实体也要幂等:
- Conversation:按 `(agent_id, user_id, title)` 查重跳过。
- LlmConfig:upsert 本身幂等(已有则更新)。
- ApiToken:按 `(tenant_id, name)` 查重跳过(token 明文无法幂等重建,已有则跳过)。
- 自定义角色:按 `(tenant_id, code)` 查重跳过。
- UserLoginMethod:按 `(user_id, login_type, identifier)` 查重跳过。

### 3.2 更新 `harness/docs/plan-demo-seed.md` 的引用

在原 plan-demo-seed.md 末尾加一行指向本任务(说明「全量补全见 plan-demo-seed-full.md」)。
不改原 plan 的历史内容(它是已 passing 任务的归档)。

### 3.3 更新演示文档(数据全景变化)

- `项目指南/附录/关系图.md` 第十一章(演示案例说明):数据全景表补「对话/消息/LLM配置/Token/自定义角色/日志」计数列 + 新增 4 个验证点(三级 fallback / 自定义角色生效 / AtoA token 可用 / 对话历史可见)。
- 脚本头部的 docstring 更新:把「Creates ... 4 agents」扩成全量清单。

### 3.4 harness 文档登记

- `feature_list.json` 追加 1 条(priority 38,area 演示案例,status not_started)
- `progress.md` 任务规划表加 1 行 + Session 记录

---

## 4. 实施步骤

> 本任务为「登记为 not_started」;以下步骤供执行会话照做。

1. **加 `--reset` 清理逻辑** —— argparse + 反向 FK 删除 + 演示白名单边界
2. **Step 6 Agent 推理参数差异化** —— 改 AGENTS 常量加 temperature/max_tokens/top_p 列
3. **Step 7 自定义角色 + 权限** —— RbacService.create + grant_permission
4. **Step 8 LLM 配置** —— upsert_platform + upsert_tenant
5. **Step 9 对话历史** —— create_or_get + append_message(每门店 1-2 段)
6. **Step 10 API Token** —— ApiTokenService.issue(2 个门店各 1)
7. **Step 11 多登录方式** —— UserLoginMethod 行
8. **Step 12 汇总打印** —— 数据全景表
9. **幂等补全** —— 默认模式对新实体的查重跳过
10. **真实 Postgres 验证** —— docker 起库 → `--reset` 跑通 → 默认模式重跑确认幂等
11. **更新演示文档** —— 关系图.md 第十一章 + 脚本 docstring
12. **`./init.sh` 全绿** —— 纯脚本任务,无 app/ 改动,基线不回归

---

## 5. 验收标准

1. `python scripts/seed_demo.py --reset` 一键清空全部演示数据 + 全量重建,无报错
2. `python scripts/seed_demo.py`(无参数)幂等可重跑,新加实体打印 exists 跳过
3. 重建后覆盖**全部业务表**(除 UserSession/VerificationCode 运行时态外),具体计数:
   - 3 门店 + 7 用户 + 2 组织 + 5+ 客户身份 + 7+ 门店档案
   - 4 Agent(**推理参数各不同**)
   - 4-6 段对话 + 20-30 条消息
   - 1 平台级 + 1 租户级 LLM 配置
   - 2 个 API Token
   - 1 个自定义角色 + 差异化权限
   - SystemLog 由过程自然产生(非空)
   - 1+ 个额外登录方式
4. 登录验证三级 fallback:朝阳店 Agent 下拉显示 deepseek-reasoner;海淀/王府井显示 deepseek-chat
5. 登录验证自定义角色:朝阳店李师傅(senior_therapist)能改客户档案但不能删
6. `./init.sh` 全绿(纯脚本,无 app/ 代码改动,基线不回归)

---

## 6. 风险 / 不做的事

### 风险
- **清理误伤**:`--reset` 裸删会误伤非演示数据。缓解:用演示白名单(门店名/用户名/code/identity_key)
  反查行 ID 再级联删,绝不用 `DELETE FROM table`(无 WHERE)。super_admin 及默认角色/权限不删。
- **Casbin 残留**:删用户/租户后 casbin policy 表可能残留行。缓解:清理时同步删
  casbin 中演示 user/tenant 的 grouping + policy 行。
- **ConversationService.append_message 无权限守卫**:它不带 require(设计如此,由调用方
  create_or_get 把关)。脚本里 create_or_get 传门店 owner 通过权限,append_message 直接调即可。
- **ApiToken 明文只展示一次**:rebuild 时旧 token 的明文已丢失,`--reset` 后是新 token。
  打印时注释标明「仅演示,生产勿用」。
- **LlmConfig api_key 占位符**:演示用 `sk-demo-placeholder`,真实调 LLM 会失败。
  脚本注释标明「演示用占位 key,真实对话请在 settings 页填真实 key」。这是预期行为
  (种子不负责提供可用 LLM 凭证)。

### 不做的事
- 不改任何 `app/` 功能代码(纯扩展 `scripts/seed_demo.py` + 更新文档)
- 不加批量导入端点 / 不做前端改动
- 不种 `UserSession` / `VerificationCode`(运行时态,造出来误导)
- 不调真实 LLM 生成对话内容(assistant 消息写死文本,避免依赖网络/key)
- 不删 `init_admin.py`(super_admin 仍由它建)
- 不碰原 `plan-demo-seed.md` 的历史归档内容(只在末尾加引用)

---

## 7. 实现记录(evidence)

> 待执行会话填写。完成后在此记录:脚本行数 / `--reset` 验证 / 幂等验证 / 各表计数 / 三级 fallback 验证 / 自定义角色验证 / `./init.sh` 结果。
