# 计划:预约排期网格(HqView 设备×时间网格 + 两级预约配置)

> **状态**:draft v2(2026-07-26,二轮审查修正)
> **feature**:`booking-schedule-grid`(priority 69,area 业务实体,depends_on `platform-cross-tenant-write` 已 passing)
> **EP 层级**:EP2 回环产物(本 plan = `/to-spec` + `/to-tickets` 产出,待 EP3 实施)
> **demo 形态已确认**:`harness/demo/booking-schedule-grid-demo.html`(用户验收过,见 §4.5 D0)

---

## 0. v1 → v2 变更摘要(二轮审查修正记录)

本 plan 经 3 个子智能体二轮审查(技术准确性 / 决策一致性 / 切片质量),修正以下问题:

| # | 问题 | 严重度 | v2 处理 |
|---|---|---|---|
| M1 | priority 59 与 feature_list.json 69 不一致 | 🔴 必修 | 改为 69(header) |
| M2 | §7 ASCII 图画错 `02→04a`(04a 无此依赖)+ 04a "Blocked by 无"与"排在 03 后"自相矛盾 | 🔴 必修 | 04a 改 `Blocked by: 03`(BookingConfig 类型契约);§7 图与拓扑序重画 |
| M3 | hq-view.test.tsx 现有测试数写成 9,实际是 8(三处) | 🔴 必修 | 全文 9→8 |
| M4 | router 注册写 `app/api/v1/__init__.py`(空文件),实际在 `app/main.py` | 🔴 必修 | 改为 `app/main.py`(对齐 tenant_config 范式) |
| P1 | 缺 §0 v1→v2 变更摘要(prd-template §0 必填) | 🟡 补强 | 本节 |
| P2 | 缺「booking_configs 无 DB 唯一约束」AC(D2 核心论证点未锁) | 🟡 补强 | 切片 01 AC 加一条 |
| P3 | effective fallback AC 未拆三种 DB 状态 | 🟡 补强 | 切片 01 AC 拆三条 |
| P4 | 切片 03 `BOOKING_WRITE_KEYS` 命名误导(配置改应失效 config 缓存非 booking 写缓存) | 🟡 补强 | 改 `BOOKING_CONFIG_KEYS`,与 04b 一致 |
| P5 | 04a 缺「沿用 demo CSS class 名作测试 selector」 | 🟡 补强 | 04a AC 加一句 |
| P6 | 04a hover tooltip 测法未说(jsdom 不支持 :hover) | 🟡 补强 | 04a AC 补 data-tooltip 断言 |
| P7 | 04b 预填值测法未说 | 🟡 补强 | 04b AC 补 spy-on-children |
| P8 | §4.5 D0 漏记 `--time-col-w: 88px` | 🟢 打磨 | 补 |
| P9 | §8 缺「配置生效范围:当前仅 HqView 网格」澄清(门店角色改配置的视觉反馈) | 🟡 补强 | §8 + §4.3 加澄清 |

---

## 1. Problem Statement

超级管理员/平台角色(super_admin + hq_staff)在 HqView 选目标门店后,**当前只能看到跨店预约列表表格**(`hq-view.tsx` 的 `<Table>`),无法直观看到「某天某店各设备的可预约时段分布」。要创建预约得手填 `datetime-local`,体验断裂。

用户需求:选目标门店后,展示**设备(X 轴)× 时间(Y 轴)**的排期网格,可点击空时段预约;预约时长(默认 45 分钟)和可预约时段(默认 08:00-22:00)需**灵活配置**,支持「平台默认 + 租户覆盖」两级。

---

## 2. Solution

- **前端**:HqView 选 target 后加 **Tabs**(手搓,沿用 `FilterChips` 范式),列表视图(现有)/ 网格视图(新)并存。网格视图 = 日期选择 + 「设备×时间」网格 + 点击空 cell 弹 `BookingCreateDialog`(复用)。
- **后端**:新增「按天查某店全设备预约」端点(现有只有单设备 schedule 或全量列表,无租户级按天窗口查);新增 `booking_configs` 两级配置表(平台默认 + 租户覆盖)。
- **配置存储**:照抄 `model_pricing` 范式(单表 `tenant_id` 可空,service upsert 不用 DB 约束,`get_effective` 三级 fallback)。
- **向后兼容**:现有 HqView 列表视图零变化;门店角色 StoreView 不动;现有 `ScheduleGridCard`(StoreView 单设备 7 天视图)保留不动。

---

## 3. User Stories

- **US1**(平台角色排期查看):作为 super_admin,我选定目标门店 + 日期后,能看到该店所有设备的当日预约排期网格,一眼看出哪个设备哪个时段被占、哪个空闲。
- **US2**(快速预约):作为 super_admin,我在网格上点一个空时段,直接预填设备 + 时段,弹 Dialog 填客户/备注即可预约,不用手填时间。
- **US3**(防误约):已占用时段和今天已过时段在网格上明显标记为不可点,我从视觉上就知道哪些不能约。
- **US4**(配置灵活):作为 super_admin,我能设平台默认的预约时长(45 分钟)和可预约时段(08:00-22:00);作为门店 owner,我能覆盖本店的配置(比如改成 60 分钟、09:00-21:00)。
- **US5**(日期导航):我能选今天或往后的日期查看排期(不能选过去日期)。

---

## 4. Implementation Decisions

### 4.0 grill 共识(D0-D7,本 plan 决策真相源)

| # | 决策点 | 选定方案 | 理由 |
|---|---|---|---|
| **D0** | 网格视觉/交互形态 | **布局 A**(设备为列,时间为行)+ 卡片式表头(大设备名+ID+状态圆点)+ 斜线分隔交叉格 + 整点大字/半点淡色 + 表格居中不撑满 + 45分钟=1整行+1半行(虚线+→:45) + 已占用=状态色块+客户名+hover tooltip 不可点 + 点空cell高亮+右下角确认面板 | **用户已在 demo 验收确认**(`harness/demo/booking-schedule-grid-demo.html`)。这是不可更改的视觉真相源,实施时严格对齐 |
| **D1** | 视图共存 | HqView 选 target 后加 **Tabs**(列表/网格),默认列表,不破坏现有 | 用户明确要求并存;现有 HqView 列表视图是写视图(platform-cross-tenant-write 切片 04 落地),不能替换 |
| **D2** | 配置存储 | **新建 `booking_configs` 表**,照抄 `model_pricing` 范式(单表 `tenant_id` 可空,平台默认 `tenant_id IS NULL` + 租户覆盖 `tenant_id = X`,service 层 upsert 不用 DB 约束,repo 继承 **`BaseRepository`** 而非 `TenantScopedRepository`) | (1) `model_pricing` 是项目已有的成熟两级配置范式;(2) `TenantScopedRepository` 强制 `tenant_id == X` 会把 NULL 的平台默认行过滤掉,不能用;(3) 部分唯一索引需 NULLS NOT DISTINCT,PG/SQLite 语义冲突,故不用 DB 约束(对齐 LlmConfig/ModelPricing 注释)。**为何不塞进 `tenant_configs`**:`tenant_configs` 是纯租户级(无平台默认行),无法表达「平台默认 + 租户覆盖」两级,领域上也与白标品牌配置解耦更清晰 |
| **D3** | 时长「灵活配置」形态 | `default_duration_minutes: Integer`(任意分钟数,前端校验合理范围如 15-240),**不是 {45,60} 枚举** | 用户原话「要求可以灵活配置时间长度」是对**配置能力**的要求,非取值限制。前端 UI 给常用预设(45/60/90)+ 自定义输入,后端存任意整数(分钟)。这避免了「加个 30 分钟档就要改枚举」的扩展问题 |
| **D4** | 按天查询数据源 | **新增 `GET /bookings/schedule-grid?tenant_id=&date=` 端点**,后端按天返回该店全设备 `BookingHqRead[]`,repo 层加 `list_for_tenant_schedule(tenant_id, range_start, range_end)` + **新建 `(tenant_id, scheduled_start_at)` 复合索引** | (1) 现有 `list_for_device_schedule` 是单设备,N 设备要 N 次调用,性能差;(2) 现有 `idx_bookings_device_schedule` 列是 `(device_id, scheduled_start_at)`,**无 tenant_id 前缀**,无法复用做 tenant 级时间范围扫描(会落到 `idx_bookings_tenant` 单列 + filesort);(3) 新建复合索引 `(tenant_id, scheduled_start_at)` 是按天网格查询的最优索引 |
| **D5** | 配置权限码 | 复用既有 **`settings:update`** 权限(对齐 `tenant_config`),不新造 `bookings:config` 权限 | 避免权限碎片化;`tenant_config` 的 PUT 端点已用 `settings:update`,本配置同属「门店运营设置」范畴 |
| **D6** | 「已过时间」测试 seam | 组件 prop 注入 `now: Date`,默认 `new Date()`,测试时传固定值 | (1) 项目前端**零 `vi.useFakeTimers`/`setSystemTime` 先例**,引入会偏离范式;(2) prop 注入是纯函数风格,测试确定性强,对齐项目测试惯例;(3) 避免时间敏感测试的不可复现问题 |
| **D7** | 配置 UI 入口 | 网格视图上方「⚙ 设置」按钮 → 弹配置 Dialog(super_admin 看平台默认 + 当前 target 店覆盖两栏;owner/admin 看当前店覆盖一栏) | 用户明确要求「网格内嵌配置 Dialog」;不入 settings 页(避免分散入口) |

### 4.1 影响面清单(文件改动表)

| 层 | 文件 | 改动类型 | 说明 |
|---|---|---|---|
| 后端 model | `app/models/booking_config.py` | **新** | 照抄 `model_pricing.py` 结构 |
| 后端 schema | `app/schemas/booking_config.py` | **新** | Read/Upsert(duration Integer 任意值,window HH:MM 字符串) |
| 后端 repo | `app/repositories/booking_config.py` | **新** | 继承 `BaseRepository`(非 TenantScopedRepository!),手写 tenant 过滤 |
| 后端 service | `app/services/booking_config_service.py` | **新** | `get_effective` 三级 fallback(tenant→platform→硬编码默认 45/08:00/22:00) |
| 后端 api | `app/api/v1/booking_config.py` | **新** | 5 端点:platform GET/PUT + tenant GET/PUT + effective GET |
| 后端 repo | `app/repositories/booking.py` | **改** | +`list_for_tenant_schedule` 方法 |
| 后端 model | `app/models/booking.py` | **改** | +`Index("idx_bookings_tenant_schedule", "tenant_id", "scheduled_start_at")` |
| 后端 service | `app/services/booking_service.py` | **改** | +`get_tenant_schedule(tenant_id, date)` |
| 后端 api | `app/api/v1/bookings.py` | **改** | +`GET /bookings/schedule-grid` 端点 |
| 后端 router 注册 | `app/main.py` | **改** | 注册 booking_config router(对齐 tenant_config 范式,`app.include_router(booking_config.router, prefix=...)`;**不是** `app/api/v1/__init__.py`,那是空文件) |
| 迁移 | `alembic/versions/2026_07_2x_xxxx_booking_config_and_index.py` | **新** | 新表 + seed 平台默认行 + 新复合索引 |
| 前端 types | `frontend/src/api/types.ts` | **改** | +`BookingConfig`/`BookingConfigUpsert` |
| 前端 endpoints | `frontend/src/api/endpoints.ts` | **改** | +6 endpoints |
| 前端 hooks | `frontend/src/hooks/queries.ts` | **改** | +5 hooks,invalidate key 纳入 |
| 前端组件 | `frontend/src/pages/bookings/schedule-grid.tsx` | **新** | 网格组件(~300 行,对齐 demo 形态) |
| 前端组件 | `frontend/src/pages/bookings/config-dialog.tsx` | **新** | 配置 Dialog(~150 行) |
| 前端视图 | `frontend/src/pages/bookings/hq-view.tsx` | **改** | +Tabs + 日期选择 + 配置触发 + 渲染网格 |
| 测试 | `tests/test_booking_config_api.py` | **新** | ~12 用例 |
| 测试 | `tests/test_bookings_api.py` | **改** | +R 章节 ~6 用例(按天查询) |
| 前端测试 | `frontend/src/pages/bookings/__tests__/schedule-grid.test.tsx` | **新** | ~10 用例 |
| 前端测试 | `frontend/src/pages/bookings/__tests__/config-dialog.test.tsx` | **新** | ~5 用例 |
| 前端测试 | `frontend/src/pages/bookings/__tests__/hq-view.test.tsx` | **改** | +Tab 切换 / 网格 smoke |

### 4.2 多租户影响评估

**是否新增租户 scoped 表?** 否 —— `booking_configs` 是**两级配置表**(`tenant_id` 可空),不是纯租户 scoped 业务表。

**隔离方案**:
- **`booking_configs` 查询**:repo 继承 `BaseRepository`(非 `TenantScopedRepository`,因平台默认行 `tenant_id IS NULL` 会被强过滤)。每个查询方法**显式** `where(BookingConfig.tenant_id == tenant_id)`(租户级)或 `where(BookingConfig.tenant_id.is_(None))`(平台级)。参照 `ModelPricingRepository`(`app/repositories/wallet.py:87`)。
- **`list_for_tenant_schedule`**:在 `BookingRepository` 层显式 `where(Booking.tenant_id == tenant_id)`,沿用现有 `list_for_device_schedule` 范式(`app/repositories/booking.py:115`)。
- **平台角色读跨店**:super_admin/hq_staff 查目标店网格,`tenant_id` 来自 query param(目标店),经 `resolve_target_tenant` 或 `is_cross_tenant_viewer` 校验(沿用 platform-cross-tenant-write 既有机制)。门店角色只能查自己店,跨租户 → 403/404。
- **平台默认配置行**:所有租户共享(`tenant_id IS NULL` 的行),租户级覆盖优先(`get_effective` fallback)。

### 4.3 权限影响评估

- **配置写**:复用 `settings:update` 权限(D5)。super_admin 全局 + 本租户 owner/admin 可写;member/customer 只读。
- **配置读**:任何能读该店 bookings 的角色可读 effective 配置(用于网格渲染)。
- **网格数据读**:`bookings:read`(已 seed)。平台写者(super_admin/hq_staff)查跨店,门店角色查本店。
- **零改动**:`DEFAULT_*_PERMS` / `casbin policy` / `require_permission caller` / `Role.data_scope` 全不动。
- **配置生效范围(澄清,P9)**:当前 booking_config 仅对 **HqView 网格** 生效(切片 04b 的 `useBookingConfigEffective` 读取)。门店角色(owner/admin)虽可改本店配置(`settings:update`),但 **StoreView 现有的 `ScheduleGridCard` 不读 booking_config**(本 feature 不动 StoreView),故门店角色改配置后**当前无视觉反馈** —— 配置改动是「为未来 StoreView 网格化预留的能力」。切片 05 dev 手测「配置改 → 网格重渲染」**只能用 super_admin 账号验证**(HqView 路径)。StoreView 网格化是后续独立 feature,不在本 plan 范围。

### 4.4 数据库表设计 checklist(呼应 AGENTS.md 铁律 6)

| # | 原则 | `booking_configs` 是否满足 |
|---|---|---|
| 1 | 能不加就不加 | **已论证**(D2):需「平台默认 + 租户覆盖」两级,`tenant_configs` 纯租户级无法表达,故新建。配置与白标品牌领域解耦 |
| 2 | 必备字段(id/created_at/updated_at) | ✅ `id: String(32) default=_uuid` + `created_at`/`updated_at: DateTime(timezone=True)` |
| 3 | 租户归属 | ⚠️ **特殊**:`tenant_id` 可空(平台默认行),**不继承 `TenantScopedRepository`**,改继承 `BaseRepository` + 手写过滤(照抄 `ModelPricing`) |
| 4 | 软删除看情况 | ✅ **无软删除**(配置是活的,抄 `LlmConfig`/`TenantConfig`/`ModelPricing`);用 `upsert` 而非 delete,无标识符复用诉求 |
| 5 | 命名规范 / FK 显式 ondelete | ✅ 表名 `booking_configs` 复数蛇形;`tenant_id` FK→`tenants.id` `ondelete=CASCADE`;普通索引 `idx_`/唯一约束 `uq_`(本表无 DB 约束) |
| 6 | 历史维度默认不搞 | ✅ 配置无历史诉求,不搞 SCD2 |
| 7 | 审计落库 | ✅ service 层 upsert 调 `logging_service.record`(old_values/new_values) |
| 8 | 双库兼容 | ✅ 全标量列(`Integer`/`String`),**不涉及 JSON**,双库天然兼容 |

### 4.5 其他实施决策

#### D0 视觉形态(demo 验收过,严格对齐)
见 `harness/demo/booking-schedule-grid-demo.html`。关键点:
- 布局 A:设备为列(卡片式表头 `--device-col-w:160px`),时间为行(`--cell-h:40px` + 左侧时间列 `--time-col-w:88px`,08:00-22:00 每 30 分钟一行 = 28 行)
- 左上角斜线分隔(CSS rotate,右上「设备 →」/ 左下「← 时间」)
- 时间列:整点大字(15px 加粗)+ 半点淡色(12px 灰)
- 设备表头:大设备名(15px 加粗)+ 设备 ID(等宽字体)+ 状态圆点(绿=active/橙=maintenance/灰=retired)
- 表格 `width: auto` + `display: inline-table` + 父容器 `text-align: center` → 设备少时居中,设备多时滚动
- 45 分钟高亮:选中 cell + 下一 cell 的 `selected-half`(左侧 75% 蓝色 + 虚线 + 「→ :45」标注);60 分钟 = 2 整 cell
- 已占用:状态色块(pending 黄/confirmed 蓝/in_service 绿/done 灰/cancelled 红)+ 客户名 + hover tooltip,**不可点**(`cursor: not-allowed`)
- 跨行预约:60 分钟 booking-block `span-2`(绝对定位延伸 2 cell),45 分钟 `span-1-5`(延伸 1.5 cell)
- 时间禁用:今天早于 `now` 的 cell 斜纹背景 + 不可点;未来日期全可点
- 点空 cell → 高亮 + 右下角确认面板(设备/日期/时段/时长 + 「填写客户并预约」按钮)

#### 跨店 target tenant 解析
- 网格数据端点 `GET /bookings/schedule-grid?tenant_id=&date=`:平台角色必带 `tenant_id`(目标店),门店角色禁带(防伪造),沿用 `resolve_target_tenant`(`app/services/_tenant_target.py`)
- 配置 effective 端点 `GET /bookings/config/effective?tenant_id=`:同上

---

## 5. Testing Decisions

- **后端测试金字塔**:API 层测试为主(对齐项目范式 —— 无独立 repo 测试文件,`tests/` 全是 `test_*_api.py`/`test_*_service.py`,但 config 表历史只用单 `test_*_api.py`)。`booking_config` 用单 `test_booking_config_api.py`(含权限 + fallback + CRUD);按天查询加进现有 `test_bookings_api.py` R 章节。
- **前端测试**:`vi.mock("@/hooks/queries")` stub 全部 hooks(沿用 `hq-view.test.tsx` 范式)。网格组件纯渲染 + 点击回调测;时间禁用用 prop 注入 `now`(D6),不用 fake timers。
- **回归护栏**:现有 `hq-view.test.tsx` 8 测试 + `store-view.test.tsx` 6 测试零修改(StoreView 不动)。
- **跨租户隔离测试**:按天查询必须覆盖「租户 A 查不到租户 B 的 booking」+ 「平台角色带 target 可查跨店」+ 「门店角色带 tenant_id → 403」。

---

## 6. 切片规划(6 切片,线性依赖无环)

> 对照 platform-cross-tenant-write 5 切片范式。04 拆成 04a/04b(审查建议:网格组件本身重,独立切片)。

### 切片 01 — 后端:booking_configs 表 + 两级配置 API(frontier) ✅

- **What it delivers**:`booking_configs` 表 + 迁移(含 seed 平台默认行)+ repo/schema/service/api 全套。super_admin 设平台默认,owner/admin/super_admin 设租户覆盖,effective 三级 fallback。
- **Blocked by**: 无(frontier,首片可立即开工)
- **状态**:**已完成**(2026-07-26)。证据:ruff clean + 全量 pytest 769 passed(含 19 新用例)+ `alembic upgrade head && alembic check` 无 drift(Postgres)+ seed 平台行已验证(tenant_id=NULL/duration=45/window 08:00-22:00)。/code-review 双轴:Standards 0 硬违规、Spec 12/12 AC 全过。
- **文件清单**:
  - `app/models/booking_config.py`(新)
  - `app/schemas/booking_config.py`(新)
  - `app/repositories/booking_config.py`(新,继承 `BaseRepository`)
  - `app/services/booking_config_service.py`(新,三级 fallback)
  - `app/api/v1/booking_config.py`(新,5 端点)
  - `app/main.py`(改,注册 booking_config router —— 对齐 tenant_config 范式 `app.include_router(...)`,**不是** `app/api/v1/__init__.py`,那是空文件)
  - `alembic/versions/2026_07_2x_xxxx_booking_config.py`(新迁移,含 seed 平台默认行:duration=45/window 08:00-22:00)
  - `tests/test_booking_config_api.py`(新,~12 用例)
- **Acceptance criteria**:
  - [x] `booking_configs` 表字段:id/tenant_id(可空 FK CASCADE)/default_duration_minutes(Integer default=45,server_default text("45"))/window_start(String "08:00")/window_end(String "22:00")/created_at/updated_at
  - [x] repo 继承 `BaseRepository`(非 `TenantScopedRepository`),手写 `where(tenant_id == X)` / `where(tenant_id.is_(None))`
  - [x] **无 DB 唯一约束(P2)**:`booking_configs` 表无 `UNIQUE` / 无 `uq_` / 迁移无 `create_unique_constraint` / 无 `NULLS NOT DISTINCT`(对齐 D2 + model_pricing/llm_config 注释,唯一性由 service 层 upsert 保证)。AC 验证:`grep -i "unique\|uq_" app/models/booking_config.py` 零命中 + 迁移文件无唯一约束调用
  - [x] 迁移双库兼容(PG + SQLite),`alembic check` 无 drift
  - [x] seed 平台默认行(tenant_id=NULL, duration=45, window 08:00-22:00)
  - [x] `GET /bookings/config/effective?tenant_id=` 三级 fallback,三种 DB 状态各测一次(P3):① 有租户覆盖行 → 用之;② 无租户行有平台默认行 → 用平台;③ 两者皆无 → 硬编码默认(45/08:00/22:00)
  - [x] super_admin GET/PUT `/bookings/config/platform` 200;其他角色 → 403
  - [x] owner/admin GET/PUT `/bookings/config/tenant/{id}` 200(本租户);跨租户 → 403;super_admin → 200;member/customer → 403(无 settings:update)
  - [x] duration 校验:Integer 任意值,前端合理范围(15-240),后端只校验类型(>0)
  - [x] service upsert 调 `logging_service.record` 审计;测法(P2):`patch.object(LoggingService, "record", autospec=True)` 拦截,断言被调用 + `module="booking_config"` + `old_values`/`new_values` 非空(项目无 pytest-mock 依赖,用 unittest.mock 替代 mocker.spy)
  - [x] `./init.sh` 全绿(ruff + pytest 含 test_booking_config_api.py)
  - [x] `alembic upgrade head && alembic check` 无 drift
- **验证命令**:`./init.sh && alembic upgrade head && alembic check`

### 切片 02 — 后端:按天查询端点 + 复合索引 ✅ PR #131

- **What it delivers**:`GET /bookings/schedule-grid?tenant_id=&date=` 返回该店当天全设备 `BookingHqRead[]`;新建 `(tenant_id, scheduled_start_at)` 复合索引。
- **Blocked by**: 切片 01(共用 booking 基础设施,虽然逻辑可并行但 EP3 串行实施)
- **状态**:**已完成**(2026-07-26)。证据:`./init.sh` 全绿 ruff + pytest 777 passed(含 R 章节 8 新用例)+ `alembic upgrade head && alembic check` 无 drift(Postgres)+ 新索引 `idx_bookings_tenant_schedule` 已落地。/code-review 双轴:Standards 0 硬违规(3 个 judgement call 均为本地一致性/避免越界,不改)、Spec 8/8 AC 全过(tz 语义对齐 sibling devices schedule 范式、helper 用 read 路径 `is_cross_tenant_viewer` 语义更准)。
- **文件清单**:
  - `app/models/booking.py`(+`Index("idx_bookings_tenant_schedule", "tenant_id", "scheduled_start_at")`)
  - `app/repositories/booking.py`(+`list_for_tenant_schedule` 含 `selectinload`)
  - `app/services/booking_service.py`(+`get_tenant_schedule`,门店角色带 tenant_id → 403 防伪造,平台角色缺 tenant_id → 400)
  - `app/api/v1/bookings.py`(+`GET /bookings/schedule-grid` 端点,路由序在 `/{booking_id}` 前)
  - `alembic/versions/2026_07_26_1100_5565cf1e81bd_add_bookings_tenant_schedule_index.py`(新迁移,加索引)
  - `tests/test_bookings_api.py`(+R 章节 8 用例:R-1~R-8)
- **Acceptance criteria**:
  - [x] `list_for_tenant_schedule(tenant_id, range_start, range_end)` 显式 `where(Booking.tenant_id == tenant_id)`,半开区间 `[range_start, range_end)` 在 `scheduled_start_at` 上
  - [x] 新复合索引 `idx_bookings_tenant_schedule (tenant_id, scheduled_start_at)` 落地,`alembic check` 无 drift
  - [x] `GET /bookings/schedule-grid?tenant_id=&date=YYYY-MM-DD` 返回当天 [00:00, 次日 00:00) 的 `BookingHqRead[]`
  - [x] 平台写者带 target tenant_id 可查任何店;门店角色查自己(禁带 tenant_id,带则 403 防伪造);跨租户门店角色 → 403/404(R-5 覆盖 403;404 分支结构上不可达 —— store role 的 target 永远是自己,forge 在 403 拦截,无独立 404 路径)
  - [x] date 参数 YYYY-MM-DD 校验,非法 → 422(R-6,native `date` Query 类型 FastAPI 自动 422)
  - [x] 跨租户隔离:租户 A 查不到租户 B 的 booking(R-1/R-4 覆盖 —— 平台角色查 target 店只见 target 店 booking,store role 不见他店)
  - [x] 空店空列表返回 `[]`(R-7)
  - [x] `./init.sh` 全绿

### 切片 03 — 前端:API 层 + 配置 Dialog + 设置入口 ✅ PR #130

- **What it delivers**:前端能读写两级配置;网格上方的「⚙ 设置」Dialog 可用。
- **Blocked by**: 切片 01(配置 API 契约)
- **文件清单**:
  - `frontend/src/api/types.ts`(+`BookingConfig`/`BookingConfigUpsert`;实施时 +`BookingConfigEffective` —— 后端 effective 路由返回带 `source` 的不同形状,合理超出)
  - `frontend/src/api/endpoints.ts`(+5 endpoints;文件清单原写"+6"是笔误 —— AC#2 列 5 个 hook,后端恰好 5 路由,已对齐)
  - `frontend/src/hooks/queries.ts`(+5 hooks + 新增 `BOOKING_CONFIG_WRITE_KEYS` invalidate 集合 + `qk.bookingConfig` query key;**不**塞进 `BOOKING_WRITE_KEYS` —— P4:配置改完应失效 config 查询缓存,不是 booking 写缓存,命名上避免误导。命名对齐 `BOOKING_WRITE_KEYS` 用 `BOOKING_CONFIG_WRITE_KEYS` 而非 `BOOKING_CONFIG_KEYS`,标明它是写失效集)
  - `frontend/src/pages/bookings/config-dialog.tsx`(新,~280 行)
  - `frontend/src/pages/bookings/__tests__/config-dialog.test.tsx`(新,5 用例)
- **Acceptance criteria**:
  - [x] `BookingConfig` 类型含 id/tenant_id/default_duration_minutes/window_start/window_end
  - [x] 5 hooks:`useBookingConfigEffective(tenantId)` / `usePlatformBookingConfig()` / `useUpdatePlatformBookingConfig()` / `useTenantBookingConfig(tenantId)` / `useUpdateTenantBookingConfig(tenantId)`
  - [x] 配置 Dialog:super_admin 看两栏(平台默认 + 当前 target 店覆盖);owner/admin 看一栏(当前店覆盖)
  - [x] duration UI:常用预设按钮(45/60/90)+ 自定义数字输入(D3)
  - [x] window UI:两个 `<input type="time">`
  - [x] 提交调对应 hook,成功后 `invalidateQueries({ queryKey: qk.bookingConfig })` + toast
    - **注**:`invalidateQueries` 已在两个 update hook 内经 `useApiMutation(..., BOOKING_CONFIG_WRITE_KEYS)` 满足;**toast 延后到切片 04b** —— Dialog 按本项目 shared-dialog.tsx 既有约定设计为纯展示体(onSubmit 回调由父控制 mutation+toast),本切片文件清单不含 view 编辑,toast wiring 归属 04b 接入 StoreView/HqView 时(与其他所有 Dialog 一致)
  - [x] vitest ~5 用例:渲染 / super_admin 两栏 / owner 一栏 / duration 切换 / 提交调 mock
  - [x] `cd frontend && npm test && npm run build` 全绿 + oxlint 0
    - 证据:npm test 33/33(含新加 5)、npm run build 成功、oxlint 0 warning 0 error

### 切片 04a — 前端:ScheduleGrid 网格组件(核心) ✅

- **What it delivers**:网格组件本身(~300 行),对齐 demo D0 形态。纯展示 + 点击回调,不含数据获取(由父组件传 props)。
- **Blocked by**: 切片 03(需要 `BookingConfig` TS 类型契约 + `BOOKING_CONFIG_WRITE_KEYS`;04a 的 `Props.config: BookingConfig` 依赖切片 03 的 types.ts 改动)。**修正(M2)**:v1 写"Blocked by 无"与"EP3 排在 03 后"自相矛盾,根因是 04a 实际需要 03 的类型契约,故改为显式依赖 03。
- **文件清单**:
  - `frontend/src/pages/bookings/schedule-grid.tsx`(新,~300 行)
  - `frontend/src/pages/bookings/__tests__/schedule-grid.test.tsx`(新,~10 用例)
- **Acceptance criteria**:
  - [x] Props:`devices: DeviceHqRead[]` / `bookings: BookingHqRead[]` / `config: BookingConfig` / `selectedDate: Date` / `now: Date`(D6,默认 `new Date()`)/ `onSlotClick(device, startISO, endISO)`
    - **注**:`config` 用 `Pick<BookingConfig, "default_duration_minutes"|"window_start"|"window_end">` 结构子类型,使切片 04b 的 `useBookingConfigEffective`(`BookingConfigEffective` 形状)可直接透传无需 adapter;plan 字面 `BookingConfig` 的意图(网格只需 duration + window 三字段)由此满足,且对 04b 友好(code-review Spec 轴确认 faithful)。
  - [x] 布局 A:设备为列(卡片式表头 160px),时间为行(40px,28 行按 config window)
  - [x] 左上角斜线分隔(右上「设备 →」/ 左下「← 时间」)
  - [x] 时间列整点大字 + 半点淡色
  - [x] 设备表头:大设备名 + ID(等宽)+ 状态圆点(active 绿/maintenance 橙/retired 灰)
    - **注**:大设备名用 `model_name ?? serial_number`(贴近 demo 的「理疗床 1」语义;DeviceHqRead 无独立 name 字段,model_name 是最接近的人类可读名),小字 ID 用 `serial_number`(等宽,对应 demo 的 DEV-001 式标识符)。
  - [x] 表格 `width: auto` + `display: inline-table` + 父容器居中(D0)
  - [x] 已占用 cell:状态色块(pending 黄/confirmed 蓝/in_service 绿/done 灰/cancelled 红)+ 客户名 + hover tooltip,**不可点**
  - [x] 跨行预约:60 分钟 span-2 / 45 分钟 span-1-5(绝对定位延伸)
  - [x] 空 cell 可点击;今天早于 now 的 cell 斜纹禁用(`isSelectedToday && cellStart < now`)
  - [x] 点击空 cell:高亮(duration=45 → selected-full + selected-half;duration=60 → 2× selected-full)+ 调 `onSlotClick`
    - **泛化**:高亮规则按 duration 分钟数通用化(D3 任意分钟数),不限于 45/60;`selectionClass` 按 `duration - offset*30` 余量判定 full/half。
  - [x] 无设备时空态「该门店暂无可用设备」
  - [x] **沿用 demo 的 CSS class 名作测试 selector(P5)**:`selected-full` / `selected-half` / `span-2` / `span-1-5` / `disabled` / `booking-block.st-pending|st-confirmed|st-inservice|st-done|st-cancel` —— vitest 用 `container.querySelector('.selected-half')` 等断言 class 存在,实施时 class 名与 demo 一致不重命名
  - [x] vitest ~10 用例:空网格渲染 / 占用 cell / 跨行 span / 已过时间禁用(用 `now` prop)/ 点击回调(含「点击已占用 cell 不触发 onSlotClick」)/ 45分钟半行高亮 / 60分钟整行 / 无设备空态 / 父传新 `config` prop → 网格 rerender 行数变化(纯组件 props 驱动,不测 react-query cache)/ hover tooltip
    - **实际 11 用例**(AC 列 10 项 + 额外「未来日期全可点」1 项,覆盖 AC line 255 的「未来日期」语义)。
  - [x] **hover tooltip 测法(P6)**:断言 `data-tooltip` attribute 存在且内容正确(如 `张三 · 全身理疗 | 09:00-10:00 | 状态:已完成`),**不测 `:hover` 伪类触发**(jsdom 不支持 CSS 伪类)
  - [x] `cd frontend && npm test && npm run build` 全绿 + oxlint 0
    - **证据**:vitest 44/44(含本切片 11)、tsc 0 error、oxlint 0/0(94 文件)、npm run build 成功(chunk size warning 是既有基线)。

### 切片 04b — 前端:HqView Tabs + 网格集成 ✅

- **What it delivers**:HqView 加 Tabs(列表/网格),网格视图集成日期选择 + 配置 Dialog + ScheduleGrid + 点击弹 BookingCreateDialog。
- **Blocked by**: 切片 02(按天查询)+ 03(配置 Dialog)+ 04a(网格组件)
- **状态**:**已完成**(2026-07-26)。证据:`cd frontend && npm test` 48/48 全绿(基线 44 + 新增 4:Tab 默认列表 / 网格渲染 smoke / 设置弹 Dialog / P7 预填 spy-on-children)+ `npm run build` 成功 + oxlint 0/0(88 文件全量)+ tsc 0 error。/code-review 双轴:Standards 0 硬违规(2 判断项已修:① `DEFAULT_BOOKING_CONFIG` export 化消除 Shotgun Surgery ② `createDialogCalls` 在 afterEach 重置防未来测试继承);Spec 核心 AC 全满足(2 处 doc/spec 漂移见下方留痕,非代码缺陷)。
- **文件清单**:
  - `frontend/src/pages/bookings/hq-view.tsx`(改,+Tabs + 日期选择 + 配置触发 + 渲染网格)
  - `frontend/src/pages/bookings/__tests__/hq-view.test.tsx`(改,+Tab 切换 / 网格 smoke / 设置弹 Dialog / P7 预填)
  - `frontend/src/pages/bookings/shared-dialog.tsx`(改,BookingCreateDialog +`defaultDeviceId`/`defaultStart`/`defaultEnd` 可选预填 props —— 复用而非新建,P7 测法要求)
  - `frontend/src/pages/bookings/config-dialog.tsx`(改,`DEFAULT_BOOKING_CONFIG` const→export,hq-view 复用消除重复 —— /code-review 修)
  - `frontend/src/hooks/queries.ts`(改,+`useTenantBookingsByDate` hook + `qk.tenantSchedule` 工厂项 + `BOOKING_WRITE_KEYS` 加 `["schedule-grid"]` 失效项)
  - `frontend/src/api/endpoints.ts`(改,+`fetchTenantBookingsByDate` 调切片 02 端点)
- **Acceptance criteria**:
  - [x] HqView 选 target 后出现 Tabs(列表/网格),默认列表
  - [x] Tabs 手搓 Button 行(沿用 `FilterChips` 范式,不引 shadcn Tabs)
  - [x] 网格 Tab:日期选择(`<input type="date">` min=今天,默认今天)+ 「⚙ 设置」按钮 + `<ScheduleGrid>`
  - [x] 网格数据:`useTenantBookingsByDate(targetTenantId, selectedDate)`(切片 02 端点)
  - [x] 网格配置:`useBookingConfigEffective(targetTenantId)`(切片 01 端点)
  - [x] 点击空 cell → 复用 `BookingCreateDialog` 预填 device + start/end(= cellStart + duration),提交走现有 `useCreateBooking`;**预填值测法(P7)**:`vi.mock("./shared-dialog", ...)` 捕获 `BookingCreateDialog` 的 props,断言 `defaultDevice === clickedDevice.id` 且 `defaultStart === cellStart ISO`(spy-on-children 范式)
    - **命名留痕**:实施用 `defaultDeviceId`(值是 device id,比 `defaultDevice` 更清晰)/ `defaultStart` / `defaultEnd` 三 props,与 plan 写的 `defaultDevice` / `defaultStart` 语义等价但 prop 名更精确。P7 测法断言 `lastCall.defaultDeviceId === "d-1"` + start/end 本地小时数(slot 2 = 09:00,duration 45min → end 09:45)。
  - [x] 「⚙ 设置」按钮 → 弹切片 03 的 `ConfigDialog`
  - [x] 现有 `hq-view.test.tsx` 8 测试零回归 + 新增 ~3 测试(Tab 切换 / 网格渲染 smoke / 设置按钮弹 Dialog)
    - **基线留痕**:plan 写「8 测试」是记忆偏差,实际基线是 **9 测试**(bookings-page-split 拆分时补了 HqView smoke)。实施 9 既有零回归 + **新增 4 测试**(Tab 默认列表 / 网格渲染 smoke / 设置弹 Dialog / P7 预填)= 13/13 全绿。
  - [x] `cd frontend && npm test && npm run build` 全绿 + oxlint 0
- **实施期决策与留痕**:
  - **`useTenantBookingsByDate` 在本切片新建**(非切片 02):plan §6 切片 02 文件清单是 backend-only(端点 + 索引),但切片 04b AC line 279 直接引用 `useTenantBookingsByDate` 作为网格数据源 —— 这 hook 属 04b 范围(调用切片 02 已落地的端点)。endpoint `fetchTenantBookingsByDate` 同理。AC 合规。
  - **StoreView ConfigDialog 未接**(已知 gap,推切片 05):plan line 234(切片 03 toast 留痕)写「toast wiring 归属 04b 接入 StoreView/HqView」,但 §8 line 331 写「不动 StoreView」—— 两处冲突。本切片按 §8「不动 StoreView」执行(只接 HqView),因 StoreView 的 `ScheduleGridCard` 不读 booking_config,toast 接入目前是装饰性。**推切片 05 联调时决定**:若 StoreView 也要暴露配置入口,在切片 05 补(届时 §8 需修订)。
  - **`onTargetChange` 清 `createPrefill`**:切 target 时旧 prefill 的 deviceId 属旧店,清空防下次 create Dialog 残留跨店 device id。切片 04 既有 `qc.invalidateQueries({queryKey: qk.bookings})` 旁新增一行 `setCreatePrefill(null)`。
  - **PageHeader「创建预约」按钮也清 prefill**:列表 Tab 路径不应预填(预填是网格 cell 点击专属),按钮 onClick 加 `setCreatePrefill(null)` 防上次网格点击残留。
  - **`vi.mock("../shared-dialog", importOriginal)` spy 边界**:只替换 `BookingCreateDialog`(返回 null + push props 到 `createDialogCalls`),其他 Dialog + RowMenu 透传真实实现。既有 9 测试从不打开 create Dialog,spy 占位零影响(13/13 验证)。

### 切片 05 — 端到端联调 + feature 收尾(末切片)

- **What it delivers**:端到端验证 + feature 收尾仪式。
- **Blocked by**: 01+02+03+04a+04b
- **文件清单**:无新源码(纯联调 + 文档)
- **Acceptance criteria**:
  - [ ] `./init.sh` 全绿(ruff + pytest 全量)
  - [ ] `cd frontend && npm test && npm run build` 全绿
  - [ ] dev seed 手测:super_admin 选门店 → 网格渲染 → 点空格创建 → 重叠拒 400 → 改时间成功 → 切列表视图看到新预约
  - [ ] 配置改 duration=60 + window 09:00-21:00 → 网格重渲染(行数变 + 高亮跨度变)
  - [ ] 文档影响评估:① feature_list.json status→passing + evidence;② progress.md 顶部更新;③ `项目指南/02-后端架构/03-数据库与ORM.md` 是否需补 `booking_configs` 表(预期需要,新增两级配置范式);④ plan 文档 draft v1 → passing;不动 README
  - [ ] `./scripts/sync-active-features.sh` 刷新
  - [ ] demo 文件 `harness/demo/booking-schedule-grid-demo.html` 归档(移到 `harness/docs/archive/` 或保留作设计参考)

---

## 7. 切片依赖图(无环验证)

```
切片 01 (booking_configs 表+API)  ← 唯一 frontier
   │
   ├──────────────→ 切片 02 (按天端点+索引) ─────────────────────┐
   │                                                            │
   └──────────────→ 切片 03 (前端配置 API+Dialog)               │
                        │                                       │
                        ↓                                       │
                  切片 04a (ScheduleGrid 组件,需 03 的类型契约)  │
                        │                                       │
                        ↓                                       ↓
                  切片 04b (HqView Tabs 集成,需 02+03+04a) ←───┘
                        │
                        ↓
                  切片 05 (联调收尾,需 01+02+03+04a+04b)
```

- **拓扑排序合法**:01 → {02, 03} → 04a → 04b → 05(或其他合法序)
- **无环**:每条边都从前指向后
- **首片 frontier**:切片 01 `Blocked by: 无`,**唯一** frontier(v2 修正:04a 改为 `Blocked by: 03`,不再是无依赖,消除 v1 的双 frontier 歧义)
- **末片**:切片 05(Blocked by 全部前序)
- **关键路径**:01 → 03 → 04a → 04b → 05(5 步;02 可与 03 并行逻辑上,但 EP3 WIP=1 串行实施)

---

## 8. Out of Scope(不做,避免越界)

- **不动 StoreView / MyBookingsView**:网格只在 HqView;StoreView 现有 `ScheduleGridCard`(单设备 7 天视图)保留
- **不动 booking 状态机 / 重叠校验**:后端 `_assert_no_overlap` 已就位
- **不动权限基础设施**:`is_platform_writer` 已就位,`settings:update` 复用
- **不引 shadcn Tabs/calendar/popover/scroll-area 原语**:Tabs 手搓(沿用 FilterChips 范式);日期用原生 `<input type="date">`
- **不做客户跨店选择器**:HQ 客户字段保持自由文本(沿用 platform-cross-tenant-write D2-ii)
- **不做拖拽改约**:只做点击创建;改约走列表行内菜单
- **不做周/月视图**:只做单日网格
- **不引入日期库**:沿用原生 Date + `shared.tsx` 助手
- **不做每设备独立时长配置**:配置在门店级(duration 统一)
- **不做历史排期回看**:只看今天及以后

---

## 9. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 45 分钟半行高亮 CSS 复杂(已 demo 验收) | 🟢 低 | demo 已实现并验收,D0 锁定形态;组件移植时对齐 demo CSS |
| 设备很多时横向滚动 + sticky 列性能 | 🟢 低 | demo 已验证 sticky 表头/时间列在滚动时正常;`<table>` + overflow-x-auto |
| HQ 客户字段自由文本易输错 customer_id | 🟡 中 | 占位提示「留空=散客 walk-in」;后端 `_assert_customer_in_tenant` 兜底(非 None 时校验存在) |
| 两级配置 fallback 链测试覆盖 | 🟢 低 | service 层三级边界测试(切片 01 AC) |
| 时间区 naive vs aware | 🟢 低 | 沿用现有范式(naive ISO),网格日期运算全 wall-clock |
| 配置权限误用(门店角色改其他店配置) | 🟡 中 | repo 层显式 `where(tenant_id == X)` + 跨租户 PUT → 403(切片 01 AC) |
| 复合索引 `(tenant_id, scheduled_start_at)` 对老数据无影响 | 🟢 低 | 纯新增索引,不改动现有查询;alembic check 验证 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. 网格形态严格对齐 demo(`harness/demo/booking-schedule-grid-demo.html`),用户视觉验收过
2. HqView 选 target 后可切「列表/网格」Tab,网格渲染设备×时间
3. 点空 cell 弹 Dialog 预填设备+时段,提交成功创建预约;重叠 → 400 + Dialog 保持打开供重试
4. 已占用 cell + 今天已过 cell 不可点(视觉标记明显)
5. 配置:平台默认 + 租户覆盖两级;super_admin/owner/admin 可改;effective 三级 fallback
6. 日期可选今天及往后,不能选过去
7. 跨租户隔离:门店角色只能查/改自己店;平台角色带 target 可跨店
8. `./init.sh` 全绿 + `cd frontend && npm test && npm run build` 全绿 + `alembic check` 无 drift
9. 现有 `hq-view.test.tsx` 8 测试 + `store-view.test.tsx` 6 测试零回归
10. 文档影响评估完成(详见切片 05 AC)

---

## 11. 不越界声明

- **不动**:StoreView / MyBookingsView / booking 状态机 / `_assert_no_overlap` / 权限基础设施(DEFAULT_*_PERMS / casbin / require_permission caller)/ `ScheduleGridCard`(StoreView 用)/ router URL 前缀 / README
- **不引**:shadcn Tabs / calendar / popover / scroll-area / 日期库(dayjs/date-fns)/ 临时 owner 概念
- **不做**:拖拽改约 / 周/月视图 / 客户跨店选择器 / 每设备独立时长 / 历史排期回看 / 真实提交表单(demo 范围)

---

## plan 自检 4 项(three-tier-workflow §3 EP2 gate)

- [x] **切片依赖图无环**(§7 已验,拓扑合法解存在)
- [x] **每片有 acceptance criteria**(§6 每片 AC 清单,共 ~50 条可执行 AC)
- [x] **首片可立即开工**(切片 01 Blocked by 无,唯一 frontier)
- [x] **plan 主体决策无 TODO/待定悬空**(D0-D7 全部锁定,无悬空决策)

---

## 后续修补(2026-07-27):切片 05 后真实环境手测反馈

feature 已 passing(PR #134 合并)后,super_admin 在 `http://localhost:3000/bookings` 网格视图真实手测反馈「预约创建后网格不显示 / 时段冲突误报」。**不属于原 plan AC 范围**(原 AC 已全勾,这是 dev 环境手测发现的真问题),记录于此不丢排查成果。

### 诊断过程(Playwright 真实复现)

用 Playwright 起浏览器,真实复现 super_admin 登录 → 选 Dev HQ → 切网格 → 点空 cell → 创建预约的全链路,**捕获所有 API 请求 + 错误响应**。结论:

| 链路 | 实际发生 |
|---|---|
| POST /bookings/ | ⚠️ **400 设备时段冲突**(冲突窗口 14:30-15:15 UTC) |
| 后端冲突检查 | ✅ 正确报告冲突(已有 15:00-15:45 UTC 预约重叠 15 分钟) |
| **冲突窗口 vs 用户视角** | ❌ **时间偏移 8 小时** —— 用户点的 14:30 北京 = 应是 06:30 UTC,但前端提交的是 14:30(被当 UTC) |

### 真根因:`fromDatetimeLocalValue` 返回 naive datetime(无时区)

`frontend/src/lib/format.ts:110-114` 的旧实现:

```ts
return v.length >= 16 ? `${v}:00` : v;
// "2026-07-27T14:30" → "2026-07-27T14:30:00"(无时区后缀)
```

完整时区错乱链:

1. 用户在网格点 14:30 北京时间 → `slotHourToISO(selectedDate, 14.5)` → `new Date(本地).setHours(14, 30) → toISOString()` → `"2026-07-27T06:30:00.000Z"`(正确 UTC)
2. Dialog `defaultStart="...06:30:00.000Z"` → `toDatetimeLocalValue` 用 `getHours()`(本地)→ `"2026-07-27T14:30"`(datetime-local 格式,UI 显示 14:30 对用户正确)
3. 用户点创建 → `fromDatetimeLocalValue("2026-07-27T14:30")` → ❌ **`"2026-07-27T14:30:00"`**(丢掉了 UTC 信息)
4. 后端 Pydantic `datetime` 解析无后缀字符串 → **naive datetime**(`tzinfo=None`)
5. SQLAlchemy 写入 `DateTime(timezone=True)` 列 → 当 UTC 解释 → 14:30 UTC
6. 冲突检查 `[14:30 UTC, 15:15 UTC)` 跟已有 15:00 UTC 重叠 15 分钟 → **400 冲突**
7. 用户视角:点的 14:30 北京 ≠ 网格显示的 23:00 北京(15:00 UTC),**完全看不到冲突预约**,误以为误报

**为何之前没暴露**:`/diagnosing-bugs` 流程下,booking 测试都用 `2026-07-27T10:00:00Z` 这种**带 Z 的 ISO** 直接构造请求,绕过了 `fromDatetimeLocalValue`。前端 vitest 测试 mock 了 hooks,也没真跑 datetime 转换。bug 只在「用户从 datetime-local input 创建预约」时触发。

### 修补

#### 1. 真根因:`frontend/src/lib/format.ts:fromDatetimeLocalValue` 改返回 UTC ISO

```ts
// 旧:return v.length >= 16 ? `${v}:00` : v;  // naive
// 新:
const d = new Date(v);
return Number.isNaN(d.getTime()) ? v : d.toISOString();  // UTC + Z
```

`new Date("YYYY-MM-DDTHH:mm")` 解析 naive 值为**本地时间**,`toISOString()` 正确转 UTC。修复后:用户点北京 14:30 → 提交 `2026-07-27T06:30:00Z` → 后端正确存 06:30 UTC → 网格渲染时 `getHours()` 又转回 14:30 北京给用户看。

#### 2. 加回归测试 `frontend/src/lib/__tests__/format.test.ts`(15 用例)

新文件,覆盖 `lib/format.ts` 所有 6 个 export。重点锁定 `fromDatetimeLocalValue`:
- 必须返回带 `Z` 的 UTC ISO(`/Z$/` regex)
- round-trip:本地 wall-clock pick → API ISO → 解析回 Date,**instant 必须等于原时刻**(±60s,因 datetime-local 无秒)

#### 3. UI 布局修补(辅助):`schedule-grid.css` 网格撑满

副产物(同时修):用户原本反馈「网格两边空白过多」让预约块视觉上扫不到。`schedule-grid.css` 改 2 处:
- `.grid-scroll`: `text-align: center` → `left`(表格从左边缘铺开)
- `table.grid`: `width: auto / display: inline-table / margin: 0 auto` → `width: 100% / display: table / margin: 0`

Playwright 实测 table 从 408px → 1044px 撑满容器,预约块占满列宽立即可见。**CSS class 名不变**(P5 测试 selector 契约保留)。

### 文件改动清单

- `frontend/src/lib/format.ts`:`fromDatetimeLocalValue` 改返回 UTC ISO(核心 bug fix)
- `frontend/src/lib/__tests__/format.test.ts`:新建,15 用例(回归守护)
- `frontend/src/pages/bookings/schedule-grid.css`:`.grid-scroll` text-align + `table.grid` width/display/margin(辅助 UI 修补)
- `harness/docs/plan-booking-schedule-grid.md`:本段(后续修补记录)
- 不改:`schedule-grid.tsx` / `hq-view.tsx` / `shared-dialog.tsx` / `queries.ts` / 任何后端代码

### 验证

- `cd frontend && npm test`:**65/65 passed**(原 50 + 新加 15 个 format 测试,零回归)
- `cd frontend && npm run build`:成功
- `cd frontend && npx oxlint .`:0 warnings / 0 errors
- **Playwright 端到端复测**(设置 `timezoneId: 'Asia/Shanghai'`):
  - 点北京 13:30 → POST 201 ✓ → 返回 `scheduled_start_at: "2026-07-27T05:30:00Z"` ✓(北京 13:30 = UTC 05:30)
  - 点北京 18:00 → POST 201 ✓ → 返回 `scheduled_start_at: "2026-07-27T10:00:00Z"` ✓(北京 18:00 = UTC 10:00)
  - 网格 tooltip 显示新预约在用户点击的时段(13:30 / 18:00)✓

### 历史诊断错误(留痕反思)

第一次修补(已回滚)尝试 `hq-view.tsx` 加 `max-w-3xl mx-auto` 限宽居中,凭直觉以为「缩窄容器减少空白」。**错的方向** —— 限宽后表格更小更难看到预约块。已回滚。

第二次诊断(已修正)说「代码链路从未坏过,根因是 UI 布局」。**部分错误** —— Playwright 复现确实看到 POST 201 成功案例(因为避开了所有冲突时段,bug 不暴露),但**没在真冲突场景下测试**,漏了 `fromDatetimeLocalValue` 的 datetime bug。第三次诊断才用真冲突场景发现时间偏移 8 小时。

**教训**:① 布局调整必须用 Playwright 实测数据,不能凭直觉;② bug 复现必须覆盖**失败路径**(400/500),不能只测成功路径(201);③ datetime 涉及时区转换,测试必须在目标时区(`timezoneId: 'Asia/Shanghai'`)下跑,不能在 UTC 默认环境跑。
