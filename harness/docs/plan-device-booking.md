# 计划:设备预约订单 CRUD + 排期(不含 start/end)

> **id**: `device-booking`
> **状态**: draft v1(EP2 回环产出,grill ✅ → to-spec → to-tickets 一个回环内完成)
> **优先级**: 63(设备功能系列 3/4)
> **创建日期**: 2026-07-23
> **依赖**: `devices-crud-ui`(priority 62)
> **范围**: 预约订单生命周期 CRUD + 时段管理 + 排期聚合。**不含** start/end/no-show 状态机动作(归 `device-poweron`)。

---

## 0. 决策记录(grill 共识)

> 本回环经 `/grill-with-docs` 烤清 8 个核心决策。用户拍板 5 个,另 3 个采用推荐默认(均对齐仓库现状/AGENTS 铁律,plan 中标注 `[默认]`)。

| # | 决策点 | 结论 | 来源 |
|---|---|---|---|
| D1 | 时段冲突状态码 | **400**(走 `BizError`) | `[默认]` 全仓库无 409 概念,与 Group 同名/device 序列号重复范式一致(`feature_list.json` verification 写「409」是笔误,以本 plan 为准) |
| D2 | 状态机纯函数 | **本 feature 不建**(`booking_state.py` 留给 `device-poweron` 建 6 态完整图) | `[默认]` AGENTS 铁律 6「按需加,不预建空架子」;本 feature 只有 pending↔cancelled 两转换,Service inline 校验足够 |
| D3 | walk-in 预约(customer_id 空) | **支持**,`customer_id` nullable + FK SET NULL | `[默认]` 对齐 `devices.customer_id` 范式;与 `device-poweron` walk-in 边界天然衔接 |
| D4 | 冲突颗粒度 | **左闭右开,无 buffer**(`start1 < end2 AND start2 < end1`) | `[默认]` 背靠背合法、SQL 易写、符合直觉 |
| D5 | customer 端视图 | **门店端 + customer 端都做** | ✅ 用户拍板 |
| D6 | 排期网格 | **后端 schedule 端点 + 前端 slot-box 三态都做** | ✅ 用户拍板 |
| D7 | 表时间列 | **一次建齐**(scheduled_* NOT NULL + started_at/ended_at/feedback nullable) | ✅ 用户拍板(notes 明确,避免 `device-poweron` 再加迁移) |
| D8 | 删除/取消语义 | **不软删,只用 cancelled 态** | ✅ 用户拍板;`bookings` 表**不加** `is_deleted`/`deleted_at` 列,无 `DELETE /bookings/{id}` 端点 |
| D9 | 取消入口 | **POST /bookings/{id}/cancel** 动作端点(→ 204) | `[默认]` 对齐 `device-poweron` 的 /start /end /no-show 风格;保持「status 只由动作端点改」铁律 |
| D10 | 改约边界 | **PUT 仅 pending 可调**;可改 scheduled_*/customer_id/notes,不可改 device_id | `[默认]` 防「取消后偷偷改时间复活」;换设备=重建 |
| D11 | customer own 端点 | **GET /me/bookings**(后端注入 `current_user.customer_id`) | `[默认]` 对齐 `/auth/me` 范式,customer 不传 id 防越权 |
| D12 | 排期时间轴 | **按天聚合**(`GROUP BY DATE(scheduled_start_at)`) | `[默认]` SQL 简单、前端渲染直观 |

---

## 1. Problem Statement

门店员工目前只能在 `devices-crud-ui` 维护设备**实例**(入库/状态/绑定),但**无法预约设备的使用时段** —— 客户「明天 10 点用某设备」这类需求无处记录、无处查看、无处防撞。

`device-booking` 填补这一层:让门店员工为本店设备创建/改约/取消预约订单,并按今日/明日/本周过滤查看 + 排期网格。客户也能在 customer 端看自己的预约。

**为什么现在做**:`devices-crud-ui` 切片 01-05 已落地(设备实例可被 CRUD + 绑定客户),预约订单是它的直接下游;`device-poweron`(系列 4/4)的 start/end/no-show 动作需要本 feature 先建好 schema(`started_at`/`ended_at`/`feedback` 三列)和状态机骨架。

---

## 2. Solution

一张租户级表 `bookings`(一次建齐全部时间列 + 6 态 status CHECK),Service 层做时段冲突检测(左闭右开,冲突 → BizError 400)+ 状态守卫(POST/PUT schema 层忽略 status,只由 `/cancel` 动作端点改)+ 跨租户/越权防护。

前端两套视图:门店端预约管理页(列表 + filter chips + 排期网格 slot-box)+ customer 端「我的预约」(只读)。

---

## 3. User Stories

- **owner/admin**(门店):为本店设备创建预约(选设备 + 可选客户 + 预约时段)、改约、取消、按今日/明日/本周看列表、看设备排期网格。
- **member**(门店):只读看本店预约列表 + 排期网格(无写按钮)。
- **customer**:在 customer 端看自己的预约列表(只读,不能创建/改/取消 —— 创建预约是门店员工的职责)。
- **super_admin/hq_staff**:跨租户只读看所有门店的预约全景(HQ 视图)。
- **device-poweron feature**(下游消费方):依赖本 feature 建好的 `started_at`/`ended_at`/`feedback` 列 + `pending`/`in_service`/`done`/`no_show` 状态值。

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端 model | 1 新 | `app/models/booking.py`(Booking ORM) |
| 后端 schema | 1 新 | `app/schemas/booking.py`(BookingCreate/Update/Read/HqRead/ + action DTOs) |
| 后端 repo | 1 新 | `app/repositories/booking.py`(BookingRepository,重写 list 加 status/device/customer filter + 排期聚合 SQL) |
| 后端 service | 1 新 | `app/services/booking_service.py`(CRUD + 时段冲突 + 状态守卫 + own 校验 + HQ 分叉) |
| 后端 api | 1 新 | `app/api/v1/bookings.py`(7+ 端点)+ `app/api/v1/me.py` 加 `GET /me/bookings`(或并入 bookings.py) |
| 后端 main | 1 改 | `app/main.py` 注册 bookings router |
| 后端权限 seed | 2 改 | `app/services/permission_service.py`(`DEFAULT_*_PERMS` + `DEFAULT_MENU_PERMS`)+ backfill 脚本 |
| alembic 迁移 | 1 新 | `alembic/versions/..._add_bookings_table.py`(down_revision=`a0eaec7aab7c`) |
| 前端 types | 1 改 | `frontend/src/api/types.ts`(Booking + DTOs) |
| 前端 endpoints | 1 改 | `frontend/src/api/endpoints.ts`(fetchBookings/create/update/cancel/schedule/me) |
| 前端 hooks | 1 改 | `frontend/src/hooks/queries.ts`(qk.bookings + 6 hooks) |
| 前端页面 | 1 新 | `frontend/src/pages/bookings-page.tsx`(StoreView + HqView + 排期网格 + customer 视图) |
| 前端路由/nav | 2 改 | `frontend/src/App.tsx` + `frontend/src/components/layout/nav-items.ts` |
| 测试 | 1 新 | `tests/test_bookings_api.py`(覆盖 CRUD + 冲突 + 状态守卫 + 租户隔离 + own 校验 + 排期聚合) |
| conftest | 1 改 | `tests/conftest.py`(import Booking) |

### 4.2 多租户影响评估

- 新增租户 scoped 表 `bookings`?**YES**(`tenant_id` FK→tenants CASCADE + 索引)
- 修改现有租户隔离逻辑?**NO**(复用 `TenantScopedRepository` 基类 + 软删重写范式)
- 引入跨租户访问点?**YES**(HQ 全景:super_admin/hq_staff 跨租户只读,守卫复用 `is_cross_tenant_viewer`)
- 验证:跨租户 GET/PUT/cancel → 404(防 enumeration,对齐 device 范式);HQ 视图测 super_admin+hq_staff 两身份

### 4.3 权限影响评估

- 新增 permission code?**YES**:`bookings:create`/`read`/`update`/`delete`(delete 用于 cancel 动作的守卫,实际语义=取消)
- 修改 `DEFAULT_*_PERMS`?**YES**:owner/admin 加 `bookings:create/read/update/delete`;member 加 `bookings:read`
- 修改 `DEFAULT_MENU_PERMS`?**YES**:owner/admin/member 各加 `bookings` code(对应 `menu:bookings`)
- 影响 60+ 处 `require_permission` caller?**NO**(只新增,不改现有)
- 影响 graph.py 工具内 check?**NO**
- customer own 校验:`GET /me/bookings` 不走 `require_permission`(customer 可能无 tenant role),改用 `current_user.customer_id` 存在性 + 非 None 校验;若 `customer_id` 为空(门店员工账号)→ 403
- scope 闸门(API token):`bookings:read/write` 自然纳入既有 scope gate 机制(`{obj}:{act}` 匹配),无需额外改造

### 4.4 数据库表设计 checklist

`bookings` 表(呼应 AGENTS.md 铁律 6):

- [x] **租户归属**:`tenant_id` String(32) FK→tenants.id `ondelete=CASCADE` NOT NULL + 普通索引 `idx_bookings_tenant`
- [ ] **软删除**:**不加**(D8 决策 —— 不软删,只用 cancelled 态)。`bookings` 无 `is_deleted`/`deleted_at` 列,无部分唯一索引
- [x] **命名**:`bookings`(snake_case,业务前缀 booking)
- [x] **双库兼容**:全用标准 SQLAlchemy 类型(String/DateTime/JSON/CheckConstraint),无 PG 专有类型(`feedback` 用 `JSON`(SQLAlchemy 通用)而非 `JSONB`,SQLite/PG 都兼容;若要 JSONB 查询性能留给 device-poweron 按需改)
- [x] **历史维度**:status 本身是状态机轨迹(6 态),`updated_at` 记最后变更;不额外加 audit(对齐仓库惯例,system_logs 不强制)
- [x] **timestamp**:`created_at`/`updated_at`(`server_default=func.now()` + `onupdate`)
- [x] **外键约束**:
  - `device_id` FK→devices.id `ondelete=SET NULL`(设备软删时保留历史 booking —— 对齐 devices.customer_id 范式)
  - `customer_id` nullable FK→customers.id `ondelete=SET NULL`(walk-in booking 可空 + 客户删时保留历史)
  - `tenant_id` FK→tenants.id `ondelete=CASCADE`
- [x] **index 策略**(查询模式驱动):
  - `idx_bookings_tenant`(tenant_id)—— 列表查询主路径
  - `idx_bookings_device_schedule`(device_id, scheduled_start_at)—— 排期网格 + 冲突检测主路径
  - `idx_bookings_customer`(customer_id)—— customer own 查询(`GET /me/bookings`)
  - `idx_bookings_status`(status)—— filter chips(待确认/爽约)+ 排期 slot-box 三态
- [x] **status CHECK**:`ck_bookings_status_valid` — `status IN ('pending','confirmed','in_service','done','cancelled','no_show')`,`server_default='pending'`(复刻 devices 表的 CheckConstraint 范式)

**时间字段**(一次建齐,D7):
- `scheduled_start_at` DateTime(tz=True) **NOT NULL** —— 预定开始(本 feature 写,排期聚合源)
- `scheduled_end_at` DateTime(tz=True) **NOT NULL** —— 预定结束(本 feature 写)
- `started_at` DateTime(tz=True) **nullable** —— 实际开始(留给 device-poweron 的 /start 写)
- `ended_at` DateTime(tz=True) **nullable** —— 实际结束(留给 device-poweron 的 /end 写)
- `feedback` JSON **nullable** —— 服务反馈(留给 device-poweron 的 /end 写)
- `notes` Text **nullable** —— 预约备注(本 feature 写,门店员工手填)

### 4.5 其他实施决策

- **状态守卫铁律**:POST/PUT 的 pydantic schema **不含** status 字段 → 客户端传 status 也被忽略(防绕过状态机)。status 只能由 `/cancel` 动作端点改。`started_at`/`ended_at`/`feedback` 同理(schema 不暴露,留给 device-poweron 端点写)。
- **冲突检测 SQL**(D4 左闭右开):`SELECT 1 FROM bookings WHERE device_id=:did AND tenant_id=:tid AND status IN ('pending','confirmed','in_service') AND scheduled_start_at < :new_end AND :new_start < scheduled_end_at LIMIT 1`。**只对活跃态(pending/confirmed/in_service)判冲突**,cancelled/done/no_show 不占时段(已释放)。改约时 `exclude_id` 排除自身。
- **confirmed 是占位态**:CHECK 允许但本 feature 永不写入(无 /confirm 端点),booking 直接从 pending 跳 in_service(对齐 StorePilot v1 处理)。
- **HQ 全景**:对齐 device 的 `DeviceHqRead` 范式 —— `BookingHqRead` extends `BookingRead` 加 `tenant_name`/`device_name`/`customer_name`,`selectinload` 防 MissingGreenlet。
- **排期聚合 SQL**(D12 按天):`SELECT DATE(scheduled_start_at) as d, ... FROM bookings WHERE device_id=:did AND tenant_id=:tid AND scheduled_start_at >= :range_start AND scheduled_start_at < :range_end GROUP BY DATE(scheduled_start_at) ORDER BY d`。返 `{date: [booking,...]}`。slot-box 三态由 status 派生:pending/confirmed→booked、in_service→active、done→done。
- **错误处理**:复用现有 `BizError`(400)/`NotFoundError`(404)/`PermissionError`(403)三件套,全局 handler 已注册,无新增。

---

## 5. Testing Decisions

- **测试金字塔**:integration 为主(每个 API 端点至少 1 个测试章节),unit 补时段冲突纯逻辑(可选抽 helper)。无 E2E(前端 build + oxlint 即可)。
- **测试库**:SQLite 内存库(conftest 既有 fixture)。本 feature 无 PG 专有类型(`feedback` 用通用 JSON),SQLite 完全兼容。**无需真 PG**(不像 pgvector/knowledge-base 那样必须 docker)。
- **覆盖率目标**:不低于仓库基线 93%。新增 service/repo/api 全覆盖。
- **边界 case 清单**:
  - 时段冲突:同设备同时段重叠 → 400;背靠背(11:00 结束 + 11:00 开始)→ 201(不冲突);改约排除自身 → 200;cancelled 态占的时段可被新 booking 复用 → 201
  - 状态守卫:POST 传 `status=done` → 创建后 status 仍为 pending;PUT 传 status → 忽略;POST 传 started_at/feedback → 忽略
  - 状态转换:pending → cancel(204);cancelled → cancel 再调 → 幂等 204 或 400(见切片决策);cancelled → PUT 改约 → 400(终态不可改)
  - 租户隔离:跨租户 GET/PUT/cancel → 404(防 enumeration)
  - 权限矩阵:owner/admin 写 200,member 写 403,unauth 401,hq_staff 写 403(只读)
  - customer own:`GET /me/bookings` 用 customer 身份 → 只看自己的;门店员工身份(无 customer_id)→ 403;walk-in booking(customer_id 空)不在 customer 视图出现
  - 排期聚合:某设备某天有 2 条 booking → 返 `{date: [b1, b2]}`;无 booking 的天 → 该 date key 不出现或空数组(见切片)
  - device/customer SET NULL:设备软删后 booking 仍可见(device_id 保留但 device 关系为 None);客户删后 customer_id SET NULL
- **多租户隔离测试**:至少 3 条(不同租户互不可见 + 跨租户操作 404 + HQ 跨租户可见)。

---

## 6. Out of Scope(边界声明)

❌ **不做**(归 `device-poweron` 系列 4/4):
- `/bookings/{id}/start`(pending/confirmed → in_service,填 started_at)
- `/bookings/{id}/end`(in_service → done,填 ended_at + feedback)
- `/bookings/{id}/no-show`(→ no_show)
- `/bookings/{id}/confirm`(→ confirmed)—— confirmed 是 CHECK 占位态,补 confirm 端点是 backlog
- `booking_state.py` 6 态纯函数(D2)
- 硬件下发链路(MQTT/WS/寻址)—— 系列外,未来 IoT feature

❌ **不做**(本 feature 边界):
- 重复预约提醒/通知(无通知基础设施)
- 预约导出/报表
- 客户自助创建/取消预约(创建预约是门店员工职责)
- `bookings` 表的 `is_deleted` 软删(D8,只用 cancelled 态)
- IoT 风险采集(risk_ack/血压,那是医疗特定业务,本 SaaS 脚手架不假设)

---

## 7. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 时段冲突并发(两个请求同时建同设备同时段) | 中 | Service 层 `SELECT ... FOR UPDATE` 行锁(device 行)+ 冲突检测;SQLite 测试无并发,真 PG 靠 device 行锁兜底。本 feature 不上应用层分布式锁(YAGNI) |
| `device_id` SET NULL 后排期查询 device_name 缺失 | 低 | HQ 视图 `device_name` nullable,前端显示「已删除设备」 |
| customer 端 own 校验绕过(传他人 customer_id) | 高 | `GET /me/bookings` 后端注入 `current_user.customer_id`,**忽略**客户端传入的 customer_id 参数;端点不接受 customer_id 参数 |
| status 被客户端绕过(POST 传 status=done) | 高 | pydantic schema 不含 status 字段(防注入);DB CHECK 是 backstop |
| depends_on `devices-crud-ui` 仍 in_progress(切片 06-07 待做) | 中 | 本 feature **不依赖** devices 前端 UI,只依赖后端 Device 表 + DeviceService(切片 01 已落地 ✅)。前端可平行开发;但 EP3 实施须等 devices-crud-ui 全 passing 后再开(WIP=1) |
| `feedback` JSON vs JSONB 性能 | 低 | 本 feature `feedback` 永远是 null(device-poweron 才写),用通用 JSON 足够;若 device-poweron 需 JSONB 查询,届时一次 ALTER 改类型 |

---

## 8. 验收标准(同步 feature_list.json verification,以本 plan 修正版为准)

> ⚠️ feature_list.json verification 第 3/4 条的「409」「DELETE /api/v1/bookings」是**笔误**,以本 plan 的 D1(400)/D8(无 DELETE,用 POST /cancel)为准。实施完成后回填 feature_list.json 修正。

1. 后端:`POST/GET/PUT /api/v1/bookings` + `POST /api/v1/bookings/{id}/cancel` + `GET /api/v1/devices/{id}/schedule` + `GET /api/v1/me/bookings`;`bookings.tenant_id` FK CASCADE,`device_id` FK→devices SET NULL,`customer_id` nullable FK→customers SET NULL
2. `bookings` 时间字段一次建齐:`scheduled_start_at`/`scheduled_end_at` NOT NULL(本 feature 写)、`started_at`/`ended_at`/`feedback` nullable(留给 device-poweron)
3. status CHECK 6 态(default pending);本 feature 只允许 pending→cancelled 流转(POST/PUT schema 层忽略 status,只由 /cancel 改)
4. 权限:门店 staff+ 写,member 读;customer 端 `GET /me/bookings` 只看自己的;排期要求本租户设备
5. 前端:门店端预约管理页(列表 + filter chips 今日/明日/本周/待确认/爽约 + 排期网格 slot-box booked/active/done)+ customer 端预约视图(只看自己)
6. pytest:覆盖 CRUD + 状态流转(pending↔cancelled)+ 状态机绕过防护 + 时段冲突(重叠 → **400** 不是 409)+ 租户隔离 + 权限矩阵 + customer own 校验 + 排期聚合 SQL + alembic check 无 drift
7. `cd frontend && npm run build` 通过 + oxlint 0 warnings

---

## 9. 不越界声明

本次改动**只**涉及:`bookings` 表 + 其 CRUD/cancel/schedule API + customer own 端点 + 前端 bookings-page + 权限 seed;**不**触碰 devices/customer_profiles 的现有后端逻辑(只读引用其表)、**不**实现 device-poweron 的 start/end/no-show 动作、**不**加 `bookings` 软删列、**不**改 devices-crud-ui 的前端 UI(平行存在)。

---

## 实施切片(7 个 tracer-bullet 垂直切片,每个切片一个 context window 完成)

> 切片原则:每切片是窄而全的垂直切片(Model→Migration→Repo→Service→API→测试闭环),不是按层水平切。每切片可独立 demo/verify。阻塞边明确,frontier 上无 blocker 的切片可立即开工。
>
> 实施节奏:一次一个切片,用 `/implement` 推进,切片间清 context。WIP=1 仍然适用 —— 同一时刻只在一个切片上 in_progress,该切片全绿才进下一个。**前置条件**:`devices-crud-ui` 全 passing(本 feature 依赖其切片 01 的 Device 表 + DeviceService,虽已合并 main,但 EP3 开工须等 devices-crud-ui 收尾)。

### 切片 01 — 后端地基:Booking 表 + 时段冲突 + 状态守卫 CRUD ✅ (PR #106)

**Blocked by:** 无 —— 可立即开工(依赖 devices-crud-ui 切片 01 已 ✅)

**What it delivers:** 一个 tenant 内的 owner/admin 能创建/读/改/取消本店设备的预约订单(选设备 + 可选客户 + 预约时段),member 只读,跨租户操作返 404 防 enumeration。同设备同时段重叠 → 400(走 BizError,非 409)。POST/PUT schema 层忽略 status/started_at/ended_at/feedback(防绕过状态机)。本切片**不含** HQ 全景、不含排期网格端点、不含 customer own 端点、不含前端、不含权限 backfill。

**Acceptance criteria:**
- [x] `app/models/booking.py`:`Booking` ORM model(audit 列 / 6 态 status CHECK / 5 个时间字段一次建齐 / FK 写法对齐 `Device`)
- [x] alembic 迁移:down_revision=`a0eaec7aab7c`,`create_table` + `CheckConstraint(status IN (...))` name=`ck_bookings_status_valid` + 4 个 index(`idx_bookings_tenant`/`idx_bookings_device_schedule`/`idx_bookings_customer`/`idx_bookings_status`),**upgrade 和 downgrade 都写全**(防 drift)
- [x] `app/schemas/booking.py`:`BookingStatus = Literal[...]`、`BookingBase`/`BookingCreate`(**不含** status/started_at/ended_at/feedback)/`BookingUpdate`(**不含** status/device_id,仅 pending 可调)/`BookingRead`
- [x] `app/repositories/booking.py`:`BookingRepository(TenantScopedRepository[Booking])`,重写 `get_for_tenant`/`list_for_tenant`(无软删,故不滤 is_deleted),新增 `find_overlap(tenant_id, device_id, new_start, new_end, exclude_id=None)`(左闭右开 SQL,只对 pending/confirmed/in_service 态判冲突)、`list_for_device_schedule(tenant_id, device_id, range_start, range_end)`
- [x] `app/services/booking_service.py`:`_get_live_booking`(跨租户/不存在 → NotFoundError)、`_assert_no_overlap`(→ BizError 400,**不是 409**)、`_assert_device_in_tenant`(设备须本租户活设备,复用 `DeviceRepository.get_for_tenant`)、`_assert_customer_in_tenant`(可空,非空时校验,复用 `CustomerProfileRepository`)、`create`/`update`(PUT 仅 pending 可调,cancelled 等终态 → BizError)、`cancel`(pending→cancelled)
- [x] `app/api/v1/bookings.py`:`GET/POST/PUT /api/v1/bookings` + `POST /api/v1/bookings/{id}/cancel`(→ 204,**无 DELETE 端点**,D8/D9)+ `app/main.py` 注册 router
- [x] `tests/conftest.py` 的 `from app.models import (...)` 块加 `Booking`
- [x] `tests/test_bookings_api.py` 章节:A(CRUD 全字段断言)+ B(跨租户 GET/PUT/cancel → 404 防 enumeration)+ C(时段冲突:同设备同时段重叠 → **400**;背靠背 11:00 结束+11:00 开始 → 201;cancelled 态占的时段可复用 → 201;改约 exclude 自身 → 200)+ D(状态守卫:POST 传 status=done → 仍 pending;PUT 传 status → 忽略;POST 传 started_at/feedback → 忽略)+ E(状态流转:pending→cancel 204;cancelled→PUT 改约 → 400;cancelled→cancel 再调 → 幂等 204)+ F(权限矩阵:owner/admin 写 200,member 写 403,hq_staff 写 403,unauth 401)+ G(walk-in:customer_id 空 → 创建成功 201,GET 正常显示「未指定客户」)+ H(device/customer SET NULL:设备软删后 booking 仍可见 + customer SET NULL FK 声明校验)
- [x] 本地 `alembic upgrade head` 通过(SQLite 内存库)—— 注:本仓库迁移为 PG-only(早期迁移用 `now()` 默认值),SQLite 走 `Base.metadata.create_all`(conftest 既有路径);alembic head 链 `a0eaec7aab7c → 8423ee2df128` 已验证正确,真 PG `alembic check` 走 CI

---

### 切片 02 — 权限 seed + 老租户 backfill(不破坏现存租户) ✅ PR #107

**Blocked by:** 01(bookings obj/act 已在 Service 里被 require,backfill 才有目标)

**What it delivers:** 新建租户的 owner/admin/member 自动拿到 bookings 权限和 `menu:bookings`;**现存所有租户**也能拿到(backfill 幂等),功能上线即用,不破坏其他 perm。

**Acceptance criteria:**
- [x] `app/services/permission_service.py`:`DEFAULT_OWNER_PERMS`/`DEFAULT_ADMIN_PERMS` 加 `bookings:create/read/update/delete`;`DEFAULT_MEMBER_PERMS` 加 `bookings:read`
- [x] `DEFAULT_MENU_PERMS["owner"|"admin"|"member"]` 各加 `"bookings"` code(对应 `menu:bookings`)
- [x] 新增 `backfill_bookings_perms_for_existing_tenants(db)` 函数:扫 `tenants` 表未软删租户,对每个租户的 owner/admin/member role 幂等补 bookings 相关 perm(调 `_upsert_permission` + `RolePermissionRepository.grant` + `sync_role_permissions_to_casbin`),**只动 bookings/menu:bookings 相关,不碰其他 perm**(复刻 devices 切片 02 范式)
- [x] `scripts/backfill_bookings_perms.py` 独立一次性脚本(async main + DB session 初始化 + 调上述函数 + 打印每租户补了几条),CI 不跑,手动执行一次
- [x] `tests/test_bookings_api.py` K 章节:K1 造无 bookings 策略租户 fixture → K2 跑 backfill → K3 owner 拿全 + `menu:bookings` → K4 member 只 `bookings:read` + `menu:bookings`(防过度授权)→ K5 幂等(再跑 no-op 不报错)→ K6 其他 perm(如 `devices:read`)不受影响

---

### 切片 03 — HQ 全景视图 + 排期聚合端点(后端) ✅ PR #108

**Blocked by:** 01(共用 BookingService 骨架)

**What it delivers:** super_admin 和 hq_staff 能看到跨所有租户的预约全景(带 tenant_name/device_name/customer_name);门店员工能查某设备的排期网格(按天聚合,某天有哪些 booking)。hq_staff 写端点返 403。

**Acceptance criteria:**
- [x] `app/schemas/booking.py` 加 `BookingHqRead`(全景字段:tenant_name/device_name/customer_name,nullable)
- [x] `app/repositories/booking.py` 加 `list_all_with_meta()` / `get_all_with_meta(booking_id)`:`selectinload(Booking.tenant)` / `selectinload(Booking.device)` / `selectinload(Booking.customer)`(防 N+1 + MissingGreenlet,复刻 device 范式)+ `list_for_device_schedule` 实现按天聚合(Python 端 `itertools.groupby` 聚合 —— SQLite/PG `DATE()` 在 tz-aware datetime 上语义漂移,Python `.date()` 跨库确定;实测 SCH-1/SCH-2 覆盖)
- [x] `app/services/booking_service.py`:`list(actor_id, tenant_id, platform_role)` / `get(...)` 接 `platform_role` 参数,用 `is_cross_tenant_viewer` 分叉返 `BookingHqRead` vs `BookingRead`;新增 `get_device_schedule(tenant_id, device_id, range_start, range_end)` 返 `dict[date, list[BookingRead]]`(加 `from __future__ import annotations` 修 `list` 方法遮蔽 builtin 的注解求值 bug)
- [x] `app/api/v1/bookings.py`:`GET /` 和 `GET /{id}` **改为端点函数体内分流**(复刻 devices.py 范式,移除切片 01 临时 router-level `require_permission("bookings","read")` 依赖);新增 `GET /api/v1/devices/{device_id}/schedule?start=&end=`(挂 devices router,range 默认今日±7 天,要求本租户设备,跨租户/不存在 → 404)
- [x] `tests/test_bookings_api.py` HQ 章节(HQ-1~4:super_admin 全景 + 跨租户读、hq_staff 全景 + 写端点 403)+ 排期章节(SCH-1 同天聚合、SCH-2 空天省略、SCH-3 跨租户设备 404、SCH-4 不存在设备 404)

---

### 切片 04 — customer own 端点(GET /me/bookings,防越权) ✅ PR #110

**Blocked by:** 01(共用 BookingService 骨架)

**What it delivers:** customer 身份能看自己的预约列表(只读,只看 `customer_id = current_user.customer_id` 的 booking)。门店员工账号(无 customer_id)调此端点 → 403。后端注入 customer_id,**忽略**客户端传入参数(防越权看他人预约)。

**Acceptance criteria:**
- [x] `app/api/v1/me.py`(或并入 bookings.py):新增 `GET /api/v1/me/bookings`,用 `current_user.customer_id` 过滤;若 `customer_id` 为 None(门店员工)→ 403 `BizError`/`PermissionError`
- [x] **端点不接受 customer_id 查询参数**(防越权);复用 `BookingRepository.list_for_customer(customer_id)` 或新增方法
- [x] `app/repositories/booking.py`:新增 `list_for_customer(customer_id)`(按 customer_id 过滤,无需 tenant_id 校验 —— customer 是全局身份,但对齐仓库可加 tenant scope)
- [x] `app/services/booking_service.py`:`list_my_bookings(customer_id)` 返 `list[BookingRead]`(不带 tenant_name 等 HQ 字段,customer 只看自己)
- [x] `tests/test_bookings_api.py` M 章节:M1 customer 身份 → 只看自己的 booking(造 2 条自己 + 1 条他人,只返 2 条)+ M2 门店员工身份(无 customer_id)→ 403 + M3 walk-in booking(customer_id 空)→ 不出现在任何 customer 的 /me/bookings + M4 端点忽略传入的 customer_id 参数(传他人 id 仍只返自己的)

---

### 切片 05 — 前端地基:types/endpoints/queries + 路由 + nav ✅ PR #111

**Blocked by:** 03(`BookingHqRead` schema 定型 + schedule 端点形状定型),04(`/me/bookings` 形状定型)

**What it delivers:** 前端拿到 bookings 的完整类型和 API client,`/bookings` 路由可达(空页即可),nav 项出现。UI 实现留给切片 06/07。

**Acceptance criteria:**
- [x] `frontend/src/api/types.ts`:`Booking`、`BookingCreate`、`BookingUpdate`、`BookingStatus`、`BookingHqRead`、`DeviceSchedule`( `{ [date: string]: Booking[] }` )
- [x] `frontend/src/api/endpoints.ts`:`fetchBookings()`、`fetchBooking(id)`、`createBooking(payload)`、`updateBooking(id, payload)`、`cancelBooking(id)`(POST /cancel,**不是 DELETE**)、`fetchDeviceSchedule(deviceId, start, end)`、`fetchMyBookings()`(打 /me/bookings)
- [x] `frontend/src/hooks/queries.ts`:`qk.bookings` / `qk.deviceSchedule` / `qk.myBookings` + `useBookings()`、`useCreateBooking()`、`useUpdateBooking()`、`useCancelBooking()`、`useDeviceSchedule(deviceId, start, end)`、`useMyBookings()`(+ `useBooking(id)` 顺带补齐,与 useDevice/useCustomerProfile 范式一致)
- [x] `frontend/src/App.tsx`:`const BookingsPage = lazy(...)` + `<Route path="/bookings" element={<BookingsPage/>}/>`(裸 ProtectedRoute,member 可读)
- [x] `frontend/src/components/layout/nav-items.ts`:业务管理 subgroup 加 `{ to: "/bookings", label: "预约", icon: <Calendar/>, menuCode: "menu:bookings" }`(注:文件约定用 component ref `icon: Calendar`,非 JSX)
- [x] `cd frontend && npm run build` + `npx oxlint` 通过(✓ built 1.67s + 0 warnings/errors)

---

### 切片 06 — 前端门店端 StoreView(列表 + filter chips + 排期网格 + CRUD Dialog) ✅ PR #112

**Blocked by:** 05

**What it delivers:** 门店 owner/admin 在 `/bookings` 看到本店预约表格,能创建/改约/取消;member 只读,写按钮按 `hasPermission` 隐藏。filter chips(今日/明日/本周/待确认/爽约)过滤列表。排期网格 slot-box 三态(booked/active/done)按天展示某设备的预约。

**Acceptance criteria:**
- [x] `frontend/src/pages/bookings-page.tsx` StoreView:列表 Table(设备名 / 客户名 / 预约时段 / 状态 Badge / 创建时间 / 操作 DropdownMenu)
- [x] filter chips:今日 / 明日 / 本周 / 待确认(status=pending)/ 爽约(status=no_show)—— 复用 shadcn Badge/Tabs 或新建 chip 组件(无既有范式,新建)
- [x] 状态 Badge 映射:pending→待确认(dot-warning)/ confirmed→已确认 / in_service→服务中(dot-success)/ done→已完成 / cancelled→已取消(dot-muted)/ no_show→爽约(dot-destructive)
- [x] 创建 Dialog:设备 Select(本租户活设备,从 `useDevices()` 拉)+ 客户 Select(可选,从 `useCustomerProfiles()` 拉,含「不指定客户」walk-in 选项)+ scheduled_start_at/scheduled_end_at DateTime Input + 备注 Input
- [x] 改约 Dialog:仅 pending 态可点(cancelled/done 等禁用按钮);可改 scheduled_*/customer_id/notes,**不可改 device_id**(灰显)
- [x] 取消按钮:pending → 点击确认 Dialog → `cancelBooking(id)`;cancelled/done 等终态隐藏取消按钮
- [x] 排期网格:选某设备后展示 7 天 × slot-box,每格列出当天 booking(状态三态色);复用 `useDeviceSchedule(deviceId, today, today+7d)`
- [x] 时段冲突 UX:创建/改约返 400 时,toast 显示后端冲突信息(不前端预判)
- [x] `canCreate`/`canUpdate`/`canCancel` 用 `hasPermission(me,"bookings",act)` 隐藏写按钮
- [x] `cd frontend && npm run build` + `npx oxlint` 通过(✓ built 1.93s + 0 warnings/errors)

---

### 切片 07 — 前端 HqView + customer 视图 + 整体验证收尾

**Blocked by:** 06

**What it delivers:** super_admin 和 hq_staff 在 `/bookings` 看到跨租户只读全景表格;customer 身份看到「我的预约」只读列表;整 feature 走完 `./init.sh` 全绿 + feature_list.json/progress.md 更新 + 文档影响评估。

**Acceptance criteria:**
- [ ] `bookings-page.tsx` 顶层三叉:`isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : hasCustomerIdentity(me) ? <MyBookingsView/> : <StoreView/>`
- [ ] HqView:跨租户表格(列:tenant_name / 设备名 / 客户名 / 预约时段 / 状态 Badge),只读,无写按钮
- [ ] MyBookingsView:customer 身份只读列表(调 `useMyBookings()`),无写按钮(创建预约是门店员工职责)
- [ ] `hasCustomerIdentity(me)` helper 判断 `me.customer_id` 非空(新建于 `frontend/src/lib/permission.ts`,参照 isHQStaff 范式)
- [ ] `./init.sh` 全绿(ruff + pytest 全章节 A-M + frontend build + oxlint)
- [ ] `alembic upgrade head && alembic check` 本地通过(若本地 docker 起不来,依赖 CI 通过)
- [ ] `feature_list.json`:`device-booking` status=`passing` + evidence 字段写实测结果 + **修正 verification 第 3/4 条笔误**(409→400、DELETE→POST /cancel)
- [ ] `./scripts/sync-active-features.sh` 刷新 active 视图
- [ ] `progress.md` 加 Session 记录 + 更新「当前最高优先级未完成功能」指向 device-poweron
- [ ] 文档影响评估(4 行格式)

---

### 切片依赖图

```
01 (后端地基:表+冲突+状态守卫 CRUD) ──┬─→ 02 (权限 seed + backfill)
                                         ├─→ 03 (HQ 全景 + 排期聚合后端) ──┐
                                         └─→ 04 (customer own 端点)     ──┤
                                                                            ↓
                                                                  05 (前端地基) ──→ 06 (StoreView) ──→ 07 (HqView+customer视图+收尾)
```

**Frontier 推进策略**:
- 切片 01 完成后,02/03/04 三者 blocker 都是 01,逻辑上可并行,但 WIP=1 要求**串行** —— 推荐 02 → 03 → 04 顺序(02 是上线即用必备,03 改动 01 的 API 守卫最好早做避免后续返工,04 相对独立)
- 切片 05 等 03+04 都完成(HQ + customer own schema 都定型)
- 切片 06 → 07 严格串行

---

## 调研证据(Explore + codegraph,2026-07-23)

| 关键论点 | 出处 |
|---|---|
| 全仓库无 409 ConflictError,所有冲突走 BizError → 400 | `app/services/errors.py:11-30` + `app/main.py:299-314` 全局 handler |
| 子类化 BizError + 注册专用 handler 覆盖状态码的唯一先例(ScopeError→422) | `app/main.py:310` 注释强调注册顺序 |
| `_assert_serial_unique`(device)/`_assert_code_unique`(group)是冲突 assert 范式 | `app/services/device_service.py:110-122` / `app/services/group_service.py:69-75` |
| `TenantScopedRepository` 基类只有 get/add/list_for_tenant/get_for_tenant + 硬删 delete | `app/repositories/base.py:18-63` |
| DeviceRepository 重写 get/list 加 is_deleted 过滤 + get_by_tenant_serial(exclude_id)范式 | `app/repositories/device.py:39-84` |
| migrations head = `a0eaec7aab7c`(devices 表,down=`e649e80a4169`) | `alembic/versions/2026_07_22_1000_a0eaec7aab7c_add_devices_table.py:36-37` |
| `customer_id` nullable + FK SET NULL 写法(devices 表) | `alembic/versions/2026_07_22_1000_a0eaec7aab7c_...py:55,79-81` |
| devices.status CHECK 约束写法(全仓库唯一 DB 层状态范例;customer_profiles 4 态无 CHECK) | `alembic/versions/2026_07_22_1000_a0eaec7aab7c_...py:49-54,89-92` |
| 全仓库无 booking_state.py / StorePilot 参考;唯一状态变更是 user.change_status(非转换图) | `app/services/user_service.py:385-398` |
| HQ 全景范式(DeviceHqRead + selectinload + 端点体内分流 + is_cross_tenant_viewer) | `app/schemas/device.py:63-80` + `app/api/v1/devices.py:59-91` + `app/services/device_service.py:78-96` |
| 前端双视图范式 `isSuperAdmin(me) ? <HqView/> : <StoreView/>`(customers-page 实际只用 isSuperAdmin) | `frontend/src/pages/customers-page.tsx:120-128` + `frontend/src/lib/permission.ts:27-44` |
| 前端 filter chips(今日/明日/本周)**无既有范式**(logs-page 用 Select 下拉,非 chip) | `frontend/src/pages/logs-page.tsx:165-210` |
| StoreView 骨架(button-level 权限 + Dialog) | `frontend/src/pages/customers-page.tsx:134-160` |
| 权限 backfill 脚本范式(devices 切片 02) | `scripts/backfill_devices_perms.py` + `permission_service.DEFAULT_*_PERMS` |
