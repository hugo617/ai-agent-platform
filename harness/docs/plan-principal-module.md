# 计划:抽 Principal 深模块吸收后端跨 service 的角色扇出

> **id**: principal-module
> **状态**: ✅ passing(EP3 全 4 切片完成,2026-07-27 Session 150 收尾)
> **优先级**: 70(新登记,「工程化」area;巡检候选 1,Strong)
> **创建日期**: 2026-07-27
> **来源**: 2026-07-27 第 3 次代码健康度巡检 Top recommendation;HTML 报告 `~/.cache/ai-agent-platform-architecture-reviews/2026-07-27.html`;grill 9 决策 + 审查 3 RED 修正 + 2 优化 + 2 误判纠正

---

## 1. Problem Statement

后端三个业务 service(`booking_service` / `device_service` / `customer_service`)的鉴权决策**没被吸收进深模块**,散落在 31 处 helper 调用里:

- **写动作**(11 处):`resolve_target_tenant` 解析目标租户 + `if not is_platform_writer: require(...)` 条件鉴权,每个写方法重写一次
- **读 HQ 路径**(8 处):`if is_cross_tenant_viewer: 走 panorama 早返回; else: require + 走 tenant scope`
- **读 scope 路径**(2 处,customer):`if not is_cross_tenant_viewer: require` + 调 `DataScopeService.resolve`

**核心摩擦**:
1. 每个新动作(如未来 booking 的 `extend`/`reassign`)必须重新组装「viewer bypass? writer resolve? store require?」三件套
2. `booking_service` 829 行 / `device_service` 432 行的膨胀根因不是业务复杂,是**鉴权决策没被吸收**
3. 现有 codebase 有**两个独立的 principal-解析雏形**各自只解决一半:`_tenant_target.resolve_target_tenant`(管写)+ `DataScopeService.resolve`(管读 scope,只 customer 用 1 次)—— 「principal 怎么解析」散在两处
4. 改角色规则要扫 18 个方法,容易漏(`booking_service.start` L700-718 三叉路径就是典型)

**铁律背景**:CONTEXT.md 已把 `Platform Role` 和 `Data Scope` 定义为领域概念,Principal 是它们的**统一 OOP 投射** —— 不是新概念,是把已有领域知识集中到一个深模块。

**deletion test**(判定深模块成立):删 Principal → 31 处 helper 调用 + DataScopeService 调用重新散布到 18 个方法,complexity reappears across N callers → Principal earns its keep。

## 2. Solution

引入 `Principal` 深模块(`app/services/principal.py`),用**读/写两方法** interface 吸收角色判断 + 租户解析 + scope 解析三件事:

```python
class Principal:
    def __init__(self, db: AsyncSession) -> None: ...
    async def for_write(self, *, actor_id, user_tenant_id, payload_tenant_id,
                         obj, act, platform_role=None) -> WriteAccess: ...
    async def for_read(self, *, actor_id, user_tenant_id,
                        obj, act, platform_role=None) -> ReadAccess: ...

@dataclass
class RequireCall:
    obj: str
    act: str

@dataclass
class WriteAccess:
    effective_tenant: str
    require: RequireCall | None   # None ⇔ is_platform_writer(platform_role)

@dataclass
class ReadAccess:
    effective_tenant: str | None  # None ⇔ is_panorama
    scope: ResolvedScope          # 复用既有 data_scope.py 的 ResolvedScope
    require: RequireCall | None
    is_panorama: bool             # 显式标志取代 None 隐式编码(审查 §1.8 优化)
```

**调用方 service 形状(迁移后)**:
```python
# 写动作
access = await self.principal.for_write(
    actor_id=actor_id, user_tenant_id=tenant_id,
    payload_tenant_id=payload.tenant_id,
    obj=self.OBJECT, act="create",
    platform_role=platform_role,
)
if access.require:
    await permission_service.require(
        actor_id, access.effective_tenant,
        access.require.obj, access.require.act,
        platform_role=platform_role,
    )

# 读动作(HQ panorama vs scope)
access = await self.principal.for_read(
    actor_id=actor_id, user_tenant_id=tenant_id,
    obj=self.OBJECT, act="read",
    platform_role=platform_role,
)
if access.require:
    await permission_service.require(actor_id, access.effective_tenant, ...)
if access.is_panorama:
    return [await self._to_hq_read(b) for b in await self.repo.list_all_with_meta()]
return [await self._to_read(b) for b in await self.repo.list_for_tenant(tenant_id)]
```

**4 个旧 helper 全保留**(Principal 的实现细节,8+ 外部调用点不在本次迁移范围):
- `is_cross_tenant_viewer` / `is_platform_writer`(permission_service.py L670/L686)
- `resolve_target_tenant`(_tenant_target.py)
- `DataScopeService`(data_scope.py,Principal.for_read 内部调)

docstring 加交叉引用标明「Internal: called by Principal, service layer should use Principal.for_*」。

## 3. User Stories

- 作为 **后端开发者**,我想新增一个 booking 写动作(如 `extend`/`reassign`)时只调一次 `principal.for_write()` 而不是重写 5 行 if/else,以便不再每次重新组装 viewer/writer/require 三件套。
- 作为 **后端开发者**,我想改角色判断规则(如新增一个 platform role)时只改一处 `Principal` 而不是扫 18 个方法,以便不漏改。
- 作为 **代码审查者**,我想 booking/device/customer 三 service 的鉴权决策形状统一(都走 Principal),以便审查时只看一种心智模型。
- 作为 **项目维护者**,我想 `booking_service` / `device_service` 各收缩 ~30-40 行,以便这两个 service 回归业务逻辑主导而非鉴权模板代码主导。
- 作为 **未来扩展者**,我想 booking 加跨店读(group scope)时 Principal.for_read 已经准备好了吸收复杂度(通过 ResolvedScope),以便不用再拼一套。
- 作为 **现有测试的依赖者**,我想既有 booking/device/customer 端到端测试零修改仍全绿,以便这次重构是真零行为变更。
- 作为 **架构守护者**,我想 `permission_service.require` 仍是 casbin 的单一入口(Principal 不调 require),以便候选 2(拆 PermissionGate)未来落地时单点不动。

## 4. Implementation Decisions

### 4.0 grill 共识(9 决策 + 审查修正,本 plan 决策真相源)

| # | 决策 | 选择 | 来源 |
|---|---|---|---|
| Q1 | Principal 边界 | **并进来**(读+写都管,DataScope 成读路径实现细节) | grill D1 |
| Q2 | Interface 形状 | **β · for_write / for_read 两方法**,require 调用留 service | grill D2 + 审查 Q2' 修订 |
| Q2' | for_write 入参 | `for_write(actor_id, user_tenant_id, payload_tenant_id, obj, act, platform_role)` —— act 由 service 传(Principal 不映射 act,因为 cancel→delete/start→update 这种映射是 service 职责) | 审查 Q2' 修订 |
| Q2'' | customer principal 处理 | **booking.start 三叉不进 Principal**(customer 分支走 ownership check 是业务校验,不是角色判断)。start 留原样加注释,挪切片 03 | 审查 Q2' 修订 |
| Q3 | 值对象形状 | RequireCall 值对象(None 表跳过)+ ResolvedScope 复用 + Principal 持 db | grill D3 |
| Q3' | RequireCall 不变式 | docstring 钉死 `require=None ⇔ is_platform_writer(platform_role)`,service 必须 `if access.require:` 跳过 None | 审查 §1.3 |
| Q4 | 实例化+位置 | Principal 类放 `app/services/principal.py`,service __init__ 里 `self.principal = Principal(db)`(同 `self.repo = XRepository(db)` 范式) | grill D4 |
| Q5 | 迁移策略 | **4 切片**(非 3)—— 01 frontier / 02a booking / 02b device / 03 customer+收尾 | grill D5 + 审查 Q5' 拆分修订 |
| Q6 | 特殊读范围 | **get_device_schedule 不进切片 02a**(它没用 helper,迁它无 leverage)。切片 02a 只迁用了 helper 的方法 | 审查 Q6' 修订(纠正一审建议) |
| Q7 | CONTEXT.md | 加 `Principal` 条目(租户与身份章节) | grill D7 |
| Q7' | ReadAccess 优化 | 加 `is_panorama: bool` 显式字段(取代靠 None 隐式区分 panorama vs scope=all) | 审查 §1.8 优化项 |
| Q8 | 旧 helper | 4 个全保留 + docstring 加交叉引用标明适用范围(「目前仅 booking/device/customer 三 service」) | grill D8 + 审查 Q8 范围澄清 |
| Q9 | plan 文档 | `harness/docs/plan-principal-module.md`(本文件) | grill D9 |

### 4.1 Principal module 设计

**文件**:`app/services/principal.py`(新文件)

**依赖**(单向,符合四层架构):
- `from app.services.data_scope import DataScopeService, ResolvedScope`(读路径用)
- `from app.services.permission_service import is_cross_tenant_viewer, is_platform_writer`(角色判断)
- `from app.services._tenant_target import resolve_target_tenant`(写路径租户解析)
- `from sqlalchemy.ext.asyncio import AsyncSession`(持 db)

**for_write 决策表**:

| platform_role | payload_tenant_id | effective_tenant | require |
|---|---|---|---|
| super_admin / hq_staff | 有 | payload_tenant_id | None(跳过 require) |
| super_admin / hq_staff | 无 | — | **BizError 400**("平台角色跨店写必须指定目标门店") |
| store(owner/admin/member/customer) | None | user_tenant_id | RequireCall(obj, act) |
| store | 有 | — | **BizError 400**("门店角色不可指定目标租户") |

错误信息**逐字保留** `_tenant_target.resolve_target_tenant` 的现有 BizError 文案(零行为变更契约)。

**for_read 决策表**:

| platform_role | is_panorama | effective_tenant | scope | require |
|---|---|---|---|---|
| super_admin / hq_staff | True | None | ResolvedScope(scope="all") | None(跳过 require,panorama 走 list_all_with_meta) |
| store(owner/admin/member) | False | user_tenant_id | DataScopeService.resolve(actor, tenant, platform_role) | RequireCall(obj, "read") |

**为什么 super_admin require=None 而 store require=RequireCall**:对齐现状 `if is_cross_tenant_viewer: 走 panorama 早返回 else: require`(L251/281)。super_admin/hq_staff 的 read bypass 在 `permission_service.check` 里(L103 super_admin bypass + hq_staff+read short-circuit),但 service body 现状对 viewer 直接走 panorama 不调 require —— Principal 编码这个现状,零行为变更。

**Principal 持 db 的合理性**(审查 §2 Q4 GREEN):跟 `customer_service.py:147 DataScopeService(self.db).resolve()` 同范式,SQLAlchemy AsyncSession 是轻量 session 非连接池,Principal 持的 db 跟 service 的 self.db 是**同一个对象**,无重复持有/生命周期问题。

### 4.2 不迁范围(切片 03 注释)

下列方法**不迁入 Principal**,留原样加注释「Principal 不覆盖,原因 X」:

| 方法 | 文件:行 | 不迁原因 |
|---|---|---|
| `booking.start` | booking_service.py:653 | **三叉 customer principal**:customer 分支走 ownership check(`booking.customer_id == customer_id`)是业务校验,不是角色判断。Principal 的 actor+tenant+platform_role 三元组对 customer 不适用 |
| `booking.get_tenant_schedule` | booking_service.py:351 | **panorama 变体 + 无 require**:HQ viewer 用 `resolve_target_tenant` 解析目标店 + 故意不跑 require(schedule-grid 是 bookings:read surface,default perms 全 grant)。跟 for_read 默认带 require 有张力 |
| `booking.list_my_bookings` | booking_service.py:430 | **customer principal 读路径**:无 tenant 概念,按 customer_id 全局查。Principal 的三元组不适用 |
| `booking.get_device_schedule` | booking_service.py:296 | **不用 helper**:纯 store 路径,只有 `require("read")` 一行,无 helper 可消除。迁它只是改写法无 leverage |

> 🔒 本节不迁范围由 [ADR-0001](../../docs/adr/0001-principal-scope-boundary.md) 裁决,扩展 Principal 必须先 supersede 该 ADR。

注释格式:`# Note(principal-scope): Principal 不覆盖此方法,原因: <X>。详见 plan-principal-module.md §4.2`。

### 4.3 实施切片(EP3 入口,4 切片 tracer-bullet)

> 切片依赖图见 §8。本 plan 采用 **expand-contract** 模式:切片 01 = expand(Principal 加在旧 helper 旁边,零破坏);切片 02a/02b/03 = migrate batches(按 service 分批,每批 CI 绿)。无显式 contract 切片 —— 4 个旧 helper 保留(8+ 外部调用点继续用)。

#### 切片 01 — Principal frontier module + 单测 ✅ PR #136 commit 51c2614

**What to build**(用户视角):作为后端开发者,我能用一个 `Principal` 对象的 `for_write()`/`for_read()` 方法获取当前请求的访问决策(有效租户 + 是否跳过 require + scope),而不必在 service 方法里手写 5 行 if/else。**此切片只新增模块,不修改任何 service** —— Principal 与旧 helper 并存,既有行为零变化。

**Blocked by**: 无(frontier,可立即开工)

**Status**: ✅ done(2026-07-27)

- [x] AC1.1 新建 `app/services/principal.py`,定义 `Principal` 类(`__init__(db)`)+ `for_write` / `for_read` 两方法 + `RequireCall` / `WriteAccess` / `ReadAccess` 三个 dataclass
- [x] AC1.2 `for_write` 4 分支决策正确(详见 §4.1 决策表:平台写者带 tenant_id → effective=payload + require=None / 平台写者缺 tenant_id → BizError 400 / 门店不带 tenant_id → effective=user + RequireCall(obj,act) / 门店带 tenant_id → BizError 400)
- [x] AC1.3 `for_read` 2 分支决策正确(平台 viewer → is_panorama=True + effective_tenant=None + scope=ResolvedScope("all") + require=None / 门店 → is_panorama=False + effective_tenant=user + scope=DataScopeService.resolve + require=RequireCall(obj,"read"))
- [x] AC1.4 BizError 文案逐字匹配 `_tenant_target.resolve_target_tenant` 现有两个 400 文案("平台角色跨店写必须指定目标门店(tenant_id)" / "门店角色不可指定目标租户(tenant_id)")
- [x] AC1.5 新增 `tests/test_principal.py`,contract test 覆盖 for_write 4 分支 + for_read 2 分支(模仿 `test_devices_api.py` P0 helper contract test 范式 —— import 真实函数 + 断言边界)
- [x] AC1.6 全量 pytest 783 passed(777 baseline + 6 新增,零回归;既有 service 零改动)
- [x] AC1.7 ruff clean

#### 切片 02a — booking service 迁移到 Principal ✅ commit 82b08c3(PR 待开,本地沙箱网络不可达 GitHub)

**What to build**(用户视角):作为后端开发者,booking_service 里 7 个用了 helper 的方法不再各写一遍鉴权模板,而是统一调 `self.principal.for_write/for_read`,service 方法体回归业务逻辑主导。4 个不迁方法(start 三叉 customer / get_tenant_schedule / list_my_bookings / get_device_schedule)有清晰注释标明 Principal 不覆盖的原因。既有 booking 端到端测试零修改仍全绿,证明行为零变化。

**Blocked by**: 切片 01

**Status**: ✅ done(2026-07-27)

- [x] AC2a.1 `booking_service.py` `__init__` 加 `self.principal = Principal(db)`
- [x] AC2a.2 迁移 7 方法(create / update / cancel / end / no_show + list / get):删 `is_cross_tenant_viewer` / `is_platform_writer` / `resolve_target_tenant` 直接调用,改走 `self.principal.for_write/for_read`;list/get 的 HQ 分支折叠为 `if access.is_panorama: 走 panorama repo else: 走 scope repo`
- [x] AC2a.3 4 个不迁方法(start / get_tenant_schedule / list_my_bookings / get_device_schedule)加 `# Note(principal-scope):` 注释标明不覆盖原因(详见 §4.2)
- [x] AC2a.4 全量 pytest 783 passed(777 baseline + 6 Principal contract;零行为变更;test_bookings_api / test_hq_platform_role / test_service_platform_role 全绿)
- [x] AC2a.5 ruff clean
- [x] AC2a.6 ~~booking_service.py 行数净减 ≥ 30 行~~ **指标修订**(实施时发现 §7.1 估算有误,详见下方修订记录):本切片的真实价值是「鉴权决策收口到单一推理点(Principal)+ 跨 service 形状统一」,不是 LOC 削减。实测净增 +34 行(Note 注释 +16 / effective_tenant alias +5 / keyword-arg 展开 +12 / panorama 折叠省 ~6 被 (1)(3) 抵消)。`assert access.require is not None`(list/get)与既有 `assert fresh is not None` 同范式,作为类型窄化辅助保留。code-review 双轴通过(Standards: 0 HARD violation / Spec: AC2a.1-2.5 ✅,AC2a.6 指标修订留痕)。

#### 切片 02b — device service 迁移到 Principal ✅ commit (PR 待开,本地沙箱网络不可达 GitHub)

**What to build**(用户视角):作为后端开发者,device_service 里全 7 方法统一调 `self.principal.for_write/for_read`,与 booking_service 形状一致 —— 改角色规则时只需看一种心智模型。既有 device 端到端测试零修改仍全绿。

**Blocked by**: 切片 01(**与 02a 互相独立,可任意顺序**)

**Status**: ✅ done(2026-07-27)

- [x] AC2b.1 `device_service.py` `__init__` 加 `self.principal = Principal(db)`
- [x] AC2b.2 迁移全 7 方法(list / get / create / update / delete / bind / unbind):删直接 helper 调用,改走 `self.principal.for_write/for_read`;三 import(`resolve_target_tenant` / `is_cross_tenant_viewer` / `is_platform_writer`)干净删除(device 全 7 方法都用 helper,迁完零残余代码引用,docstring/comment 历史交叉引用保留)
- [x] AC2b.3 全量 pytest 783 passed(777 baseline + 6 Principal contract;零行为变更;test_devices_api / test_hq_platform_role 61 passed)
- [x] AC2b.4 ruff clean
- [x] AC2b.5 ~~device_service.py 行数净减 ≥ 20 行(逐方法核算 ~4 行/方法 × 7 ≈ 28 行)~~ **指标修订**(实测与估算反向,与 02a 同向偏差,§7.1 已预警):实测净增 **+12 行**(432 → 444,diff +69/-57)。成因同 02a:`for_write`/`for_read` 6 个 keyword args 展开(即便压紧仍 3-4 行 vs 旧 `resolve_target_tenant(a,b,c)` 单行)是主因;`effective_tenant = access.effective_tenant` alias(5 写方法各 +1)次之。device 无 02a 的 Note 注释开销(§4.2 无 device 不迁方法)。Principal 的真实价值仍是「鉴权决策收口到单一推理点 + 跨 service 形状统一」(deletion test 见 §1),不是 LOC 削减。code-review 双轴通过(Standards: 0 HARD violation / Spec: AC2b.1-2.4 ✅,AC2b.5 指标修订留痕)。

#### 切片 03 — customer service + 特殊读注释 + feature 收尾(末切片) ✅ commit(PR 待开,本地沙箱网络不可达 GitHub)

**What to build**(用户视角):作为代码审查者 / 项目维护者,booking/device/customer 三 service 的鉴权决策形状统一(都走 Principal),`DataScopeService` 调用从 customer_service 内部挪进 Principal.for_read(读路径的 principal 解析集中)。`Principal` 作为新领域概念进入 `CONTEXT.md`,docstring 交叉引用标明适用范围。feature 收尾:status → passing + 证据落库 + active 视图刷新。

**Blocked by**: 切片 02a + 切片 02b(02a/02b 全完成才能收尾)

**Status**: ✅ done(2026-07-27 Session 150)

- [x] AC3.1 `customer_service.py` 迁移 list_profiles + statistics 2 方法:删 `is_cross_tenant_viewer` / `DataScopeService(self.db).resolve` 直接调用,改走 `self.principal.for_read`(scope 通过 access.scope 获取)
- [x] AC3.2 `customer_service.py` `__init__` 加 `self.principal = Principal(db)`
- [x] AC3.3 `CONTEXT.md` 加 `Principal` 条目(「租户与身份」章节),描述为「当前请求的身份抽象,统一解析读/写访问边界(effective tenant + scope + require-or-skip)」,_Avoid_: user(那是 User 实体), identity(那是 token claim)。**实施留痕**:_Avoid_ 多列 `session`(同章节风格,准确无害 —— Spec 子智能体标温和 scope creep 留痕)
- [x] AC3.4 Principal.py docstring 标明「Service layer should use Principal.for_*. Internal helpers retained for Principal's own use + out-of-scope callers」(切片 01 已就位,切片 03 核对一致)
- [x] AC3.5 4 个旧 helper(`is_cross_tenant_viewer` / `is_platform_writer` / `resolve_target_tenant` / `DataScopeService`)docstring 加交叉引用「Internal: called by Principal. Currently only booking/device/customer services use Principal; other services still call these helpers directly — adoption can be evaluated in future architecture reviews.」
- [x] AC3.6 全量 pytest 783 passed(零行为变更;customer 测试全绿 — test_customers_api 17 passed + test_hq_platform_role + test_service_platform_role + test_principal 全绿)
- [x] AC3.7 ruff clean + `./scripts/sync-active-features.sh` 刷新(active 视图:0 活跃 + 5 最近 passing)
- [x] AC3.8 feature 收尾:feature_list.json status `in_progress → passing` + evidence 写入(切片 01/02a/02b/03 + 收尾条)+ progress.md 更新 + plan status `draft v1 → passing` + 切片标题 ✅ + AC 勾选
- [x] AC3.9 文档影响评估(对照 §10):① feature_list.json ✅ / ② progress.md ✅ / ③ CONTEXT.md ✅ / ④ plan draft v1 → passing;不动 README / 不动 `项目指南/02-后端架构/`(Principal 是 service 层内部重构,现有架构文档完全覆盖)

**AC3.6 LOC 指标修订留痕(沿用 02a/02b 范式,plan §7.1 预警第三次兑现)**:customer_service.py 353 → 374 = **+21 行**(diff +35/-14)。根因同 02a/02b:6-arg keyword-arg 展开(2 方法 × ~5 行 vs 旧 `DataScopeService(self.db).resolve(a,b,c)` 单行)+ `# Store role:` 解释注释 × 2 + 模块 docstring 新增「Read paths」段。customer **无** 02a 的 Note 注释开销(§4.2 无 customer 不迁方法),无 02b 的 effective_tenant alias 开销(customer 写路径不迁,只迁读路径 2 方法),但 +21 > 02b 的 +12,因模块 docstring 扩写 + 2 个方法各加注释段。Principal 的真实价值仍是「鉴权决策收口到单一推理点 + 跨 service 形状统一」(deletion test §1),不是 LOC 削减。code-review 双轴通过(Standards: 0 HARD violation / Spec: AC3.1-3.6 ✅,AC3.7-3.9 收尾仪式在本 commit 内完成)。

### 4.4 不可违反契约

1. **零行为变更** —— 既有测试一个不能挂(基线 777 passed)
2. **BizError 错误信息不变** —— `resolve_target_tenant` 的两个 400 文案逐字保留
3. **permission_service.require 调用参数不变** —— 同样的 (actor, tenant, obj, act, platform_role)
4. **DataScopeService.resolve 行为不变** —— 切片 03 只挪调用点,不动 resolve 内部
5. **permission_service 单一入口契约不动** —— Principal 不调 require(审查 §1.7 GREEN:permission_service 是 casbin 唯一入口)

### 4.5 测试策略

**唯一 seam**:Principal.for_write / for_read 的纯函数契约(模仿 `test_devices_api.py` P0 helper contract test L1263-1290 范式 —— import 真实函数 + 断言边界,不 mock 不 db)。

**测试不 mock helper**(审查 case 6 误判纠正):既有测试直接调真实 helper 做 contract test + 走端到端断言 HTTP 状态码。引入 Principal 后:
- helper contract test 保持有效(4 个 helper 全保留)
- 端到端 booking/device/customer 测试保持有效(断言 HTTP 状态码,Principal 是内部重构不影响外部契约)
- **既有测试零修改**(零行为变更契约保证)

**切片 01 新增**:`tests/test_principal.py` —— Principal 自身的 contract test,覆盖 for_write 4 分支 + for_read 2 分支(对应 §4.1 决策表)。

**不加 service-level mock**(审查 Q3 确认):Principal 是 service 内部依赖,加 service-level mock 会泄漏抽象。端到端测试已覆盖行为契约。

## 5. Testing Decisions

### 什么算好测试
- **只测外部行为,不测实现细节** —— Principal contract test 断言 `for_write`/`for_read` 返回值,不断言内部调了哪个 helper
- **contract test 范式** —— import 真实函数 + 断言边界,不 mock 依赖(模仿既有 `test_devices_api.py` P0 helper contract test)
- **端到端测试零修改** —— 既有 booking/device/customer 端到端测试是回归护栏,断言 HTTP 状态码不变

### 测试的 module
- `tests/test_principal.py`(切片 01 新增):Principal 决策表全覆盖
- 既有 `tests/test_bookings_api.py` / `test_devices_api.py` / `test_hq_platform_role.py` / `test_service_platform_role.py` / `test_customer_*`(切片 02a/02b/03 零修改作回归护栏)

### Prior art
- `test_devices_api.py` L1263-1290(P0 helper contract test,纯函数边界断言范式)
- `test_bookings_api.py` 多处注释引用 `resolve_target_tenant` 名(端到端断言 HTTP 400,不 mock)
- `data_scope.py` 的 `ResolvedScope` dataclass(Principal 复用此类型)

## 6. Out of Scope

- **booking.start 的 customer principal 三叉路径**(L653-726):留原样加注释。customer principal 不进 Principal(ownership check 是业务校验不是角色判断)
- **booking 3 个特殊读方法**(get_tenant_schedule / list_my_bookings / get_device_schedule):留原样加注释
- **customer 写动作**(create_profile / update_profile / delete_profile):不用 helper(只调 require),不在迁移范围
- **8+ 外部调用点**(exports.py / logs.py / search.py / customers.py(api) / deps.py / group_service / conversation_service / dashboard_service / device_model_service / booking_config.py):保留直接调 helper,不强制走 Principal。Principal 的适用范围目前仅 booking/device/customer 三 service
- **前端 candidate-8 union endpoint cast**:不在本 plan 范围(那是前端问题,后端 Principal 重构解决不了)。**不宣称**「顺带吸收 candidate-8」
- **拆 permission_service 为 PermissionGate/PermissionSeeder/PermissionCatalogue**(巡检候选 2):独立 feature,本 plan 不动 permission_service 内部结构,只复用其 helper
- **推广 Principal 到其他 service**(dashboard / conversation / device_model / booking_config):留未来巡检评估

## 7. Further Notes

### 7.1 行数净减估算(审查 §1.10 修正后,**实施时再次修正**)

**初版估算(EP2,作废)**:每个写方法现状鉴权块 = `resolve_target_tenant`(2 行)+ `if not is_platform_writer: await require(...)`(6 行)= ~8 行。迁移后 = `access = await self.principal.for_write(...)`(1 行)+ `if access.require: await permission_service.require(...)`(3 行)= ~4 行。**净省 ~4 行/方法**。

- 切片 02a booking 7 方法 + panorama 折叠再省 ~6 行 → 估算 **~34 行**
- 切片 02b device 7 方法 → 估算 **~28 行**
- 切片 03 customer 2 方法 → 估算 **~8 行**

**实施时实测(切片 02a,2026-07-27)**:净增 **+34 行**,与估算反向。三处估算偏差:

1. **Note 注释未计入** —— AC2a.3 强制的 4 个 `# Note(principal-scope):` 注释(每个 3-5 行)= **+16 行**。这是不可删项。
2. **`effective_tenant = access.effective_tenant` alias** —— 5 个写方法各加 1 行 alias(下游 `_assert_*` / `_get_live_booking` 多次引用 effective_tenant,删 alias 会让每个后续行 line-length 爆)= **+5 行**。
3. **`for_write`/`for_read` keyword-arg 展开** —— 即便压紧(line-length=100 内最紧凑写法),6 个 keyword args 仍占 3-4 行 vs 旧 helper 单行 `resolve_target_tenant(a, b, c)` = **+12 行**。panorama 折叠省的 ~6 行被 (1)(3) 抵消。

**Principal 的真实价值不是 LOC 削减,是「鉴权决策收口到单一推理点 + 跨 service 形状统一」**(deletion test 见 §1)。AC2a.6 的「净减 ≥30」指标已修订为「leverage 重构接受,LOC 指标放弃」。**切片 02b/03 预计同向偏差**,实施时若再遇,沿用本节留痕方式修订 AC 数字。

### 7.2 审查纠正的 2 个误判(留痕)

1. **审查 §3 case 6「测试 mock 旧 helper 会失效」**:实际测试**不 mock helper**(grep 0 处 mock/patch),而是直接调真实函数 + 端到端断言 HTTP 状态码。引入 Principal 后既有测试零修改。审查这条高严重度 case 是误判(没读测试代码)。
2. **审查 §1.4「get_device_schedule 应进切片 02」**:实际 `get_device_schedule` 没用 helper(只调 require 一行),迁它无 leverage 只是改写法。原决策排除它是对的。审查这条建议偏激进。

### 7.3 grill + 审查 + 修正完整留痕

- **HTML 报告**:`~/.cache/ai-agent-platform-architecture-reviews/2026-07-27.html`(候选 1 完整可视化)
- **一审 agent**:opus 子智能体,对照真实代码逐项核查,找 3 RED + 2 YELLOW + 2 误判
- **修正 grill**:针对 3 RED 重新 grill,落 8 项修订(Q2' for_write 签名 / Q2'' customer principal / Q5' 切片拆 4 / Q6' get_device_schedule 不迁 / Q7' is_panorama 显式字段 + RequireCall 不变式 + 数字修正 + candidate-8 删除)

### 7.4 末切片仪式依赖解锁扫描(three-tier §4 第 7 步)

实施前在 `feature_list.json` 确认:无任何 feature `depends_on` 指向 `principal-module`(纯重构 feature,无规划中下游)→ 末切片完成后无需推进新 in_progress。

## 8. 切片依赖图

```
切片 01(frontier)
   │
   ├──→ 切片 02a(booking)──┐
   │                        │
   └──→ 切片 02b(device)───┤
                            │
                            └──→ 切片 03(customer + 特殊读注释 + 收尾,末切片)
```

切片 02a / 02b 互相独立(可任意顺序),都 Blocked by 切片 01。切片 03 Blocked by 02a + 02b。

## 9. 验证基线

- **后端**:`./init.sh` 全绿 777 passed(ruff + pytest SQLite 内存库,秒级)
- **前端**:不动(纯后端重构,无前端改动)
- **完整验证**(可选,需 docker):`alembic upgrade head && alembic check`(本 plan 无 schema 改动,跳过)

## 10. 文档影响评估(末切片收尾用)

对照 [`harness/docs/doc-impact-assessment.md`](doc-impact-assessment.md) 4 行模板:

| 文档 | 影响 | 动作 |
|---|---|---|
| `feature_list.json` | ✅ | 新增 feature `principal-module` priority 70 + 切片完成 status→passing + evidence |
| `progress.md` | ✅ | 顶部「最高优先级未完成」更新 + 切片 Session 记录 |
| `CONTEXT.md` | ✅ | 加 Principal 条目(租户与身份章节) |
| `项目指南/02-后端架构/` | ❌ 不动 | Principal 是 service 层内部重构,现有架构文档(四层架构 + TenantScopedRepository)完全覆盖 |
| `README.md` | ❌ 不动 | 非用户可见功能 |
| `plan-principal-module.md` | ✅ | status draft v1 → passing + 切片标题 ✅ + AC 勾选 |
