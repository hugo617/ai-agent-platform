# 计划:TurnAccountant 计费编排下沉收口(turn-accountant sinking)

> **id**: turn-accountant-sinking
> **状态**: in_progress(EP2 已完成 2026-08-25 Session 231,切片 01 待 EP3 实施)
> **优先级**: 99(feature_list.json)
> **创建日期**: 2026-08-25
> **最后修订**: 2026-08-26(v1.2:EP3 code-review 回写,§0.2 实施注记)

---

## 0. v1 → vN 变更摘要(若有修订,必填)

v1 首发,无修订。(自审 §7 的三项发现已同步吸收进 v1 正文,见 §0.1 与 §7 说明。)

**v1.1(2026-08-26 Session 232,EP3 开工)**:仅 §0.1 复核窗口关闭留痕,D4-D7 决策与正文零改动。

**v1.2(2026-08-26 Session 232,EP3 code-review 回写)**:新增 §0.2 实施注记;正文决策零改动。

---

## 0.1 决策拍板状态说明

本 feature 的架构主轴三决策(**D1 seam 形态 / D2 两路径统一程度 / D3 SSE 是否 paired charge**)于 2026-08-25 Session 231 经 AskUserQuestion 问询,**用户逐项拍板全部采纳推荐方案**——本 feature 是「必须问用户拍板,不默认采纳」的指定项,无默认采纳成分。

次级工程形态四决策(**D4 钱包门处置 / D5 N+1 循环形态 / D6 测试策略 / D7 切片数**)第二轮 AskUserQuestion 问询**未获回复**。处置:按 Session 219/222/229 先例(「未获回复按推荐采纳并如实标注」),D4-D7 全部按推荐方案落地,逐项如实标注于 §4.5。**复核窗口 = EP3 开工前**。

**✅ 复核窗口已关闭(2026-08-26 Session 232,EP3 开工首动作)**:AskUserQuestion 逐项问询 D4-D7(含各推荐方案与推翻选项)**仍未获回复**——按本节预设协议,窗口关闭,D4-D7 **维持推荐方案**落地(D4 钱包门不动留 API / D5 保持循环改单调用 / D6 六例零改动+四条 seam 单测 / D7 单切片)。§4.5 决策表与正文零改动。

---

## 0.2 实施注记(EP3 Session 232,commit a04aa4b + PR #177)

实施与 plan 承诺的偏差逐项留痕(均为留痕级,无阻塞):

1. **`_u` 落地形态 = 改名公开 `extract_usage_int`**(§4.5 授权「EP3 定名」两形态之一):迁入 seam 模块并公开,chat.py `append_message` 的 token 列参数改 import 之——无双份实现,无私有名跨模块 import。
2. **record 失败日志文案统一为 `"UsageEvent insert failed (agent_id=%s, conv=%s)"`**:旧 composite 版为 `"composite UsageEvent insert failed ..."`(去 `composite ` 前缀以覆盖两路径),落在 §7 🟡 已采纳的「统一 logger.exception 良性超集」边界内;charge 失败文案 `"wallet charge failed (tenant=%s, event=%s)"` 逐字镜像现状。
3. **SSE 异常分支守卫吸收的边缘语义统一**:旧异常分支调用点守卫 `if usage_data and _u(usage_data, "total_tokens")` 为**真值**判断(total=0 跳过记账);seam 入口统一为旧正常分支 `_record_usage` 内部的 **None** 判断(§4.6 规格:「`total_tokens` 缺失 → 返回 None」)。退化场景「失败轮 + total_tokens=0」从「跳过」变为「记 0-token 事件」——两路径契约统一(本 feature 的目的本身),HTTP 用例锁不到该边缘,如实施注记留痕。
4. **charge 的 tenant 来源统一 `conv.tenant_id`**:旧 SSE 路径 `_charge_usage(db, user.tenant_id, ...)`、composite 路径 `conv.tenant_id`;两者恒等(conv 均以 `user.tenant_id` 创建),§4.6 核心规格即写 `charge(conv.tenant_id, ...)`,合规非行为变化,记档。
5. **seam 单测 case 1「两入口各覆盖」落地为 stream 双守卫态**(usage_data=None / total_tokens 缺失):composite 入口三元组签名必填,无「无 usage」态可表达(§4.6 对其无守卫规格);其退化输入(record 抛错)由 case 2 覆盖。测试文件 docstring 已自述。
6. **kwargs 对照留痕(AC 证据)**:脚本归一化对照——旧 composite 版 UsageEvent 构造 kwargs 与新 `_record_and_charge` 核心**严格一致**;旧 SSE 版五项值表达式(model `or ""` / prompt `or 0` / completion `or 0` / total 解析 / None 守卫)与新 SSE 入口逐项 **IDENTICAL**(仅 `_u`→`extract_usage_int` 改名)。
7. **code-review 双轴结果**:Standards 轴 0 硬违规 0 阻塞(铁律 1/2 逐条核验通过;弱项 Data Clumps / Feature Envy 仓库先例背书现形态,留巡检);Spec 轴 0 缺失(上述 1-3 为全部偏差,均有据可查)。

---

## 1. Problem Statement

`app/api/v1/chat.py`(558 行)的计费编排块(L52-222,~171 行;第 10 次巡检 140 行 → 第 11 次 171 行微膨胀)承载着**同一份「一轮对话记账→扣费」契约的两套实现**:

- **SSE 路径**:`_record_usage`(记 1 条 UsageEvent,commit,try/except best-effort)**不扣费**——charge 由 caller 分两步调 `_charge_usage`,散在正常/异常 **2 个调用点**,顺序敏感(record 必须先于 charge,且中间隔 commit);
- **composite 路径**:`_record_composite_usage`(构造字段与 SSE 版逐字镜像的 UsageEvent 行 + commit + 容错)**内置 paired charge**(函数尾随 `_charge_usage`),N+1 循环内联调用 ~25 行;
- 两函数的 docstring 自述「NOT shared」——差异只剩入参形态(SSE 拿流式聚合 usage dict + Agent 对象,composite 拿已解析 token 三元组 + agent_id=None),**行为本体是逐字镜像**。

由此产生的结构性风险:

1. **record→charge 顺序契约散在 3 处调用点,无 locality**——将来一处改了另一处漏改(比如某调用点漏调 charge),对账 job(`BillingReconciliationService._find_missed_events` 的 NOT EXISTS 漏扣检出)恰以「每条 UsageEvent 配对 consume WalletTransaction」为前提,**漏改 = 对账报表出现系统性假差额**(feature 93 落地后论据从「防漏」升级为「对账一致性前置」);
2. **分层铁律违反**:`UsageEventRepository` 被 API 层直摸 3 处(import/实例化),`BillingService` 在 API 层函数内延迟 import 2 处——记账编排是 Service 职责,不是路由职责(与 feature 92 code-review 判「审计属 Service 职责」同型的层次卫生问题);
3. **「在 API 层打补丁」的路线已走到头**:feature 94 修钱包门(feature 98 修定价)都在给 API 层计费 helper 做加法,本块 140→171 的涨幅就是这个趋势的读数。

这是第 6/9/10/11 次巡检四度复现的架构候选 ②(Strong,候选池最强)。**TurnAccountant 至今是巡检概念,app/ 零匹配**——本 feature 即该 seam 的落地;历史留痕兑现:chat-stream-wallet-gate(94)title 明文「不动 TurnAccountant——架构候选 ② 独立立项时消化」,plan-risk-hardening-overview.md 系列边界 D5 同承诺。

## 2. Solution

新建 `app/services/turn_accountant_service.py` 的 **`TurnAccountantService`**,把两路径的记账编排收口为**两薄入口 + 单核心**(D2):

- `record_stream_turn(conv, msg, agent_id, user_id, usage_data)`——SSE 形态(流式聚合 usage dict),内部解析 token 三元组;
- `record_composite_row(conv, msg, agent_id, user_id, prompt_tokens, completion_tokens, total_tokens, model)`——composite 形态(已解析三元组);
- 两入口归一入参后走同一私有核心 `_record_and_charge`:UsageEvent 构造 → commit → **paired charge**(D3)→ best-effort 容错(record 失败 rollback 不 charge;charge 失败 rollback 不伤已 commit 的事件行)。

**record→charge 顺序契约从此单点持有在 seam 内部**;chat.py 三处调用点(SSE 正常/异常 + composite N+1 循环)全部收缩为单次调用;`_record_usage`/`_record_composite_usage`/`_charge_usage` 三函数从 API 层删除,`UsageEventRepository` 直摸与 `BillingService` 延迟 import 随之归位消失。**验收锚点:既有 6 条计费行为用例(SSE 4 + composite 2,全走 HTTP 接缝断 DB 行)零改动通过**——纯结构迁移,用户可见行为逐字不变。

## 3. User Stories

1. 作为门店店员(member),我通过 SSE 流式对话,期望每轮的 token 记账与钱包扣费行为与收口前逐字一致,以便无感升级。
2. 作为门店店员(member),我发起 composite 多智能体提问,期望 N+1 条 UsageEvent(fragment 行 + synthesize 行)与配对扣费照常落账,以便用量报表与本店账单不漂移。
3. 作为门店 owner,我在计费页查看钱包余额与用量事件,期望余额扣减、total_consumed 累计、UsageEvent 字段(agent/customer/token/model/cost)与收口前完全一致,以便对账口径稳定。
4. 作为平台运维,我依赖每日计费对账 job 的漏扣检出,期望 record→charge 配对契约从「散在 3 处调用点的约定」变成「seam 内部的结构事实」,以便对账报表不因调用点漂移出现系统性假差额。
5. 作为 super_admin,我通过 CLI 或前端走任一对话路径,期望 best-effort 容错语义(记账/扣费失败不破坏已成功的对话回复)逐字保持,以便极端故障下用户体验不回退。
6. 作为后续开发者,我希望对话记账逻辑在 Service 层可发现(TurnAccountantService 单一入口),以便改计费规则(如未来按时长计费、按 agent 差异化定价)时不必翻 API 路由文件;仓库分层检查(铁律 1/2)对 chat 域的记账段通过。
7. 作为巡检 agent,我希望 chat.py 计费编排块从 171 行收缩、API 层不再直摸 UsageEventRepository,以便第 12 次巡检「候选 ② 四度复现」的恶化读数终止并记档关闭。

## 4. Implementation Decisions

### 4.1 影响面清单(项目特化,必填)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 2 | `app/services/turn_accountant_service.py`(新建,TurnAccountantService 两入口 + 单核心 + `_u` 迁入)、`app/api/v1/chat.py`(删 `_record_usage`/`_charge_usage`/`_record_composite_usage` 三函数 + 三调用点收缩为单调用 + import 收拾) |
| 数据库迁移 | 0 | 零 schema 变化(纯代码迁移) |
| 前端文件改动 | 0 | API 契约零变化,前端零感知 |
| 测试文件改动 | 1 | `tests/test_turn_accountant.py`(新建,seam 直接单测 4 条,见 §5);`tests/test_usage_tracking.py` / `tests/test_composite_chat.py` **零改动** |
| Skill / Hook / 配置 | 0 | — |

### 4.2 多租户影响评估(项目特化)

- 是否新增租户 scoped 表? **NO**(零 schema 变化)
- 是否修改现有租户隔离逻辑? **NO**(UsageEvent 的 tenant_id 取自 `conv.tenant_id` 逐字保持;UsageEventRepository 继承 TenantScopedRepository 的写路径 `add` 原样)
- 是否引入跨租户访问点? **NO**(两路径均为本租户对话记账,tenant_id 取自 conv.tenant_id;super_admin 对话同样记账,现状如此且不动)
- 验证:既有 `test_usage_events_tenant_isolated`(UsageEventRepository 租户隔离)零改动通过即证。

### 4.3 权限影响评估(项目特化)

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(两路由的 `conversations:chat` 门与 composite 的 per-agent 二次 check 原样)
- 是否影响 graph.py 工具内 check? **NO**
- 验证:既有 chat/composite 权限用例零改动通过即证。

### 4.4 数据库表设计 checklist(呼应 AGENTS.md 铁律 6)

不适用——零新表、零列变化、零迁移。UsageEvent/WalletTransaction 两表现有结构与写入路径完全不动。

### 4.5 决策表(D1-D3 用户逐项拍板;D4-D7 未获回复按先例推荐采纳,复核窗口 = EP3 开工前)

| # | 决策 | 结论 | 状态 |
|---|---|---|---|
| D1 | seam 形态 | **新建 `TurnAccountantService`**(`app/services/turn_accountant_service.py`),镜像 PricingService/BillingService 先例;依赖单向 API → TurnAccountantService → UsageEventRepository/BillingService;UsageEventRepository 直摸与延迟 import 自然归位消失 | ✅ 用户拍板(采纳推荐) |
| D2 | 两路径统一程度 | **两薄入口 + 单核心**:`record_stream_turn`(SSE 形态)与 `record_composite_row`(三元组形态)两个 public 方法,内部共享同一 `_record_and_charge` 核心;入参形态差异(流式聚合 dict vs 已解析三元组)是两路径真实差异,保留薄适配、消灭行为双实现;不造宽签名 | ✅ 用户拍板(采纳推荐) |
| D3 | SSE 是否 paired charge | **SSE 也 paired,收进 seam**:两路径调用点都变单次调用,record→charge 顺序契约真正单点持有;行为等价有保证(charge 对 None 跳过 / record 失败不 charge / charge 失败 rollback 不伤已 commit 事件行,逐字镜像现有语义) | ✅ 用户拍板(采纳推荐) |
| D4 | 钱包门 `_require_wallet_balance` 处置 | **不动,留 API 层**——钱包门是预检(连接前拦 402)不是记账编排;feature 94 刚稳定的共享 helper 位置零风险;范围收窄为纯记账编排收口 | 未获回复按推荐采纳 |
| D5 | composite N+1 循环形态 | **保持循环,循环体改调 seam**——循环是端点编排(fragments 迭代 + token 解析天然在端点),「serial 不是 gather」(FOR UPDATE 串行化)注释留在调用处仍成立;seam 不需要知道 composite_query 的 result dict 形状 | 未获回复按推荐采纳 |
| D6 | 测试策略 | **既有 6 例零改动(green-on-both)+ 新增 seam 直接单测 4 条**锁配对语义(无 usage 不记不扣 / record 失败不 charge / charge 失败不伤事件行 / paired 全链事件+txn+余额)。镜像 pricing-service-extraction 先例 | 未获回复按推荐采纳 |
| D7 | 切片数 | **1 切片**(~171 行块收口 + 新 service 文件,一天内;SSE/composite 拆两片无自然边界——共用同一新文件;单切片 = 末切片一次 PR 端到端,镜像 feature 92/97/98 单切片先例) | 未获回复按推荐采纳 |

工程判断项(非用户拍板,EP2 会话内定,依据如下):

- **方法签名收 `user_id: str` 而非 `CurrentUser` 对象**:`CurrentUser` 定义在 `app/api/deps.py`(API 层),Service import 它违反铁律 1 方向;镜像 PricingService 收 `operator_id: str` 先例。调用点传 `user.user_id`,行为零变化。
- **`_u()`(usage dict 取数 helper)迁入 seam 模块并回供 chat.py import**:它有双消费者(seam 内 SSE 入口解析 + chat.py `append_message` 的 token 列参数);迁移后 chat.py `from app.services.turn_accountant_service import TurnAccountantService, _u`,避免第二份实现(API → Service import 方向合法)。私有名跨模块 import 不理想,但它是 SSE usage dict 形态的领域解析,归 seam 模块最内聚;EP3 落地时可改名公开(如 `extract_usage_int`)——两形态任一都行,EP3 定。
- **record 失败容错统一带 `logger.exception`**:现状 SSE 版 `_record_usage` 静默吞(注释说明但无日志)、composite 版有 `logger.exception`——单核心收口后统一带日志。这是**有意的良性超集**(可观测性对齐:composite docstring 的「N+1 rows amplify the cost of a quiet bug」论据同样适用于 SSE 单行;API/SSE 帧/DB 行为零变化),§7 自审 🟡 留痕。
- **`charge` 的 `operator_id=None` 逐字保持**(两路径现状都是 None,consume 交易无操作人),不「顺手」透传 user_id——那是行为变化。

### 4.6 收口规格(逐处)

**新建 `app/services/turn_accountant_service.py`**:

- `class TurnAccountantService`,`__init__(db: AsyncSession)` 持 `self.db` 与 `UsageEventRepository(db)`(镜像 BillingService 的 repo 持有形态);模块级 import `BillingService`(service→service 无环,消除 API 层延迟 import);
- `async def record_stream_turn(conv: Conversation, msg: Message, agent_id: str, user_id: str, usage_data: dict | None) -> UsageEvent | None`——SSE 薄入口:`usage_data is None` 或 `total_tokens` 缺失 → 直接返回 None(不记不扣,守卫逐字迁移自 `_record_usage` L102-105 与调用点 `if usage_data and _u(...)` 条件);否则 `_u` 解析三元组后走核心;
- `async def record_composite_row(conv: Conversation, msg: Message, agent_id: str | None, user_id: str, *, prompt_tokens: int, completion_tokens: int, total_tokens: int, model: str) -> UsageEvent | None`——composite 薄入口:三元组直传核心(`agent_id: str | None`——synthesize 行为 None);
- 私有核心 `async def _record_and_charge(...)`——归一后的构造参数统一落 UsageEvent(**字段与 kwargs 逐字对齐现状**:tenant_id=conv.tenant_id / conversation_id=conv.id / message_id=msg.id / agent_id / customer_id=conv.customer_id 透传 / user_id / model / prompt_tokens / completion_tokens / total_tokens / cost=None)+ `repo.add` + `await db.commit()`;失败 `logger.exception` + `await db.rollback()` + return None(不 charge);成功后 paired `BillingService(self.db).charge(tenant_id, event, operator_id=None)`,charge 异常 `logger.exception`(文案镜像现有 `"wallet charge failed (tenant=%s, event=%s)"`)+ `await db.rollback()`(事件行已 commit 存活);返回 event(或 None);
- docstring 必须写明三件事:① record→charge 顺序契约在本类单点持有(对账 job 的一致性地基,链接 CONTEXT.md「对账」词条);② 两入口的差异只是入参形态适配(取代旧「NOT shared」声明);③ best-effort 语义(记账/扣费失败不破坏已成功的对话回复)。

**`app/api/v1/chat.py` 收缩**:

- 删模块级 `_record_usage` / `_charge_usage` / `_record_composite_usage` 三定义与 `_u`(迁走);`_require_wallet_balance` **原样保留**(D4);
- SSE 正常分支(现 L389-393)收缩为 `await TurnAccountantService(db).record_stream_turn(conv, msg, agent.id, user.user_id, usage_data)`;异常分支(现 L364-370)去掉外层 `if usage_data and _u(...)` 守卫(守卫入 seam)同样单调用;两处注释改为指向 seam;
- composite N+1 循环(现 L528-552)**保持循环形态**,循环体与 synthesize 行各改调 `record_composite_row`(frag 的 agent_id / synthesize 行 None 语义原样);「serial 不是 gather」注释留原地;
- import 收拾:删 `UsageEvent` / `UsageEventRepository`(收口后 chat.py 零消费);`BillingService` 延迟 import 随 `_charge_usage` 消失(钱包门内的延迟 import 保留,属 D4 不动);新增 `from app.services.turn_accountant_service import TurnAccountantService`(+ `_u` 或其公开名);
- 计费编排块预期从 ~171 行收缩到 ~20 行(钱包门 18 行 + 三行调用点注释),chat.py 总行数 558 → ~430。

### 4.7 取证留痕(源码级,本 EP2 会话 grep/直读确认)

1. **双实现镜像面**:`_record_usage`(L84-131)与 `_record_composite_usage`(L162-223)的 UsageEvent 构造 kwargs(11 字段)、`repo.add` + `commit`、except→rollback、返回 event 逐字同构;差异仅:①入参形态(Agent 对象 + usage dict vs 三元组 + agent_id)②composite 版尾随 paired charge(L222)与 except 带 logger.exception(L211)③SSE 版 except 无日志(§4.5 工程判断项:统一带日志,良性超集)。
2. **SSE 顺序敏感实锤**:正常分支 `event = await _record_usage(...)` → `await _charge_usage(...)`(L389-393)与异常分支(L365-370)是两份手写顺序;charge 漏调/顺序颠倒编译期不可见,只能靠对账 job 事后发现——D3 收口的结构性收益。
3. **既有 6 条行为锚定用例,全 HTTP 接缝断 DB 行**:test_usage_tracking.py 4 例(records_usage_on_message_and_ledger / without_usage_keeps_nulls_and_no_ledger / interrupted_stream_records_partial_usage / usage_events_tenant_isolated)+ test_composite_chat.py 2 例(records_n_plus_1_usage_events / customer_id_propagated_to_usage_events)——均不 import 被迁移符号,收口后天然零改动。
4. **三函数零外部消费者**:`_record_usage|_charge_usage|_record_composite_usage` 全仓 grep 仅 chat.py 自身(定义 + 3 调用点)——迁移无隐藏耦合面。
5. **CurrentUser 在 API 层**:`app/api/deps.py` 定义(`CurrentUser = Annotated[...]`),Service 层不可 import(铁律 1)——签名收窄 user_id 的依据。
6. **对账地基**:`BillingReconciliationService._find_missed_events`(L316-321)的 `~_CONSUME_TX_EXISTS`(NOT EXISTS consume txn 配对)逐事件检出漏扣——record→charge 配对是对账正确性的定义基础;`BillingService.charge` docstring 自述「Reconciliation from usage_events recovers the missing charge later」。
7. **wallet gate 延迟 import 是刻意设计**:`_require_wallet_balance` 内 `from app.services.billing_service import BillingService`(L63)函数内 import——feature 94 落地形态,D4 不动它,收口后 chat.py 仅剩这一处延迟 import。
8. **charge 无钱包语义**:wallet 不存在 → charge 返 None(跳过扣款,事件行留存由对账兜底)——seam paired 后此语义逐字保持(`_charge_usage` 对 event None 早退的守卫移入核心入口)。

## 5. Testing Decisions

- **测试哲学**:纯结构迁移,外部行为逐字不变是唯一验收面——既有 HTTP 接缝用例就是验收器;新增 seam 直接单测只为锁「配对契约在 seam 内部」这个结构性质(HTTP 接缝断不到 seam 内部,但它是本 feature 的存在理由)。
- **既有 6 用例零改动通过**(§4.7-3 清单)= 主验收;执行顺序:收口前先跑一遍确认基线绿,收口后再跑确认仍绿(green-on-both)。
- **新增 `tests/test_turn_accountant.py` 4 条直接单测**(db_session 接缝,镜像 test_billing.py 的 BillingService 直连单测形态):
  1. `无 usage / total None → 不记不扣`(两入口各覆盖:0 行 UsageEvent + 0 行 WalletTransaction + 钱包余额不变);
  2. `record 失败不 charge`(monkeypatch repo.add 抛 → 返回 None + 0 事件行 + 0 txn + 余额不变);
  3. `charge 失败不伤已 commit 事件行`(monkeypatch BillingService.charge 抛 → 事件行存活 + rollback 干净 + 返回 event);
  4. `paired 全链`(funded wallet → record_stream_turn 一次调用 = 1 事件行 + 1 consume txn + 余额扣减 + total_consumed 累计;record_composite_row 对称一条)。
- **全量门**:`./init.sh full` 零回归 + ruff 绿(新文件 import 排序)+ 前端 build 绿(零前端改动确认,git diff frontend/src 为空)。
- 多租户/权限:不新增(§4.2/§4.3 既有用例零改动通过即证)。

## 6. 切片规划

### Ticket 1(唯一切片):TurnAccountantService 收口 + 三调用点收缩 + seam 单测
- **What to build**: 两路径记账编排收口进 TurnAccountantService(两薄入口 + 单核心 paired charge),chat.py 三调用点变单调用、三函数删除;既有 6 例零改动通过 + 4 条 seam 单测新增;全量零回归。
- **Blocked by**: 无
- **文件清单**: 2 改后端(1 新建)+ 1 新测试
- **验证命令**: `pytest tests/test_usage_tracking.py tests/test_composite_chat.py tests/test_turn_accountant.py -q`(先基线后回归)+ `grep -n "UsageEventRepository\|_record_usage\|_charge_usage\|_record_composite_usage" app/api/v1/chat.py`(应为 0 处)+ `./init.sh full`

## 7. 对抗式审查(轻量自审;未触发复杂任务条件 —— 文件 ≤3、无鉴权/迁移/跨服务变化)

单模型双轴自查(Standards:铁律/分层/范式;Spec:本 plan 承诺 vs 代码现状),三项发现已吸收进 v1 正文:

- 🟡 **SSE record 失败静默吞 vs composite 有日志的不对称**(Spec 轴):单核心统一后无法同时保持两种容错——保持逐字镜像意味着核心要参数化「是否打日志」,为一个静默路径保留分支复杂度不值。→ **采纳**:统一 `logger.exception`(可观测性增强,API/SSE 帧/DB 行为零变化),§4.5 工程判断项 + §4.6 核心规格已按此写;EP3 实施注记如实记录这一良性超集。
- 🟡 **`_u` 跨模块私有名 import 的形态摇摆**(Standards 轴):`from ... import _u` 私有名跨模块在 lint 与可读性上欠佳,但 `_u` 留 chat.py 则 seam 内出现第二份 dict 解析(违背本 feature 消灭双实现的初衷)。→ **采纳**:迁入 seam 模块,EP3 落地时改名公开(`extract_usage_int` 或保留 `_u` + chat.py 改用 seam 的解析结果——两形态任一,EP3 定,不再造双份)。v1 已在 §4.5 工程判断项记档。
- 🟢 **`record_stream_turn` 返回值在 SSE 调用点成为死值**(Standards 轴):paired 后调用点不再消费返回 event(旧代码拿它传给 `_charge_usage`)。→ **保留返回**(composite 版现状 docstring 自述「for test observability」,seam 单测需要断言返回;对称起见两入口都返 `UsageEvent | None`),非死代码。

## 8. Out of Scope

- ❌ 钱包门 `_require_wallet_balance` 任何改动(D4:留 API 层,含其内部延迟 import)
- ❌ `BillingService.charge` / `recharge` / `calc_cost` 方法体任何改动(只消费 charge,operator_id=None 逐字保持)
- ❌ API 路由路径/签名/response_model/状态码/权限门/SSE 帧格式任何变化
- ❌ UsageEvent / WalletTransaction / Wallet 表结构与任何 alembic 迁移
- ❌ composite N+1 循环的 batch 化 / gather 并行化(D5:循环形态保持;「serial 不是 gather」语义不动)
- ❌ graph.py 三路分家(候选 ③)、usage_acc 三份循环收敛(候选 ③ 附带项)——独立巡检候选,不入本 feature
- ❌ CLI(cli/commands/chat.py,走 /chat/stream API 零感知)与前端任何文件
- ❌ 对账 job(billing_reconciliation_service)任何改动——它是收口收益的受益方不是改动方
- ❌ 顺手重构无关代码(命名/注释风格/格式化蔓延)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 迁移手误改语义(UsageEvent kwargs 抄错 / record-charge 顺序颠倒 / 守卫丢失) | 高 | 既有 6 用例零改动全绿(先跑基线,green-on-both)+ §4.6 硬要求构造 kwargs 逐字对齐现状(EP3 diff 对照留痕) |
| seam 内部配对语义无直接锤(HTTP 接缝断不到) | 中 | 新增 4 条 seam 直接单测(D6,§5),锁「不记不扣 / record 失败不 charge / charge 失败不伤事件行 / paired 全链」 |
| 异常分支(流中断)守卫迁移走样(SSE failed turn 的 partial usage 记账) | 中 | `test_interrupted_stream_records_partial_usage` 零改动通过即锁;守卫逐字迁移进 seam(§4.6) |
| SSE 调用点漏改(收口后仍残留旧两步调用) | 低 | EP3 验证命令 `grep "_record_usage|_charge_usage|_record_composite_usage" app/api/v1/chat.py` = 0;ruff F401 兜住死 import |
| import 残留 / 循环引用 | 低 | ruff 门 + seam 只 import repo/model/billing_service(无反向依赖,铁律 1 方向天然成立) |
| conftest 事务语义与 best-effort 断言交互 | 低 | feature 97 已把 test engine 对齐 PG 回滚语义;seam 单测的「事件行存活 / rollback 干净」断言直接可信 |

## 10. 验收标准(同步 feature_list.json verification)

1. 既有 SSE 计费 4 用例零改动通过(test_usage_tracking.py:records_usage_on_message_and_ledger / without_usage_keeps_nulls_and_no_ledger / interrupted_stream_records_partial_usage / usage_events_tenant_isolated);执行序列 = 收口前基线绿 → 收口后仍绿。
2. 既有 composite 计费 2 用例零改动通过(test_composite_chat.py:records_n_plus_1_usage_events / customer_id_propagated_to_usage_events)。
3. record→charge 顺序契约单点持有:chat.py 三调用点(SSE 正常/异常 + composite N+1 循环)全部为对 TurnAccountantService 的单次调用;`grep "_record_usage|_charge_usage|_record_composite_usage" app/api/v1/chat.py` = 0 处。
4. 分层合规:`grep "UsageEventRepository" app/api/v1/chat.py` = 0 处(API 层不再直摸 repo);依赖向 API → TurnAccountantService → UsageEventRepository/BillingService 单向。
5. 新增 tests/test_turn_accountant.py 4 条 seam 单测通过(不记不扣 / record 失败不 charge / charge 失败不伤事件行 / paired 全链)。
6. UsageEvent 构造 kwargs 与现状逐字一致(EP3 diff 对照留痕);`operator_id=None` 保持;SSE record 失败统一 logger.exception(良性超集留痕)。
7. `./init.sh full` 全量零回归 + ruff 绿 + 前端 build 绿(git diff frontend/src 为空)。

## 11. 不越界声明

本次改动**只**涉及:新建 app/services/turn_accountant_service.py(TurnAccountantService 两入口 + `_record_and_charge` 核心 + `_u` 迁入)、app/api/v1/chat.py 三计费函数删除 + 三调用点收缩 + import 收拾、tests/test_turn_accountant.py 新建 4 条 seam 单测。**不**触碰:钱包门与 BillingService 方法体、API 契约与权限门、UsageEvent/Wallet/WalletTransaction schema 与迁移、composite N+1 循环形态、graph.py、对账 job、CLI 与前端、容错语义(除 §7 🟡 有意统一 record 失败日志)。

## 12. 实施切片(to-tickets 产出)

### 切片依赖图

```
01 ⬜(唯一 = 末切片,Blocked by: 无)
```

### 切片 01 — TurnAccountantService 收口 + 三调用点收缩 + seam 单测(末切片 = feature 收官)
- **Blocked by**: 无(可立即开工)
- **What it delivers**: 两路径记账编排(record + paired charge)收口进 TurnAccountantService 单 seam,record→charge 顺序契约单点持有;chat.py 计费编排块 ~171 行 → ~20 行,API 层 UsageEventRepository 直摸清零;外部行为逐字不变——既有 6 条计费用例零改动通过 + 4 条 seam 单测新增;feature 收尾八步同片闭环。
- **Acceptance criteria**:
  - [ ] `app/services/turn_accountant_service.py` 新建:TurnAccountantService(`record_stream_turn` + `record_composite_row` 两薄入口 + `_record_and_charge` 单核心 paired charge);UsageEvent 构造 kwargs 与现状逐字一致(diff 对照留痕);record 失败统一 `logger.exception` + rollback + 不 charge;charge 失败 `logger.exception`(文案镜像现状)+ rollback + 事件行存活;`operator_id=None` 保持
  - [ ] `_u`(或其公开改名)迁入 seam 模块,chat.py 不再自有 dict 解析副本(无双份实现)
  - [ ] `app/api/v1/chat.py`:删 `_record_usage`/`_charge_usage`/`_record_composite_usage`;SSE 正常/异常两调用点 + composite N+1 循环体改单调用;守卫(`if usage_data and _u(...)`)逐字迁入 seam 入口;import 收拾(UsageEvent/UsageEventRepository 出);`_require_wallet_balance` 与其延迟 import 原样保留(D4);「serial 不是 gather」注释留原地(D5)
  - [ ] `grep -n "_record_usage\|_charge_usage\|_record_composite_usage\|UsageEventRepository" app/api/v1/chat.py` = 0 处
  - [ ] `tests/test_turn_accountant.py` 新建 4 条 seam 单测通过(不记不扣 / record 失败不 charge / charge 失败不伤事件行 / paired 全链事件+txn+余额)
  - [ ] 既有 6 条计费用例零改动通过(收口前基线绿留痕 → 收口后仍绿)
  - [ ] `./init.sh full` 零回归 + ruff 绿 + 前端 build 绿(git diff frontend/ 为空)
  - [ ] feature 收尾八步(three-tier §4:全量验证/status+evidence/sync-active/progress.md/checklist/文档影响评估/依赖解锁扫描/分支清理)

> EP2 plan 自检(four-tier §3):① 切片依赖图无环(单切片)✅ ② 每片有 AC(8 条 `- [ ]`)✅ ③ 首片可立即开工(Blocked by: 无)✅ ④ plan 主体决策已落定(D1-D7 全拍板/按先例采纳,零 TODO 悬空)✅
