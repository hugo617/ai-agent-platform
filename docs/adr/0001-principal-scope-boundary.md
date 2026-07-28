# ADR-0001: Principal scope boundary(Principal 半收口边界)

- **Status**: Accepted
- **Date**: 2026-07-28(ADR 立档日期;决策源自 2026-07-27 第 4 次巡检,见 Deciders)
- **Deciders**: 2026-07-27 第 4 次代码健康度巡检 + `plan-principal-scope-doc-alignment` grill 共识(opus 子智能体审查 ×2)
- **Supersedes**: —(本 ADR 为项目首个 ADR)
- **Superseded by**: —(尚无后续 ADR 推翻)

---

## Context

`principal-module` feature(priority 70,2026-07-27 收官)抽出了 `Principal` 深模块(`app/services/principal.py`),吸收 booking/device/customer 三 service 的鉴权决策。`Principal.for_write()` / `Principal.for_read()` 两方法覆盖了「Platform Role + 门店角色 + 目标租户 + Data Scope 四元组」的统一解析。

但 principal-module 的 plan §4.2 经过 EP2 回环的 opus 子智能体审查后,**明确列出 4 个不迁方法 + 4 个非采用 service**(均有 leverage 论证):

| 不迁方法 | 不迁原因 |
|---|---|
| `booking.start` | 三叉 customer principal:customer 分支走 ownership check 是业务校验,不是角色判断。Principal 的四元组对 customer 不适用 |
| `booking.get_tenant_schedule` | panorama 变体 + 故意无 require:HQ viewer 用 `resolve_target_tenant` 解析目标店 + schedule-grid 是 `bookings:read` surface,default perms 全 grant,跑 require 无意义。跟 `for_read` 默认带 require 有张力 |
| `booking.list_my_bookings` | customer principal 读路径:无 tenant 概念,按 customer_id 全局查。Principal 的四元组不适用 |
| `booking.get_device_schedule` | 不用 helper:纯 store 路径,只有 `require("read")` 一行,无 helper 可消除。迁它只是改写法无 leverage |

| 非采用 service | 不采用原因 |
|---|---|
| `conversation_service` | 读路径用 `is_cross_tenant_viewer` 做 panorama 分流,不属于 Principal 的 panorama/scope 二分场景 |
| `dashboard_service` | 同上 |
| `device_model_service` | **platform-level service**(super_admin only,无 tenant 概念),不在 Principal 适用域(tenant-scoped)内 |
| `group_service` | 同上(platform-level)|

**额外覆盖(plan §6 隐含但 §4.2 未显式列)**:

- `customer_service.list_customers_hq` / `customer_service.get_customer_aggregate` —— 2 个 super_admin 全局读方法,无 helper 无 require,纯 SQL 聚合
- 6 个 api 层文件直接调用 helper(`app/api/v1/exports.py` / `logs.py` / `search.py` / `customers.py` / `booking_config.py` + `app/api/deps.py`),共 8+ 外部调用点

**触发本 ADR 的张力**:

principal-module 收官后,这个「半收口」决策散落在三处且**口径不一致**:

1. `CONTEXT.md:30` 措辞过宽:「booking / device / customer 三 service 的鉴权决策**统一走 Principal**」—— 暗示全覆盖
2. `app/services/principal.py` docstring(L18-22)留模糊口子:「adoption of Principal across other services can be evaluated in future architecture reviews」—— 把已审查的「不迁」说成「未来可扩」
3. 4 个 helper docstring(`permission_service.py:677,702` + `_tenant_target.py:40-42` + `data_scope.py:70-71`)同款「future architecture reviews」口子,共 5 处散落

**后果**:未来巡检 agent 会 re-suggest「Principal 没全覆盖,该扩」(本项目第 4 次巡检已经 re-suggest 了),因为读 docstring 看到的是「开放决策」而非「已裁决边界」。每次都要重新走一遍 grill。

---

## Decision

**Principal 的覆盖范围定格在「booking/device/customer 三 service 的读写鉴权路径」**,不扩到上述不迁清单。具体边界:

1. **不迁的 4 个 booking 方法**(`start` / `get_tenant_schedule` / `list_my_bookings` / `get_device_schedule`)继续直接用 helper,**理由见上方 Context 表**(每条都是 leverage 论证,不是疏漏)
2. **2 个 customer super_admin 全局读方法**(`list_customers_hq` / `get_customer_aggregate`)继续无 Principal 无 helper(纯 SQL)
3. **4 个非采用 service**(`conversation_service` / `dashboard_service` / `device_model_service` / `group_service`)继续直接用 `is_cross_tenant_viewer` 或 `require_super_admin`,**理由见上方 Context 表**(platform-level + 读路径特殊)
4. **4 个内部 helper**(`resolve_target_tenant` / `is_platform_writer` / `is_cross_tenant_viewer` / `DataScopeService`)**保留**为 Principal 的实现细节 + 上述 out-of-scope 调用方使用

**单一真相源**:本 ADR 是「Principal 不迁清单」的权威记录。其他文档(CONTEXT.md / principal.py docstring / 4 helper docstring / booking Note 注释 / 4 service docstring)只做「见 ADR-0001」的指针,**不枚举清单**(避免双重维护漂移)。

---

## Consequences

**正面**:

- **防 re-suggest**:未来巡检 agent 看到 ADR-0001 Accepted + supersede 流程,知道这是已裁决边界,re-suggest 时必须先走 supersede 流程(不能直接当新候选提)
- **口径统一**:5 处「future architecture reviews」模糊口子统一收口为「do NOT extend without superseding ADR」,CONTEXT/docstring/ADR 三套口径一致
- **范式建立**:项目首个 ADR,建立未来架构决策的记录范式

**负面**:

- **未来扩 Principal 的成本变高**:必须先写 ADR-NNNN 标 `Superseding ADR-0001` + 改本 ADR Status,不能顺手迁。这是设计意图(防止误迁移),但确实是流程成本
- **清单维护**:不迁清单(4 方法 + 4 service + 2 super_admin 方法 + 6 api 文件)现在固定在 ADR 里,如果某天 booking 加了新方法且走 Principal,本 ADR 不需要改(它只列「不迁的」);但如果新方法不走 Principal,要补进 ADR

**中性**:

- **零代码影响**:本 ADR 是纯文档对齐决策,不要求任何代码改动(principal-module 已落地的不迁范围就是 ADR 的内容)

---

## Superseding this ADR

**要扩 Principal 超出本 ADR 范围**(如把 `booking.start` 三叉 customer 收进 Principal / 把 4 个非采用 service 迁进 Principal),必须:

1. 新建 `docs/adr/NNNN-*.md`(NNNN = 下一个 ADR 编号),Status 标 `Superseding ADR-0001`
2. 在新 ADR 的 Context 段论证:为什么推翻 ADR-0001 的 leverage 论证(如「Principal 接口扩展后,吸收 customer principal 的成本变低了」)
3. 把本文件(ADR-0001)的 Status 从 `Accepted` 改为 `Superseded by ADR-NNNN`
4. 同步更新 CONTEXT.md / principal.py docstring / 4 helper docstring / booking Note / 4 service docstring 的指针(从「见 ADR-0001」改成「见 ADR-NNNN」)

**禁止**:直接编辑本 ADR 的 Decision 段(增量加方法 / 删方法)。ADR 是不可变档案,改决策 = 推翻 + 新建。

---

## References

- [`harness/docs/plan-principal-module.md`](../../harness/docs/plan-principal-module.md) §4.2 不迁清单(本 ADR 的 leverage 论证来源)
- [`harness/docs/plan-principal-module.md`](../../harness/docs/plan-principal-module.md) §6 Out of Scope 非采用 service 清单
- [`CONTEXT.md`](../../CONTEXT.md) Principal 条目(L29-31,本 ADR 钉死其边界措辞)
- [`app/services/principal.py`](../../app/services/principal.py) Principal 深模块本体
- [`harness/docs/plan-principal-scope-doc-alignment.md`](../../harness/docs/plan-principal-scope-doc-alignment.md) 本 ADR 的产出 plan(含 grill 决策 + opus 审查发现)
- [`harness/docs/codebase-health-log.md`](../../harness/docs/codebase-health-log.md) 2026-07-27 第 4 次巡检候选 3(本 ADR 的触发源)
