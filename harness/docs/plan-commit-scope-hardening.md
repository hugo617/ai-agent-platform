# 计划:commit-scope 悬空修复(三处「commit 后副作用写」生产 100% 丢失 + 3 个假阳性测试 + QW1 CI npm test)

> **id**: commit-scope-hardening
> **状态**: passing(切片 01 唯一=末切片端到端 2026-08-25:PR #175 merge 80ea079,feature 收官)
> **优先级**: 97(feature_list.json)
> **创建日期**: 2026-08-25
> **最后修订**: 2026-08-25(v3:EP3 实施注记 + §4.7-3/§5 方言断言勘误 + code-review 双轴回写;v2:对抗式自审 4🟡+1🟢 回写,零 🔴)
> **素材源**: [codebase-health-log.md](./codebase-health-log.md) 第 11 次条目 Baseline 快照「commit-scope 悬空缺陷」表(候选 Ⓐ Strong Top;risk-hardening 系列直系续篇,同 R4 危害档)

---

## 0.2 EP3 实施注记与勘误(v3,Session 228)

1. **§4.7-3 / §5 方言断言勘误(实证证伪)**:原断言「请求结束时 get_db 的 session.close() 会回滚该连接上的未提交事务,故 HTTP 接缝 + 请求结束后用 db_session 断言 = 悬空行查不到」对**纯裸 INSERT** 成立(实验证实),但对 `record`/`create` 的 **SAVEPOINT 形态在 SQLite legacy 驱动下不成立**:pysqlite legacy 隔离模式从不发真 BEGIN,SAVEPOINT 无外层事务时其 RELEASE 等价 COMMIT(裸 sqlite3 驱动实验:`SAVEPOINT→INSERT→RELEASE` 后显式 rollback 行仍在)→ 悬空行被驱动意外持久化,跨 session 断言照样查到,红证不可达。§5「悬空/持久语义与 PG 一致,无方言差异」同此证伪 —— 方言差异恰在 SAVEPOINT 边界。
2. **对应适配(conftest.py 越界豁免,§11 允许清单补一行)**:test engine 改 `isolation_level=None` + `begin` 事件显式 `BEGIN`(`in_transaction` 检查防止 StaticPool 共享连接的双 BEGIN —— db_session 在 commit 后 refresh 会留下打开读事务,请求 session 再 BEGIN 会炸;在事务中则跳过、加入既有事务,等价旧行为)。效果:SAVEPOINT 恒落真实外层事务,RELEASE 永不意外提交,测试栈获得 PG 生产回滚语义(SQLAlchemy 文档「Serializable isolation / Savepoints / Transactional DDL」标准配方)。豁免依据:AGENTS.md「窄范围 blocker 修复」—— 不改则 D5 红证物理不可达(断言层无解,行已被驱动提交);只给测试文件单独建引擎会造成双测试栈、其余 HTTP 用例仍假绿。红证留存:stash 源码修复终验 3 改造用例 3 failed,恢复后全绿。
3. **§4.6-① 方法级 docstring**:plan 仅要求模块 docstring 措辞同步,实施顺带把 `_upsert` 方法 docstring 补原子范式一句(code-review 判良性超集)。
4. **ci.yml job name 文案**同步为「typecheck + build + lint + unit tests」(§4.6-⑥ 只要求加 step;良性超集)。
5. **§4.8 role_change 改造用例 setup 细节**:原用例手动 seed User/UserTenant/casbin;改造后走 HTTP POST `/tenants/me/members/` 建成员(镜像 test_users_api 既有先例),membership 断言加 SCD2 `valid_to IS NULL` 过滤 + 通知行加 `tenant_id` 断言(等价增强,code-review 判非偏离)。
6. **code-review 双轴结论(2026-08-25,general-purpose ×2 并行)**:Standards 代码层 **0 硬违规**;判断项 2 留痕 —— ① 3 处 guard 同形块(recharge/update_role/_notify_super_admins)rule-of-three 名义到界,plan D4 明文「逐处改零新抽象」压制,下次巡检 `/improve-codebase-architecture` 重评提取;② conftest `exec_driver_sql("BEGIN")` SQLite 专有限于测试基建,注释已载缘由。Spec 前 8 条 AC 全满足、§11 禁碰项逐项未触碰、§4.6①-⑥ 字段级吻合;唯一「缺失」= AC-9 收尾八步(本就排在 PR 合并后,见 §12 勘误于收尾 commit 勾选)。

---

## 0. v1 → v2 变更摘要(对抗式自审回写)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| §1/§4.7 把「docstring 自称 passthrough 不实」误挂在 service 模块 docstring 上 —— 实际不实的是**测试** docstring:A 章唯一审计用例 `patch.object(LoggingService, "record", autospec=True)` 无 `side_effect` 是**纯替换**(审计行根本没被尝试写),其 docstring 却自称「real method passthrough so the audit row still writes」 | 🟡 | §4.7-7 更正留痕;改造时删除该误导性 docstring(mock 与假自述一并根除)。service 模块 docstring「traceable」宣称在修复后才变为如实,同步微调 |
| §4.8 未区分红证适用范围:新增的 role_change guard 用例锁的是业务韧性(通知炸不阻断),未修复代码上本来就绿;只有 3 个**改造**用例要求「修复前必红」 | 🟡 | §4.8 补注:红证仅适用 3 个改造用例;guard 新增用例是语义锁(green-on-both),不参与红证 |
| 尾随 commit 的空提交场景未显式论证(create 内部 SAVEPOINT 回滚后,尾随 commit 提交的是空事务) | 🟡 | §4.7-5 扩写:savepoint 回滚后 outer 事务为空,commit 为 no-op,`_notify_super_admins` 同型先例;既有 recharge 炸通知用例在修复后语义仍真 |
| CONTEXT.md 词条 `_Avoid_` 字段用法漂移(其他词条列「别名误称」,v1 草案列的是反例模式) | 🟡 | §4.6-⑤ 定稿:`_Avoid_` 列别名误称(「事务边界」「autocommit」),反例描述放词条正文 |
| booking_config 改造用例的平台行覆盖边界未言明 | 🟢 | §4.8 明确:改造用例沿用原 A 章 tenant-own 双 PUT 场景(与原覆盖面等价,platform 行同路径同型不扩——§5 边界①) |

## 0.1 决策拍板状态说明

**D1-D7 全部经 AskUserQuestion 获用户逐项拍板(2026-08-25,两轮问询均获回复,全按推荐方案采纳,无默认采纳项)。** 无需 EP3 开工前复核窗口。

---

## 1. Problem Statement

第 11 次巡检坐实的同根同型缺陷类:**best-effort 副作用写(审计/通知)落在业务最终 `commit()` 之后 → 悬在 session 自动开启的隐式新事务里 → 请求结束 `get_db` 关闭 session → 回滚 → 生产 100% 丢失**。

机制源码级确认(`app/core/database.py` 的 `get_db`):正常路径**不 commit**(仅异常分支 rollback),`async with` 退出即 `session.close()` —— SQLAlchemy session 关闭时回滚未提交事务。因此「业务 commit 之后的裸写」必然丢失,而现有三个测试用假阳性方式放行:

| # | 位置 | 现状 | 生产影响 | 假阳性测试 |
|---|---|---|---|---|
| 1 | `booking_config_service._upsert`(flush→**commit**→refresh→**record**) | 审计行悬在隐式新事务 | **审计 100% 从未持久,功能等于失效**(模块 docstring 宣称可追责,不实) | `test_booking_config_api.py` A 章:`patch.object(LoggingService, "record")` mock 只断 kwargs,从未验 DB 行 |
| 2 | `billing_service.recharge`(L252 **commit** → L260 `NotificationService.create`) | 通知行悬空(create 只 SAVEPOINT flush,无人 commit) | **充值到账通知 100% 丢失** | `test_notifications.py::test_recharge_creates_notification`:service 直调 + **同一个 db_session** SELECT —— 自己能看到自己未提交的行 |
| 4 | `member_service.update_role`(L110 **commit** → L117 create) | 与 #2 完全同型 | **role_change 通知 100% 丢失**(feature 92 留痕未列,第 11 次巡检新发现) | `test_notifications.py::test_role_change_creates_notification`:同型同 session 假阳性 |

全仓库普查复核(本 EP2 会话):`NotificationService.create` 共 5 类调用点(scheduler `scan_balance_warnings` / `billing_reconciliation_service._notify_super_admins` / notifications.py 读侧 ×4[mark_read 内部自带 commit] / recharge / update_role),`LoggingService.record` 直接调用共 8 处 —— **悬空恰好上表 3 处,无第 4 处源码悬空**;定价 4 端点(`app/api/v1/billing.py` ×4 record)行为正确(record 全在 commit 前),仅层次卫生问题(feature 92 code-review 1 硬违规 D8 留痕,巡检另立候选 Ⓑ)。

正确反例已在仓库(证明可修、无需发明新机制):审计 = `user_service` 的 record→commit 原子范式(feature 92 六处同型刚验证);通知 = `billing_reconciliation_service._notify_super_admins` 显式尾随 commit(`scan_balance_warnings` 同型)。锁死测试范式已由 feature 92 `test_super_admin_audit` 树立(HTTP 接缝 + request-close 后跨 session 持久断言,「booking_config 教训落地」原文)。

## 2. Solution

**逐处修,零新抽象**:三处悬空按语义归位到仓库已验证的两范式之一 —— ① `booking_config` 审计移到 commit 前(record→commit 原子,审计行与配置写同事务持久);② recharge + role_change 两处通知保持「业务 commit 之后」的位置不变,补**显式尾随 commit + try/except best-effort guard**(镜像 `_notify_super_admins`)。**三个假阳性测试改造为 HTTP 接缝 + 跨 session 真实持久断言**(mock 与同 session SELECT 假阳性根因一并根除),改造后用例在未修复代码上必须先红(TDD 红证锁死防复燃)。**契约防再犯**:LoggingService / NotificationService docstring 强化两范式说明 + CONTEXT.md 新增「提交范围(Commit Scope)」术语。**顺手 QW1**:CI frontend job 补 `npm run test` step(259 个 vitest 用例进 CI,消除「本地绿 CI 不跑」倒挂)。定价 4 端点不碰(Ⓑ pricing-service-extraction 独立立项)。

## 3. User Stories

- 作为**门店 owner/admin**,我希望保存预约网格配置后审计日志页真的出现 `booking_config` 记录,以便配置变更有据可查(现状:配置改成功但审计 100% 丢失,出了问题无法追责)。
- 作为**租户 owner/admin**,我希望租户被充值后铃铛真的收到「充值到账」通知,以便第一时间知道钱包到账(现状:100% 丢失,只能自己去账单页刷)。
- 作为**普通 member**,我希望角色被管理员变更后收到「角色变更」通知,以便知道自己权限变了(现状:100% 丢失)。
- 作为**平台运维**,我希望 CI 在每个 PR 上执行前端 259 个 vitest 用例,以便前端回归在合并前暴露而非流到用户。
- 作为**后续开发者**,我希望 CONTEXT.md 有「提交范围」词条 + 两个范式的 docstring 契约,以便新写审计/通知触发点时不再踩「commit 后裸写」的坑(已两次被巡检抓获)。
- 作为**审计读者(合规)**,我希望审计/通知这类副作用的持久性与业务写一样被测试锁定,以便「passing 但代码站不住」不再发生。

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动(源码修复) | 3 | `app/services/booking_config_service.py`(record 移位)/ `app/services/billing_service.py`(recharge 通知尾随 commit + guard)/ `app/services/member_service.py`(update_role 通知尾随 commit + guard) |
| 后端注释强化(零行为) | 2 | `app/services/logging_service.py` / `app/services/notification_service.py`(docstring 两范式契约) |
| 数据库迁移 | 0 | 无(纯事务边界修复) |
| 前端文件改动 | 0 | 无(通知/审计均后端侧,前端铃铛与审计页现状已能展示) |
| 测试改造 | 2 文件 3 用例 + 1 新增用例 | `tests/test_booking_config_api.py`(A 章 mock 用例改造)/ `tests/test_notifications.py`(2 用例改造 + 1 条 role_change guard 对称用例) |
| 词汇表 / CI | 2 | `CONTEXT.md`(新术语)/ `.github/workflows/ci.yml`(frontend job +1 step) |

### 4.2 多租户影响评估

- 新增租户 scoped 表? **NO**(零迁移零新表)
- 修改租户隔离逻辑? **NO**(三处修复只动事务边界,查询逻辑零变化;booking_config 审计行 `tenant_id` 语义不变[tenant 覆盖行=目标租户 / platform 行=NULL],recharge 通知 `tenant_id`=被充值租户,role_change 通知 `tenant_id`=成员所在租户,均维持现状)
- 引入跨租户访问点? **NO**
- 验证:booking_config 改造用例沿用既有 A 章租户语义断言(`tenant_id` 归属),无新跨租户面

### 4.3 权限影响评估

- 新增 permission code? **NO**
- 修改 DEFAULT_*_PERMS? **NO**
- 影响 require_permission caller? **NO**(三处端点鉴权零变化:PUT /bookings/config/** super_admin / settings:update,POST /billing/recharge super_admin,PATCH /tenants/me/members/{uid} users:update)
- graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist

不适用 —— 零新表零迁移。SystemLog / Notification 表结构不变;本 feature 只是把「本应发生的 INSERT」真正提交。

### 4.5 用户拍板决策(D1-D7,全部 AskUserQuestion 逐项确认)

| # | 决策 | 拍板结果 |
|---|---|---|
| D1 | booking_config 审计形态 | **record→commit 原子**(user_service 30+ 处先例;业务成功 ⇒ 审计必持久,仅 record 内部 SAVEPOINT 失败被吞时丢审计且业务不受损) |
| D2 | recharge + role_change 通知形态 | **显式尾随 commit + try/except best-effort guard**(镜像 `_notify_super_admins` + `scan_balance_warnings`;业务已提交,通知失败只丢通知) |
| D3 | 定价 4 端点处置 | **不碰,Ⓑ 独立立项**(定价行为正确非悬空;提取是结构重构与止血不同质,混做 PR 难审;巡检原建议分立) |
| D4 | 修复机制 | **逐处改,零新抽象**(3 处异质、两范式各有归属;rule-of-three 未到不预建 helper;防再犯靠 docstring 契约 + CONTEXT 术语) |
| D5 | 假阳性测试改造 | **改造为真实持久断言**(HTTP 接缝 + 跨 session 查真实行;kwargs 断言并入真实行断言;改造后未修复代码上必红) |
| D6 | 切片划分 | **1 切片端到端**(镜像 feature 91/92 单切片先例;~250-300 行一天内) |
| D7 | CONTEXT.md 术语 | **新增「提交范围(Commit Scope)」**(glossary 格式,两合法范式 + 反例,零实现细节) |

### 4.6 修复规格(逐处)

**① `booking_config_service._upsert`(D1)**:`record` 调用整体移到 `await db.commit()` 之前(紧跟 `await db.flush()` —— `row.id` 经 flush 已可用,feature 92 §4.7.9-1 同型验证);commit 后仅剩 `refresh` + `_to_read` + return。审计失败仍被 LoggingService SAVEPOINT 吞掉不阻断配置写。模块 docstring「Each upsert records an audit log row … traceable」由不实变为如实,同步微调措辞指向原子范式。

**② `billing_service.recharge`(D2)**:通知 stage(commit 后)包 `try/except Exception: logger.exception(...)`,create 之后补 `await self.db.commit()`(镜像 `_notify_super_admins` 的注释与结构,注释点明「create() 只在 SAVEPOINT 内 flush,调用者必须提交」)。既有注释「Best-effort — never breaks the committed recharge」语义保真增强。

**③ `member_service.update_role`(D2)**:与 ② 完全同型同修(try/except + 尾随 commit),注释镜像。

**④ 契约强化(零行为)**:`LoggingService.record` docstring 补「record 必须落在持有它的提交范围内(原子范式:commit 前;本类不负责 commit)」;`NotificationService.create` docstring 把「caller commits」从隐式约定升为显式契约 + 尾随 commit 范式示例指向。

**⑤ CONTEXT.md(D7)**:「工程概念(项目特有部分)」节新增「**提交范围(Commit Scope)**」词条:副作用写(审计/通知)必须落在持有它的提交范围内,否则悬在隐式事务里随请求结束回滚;两个合法范式 = 原子(副作用与业务写同事务提交,user_service 审计)/ 显式尾随 commit(业务提交后副作用单独提交,_notify_super_admins);反例 = 业务 commit 后裸写不提交(生产 100% 丢失)。`_Avoid_: 事务边界(泛称), autocommit(本项目未用)`。

**⑥ QW1(CI)**:`ci.yml` frontend job 在 `Lint (oxlint)` 与 `Typecheck & build` 之间加一步 `npm run test`(= `vitest run`,本地实测 259 用例 ~10s,CI 增量可忽略)。

### 4.7 取证留痕(源码级,本 EP2 会话复查确认)

1. **悬空机制**:`get_db`(app/core/database.py)正常路径无 commit,仅 `except: rollback`;`async with` 退出 → `session.close()` → 隐式事务回滚。「业务 commit 后的裸写」100% 丢失。
2. **完整清单复核**:`NotificationService.create` 调用点 = scheduler(L97 create → L109 一次 commit ✅)/ `_notify_super_admins`(L446 create → 尾随 commit ✅)/ notifications.py ×4(读侧 + mark_read/mark_all_read **内部自带 commit** ✅)/ recharge ⚠ / update_role ⚠;`LoggingService.record` 直接调用 = billing.py ×4(均 commit 前 ✅)/ knowledge_service ×2(feature 92 验证 ✅)/ billing_service.recharge(feature 92 验证 ✅)/ booking_config ⚠;`self.logs` 持有者(user/auth/rbac_service)= record→commit 范式源头 ✅。**悬空恰 3 处,与巡检表一致,无新增**。
3. **假阳性机制**(测试改造依据):conftest 单连接 StaticPool,`db_session` 与请求 session **共享同一连接** —— 但请求结束时 get_db 的 session.close() 会回滚该连接上的未提交事务,故 HTTP 接缝 + 请求结束后用 db_session 断言 = 悬空行查不到(未修复必红),已提交行可见(修复后绿)。同 session 直调则自己能看到自己未提交的行(假阳性根因)。
4. **`expire_on_commit=False`**(session factory 配置):recharge 通知内容读 `wallet.balance` 在 commit 后仍可用,尾随 commit 范式无 expired-object 风险。
5. **既有 `test_notification_failure_does_not_break_recharge`**(ExplodingNotification 强制 create 内部炸):SAVEPOINT 吞掉后 guard 无异常可捕,尾随 commit 提交**空事务**(savepoint 回滚后 outer 事务为空,commit 为 no-op;`_notify_super_admins` 同型先例)—— 该用例语义在修复后**仍真**,保留不动。
6. **路由确认**:PATCH `/api/v1/tenants/me/members/{user_id}`(users:update)/ POST `/api/v1/billing/recharge`(super_admin_client)/ PUT `/api/v1/bookings/config/tenant/{tenant_id}`(settings:update;platform 行走 super_admin)—— 三处均有 HTTP 端点,测试范式可直接套用。
7. **假阳性自述更正(v2)**:A 章唯一审计用例 `test_a_upsert_writes_audit_log` 的 docstring 自称「real method passthrough so the audit row still writes」,但 `patch.object(..., autospec=True)` 无 `side_effect` 是**纯替换** —— 审计行在测试里根本没被尝试写,「passthrough 仍写行」是双重假安慰(既没写行、生产里写了也丢)。巡检所指「docstring 自称 passthrough 不实」即此处;service 模块 docstring 的「traceable」宣称在修复(§4.6-①)后才变为如实。

### 4.8 测试改造规格(D5)

| 用例 | 现状(假阳性) | 改造后 |
|---|---|---|
| `test_booking_config_api.py` A 章审计用例 | `patch.object(LoggingService, "record")` spy 断 kwargs | 删 mock;两次 PUT `/bookings/config/tenant/{own}`(建行→改行)经 HTTP;请求结束后 db_session 查真实 `SystemLog` 行:action=`booking_config.create` + `booking_config.update` 各一,update 行断 `old_values`/`new_values` 三字段快照与 `user_id`/`tenant_id`/`resource_id`;kwargs 断言并入真实行断言 |
| `test_notifications.py::test_recharge_creates_notification` | service 直调 + 同 session SELECT | `_seed_wallet` 后经 `super_admin_client` POST `/billing/recharge`;请求结束后 db_session 跨 session 断 `Notification` 行(type=recharge / user_id=None / content 含金额)+ 充值本体行(WalletTransaction)仍在 —— 双持久断言 |
| `test_notifications.py::test_role_change_creates_notification` | 同上同型 | 经 `app_client` PATCH `/tenants/me/members/{target}`(owner actor);请求结束后跨 session 断 role_change 行(user_id=target / content 含新角色)+ membership 角色已改 —— 双持久断言 |
| (新增)`test_role_change_notification_failure_does_not_break` | — | 镜像既有 recharge 炸通知用例:Exploding 强制 create 炸 → PATCH 仍 200 + membership 角色已提交持久(guard 对称锁) |

**红证要求**:仅上表**前三个改造用例**在修复前代码上运行必须 FAIL(悬空行跨 session 查不到)—— /implement 先跑红证留存,再修复转绿。**guard 新增用例不参与红证**(它锁业务韧性,未修复代码上本来就绿,green-on-both 语义锁)。改造 booking_config 用例沿用原 A 章 tenant-own 双 PUT 场景(与原覆盖面等价;platform 行同路径同型,§5 边界① 不扩),并删除原误导性「passthrough」docstring(§4.7-7)。

## 5. Testing Decisions

- 测试金字塔:改造 3 + 新增 1 = 4 条集成用例(HTTP 接缝);零单元零 E2E 新增(修复本身在 service 层,接缝已在最高点)。**HTTP 是本 feature 唯一测试接缝**(沿用 feature 92 已验证范式,不新建接缝)。
- SQLite 内存库(conftest StaticPool 单连接)—— 悬空/持久语义与 PG 一致(均为 session 事务语义,无方言差异);无 PG 专有构造。
- 覆盖率:不动既有 80% gate;4 用例覆盖三处修复 + guard 对称。
- 边界 case:① booking_config 平台行(super_admin PUT /platform)审计持久 —— 改造用例覆盖 tenant 行即可,platform 行同路径同型(§11 不扩);② 通知炸不阻断业务(recharge 既有 + role_change 新增对称);③ 审计炸不阻断配置写(LoggingService SAVEPOINT 语义,既有实现不改,不在本 feature 重测)。
- 多租户:booking_config 用例沿用既有自身租户语义;无新跨租户面(§4.2)。
- QW1 验证:本地 `cd frontend && npm run test` 259/259(冒烟已验 10.0s)+ push 后 CI frontend job 四步全绿。

## 6. 切片规划

### Ticket 1(唯一切片):三处悬空修复 + 假阳性测试改造 + QW1 + 收尾

- **What to build**: 配置写成功必有审计行、充值/角色变更后通知必达(或 best-effort 失败仅丢通知不伤业务)、三个假阳性测试根因根除且红证锁死、CI 每_PR 跑前端 259 用例。
- **Blocked by**: 无
- **文件清单**: §4.1 全量(3 源码 + 2 docstring + CONTEXT.md + ci.yml + 2 测试文件)
- **验证命令**: `pytest tests/test_booking_config_api.py tests/test_notifications.py -q`(定向)+ `./init.sh full`(全量)+ `cd frontend && npm run test && npm run build`(零前端源码改动确认)

## 7. 对抗式审查(单模型双轴,v1 → v2)

触发条件:涉及审计(可追责性)与通知(生产可靠性)的事务语义修复 + CI 门禁变化 —— 按惯例执行单模型双轴自审,产出回写 §0。(v2 回填)

## 8. Out of Scope

- ❌ 定价 4 端点提取 PricingService / 最小搬移(候选 Ⓑ 独立立项,本 feature 零触碰 `app/api/v1/billing.py` 定价路径)
- ❌ 统一 helper(`create_and_commit` / `record_and_commit` / 基类方法)—— D4 拍板逐处改
- ❌ `NotificationService.create` / `LoggingService.record` 的行为与签名(两类的 SAVEPOINT + 吞错语义是仓库级契约,只改 docstring)
- ❌ `get_db` 加「请求结束自动 commit」(那会改变全部 28 个依赖端点的事务语义,危害远大于收益;正确方向是副作用调用方自我提交)
- ❌ notifications.py 读侧/mark 路径(内部自带 commit,无悬空)
- ❌ TurnAccountant(候选 ②)/ graph.py(候选 ③)等其他巡检候选
- ❌ 前端任何改动(铃铛/审计页现状已能展示持久化后的行)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 尾随 commit 在通知 create 被吞后提交「别人的」pending 写(同一 session 里业务 commit 后理论上无 pending 写,但防御性确认) | 低 | 三处修复点的 commit 后均无其他写;guard 的 except 路径不 commit(镜像 `_notify_super_admins` 结构);code-review 双轴复核 |
| booking_config record 移位后 `row.id` 不可用(flush 前) | 低 | record 放 flush 之后 commit 之前(§4.6-①);feature 92 txn.id 同型验证先例 |
| 假阳性改造后测试与既有 conftest fixture 时序冲突(如 app_client 每测试重建 app) | 低 | 三处端点均已被现有 HTTP 用例使用(test_booking_config_api / test_billing:599 / members 路由),fixture 路径已验证 |
| CI 加 npm test 后首次跑暴露本地未见的失败(环境差异) | 中 | 第 11 次巡检实测本地 259/259 全绿(10.0s);若 CI 环境仍红,属真实回归应在合并前修(这正是 QW1 的目的),不回滚 step |
| 修复改变测试期望导致相邻用例回归(如 test_booking_config_api 其余章节) | 低 | 红证 + 定向 + 全量 `./init.sh full` 兜底(收尾八步第 1 步) |

## 10. 验收标准(同步 feature_list.json verification)

1. 三个改造用例经 HTTP 接缝断言真实持久:SystemLog(booking_config create+update 两行,old/new_values 快照)+ Notification(recharge / role_change)在 request-close 后跨 session 可查;红证留存(修复前 FAIL)。
2. best-effort 语义保持:recharge 炸通知用例(既有)+ role_change 炸通知用例(新增对称)均绿 —— 通知失败不阻断已提交业务。
3. `pytest tests/test_booking_config_api.py tests/test_notifications.py -q` 定向全绿;`./init.sh full` 全量零回归(基线 = 收尾时点全量数)+ ruff 绿。
4. CONTEXT.md「提交范围(Commit Scope)」词条落地(glossary 格式,零实现细节);LoggingService/NotificationService docstring 契约强化。
5. QW1:`.github/workflows/ci.yml` frontend job 含 `npm run test` step;PR 的 CI frontend job 四步全绿(oxlint + test + build)。
6. 前端零源码改动(`git diff --stat frontend/src` 为空)。

## 11. 不越界声明

本次改动**只**涉及:上表 3 个 service 文件的事务边界(共 3 个方法体)+ 2 个 docstring + CONTEXT.md 1 词条 + ci.yml 1 step(+job name 文案同步,见 §0.2-4)+ 2 个测试文件的 4 个用例 + **tests/conftest.py 的 test engine 事务模式适配(EP3 越界豁免,见 §0.2-2,不改则 D5 红证物理不可达)**。**不**触碰:`app/api/v1/billing.py`(定价路径)、`LoggingService.record` / `NotificationService.create` 的代码行为、`get_db`、任何 repository/model/schema、任何前端文件、任何其他 service 的既有 commit 位置(正确的那些一律不动)。

---

## 12. 实施切片(to-tickets 产出)

### 切片依赖图

```
切片 01(唯一 = 末切片)
```

### 切片 01 ✅ — commit-scope 悬空修复(三处两范式 + 假阳性测试根除 + QW1 CI npm test)

> **完成证据(2026-08-25)**:PR #175(merge `80ea079`,CI 4/4 绿:Migrations 53s / Backend 9m36s / E2E 1m57s / Frontend 54s[含新 npm run test step,259 vitest]);commits 0da3c4b + 4fd6eea;全量 1090 passed(基线 1089+1)零回归 + ruff + 前端 259/259 + build 绿(frontend/src 零改动);code-review 双轴 Standards 代码层 0 硬违规 / Spec 前 8 AC 满足 0 越界(§0.2-6)。

- **Blocked by**: 无(frontier,可立即开工)
- **What it delivers**: 配置写成功必有审计行(booking_config 审计从 100% 丢失到随业务原子持久);充值/角色变更后通知必达(recharge / role_change 从 100% 丢失到显式尾随 commit 持久,失败只丢通知不伤业务);三个假阳性测试根因根除且红证锁死防复燃;CI 从此每个 PR 跑前端 259 个 vitest 用例(QW1);CONTEXT.md「提交范围」词条 + 双 docstring 契约钉死两范式防再犯。
- **文件清单**: `app/services/booking_config_service.py`(改)/ `app/services/billing_service.py`(改)/ `app/services/member_service.py`(改)/ `app/services/logging_service.py`(docstring)/ `app/services/notification_service.py`(docstring)/ `CONTEXT.md`(词条)/ `.github/workflows/ci.yml`(+1 step)/ `tests/test_booking_config_api.py`(A 章改造)/ `tests/test_notifications.py`(2 改造 + 1 新增)
- **Acceptance criteria**:

- [x] `app/services/booking_config_service.py`:`_upsert` 的 record 整体移到 `flush` 之后 `commit` 之前(row.id 可用),commit 后仅剩 refresh + `_to_read` + return;模块 docstring 措辞同步为原子范式如实描述(§4.6-①)
- [x] `app/services/billing_service.py`:recharge 通知 stage(commit 后)包 `try/except Exception: logger.exception(...)` + `await self.db.commit()` 尾随,注释镜像 `_notify_super_admins`(§4.6-②)
- [x] `app/services/member_service.py`:update_role 通知 stage 与 recharge 完全同型同修(§4.6-③)
- [x] `app/services/logging_service.py` + `app/services/notification_service.py`:docstring 契约强化(record/create 必须落在持有它的提交范围内 + 两范式说明,零行为改动)(§4.6-④)
- [x] `CONTEXT.md`:「工程概念」节新增「提交范围(Commit Scope)」词条(§4.6-⑤ 定稿格式)
- [x] `tests/test_booking_config_api.py`:A 章用例改造 —— 删 mock 与误导性 passthrough docstring,双 PUT tenant-own 经 HTTP,请求结束后 db_session 断真实 SystemLog 行(create+update 两行,old/new_values 快照 + user_id/tenant_id/resource_id)(§4.8)
- [x] `tests/test_notifications.py`:recharge / role_change 两用例改造为 HTTP 接缝 + 跨 session 双持久断言(通知行 + 业务行);新增 role_change 炸通知 guard 对称用例;红证留存(3 改造用例修复前 FAIL,guard 用例 green-on-both)(§4.8)
- [x] `.github/workflows/ci.yml`:frontend job 在 oxlint 与 build 之间加 `npm run test` step(§4.6-⑥)
- [x] 验证:定向 `pytest tests/test_booking_config_api.py tests/test_notifications.py -q` 全绿 + `./init.sh full` 全量零回归 + ruff 绿 + 前端 `npm run test` 259/259 与 `npm run build` 绿(`git diff --stat frontend/src` 为空)+ feature 收尾八步(末切片即唯一切片)
