# 计划:计费对账闭环(billing-reconciliation-job)

> **id**: billing-reconciliation-job
> **状态**: passing(EP3 全 2 切片完成 2026-08-17:切片 01 PR #171 对账 job 核心 + 切片 02 末切片超管 targeted 通知 + feature 收官;与 feature_list.json 同 commit 翻页)
> **优先级**: 93(feature_list.json,第 10 次巡检业务风险 R3 后半 🔴)
> **创建日期**: 2026-08-17
> **最后修订**: 2026-08-17(v2:双轴自审回写)
> **来源**: [plan-risk-hardening-overview.md](./plan-risk-hardening-overview.md) §4(总纲 D5 已拍板:先钱包门止血后对账兜底,两 feature 都不动 TurnAccountant;止血已由 chat-stream-wallet-gate ✅ passing 完成)
> **EP2 回环**: grill(2026-08-17,总纲钦定 5 项决策点 + 烤问扩展共 10 项,**前 7 项用户逐项拍板无默认采纳**;后 3 项属次级工程形态,问询未获回复,按工程判断采纳并在 §4.6 D8-D10 如实标注)→ to-spec(v1)→ 对抗式自审(单模型双轴)→ to-tickets(v2,§7)

---

## 0. v1 → v2 变更摘要(双轴自审回写,2026-08-17)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| 「幂等:同窗口重跑不产生重复差额记录」(feature verification 第 3 条)在 v1 只靠「事件首告去重」解释,漏了 run 记录本身的重复:重跑同窗口会再插一条 SystemLog run 记录,严格违反字面验收 | 🔴 | 补 **as_of 日粒度幂等锁**:job 记录 details_json 带 `as_of`;重跑时最近一条 run 记录的 as_of 日期 == 本次 → skip(返回已跑摘要);`force=True` 供人工强制重跑(切片 01 AC4) |
| 事件级漏扣判据只写「无 consume 交易」,未处理 `usage_event_id` FK 的 SET NULL 语义:事件被删(conversation 级联删)会把交易的 usage_event_id 置 NULL,该交易在事件级 join 中消失但聚合层仍在——聚合残余差会告警但归因不明 | 🟡 | §4.7 明确双层互补语义:事件级管「漏扣方向」,聚合**残余差**(聚合差 − 已知漏扣 token 量)管「交易侧异常方向」(含 SET NULL 孤儿交易、手工改动);两方向独立告警,归因写进 details_json |
| 漏扣明细的成本口径未定:v1 草案含「按当前定价重算成本」,与 D7 只报不补精神冲突(calc_cost 现价 ≠ 当时价,数字有误导性) | 🟡 | 定死:**明细只报 token 事实数,不重算成本**(成本快照当时未存,现价重算会误导补扣决策);plan §4.6 D7 延伸决策 |
| 已告事件集合的来源(历史 run 记录 details_json 合并)未评估数据量与失效边界:人工用 adjust 补账后事件仍在漏扣名单,存量数永不下降,可能被认为 bug | 🟡 | §8 Out of Scope 明确:告警消除/补扣状态机不做(人工补账后事件仍计为「存量已告」,语义在 details_json 注释与 §5 测试锁语义);将来做补扣闭环时再评估 |
| 通知 targeting 的租户定位只说「超管所在租户」,未定多 membership 超管的落点与无 membership 超管的处置 | 🟡 | §4.7 钉死:取该超管**首个 active membership**(valid_to IS NULL)租户;无 membership 超管跳过并 logger.warning(不崩 job);测试锁两条边界 |
| 切片 01 文件清单漏 `scheduler.py` 注册行与 job 薄壳的体量预估,切片 02 漏 CONTEXT.md 术语条目 | 🟡 | §7 文件清单补齐(scheduler.py 薄壳 + _register_jobs 注册行;切片 02 含 CONTEXT.md「对账」术语) |
| `scheduler_enabled` 默认 False 与「对账静默不跑」的关系未写:v1 未说明本 job 同样受总开关管,读者可能误以为对账独立于开关 | 🟢 | §4.7 + §9 注明:job 注册受 `_SCHEDULER_ENABLED` 总开关管(生产单副本显式 True),开关显式化归 config-startup-guard(R5),本 feature 不越界改默认值 |
| 通知 type 取值未定,可能被实现随手新造枚举值导致前端图标缺省 | 🟢 | 钉死:复用现有 `"system"` 类型(模型注释枚举内,零前端改动);§4.7 |
| 审计页 link 路径未查证(job 通知的 link 指向哪) | 🟢 | §4.7 留待 EP3 实施时以 audit-log-ui 实际路由为准(plan 不写死未知路径,避免笔误进 AC) |

## 1. Problem Statement

计费链路的 UsageEvent 写入与钱包扣费是**两个独立事务**(第 10 次巡检 R3 后半 🔴):

- SSE 路径 `_record_usage` 先 commit 事件(`cost=NULL`),`_charge_usage` 再开独立事务 charge;composite 路径 `_record_composite_usage` 同构(record commit → paired charge)。
- charge 失败(并发冲突、DB 抖动)仅 `logger.exception` + rollback → **cost 留 NULL、无 consume 交易,少扣费静默发生**;`charge()` 遇无钱包返回 None 同样不盖章不落交易。
- `billing_service.py` docstring 宣称的 "Discrepancies are reconciled from the usage_events ledger" 对账 job **并不存在**——差额无人发现,少扣的 token 从平台净值里静默蒸发。

钱包门(chat-stream-wallet-gate ✅)已把「新会话无钱包/零余额」拦在 402,**止血**完成;本条做**兜底**:让已经发生的与残余的漏扣从静默变可见。

## 2. Solution

挂现有 APScheduler 框架新增每日对账 job(09:30,错开 09:00 余额扫描):**双层核对** usage_events 聚合 vs wallet_transactions——事件级 LEFT JOIN 检出每条「有事件无 consume 交易」的漏扣明细(可定位到租户/会话/模型/token 数),聚合层兜住事件级查不出的交易侧异常(残余差)与钱包不变式漂移。结果每次 run 必落一条 SystemLog(有差额 warning、无差额 info,details_json 带全量明细与统计);有新差额时三通道告警:logger.error + SystemLog 留痕 + 逐 super_admin targeted in-app 通知。**只报不补**——补扣由运营拿明细人工决策(走既有 `adjust` 交易类型),定价快照漂移与租户关系判断不交给自动化。

零新表、零迁移、零前端改动、零计费链路改动(只读对账,不动 charge/recharge 编排)。

## 3. User Stories

1. 作为平台运营(super_admin),每天的对账结果自动出现在审计日志页(无差额也有 info 记录),以便我确信「对账跑过了且干净」,而不是「根本没跑」。
2. 作为平台运营,当发生漏扣(有 usage_event 无 consume 交易)时,我在铃铛收到 targeted 通知并在审计日志看到明细(租户/会话/模型/token 数),以便我决定是否手工调账。
3. 作为平台运维,charge 失败不再只留一条没人看的 logger.exception——差额有系统性出口(logger.error + SystemLog + 通知三通道),少扣费从静默变可见。
4. 作为平台运营,同一条漏扣事件不会被天天重复告警轰炸——它首次发现时告警,之后在例行日报的「存量未处理」统计中保持可见。
5. 作为平台运营,若有人手工改动钱包余额或交易(绕过 charge 编排),聚合残余差/钱包不变式检查会兜底告警——事件级 join 查不出的反向异常也有覆盖。
6. 作为租户 owner,对账 job 对我完全透明:只读我的账本,不改余额、不补扣、不发面向租户的告警(差额告警只发给平台超管)。
7. 作为开发者,对账 job 的四组行为(检出/零误报/幂等/首告去重)有 SQLite 常驻回归测试,镜像 `scan_balance_warnings` 的可测范式(session_factory 注入)。
8. 作为多副本部署的运维,job 挂在既有 `_register_jobs` 注册点,与余额扫描共用 `scheduler_enabled` 总开关与单副本纪律,不引入新的部署面。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 2 | `app/core/scheduler.py`(+`reconcile_billing` 薄壳 job ~20 行 + `_register_jobs` 注册行);`app/services/notification_service.py` 等零改动 |
| 后端文件新增 | 1 | `app/services/billing_reconciliation_service.py`(`BillingReconciliationService`:双层检出 + 幂等锁 + 首告去重 + 三通道告警编排,~200-250 行) |
| 数据库迁移 | 0 | 复用 SystemLog 落结果(D6),零 schema 改动 |
| 前端文件改动 | 0 | 通知走既有铃铛(type="system" 现成图标),结果查看看既有 audit-log-ui |
| 新增测试 | 1 | `tests/test_billing_reconciliation.py`(SQLite 常驻,10-12 用例) |
| 文档 | 1-2 | `CONTEXT.md` 术语「对账(Reconciliation)」(切片 02);项目指南计费文档注记(收尾时评估) |
| CI / CLI | 0 | 零改动(纯后端 job;E2E 不触对账路径) |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(零 schema)
- 是否修改现有租户隔离逻辑? **NO**(对账是**平台级只读横切查询**,按 tenant_id 分组聚合,不修改任何租户作用域读写路径)
- 是否引入跨租户访问点? **读侧 YES(有意)**:job 全量扫描所有租户的 usage_events/wallet_transactions/wallets——这是对账的本质;**无 API 端点**(不暴露 HTTP 面),仅在 scheduler job 内运行;告警只发给 super_admin,不向租户泄露他人差额
- 验证:既有租户隔离测试零回归(`./init.sh full`);对账测试断言 per-tenant 明细不串租户

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(无新端点)
- 是否影响 graph.py 工具内 check? **NO**
- super_admin 交互面:只新增「收通知 + 审计页可查」两条既有基础设施的消费,不新增写操作(与 R4 super-admin-write-audit 的三处写审计正交,不抢线)

### 4.4 数据库表设计 checklist(AGENTS.md 铁律 6)

- 无新表无新列无索引无迁移 — **全部 N/A**(D6 拍板复用 SystemLog;按需加表铁律下,当前无独立读写面——无对账管理页、无补扣闭环——不预建 `reconciliation_runs` 空架子)
- 历史已告事件集合存于 run 记录 details_json(每天 ≤1 条 + force 重跑若干,一年 ~400 行,Python 侧合并可接受;若将来量大或要做管理页,建表时机在补扣闭环立项时)

### 4.5 用户拍板决策(D1-D7,2026-08-17 AskUserQuestion 前两轮逐项拍板,无默认采纳)

| # | 决策点 | 拍板结果 |
|---|---|---|
| D1 | 对账口径 | **双层:事件级 + 聚合**。事件级 LEFT JOIN(usage_events ⟖ wallet_transactions ON usage_event_id)检出每条漏扣明细;聚合层兜住事件级查不出的漂移。否决:仅事件级(检不出交易侧反向异常)/ 仅聚合(无明细不可操作) |
| D2 | 对账周期 | **日报一天一次**(09:30,错开 09:00 余额扫描)。兜底性质下小时级收益有限噪音更高 |
| D3 | 差额容忍 | **精确 0 + 回看缓冲**:判定标准精确为 0 不设金额阈值;事件级判定只看 `created_at` 早于 now−30min 的事件(避开在途误报;token 整数计数无 rounding,真实噪声源只有窗口边界在途) |
| D4 | 重复告警策略 | **事件粒度首告 + 汇总提及**:每条漏扣事件只在首次发现时触发告警(事件 id 去重);后续 run 仍未处理 → 例行日报统计「存量未处理数」可见,不逐条重新告警 |
| D5 | 告警通道 | **三通道全上**:logger.error(运维日志)+ SystemLog 留痕(audit-log-ui 可查)+ 逐 super_admin targeted in-app 通知(主动推铃铛;平台级 tenant_id=NULL 通知实际不可见[repo 等值匹配],必须 per-user targeting) |
| D6 | 结果落表 | **复用 SystemLog**:每 run 一条 `action=billing_reconciliation`,details_json 放窗口/统计/per-tenant 差额与事件明细。零新表零迁移;将来做对账管理页/补扣闭环时再评估建表 |
| D7 | 自动补扣 | **只报不补**(总纲建议采纳):补扣需重算定价快照(calc_cost 现价可能已错)、租户关系/是否免单需人判断、误补直接动余额二次事故;补扣由运营拿明细走既有 `adjust` 交易类型手工调账 |

### 4.6 次级工程形态决策(D8-D10,问询未获回复,按工程判断采纳——如实标注,非用户拍板)

> 第 3 轮 3 问(例行日报形态/缓冲值/切片数)发出后未获用户回复。总纲钦定的 5 项决策点(周期/容忍/通道/补扣/落表)已全部在前两轮获用户拍板;以下 3 项为次级工程形态,按最佳判断采纳**推荐项**,EP3 实施前用户仍可推翻(改动只影响 plan §7,不影响 D1-D7 语义)。

| # | 决策点 | 采纳结果(工程判断) |
|---|---|---|
| D8 | 例行日报形态(无差额时) | **SystemLog info 一条**:每 run 必落一条(有差额 level=warning,无差额 level=info),details_json 含统计(检查租户数/扫描事件数/新告漏扣/存量未处理/聚合残余差/钱包漂移数)。理由:scheduler_enabled 默认 False 叠加下,「跑了没差额」vs「根本没跑」必须可区分 |
| D9 | 回看缓冲具体值 | **30 分钟**:charge 在事件 commit 后同请求内同步 await,正常在途窗口毫秒~秒级,30min 高三个数量级冗余;日报频率下对发现时效几乎无影响 |
| D10 | 切片结构 | **2 片线性**:01 对账 job 核心(检出+幂等+落表+logger 通道+核心测试)→ 02 超管通知接入+文档+feature 收尾。体量均衡、依赖单一 |

### 4.7 其他实施决策(技术形态,EP2 定死防实施漂移)

- **Service 分层**:对账逻辑放新 `app/services/billing_reconciliation_service.py`(BillingReconciliationService,多模型聚合属业务层,依赖单向 Service→Model/Repository 合规);`scheduler.py` 只留薄壳 job(镜像 `scan_balance_warnings` 签名范式:`async def reconcile_billing(session_factory=None)`,函数体调 service 并处理异常兜底)。**不学 scan_balance_warnings 把逻辑直接写在 scheduler.py**——那是 60 行单查询的体量豁免,本 job 200+ 行不适用
- **幂等锁(as_of 日粒度)**:run 记录 details_json 带 `as_of`(本次判定基准时刻);job 启动时查最近一条 `action=billing_reconciliation` 的 SystemLog,若其 as_of 与本次**同日**且未传 `force=True` → skip 并 logger.info 返回上次摘要。测试传显式 `as_of` 控制窗口,`force` 供人工重跑。这与 D4 事件首告去重构成双幂等:run 记录不重插(日粒度)、事件不重告(事件粒度)
- **事件级检出血义**:`usage_events ue WHERE ue.created_at < as_of − 30min AND NOT EXISTS (SELECT 1 FROM wallet_transactions wt WHERE wt.usage_event_id = ue.id AND wt.type = 'consume')`。`cost IS NULL` 不作判据(charge 失败回滚后 cost 必为 NULL,与无交易同义;但「有交易而 cost NULL」属数据损坏,由聚合层兜住)
- **聚合层两条独立检查**:(a) per-tenant 残余差 = `SUM(usage_events.total_tokens) − (−SUM(consume.amount)) − 已知漏扣 token 量` ≠ 0 → 交易侧异常方向(SET NULL 孤儿交易/手工改动/多扣);(b) 钱包不变式 `wallet.balance ≠ wallet.total_recharged + Σ(refund,adjust 正向额) − wallet.total_consumed` → 钱包漂移(现网只有 recharge/consume,refund/adjust 无写入路径,检查式按通用形式写防未来误报)。残余差**不需要** 30min 缓冲——它不做在途判定,只报事件级解释不了的部分
  - *EP3 切片 01 实施注记(2026-08-17,code-review Spec 轴回写)*:(a) 的两个 SUM 与事件级**共用同一 cutoff 窗口**(事件侧与交易侧都按 `created_at < as_of−30min`)——否则缓冲内在途未扣事件会进入「事件总量−已扣量」却不在漏扣名单,残余差误报、用例 5(−5min 不告)在聚合层翻车;漏扣事件在两侧对消,残余差仍只报交易侧异常(「不需要缓冲」应读作「不需要第二个缓冲概念」,窗口复用单源常量 `LOOKBACK_BUFFER`)。(b) 的 refund/adjust 按**带符号**求和(非仅正向额):正确执行的负向 adjust 若只加正向额会误报漂移,带符号使不变式严格成立。
- **首告去重实现**:已告事件 id 集合 = 历史 run 记录 details_json 的 `new_alerted_event_ids` 并集(拉全部 action=billing_reconciliation 记录,Python 合并;量级见 §4.4)。本 run 新告 = 当前漏扣集合 − 已告集合;details_json 只存**本 run 新告** id 列表(不存全量,防记录膨胀)
- **明细口径**:漏扣明细只报 token 事实数(租户/事件 id/会话/模型/prompt/completion/total_tokens),**不重算成本**(D7 延伸:当时定价快照未存,现价重算会误导补扣决策)
- **通知 targeting**:接收者 = `User.platform_role == 'super_admin' AND is_deleted=False` 全体;每超管取其**首个 active membership**(user_tenants where valid_to IS NULL)租户发 targeted 通知(`tenant_id=该租户, user_id=超管id, type="system"`——复用现成枚举,零前端改动;title「计费对账发现差额」,content 摘要含新告数/存量数/残余差,link 指向审计日志页[EP3 以 audit-log-ui 实际路由为准]);无 membership 超管跳过 + logger.warning。发送用 `NotificationService.create`(best-effort 永不抛,job 不因通知失败崩)。**零新告且无残余差/漂移 → 不发通知**(例行 run 不打扰铃铛)
  - *EP3 切片 02 实施注记(2026-08-17,code-review 双轴回写)*:① 「首个 active membership」的 tiebreak 定死为 earliest `valid_from`(+ id 兜底)——spec 空白的确定性消歧,超管多租户 active 时落点可复现(用例 8a 锁双 membership 落点);② best-effort 范围覆盖**整个 notify stage**(target 查询 + 插入 + commit 包一层 try/except),run 记录 commit 后任何通知侧异常 logger.exception 吞掉不外抛(用例 8d 锁);③ 切片 01 留痕的「平台级跨租户只读 job 裸 select 豁免」随 targeting 查询延伸至 User/UserTenant(同属该豁免范围,无租户过滤可下沉);④ `_notify_super_admins` 不返回计数(与 scan_balance_warnings 不同,通知计数非本 job 返回契约,死返回值已删)。
- **告警分级**:新告漏扣 > 0 或 残余差 ≠ 0 或 钱包漂移 > 0 → logger.error + SystemLog level=warning + 超管通知;全部干净 → logger.info + SystemLog level=info + 零通知
- **scheduler 注册**:`_register_jobs` 加 `CronTrigger(hour=9, minute=30), id="reconcile_billing", replace_if_exists=True`;受既有 `_SCHEDULER_ENABLED` 总开关管(默认 False,生产单副本显式 True)——**开关显式化归 config-startup-guard(R5),本 feature 不越界改默认值**
- **job 异常兜底**:service 层抛错由薄壳 job 捕获 logger.exception(对账失败本身要可见,但不崩 scheduler 进程)

## 5. Testing Decisions

- **测试位置与范式**:`tests/test_billing_reconciliation.py` 新建,SQLite 内存库常驻(零 PG 专有依赖——无部分索引/VECTOR;`Numeric`/`JSONB` 均有 SQLite variant)。直接调 service 层(镜像 `test_notifications.py:365` 的 `scan_balance_warnings(factory)` 直调范式,传 session factory + 显式 `as_of`)
- **好测试标准**:只断言外部可观察行为——SystemLog 记录的存在性/level/details_json 字段、通知行的存在性与 targeting、返回报告的数字;**不断言**内部 SQL 形态或私有方法
- **用例矩阵**(对应 feature verification 三条 + 边界):
  1. **差额检出**(verification ①):构造「有 usage_event 无 consume 交易」(直接插事件行)→ run 报告漏扣明细正确 + SystemLog warning 落表 + details_json 明细字段齐全;对照组:经 `BillingService.charge` 完整链路的事件 → 不计漏扣
  2. **零误报**(verification ②):完整正常链路(record + charge 全成功)→ level=info、零告警、零通知
  3. **幂等**(verification ③):同 as_of 重跑 → skip(不插第二条 run 记录);`force=True` 重跑 → run 记录更新但**已告事件不再新告**
  4. **首告 + 存量**(D4):day1 告事件 A;day2(事件 A 仍在 + 新事件 B)→ 新告只 B,details_json 存量统计含 A
  5. **缓冲边界**(D3/D9):created_at = as_of − 5min 的事件(缓冲内)→ 不告;as_of − 31min → 告
  6. **聚合残余差**:手工插一条无 usage_event_id 的 consume 交易(模拟交易侧异常)→ 残余差告警(事件级零漏扣也能检出)
  7. **钱包不变式**:手工改 wallet.balance(不写交易)→ 漂移告警
  8. **通知边界**(切片 02):超管收到 targeted 通知(type/tenant/user_id 正确);无 super_admin 用户 → logger.warning 不崩;零差额 → 零通知
- **多租户**:用例 1 构造两个租户各一条漏扣 → 明细按租户正确分组不串
- **覆盖率**:不低于项目基线;本 feature 新 service 行为全覆盖(上述 10-12 条)

## 6. 切片规划

> 切片即 §7「实施切片」(v2 双轴审查后定稿,此处不重复;依赖图与 AC 以 §7 为准——plan 自检以 §7 为切片真相源)。

## 7. 实施切片(to-tickets v2)

```
01 对账 job 核心(检出+幂等+落表+logger)──→ 02 超管通知接入+文档+feature 收尾(末切片)
```

### 切片 01 — 对账 job 核心:双层检出 + 幂等 + SystemLog 落表 + logger 通道 ✅(2026-08-17,PR #171,merge 28a2034,CI 4/4 绿:Migrations 43s / Backend 11m14s / E2E 1m56s / Frontend 28s;commits 130f20b 翻页 + 0a0d8f9 实施 + bc8d955 审查回写)

- **Blocked by**: 无(frontier,可立即开工)
- **What it delivers**: 每日 09:30(scheduler_enabled=True 时)对账 job 运行:事件级检出全部漏扣明细(30min 缓冲)+ 聚合残余差 + 钱包不变式检查;每 run 一条 SystemLog(差额 warning / 干净 info,details_json 全量明细);同日重跑 skip、事件首告去重;差额时 logger.error。测试直调 service 验证四组行为(检出/零误报/幂等/首告+缓冲边界)。
- **文件清单**(估):`app/services/billing_reconciliation_service.py` 新建(~250 行)/ `app/core/scheduler.py` 改(薄壳 job + 注册行)/ `tests/test_billing_reconciliation.py` 新建(用例 1-7 + 幂等,~9 条)
- **Acceptance criteria**:
  - [x] `BillingReconciliationService.run(as_of, force)` 落地双层检出:事件级 NOT EXISTS 漏扣明细(created_at < as_of−30min)+ per-tenant 聚合残余差 + 钱包不变式;返回报告 dict(租户数/扫描事件数/新告/存量/残余差/漂移)
  - [x] 每 run 一条 SystemLog:`action=billing_reconciliation`,`details_json` 含 as_of / 统计 / per-tenant 差额 / new_alerted_event_ids / 存量未处理数;有差额 level=warning、干净 level=info(D8)
  - [x] 幂等双保险:同 as_of 日重跑 skip(不插第二条 run 记录);force 重跑不重复新告已告事件(已告集合 = 历史 run 的 new_alerted_event_ids 并集)
  - [x] 缓冲语义:as_of−5min 内事件不判漏扣,as_of−31min 判(D9=30min,常量单源)
  - [x] `scheduler.py`:`reconcile_billing` 薄壳 job(签名带 session_factory,镜像 scan_balance_warnings)+ `_register_jobs` 注册 CronTrigger(hour=9, minute=30);job 捕获 service 异常 logger.exception 不崩
  - [x] `tests/test_billing_reconciliation.py` 用例 1-7 落地(SQLite 常驻直调范式),TDD 先红后绿
  - [x] 验证:`pytest tests/test_billing_reconciliation.py -q` 全绿 + `./init.sh full` 全量零回归(基线 1048)+ ruff 全绿
  - [x] 不越界:不动 charge/recharge/计费编排、不动 scheduler_enabled 默认值、不发通知(切片 02)、零前端零迁移

### 切片 02 — 超管 targeted 通知接入 + 文档同步 + feature 收尾(末切片)✅(2026-08-17,PR #172,merge b14b9f6,CI 4/4 绿:Migrations 59s / Backend 10m55s / E2E 1m46s / Frontend 28s;commits 0964f92 实施 + bd42518 审查回写 + 6bc5015 feature 收尾)

- **Blocked by**: 切片 01
- **What it delivers**: 有新差额(新告漏扣/残余差/漂移任一 > 0)时,全部 super_admin 收到 targeted in-app 通知(铃铛可见,type="system",content 摘要,link 指向审计日志页);干净 run 零通知。CONTEXT.md 补「对账(Reconciliation)」术语;feature 收尾八步仪式。
- **文件清单**(估):`app/services/billing_reconciliation_service.py` 改(通知编排 ~40 行)/ `tests/test_billing_reconciliation.py` 改(用例 8,~3 条)/ `CONTEXT.md` 改(术语 1 条)/ 收尾:feature_list.json + progress.md + sync-active
- **Acceptance criteria**:
  - [x] 通知 targeting:全体 `platform_role='super_admin' AND is_deleted=False`;每超管取首个 active membership(valid_to IS NULL)租户发 targeted 通知(type="system");无 membership 超管跳过 + logger.warning
  - [x] 通知触发条件:新告漏扣 > 0 或 残余差 ≠ 0 或 漂移 > 0;全部干净 → 零通知(D5;`NotificationService.create` best-effort,job 不因通知失败崩)
  - [x] 用例 8 落地:超管收到通知(targeting 字段正确)/ 无超管不崩 / 干净 run 零通知
  - [x] `CONTEXT.md` 术语「对账(Reconciliation)」(双层口径/只报不补/首告去重三要点,glossary 格式,零实现细节)
  - [x] 验证:`./init.sh full` 全量零回归 + 前端 `npm run build` 绿(零前端改动确认)+ ruff
  - [x] feature 收尾八步:status in_progress→passing + evidence 3 条 + plan 状态行同 commit 翻 + sync-active + progress.md + 文档影响评估 + 依赖解锁扫描(92 super-admin-write-audit 无 depends_on 指向本条,确认新 frontier)+ 分支清理(PR 合并后)

## 8. Out of Scope(不越界声明)

- ❌ **自动补扣 / 补扣状态机 / 告警消除机制**(D7 只报不补;人工 adjust 补账后事件仍计「存量已告」,属既定语义非 bug;将来补扣闭环独立立项时一并评估 `reconciliation_runs` 建表)
- ❌ **不动 TurnAccountant / charge / recharge / 计费编排**(总纲 D5;对账是纯只读旁路)
- ❌ **不动 `scheduler_enabled` 默认值 / 开关显式化**(R5 config-startup-guard 的事)
- ❌ **不做对账管理页 / 对账 API 端点 / 前端改动**(D6 复用 SystemLog + audit-log-ui 既有查询已覆盖可见性)
- ❌ **不做小时级检测 / 实时对账**(D2 日报一次)
- ❌ **不做金额重算 / 定价快照回溯**(明细只报 token 事实)
- ❌ **不向租户发差额通知**(差额是平台运营视角;租户余额可见性走既有 /billing 页)
- ❌ **不修 Notification 平台级(tenant_id=NULL)不可见的既有缺口**(本 plan 用 per-user targeting 绕开;该缺口是否修是通知系统自身的独立决策)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| scheduler_enabled 默认 False → 生产忘开则对账同样静默不跑(兜底失效) | 中 | job 注册行为与余额扫描完全一致(同开关同注册点);开关显式化(部署清单+启动 WARN)已由 R5 config-startup-guard 立项,本 feature 不越界但受益 |
| 已告集合靠 SystemLog details_json 合并,记录被人工清理/篡改则去重失效 → 重复告警 | 低 | SystemLog 是审计表无清理机制;force 重跑有 logger 痕迹;重复告警的后果只是噪音(只报不补,无资损动作) |
| 全量扫描随 usage_events 增长变慢(每天一次,事件表是最大表之一) | 中 | 现阶段毫秒~秒级可接受;job 异常兜底不崩 scheduler;若将来超阈值,滚动窗口优化属实施细节(service 内查询形态可换,报告契约不变) |
| 多副本部署 double-fire cron → 重复告警 | 低 | 与余额扫描同一单副本纪律(config 注释已声明 on exactly one replica);且日粒度幂等锁 + 事件首告去重把重复 run 的副作用压到「一条多余 run 记录」以下 |
| 漏扣误报(charge 正常但交易尚未 flush 的极端慢事务) | 低 | 30min 缓冲高三个数量级冗余;真发生也只产生一条告警噪音,人工核对可辨 |

## 10. 验收标准(同步 feature_list.json verification)

1. **差额检出**:构造 charge 失败/缺失的 usage_event(无对应 consume 交易),job 产出正确差额明细(SystemLog warning + details_json)+ logger.error(切片 01 用例 1)
2. **零误报**:无差额时零告警(verification「不误报」——level=info、零通知,用例 2)
3. **幂等**:同窗口重跑不产生重复差额记录(verification 原文;实现为 as_of 日粒度 skip + 事件首告去重双层,用例 3/4)
4. 聚合残余差与钱包不变式漂移可检出(事件级 join 之外的兜底层,用例 6/7)
5. 超管 targeted 通知可达且干净 run 零通知(切片 02 用例 8)
6. `./init.sh full` 全量零回归 + ruff 全绿(两切片各自的验证节)

## 11. 不越界声明(重申)

本次改动**只**涉及:新建对账 service + scheduler 薄壳注册 + 对账测试 + CONTEXT.md 术语;**不**触碰:计费编排(charge/recharge/TurnAccountant)、scheduler_enabled 默认值、通知系统结构(只消费既有 create)、前端、数据库 schema、R4/R5 的既定范围。
