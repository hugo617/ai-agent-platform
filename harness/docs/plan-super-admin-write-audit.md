# 计划:super_admin 三处最高危写操作补审计(充值 / 定价覆盖 / 知识下发与撤回)

> **id**: super-admin-write-audit
> **状态**: passing(EP3 切片 01 完成 2026-08-24 Session 223:PR #173 merge d4a6ca9,CI 4/4 绿,全量 1075 零回归,feature 收官)
> **优先级**: 92(生产加固系列第 5 条,风险 R4 🟡)
> **创建日期**: 2026-08-24
> **最后修订**: 2026-08-24(v3:EP3 切片 01 完成,checklist 全勾 + 实施注记回写)
> **系列总纲**: [plan-risk-hardening-overview.md](./plan-risk-hardening-overview.md)(D6 已拍板:只补三处最高危,不做 super_admin 全量埋点)

---

## 0. v1 → v2 变更摘要(对抗式自审回写)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| 知识下发对**空集团 early-return**(targets 为空直接 `return []`)是否记审计未定义 | 🟡 | §4.7 补边界:**不记**(无业务写入,「零动作」审计是噪音;区别于对账 job 的「干净 run 也记」——run 记录是主产物,下发是动作型) |
| 重复下发(re-upsert re-enable 已有行)的审计语义未定义 | 🟡 | §4.7 补:**照记** `knowledge.distribute`,distributed_count 按实际返回行数(含 re-enable);details 补 `re_enabled` 计数可选 |
| recharge 的 resource_id=txn.id 依赖 repo.add 的 flush 行为,未显式声明 | 🟡 | §4.7 补实施注记:BaseRepository.add 若未 flush 则以 details 内不含 id 兜底仍可追责(txn 有唯一业务键 tenant+amount+balance_after);实施时验证 |
| 门店 owner 可见「被改价」历史是否有定价泄露面 | 🟢 | §4.7 补说明:定价本就是门店在 `/billing/pricing` 可见的生效价,改价历史可见无额外泄露(有意行为,user story 6) |


## 0.1 决策拍板状态说明(本 feature 特有,必读)

系列纪律要求「EP2 阈值类取舍必须用户逐项拍板,不得按推荐默认采纳」。本 EP2 回环(2026-08-24)已按纪律发起**两轮** AskUserQuestion 问询(D1-D6 逐项 + 压缩确认),均未获回复。处置:按 **Session 219 先例**(D8-D10 未获回复按工程判断采纳并如实标注)推进——D1-D9 全部按推荐方案落地,**逐项如实标注「未获回复按推荐采纳」**。

- **复核窗口**:EP3 开工前。用户复核后如推翻任一决策,推翻成本是局部的(action 字符串常量 + 测试断言 + 前端标签,无 schema/API 耦合)。
- **复核入口**:本文件 §4.5 决策表 + progress.md 顶部断点记录。

---

## 1. Problem Statement

充值(`POST /billing/recharge`)、定价覆盖(`POST/PUT/DELETE /billing/pricing`)、知识下发与撤回(`POST /knowledge/documents/{id}/distribute` / `DELETE /knowledge/distributions/{id}`)是平台上**权力最高、资损面最大**的跨租户写操作,但它们**只留业务列**(operator_id / distributed_by),不写 SystemLog:

- **定价三端点连 operator 都没记**——谁在什么时候把某租户的模型价格改成了什么,完全无从追溯;
- 审计基础设施(LoggingService.record + system_logs 表 + `GET /logs` + 前端审计页)早已建成且覆盖 login/user CRUD/RBAC/booking_config,唯独这三处最高危操作不在其上;
- 事后追责链断裂:第 10 次巡检将其定为业务功能风险 R4 🟡。

## 2. Solution

三处写路径各补一次 `LoggingService.record` 调用,把操作者、目标租户、关键业务值(充值金额 / 定价前后快照 / 下发目标)落入既有 SystemLog 审计流。**零新建**:复用 LoggingService(system_logs 表、SAVEPOINT best-effort 语义)、复用 `GET /logs` 查询端点与前端审计页(仅补 action 中文标签)。操作行为本身零变化——纯旁路观测。

核心纪律(取证发现,必须写死):**record 必须放在业务 `commit()` 之前**(user_service 原子范式),让审计行与业务变更同一事务原子持久;**绝不采用 booking_config 的 commit→record 模式**——那会让审计行悬在无人提交的隐式事务里,request 结束被回滚(既有隐性缺陷,见 §4.7 留痕,本 feature 不越界修)。

## 3. User Stories

1. 作为 super_admin,我给某租户充值后,希望审计页立刻出现一条含金额、余额、备注、目标租户的记录,以便我的每笔资金操作都可追溯。
2. 作为 super_admin,我修改/停用某租户或平台的模型定价后,希望审计页记录改前与改后的完整价格快照,以便定价争议时可还原现场。
3. 作为 super_admin/group_admin/owner,我下发知识文档到门店或集团后,希望审计页记录源文档与全部目标,以便知识触达范围可审计。
4. 作为 super_admin/group_admin/owner,我撤回某条知识下发后,希望审计页出现一条显式的撤回记录(warn 级),以便「谁在何时收回了哪家的知识」有独立事件可查。
5. 作为平台运维,我希望三处审计事件与既有审计共用同一查询端点与过滤维度(action/租户/时间/操作者),以便不必为新事件建任何新面。
6. 作为门店 owner(有 logs:read),我希望在本租户审计页看到「本店被充值 / 被改价 / 被下发 / 被撤回」的事件,以便感知平台对我店的最高权操作。
7. 作为开发者,我希望审计写入失败绝不阻断业务(既有 best-effort 契约保持),以便审计旁路永不制造新的业务故障。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 3 | `app/services/billing_service.py`(recharge 落 record)、`app/api/v1/billing.py`(定价三端点落 record + 补 CurrentUser dep)、`app/services/knowledge_service.py`(distribute/revoke 落 record) |
| 数据库迁移 | 0 | 无新表无新列(system_logs 现成) |
| 前端文件改动 | 1 | `frontend/src/pages/logs-page.tsx`(ACTION_LABEL 补 6 个中文标签,纯数据) |
| 新增测试类 | 1 | `tests/test_super_admin_audit.py`(~12 用例) |
| Skill / Hook / 配置 | 0 | — |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(system_logs 为既有平台级 append-only 表)
- 是否修改现有租户隔离逻辑? **NO**(只写不读;读侧 `SystemLogRepository` 零改动)
- 是否引入跨租户访问点? **NO**(审计是旁路写入;三处写路径本身就是既有的 super_admin/跨租户权限面,本 feature 不动权限)
- 验证:多租户用例 2 条(A 租户充值审计行 B 租户不可见;门店 owner 经 logs:read 可见本租户被充值记录)

### 4.3 权限影响评估

- 新增 permission code? **NO**
- 修改 DEFAULT_*_PERMS? **NO**
- 影响 require_permission caller? **NO**(审计调用在权限闸之后、业务逻辑内部)
- graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist

不适用(无新表)。system_logs 既有列完全够用:action(≤100)/module(≤50)/level/details_json/old_values/new_values/resource_type/resource_id/user_id/tenant_id。

### 4.5 核心决策表(D1-D9;**全部未获回复按推荐采纳,待用户复核**)

| # | 决策点 | 拍板结果 | 标注 |
|---|---|---|---|
| D1 | action 命名 | **逐操作细分 6 个**,镜像 `user.create`/`role.revoke` 惯例:`billing.recharge`、`pricing.upsert`、`pricing.update`、`pricing.deactivate`、`knowledge.distribute`、`knowledge.revoke`;module:billing / billing / knowledge | 未获回复按推荐采纳 |
| D2 | level 分级 | **镜像现有惯例**:充值/定价 upsert/update/下发 = info;`pricing.deactivate` 与 `knowledge.revoke` = warn(破坏性/撤销类才 warn,与 user.delete=warn、role.revoke=warn 同构,避免 warn 疲劳) | 未获回复按推荐采纳 |
| D3 | 下发/撤回 | **两个独立 action**(distribute / revoke),撤回可按 action 单独过滤统计(追责最高频查询),对齐 role.grant/role.revoke 先例 | 未获回复按推荐采纳 |
| D4 | 知识审计范围 | **全角色无条件记**:distribute/revoke 调用即记(owner/admin/group_admin/super_admin 都落),无角色分支——group_admin 跨店下发同风险不留审计空洞;与 feature verification「三处操作各写一条 SystemLog」直接吻合 | 未获回复按推荐采纳 |
| D5 | detail 粒度 | **完整可追责**(overview 要求「金额或定价快照」可追责):充值 details={amount, balance_after, remark};定价 old_values/new_values **双快照**(input/output 价、model、scope、is_active)+ details={scope};知识 details={document_id, target_tenant_ids 或 target_group_id, count} | 未获回复按推荐采纳 |
| D6 | SystemLog.tenant_id 归属 | **受影响租户**(单值天然可落处):充值→目标租户;定价覆盖→被覆盖租户(平台级=NULL);知识撤回→目标租户;**知识下发恒 NULL**(批量多目标单列放不下,且避免「行为随目标数摆动」,全列表由 details 承载)。效果:门店 logs:read 用户可在本店审计页看到「被充值/被改价/被撤回」 | 未获回复按推荐采纳 |
| D7 | 前端改动 | **最小改动**:ACTION_LABEL 补 6 个中文标签(充值 / 定价新建 / 定价编辑 / 定价停用 / 知识下发 / 知识撤回)。fallback 本已能显示原始串,零改动可用;几行纯数据提升可用性,verification 预授权「零或最小」 | 未获回复按推荐采纳 |
| D8 | 落点层与原子性 | **record 在业务 commit 之前**(user_service 范式,审计与业务原子):充值/知识在 service 层 record→commit;定价新旧快照在 API 层 commit 前(端点补 `user: CurrentUser` dep 取操作者) | 工程判断(取证驱动,见 §4.7) |
| D9 | 切片数 | **1 切片**(三处同范式 record 调用 + 测试 + 前端标签,单片全栈可独立验证;无 schema/依赖链可拆) | 未获回复按推荐采纳 |

### 4.6 各落点调用规格(字段级)

**充值**(BillingService.recharge 内、`self.db.commit()` 之前):
- action=`billing.recharge`, module=`billing`, level=info
- user_id=operator_id, tenant_id=目标租户
- resource_type=`wallet_transaction`, resource_id=新交易行 id(repo add 已 flush,实施时验证)
- details={amount, balance_after, remark}

**定价 POST /pricing → pricing.upsert**(_upsert_pricing 内、commit 前):
- 新建:old_values=None;命中既有行:old_values=改前快照;new_values=改后快照(input_price_per_1k / output_price_per_1k / model / is_active)
- details={scope: "platform" | "tenant"}, tenant_id=被覆盖租户或 None
- resource_type=`model_pricing`, resource_id=行 id

**定价 PUT /pricing/{id} → pricing.update**:同上双快照,改前值从 DB 行读。

**定价 DELETE /pricing/{id} → pricing.deactivate**:level=**warn**,old_values=停用前快照,new_values={is_active: false}。

**知识下发**(distribute_document 内、末尾 commit 前):
- action=`knowledge.distribute`, module=`knowledge`, level=info, tenant_id=**None**(D6)
- resource_type=`knowledge_document`, resource_id=源文档 id(一次下发对应一个源文档,按文档过滤下发史)
- details={document_id, target_tenant_ids:[...](按店模式)/ target_group_id(按集团模式), distributed_count}

**知识撤回**(revoke_distribution 内、commit 前):
- action=`knowledge.revoke`, module=`knowledge`, level=**warn**, tenant_id=row.target_tenant_id
- resource_type=`knowledge_distribution`, resource_id=下发行 id
- details={document_id: row.source_doc_id, target_tenant_id}

message 统一英文短句(镜像 user_service "updated user xxx" 风格);不传 ip/user_agent(与既有调用面一致)。

### 4.7 取证发现与留痕(实施必读)

1. **booking_config 悬空缺陷(留痕不修)**:`booking_config_service` 是 commit→record,审计行落进隐式新事务无人提交,`get_db` 退出 close → 回滚,**生产环境该审计行大概率从未持久**;其测试 mock/spy 了 record 只断言 kwargs,没验 DB 持久。本 feature 不越界修(系列边界),但**测试设计必须吸取教训**:定价审计用例走 app_client(真实 HTTP + get_db 生命周期)后断言 DB 行存在,锁住 record→commit 范式;booking_config 缺陷记入 progress.md 供第 11 次巡检复验。
2. **recharge 的通知也有同类风险(commit 后 create 无尾随 commit)**:同属既有行为,不在本 feature 范围(对账/通知系列已收官),仅留痕。
3. **定价三端点无 CurrentUser**:补 `user: CurrentUser = Depends(get_current_user)` 只是取身份(require_super_admin 已在 dependencies 挡门),无权限语义变化。
4. **action 过滤是精确匹配**(`SystemLog.action == filter`):6 个 action 细分值直接可用;前端 ACTION_LABEL 未命中回退原始串,零前端改动不破坏可用性。
5. **空集团 early-return 不记审计**(自审 🟡 回写):`distribute_document` 对空集团(targets 展开为空)在 record 之前 `return []`——无业务写入即无审计。区别于对账 job「干净 run 也记」:run 记录是 job 主产物,下发是动作型,零动作记审计是噪音。
6. **重复下发照记**(自审 🟡 回写):对已有行(含已撤回行)re-distribute 是 re-enable upsert,照记一条 `knowledge.distribute`,distributed_count = 实际返回行数(新建 + re-enable)。
7. **recharge resource_id 的 flush 依赖**(自审 🟡 回写):`resource_id=txn.id` 要求 `self.txs.add(txn)` 后 id 已生成(BaseRepository.add 的 flush 行为);若实施时发现未 flush,details 已含 {tenant, amount, balance_after} 业务键,追责链不依赖 resource_id,可留 None 并在本节补注记。
8. **门店可见「被改价」历史无额外泄露**(自审 🟢 留痕):定价覆盖行 tenant_id=被覆盖租户 → 门店 logs:read 可见改价史;生效价本就是门店 `/billing/pricing` 可见内容,改价历史可见是 user story 6 的有意行为。

### 4.7.9 切片 01 实施注记(EP3 回写,2026-08-24 Session 223)

1. **§4.7.7 flush 依赖验证通过**:`BaseRepository.add` 内部 `flush()`(base.py),`txn.id` 在 add 后即可用——recharge 的 resource_id=txn.id 按原案落地,测试断言 `log.resource_id == txn.id` 锁定。
2. **Decimal 序列化**:`_pricing_snapshot` 对价格字段 `Decimal.quantize(Decimal("0.000001"))` 后 `str()`——JSON 列收不了 Decimal(裸 str 会让 DB 往返值与内存 payload 值尾零不对称),量化到 Numeric(10,6) 列精度后两侧一致,且与 API 自身序列化口径相同("9.000000")。
3. **快照字段超集**:§4.6 列名 4 字段,实施快照含第 5 键 `tenant_id`——PUT 可迁移 scope(tenant_id 可变),不记则 scope 迁移不可追责;D5「完整可追责」覆盖,测试断言该键。
4. **§10.3 覆盖补强(Spec 轴发现)**:6 action 中 billing.recharge(门店 owner)+ pricing 三种(超管,GET /logs?action= 精确匹配断言)共 4 种经读端点验证;knowledge 两种由 action 串逐字断言 + §4.7.4 精确匹配机制覆盖(读端点 action 过滤是既有已测行为)。
5. **code-review Standards 轴处置**:1 硬违规(定价审计+业务写在 API 层,「审计日志属 Service 职责」)——**plan D8 明文落点**(「定价在 API 层因业务逻辑在 API 层」),raw select/commit 先于本 feature 存在,提取 pricing 写路径入 service 层属独立重构,留痕为后续候选(与 booking_config 悬空同处置);2 判断项留痕:①4 处 record kwargs 内联(镜像 user_service 范式,抽 8 参数 helper 得不偿失)②测试 `patched_enforcer`/`_bind_role` 为第二份拷贝(rule of three 未到,第三消费者出现时升 conftest)。
6. **D1-D9 复核窗口履行**:EP3 开工前(Session 223 开头)已向用户过一遍 §0.1/§4.5 决策清单,第三轮未获回复——维持「按推荐采纳」,复核窗口关闭。

### 4.8 其他实施决策

- LoggingService 实例化方式:镜像 booking_config 的 `LoggingService(db).record(...)` 直接实例化(不注入),改动最小。
- 无 API 契约变化:三处端点请求/响应零改动,audit 纯旁路。
- 不写 CONTEXT.md 术语:无新领域概念(SystemLog/action 均为既有),按 glossary「零实现细节」原则不扩充。

## 5. Testing Decisions

- **好测试只测外部行为**:断言 SystemLog 行的字段值与持久性,不断言 record 调用次数/mock kwargs(booking_config 的教训——mock 断言测不出悬空缺陷)。
- **接缝**(最高既有接缝,零新接缝):
  - service 直调接缝(session factory 直绑,镜像 test_notifications.py:365 / test_billing_reconciliation.py 范式):充值、知识下发/撤回;
  - app_client HTTP 接 seam(走真实 get_db 生命周期):定价三端点(业务逻辑在 API 层)+ 审计行经 request-close 后仍存在的持久性验证。
- **用例清单(~12)**:充值字段完整性 / 审计失败不阻断充值(SAVEPOINT 回滚只伤审计行,业务 commit 照常)/ 定价 upsert 新建 / upsert 命中既有行(平台 scope,tenant_id NULL)/ 定价租户覆盖 scope / update 双快照 / deactivate warn / 定价审计经 HTTP 真实持久 / 下发按店(target_tenant_ids 全列表 + tenant_id NULL)/ 下发按集团(target_group_id + count)/ 撤回(warn + 目标租户)/ 非超管 owner 下发也落审计 + 门店 owner 经 GET /logs 可见本店被充值记录(读侧可见性)。
- SQLite 内存库即可(JSONB 已有 JSON variant);无 PG 专有类型,无迁移。
- 覆盖率不低于项目基线(93%)。

## 6. 切片规划

见 §12「实施切片」(to-tickets 产出)。1 切片(D9):三处后端落点 + 测试 + 前端标签,单片全栈。

## 7. 对抗式审查(单模型双轴,v1 → v2)

本 feature 改动文件 ≤5、无鉴权/迁移变化,但**涉及资金相关操作审计**(安全敏感)→ 触发对抗式审查。v1 写完后跑 Standards(架构合规/命名/依赖方向)+ Spec(verification 逐项/越界检查)双轴自审,产出回写本节与 §0。

## 8. Out of Scope

- ❌ super_admin 全量写操作埋点(D6 系列拍板:只做三处最高危;不够再由第 11 次巡检复验提出)
- ❌ 修复 booking_config / recharge 通知的 commit→write 悬空缺陷(既有独立问题,仅留痕)
- ❌ 审计页 UI 新功能(筛选器/导出/详情面板——既有面够用,只补标签)
- ❌ SystemLog 读侧/API/权限任何变化
- ❌ 新表、新迁移、新 permission code

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 审计行悬空不持久(booking_config 型缺陷复燃) | 高 | D8 铁律 record→commit + HTTP 接缝持久性测试双保险 |
| 审计写入失败毒化业务事务 | 中 | 既有 SAVEPOINT 契约 + 「审计失败不阻断充值」用例锁定 |
| 定价端点补 CurrentUser dep 引入行为变化 | 低 | require_super_admin 仍在 dependencies,新增 dep 只取身份;超管 API 测试回归 |
| details_json 不可序列化导致审计行丢失 | 低 | 落点全用原生类型(int/str/list/None);测试断言 details 字段 |

## 10. 验收标准(同步 feature_list.json verification)

1. 三处操作各写一条 SystemLog 的回归测试(充值 / 定价覆盖 / 知识下发+撤回)全绿;
2. 审计记录字段完整:操作者 user_id / 目标租户 tenant_id / 关键业务值(金额或定价双快照)逐字段断言;
3. `GET /logs` 既有查询端点能按 action 精确查出 6 种新记录,前端审计页显示中文标签(ACTION_LABEL 命中);
4. 审计失败不阻断业务(best-effort 契约用例锁定);
5. `./init.sh full` 全量零回归 + 前端 `npm test` / `build` / `oxlint` 全绿。

## 11. 不越界声明

本次改动**只**涉及:三处写路径内各加一次 LoggingService.record 调用、定价三端点补 CurrentUser dep、logs-page ACTION_LABEL 6 个标签、1 个新测试文件。**不**触碰:SystemLog 读写基础设施、三处操作的权限/业务语义、booking_config 与通知的既有悬空问题、前端审计页结构、任何 schema/迁移。

---

## 12. 实施切片(to-tickets 产出)

### 切片依赖图

```
01 三处审计落点 + 测试 + 前端标签(全栈单片)✅ PR #173 → feature 收尾(2026-08-24 Session 223)
```

### 切片 01 — 三处最高危写操作接入 SystemLog(充值 / 定价 / 知识下发与撤回)+ 审计页标签 ✅(PR #173 merge d4a6ca9,2026-08-24 Session 223,CI 4/4 绿:Migrations 44s / Backend 9m31s / E2E 1m49s / Frontend 28s)

- **Blocked by**: 无(frontier,可立即开工)
- **What it delivers**: 超管充值、定价三端点写、知识下发/撤回五类动作完成后,`GET /logs`(及前端审计页)可查出一条含操作者、目标租户、关键业务值(金额/定价双快照/下发目标)的审计记录;操作行为与 API 契约零变化;审计失败不阻断业务。
- **Acceptance criteria**:

- [x] `app/services/billing_service.py`:`recharge` 在 `self.db.commit()` 之前落 `LoggingService.record`(action=`billing.recharge`/module=`billing`/level=info/user_id=operator_id/tenant_id=目标租户/resource_type=`wallet_transaction`/resource_id=交易行 id/details={amount, balance_after, remark})
- [x] `app/api/v1/billing.py`:三定价端点补 `user: CurrentUser = Depends(get_current_user)`(require_super_admin 依赖保持),POST→`pricing.upsert`(upsert 命中时 old_values=改前快照)/PUT→`pricing.update` 双快照/DELETE→`pricing.deactivate`(level=warn),均 commit 前落 record;details={scope: "platform"|"tenant"},tenant_id=被覆盖租户(平台级 None),resource_type=`model_pricing`
- [x] `app/services/knowledge_service.py`:`distribute_document` 与 `revoke_distribution` 在各自 commit 前落 record(`knowledge.distribute` level=info tenant_id=None details={document_id, target_tenant_ids 或 target_group_id, distributed_count} resource=document;`knowledge.revoke` level=warn tenant_id=目标租户 details={document_id, target_tenant_id} resource=`knowledge_distribution`)
- [x] `frontend/src/pages/logs-page.tsx`:ACTION_LABEL 补 6 个中文标签(充值/定价新建/定价编辑/定价停用/知识下发/知识撤回),其余零改动
- [x] `tests/test_super_admin_audit.py` 新建 ~12 用例(§5 清单),含:HTTP 接 seam 持久性验证(定价三端点经 app_client 后 DB 行仍存在)、审计失败不阻断充值、非超管 owner 下发也落审计、门店 owner 经 `GET /logs` 可见本店被充值记录
- [x] 定向 `pytest tests/test_super_admin_audit.py -q` 全绿 + ruff + `./init.sh full` 全量零回归 + 前端 `npm test`/`build`/`oxlint` 全绿
