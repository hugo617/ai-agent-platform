# 计划:设备开机/结束/爽约状态机动作(不含硬件下发)

> **id**: `device-poweron`
> **状态**: draft v2(经子智能体三方审查,修 5 阻断项 + 8 建议项;EP2 回环产出,需求已烤清 → to-spec → to-tickets → 三方审查修订)
> **优先级**: 64(设备功能系列 4/4 收官)
> **创建日期**: 2026-07-24
> **最后修订**: 2026-07-24(v2:三方审查修订)
> **依赖**: `device-booking`(priority 63,已 passing ✅)
> **范围**: 预约订单的状态机动作层 —— `start` / `end` / `no-show` 三个动作端点 + 6 态纯函数状态机 + customer 端「确认开机」真调 + 门店端「结束/爽约」操作按钮。**不含** 硬件下发链路(MQTT/WS/寻址)—— 归未来 priority 65+ 的 IoT feature。

---

## 0a. v1 → v2 变更摘要(子智能体三方审查:后端 / 前端 / 切片工程)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| **B1** customer `start` 端点 router-level guard 矛盾:AC 写 `require_permission("bookings","update")`,但 FastAPI 进入函数体前先跑 guard,customer(member 角色)必被 403,到不了函数体内的 `customer_id` 分叉 | 🔴 阻断 | D7/D8/§4.3/§4.5/切片01 AC 改为:**端点不挂 router-level `require_permission`**,全部授权在函数体内手工分叉(customer 走 `customer_id` 双校验;store 走 `permission_service.require(...,"bookings","update")`)。对齐 `me.py` + `BookingService.list/get` 既有范式 |
| **B2** admin 权限矩阵错:`DEFAULT_ADMIN_PERMS` **不含** `bookings:delete`(对齐 customer/device admin 不可删业务记录约定),但 D6/§0/P-4 把 admin 当 end/no-show 可操作方 | 🔴 阻断 | D6/§3 用户故事#2/#3/切片01 P-4 改为:**end/no-show 仅 owner**(admin/member/customer/hq_staff 全 403)。owner 是唯一持 `bookings:delete` 的租户角色 |
| **B3** 「结束」按钮 permission code 自相矛盾:D8 说 end→`:delete`,切片03 AC 写「`canUpdate` 守结束」 | 🔴 阻断 | 切片03 AC 改为:**「结束」「爽约」都用 `canDelete`**(`hasPermission(me,"bookings","delete")`,沿用现有 `canCancel` 变量);member 无此码 → 两按钮隐藏 |
| **B4** 用户故事#4 store 端 walk-in「确认开机」前端按钮三切片全缺 | 🔴 阻断 | 切片03 加:store `StoreView` 的 `pending`/`confirmed` 行 DropdownMenu 加「确认开机」项(走 `useStartBooking`,守 `canUpdate`=`:update`)。同时把 `endBooking/noShowBooking/useEndBooking/useNoShowBooking` 从切片02(预建空架子,违反铁律6)移到切片03 |
| **B5** EP2 收尾 feature_list.json 回填动作缺失(plan 自检声明可进 EP3 但未执行) | 🔴 阻断 | plan 自检段加第 5 项:回填 `plan` 字段 + status `not_started→in_progress`(依赖 device-booking 已 passing,当前 frontier) |
| 切片02 预建 03 才用的 `endBooking/noShowBooking` hooks(违反铁律6) | 🟡 | 见 B4 处理:hooks 随 store 按钮一起落在切片03 |
| 切片02 缺 `tsconfig.app.json` 改 types(`tsc -b` 会红闸) | 🟡 | 切片02 影响面 + AC 加:`tsconfig.app.json` 的 `types` 加 `vitest/globals` + `@testing-library/jest-dom` |
| 切片02 setup.ts「最小 jest-dom+cleanup」不够:组件测需 `QueryClientProvider` + `ToastProvider` + mock hooks | 🟡 | 切片02 AC 加:`src/test/test-utils.tsx` 导出 `renderWithProviders(ui)` + 组件测用 `vi.mock("@/hooks/queries")` stub |
| mutation 失效键表述错:`qk.deviceSchedule` 是函数非扁平 key | 🟡 | §4.1 + 切片02/03 AC 改为:沿用 `BOOKING_WRITE_KEYS` 数组(`[qk.bookings, ["device-schedule"], qk.myBookings]`) |
| devDeps 未锁版本(React 19 需 `@testing-library/react@^16.1.0`) | 🟡 | 切片02 AC 标最低版本:`@testing-library/react@^16.1.0` / `jest-dom@^6` / `user-event@^14` / `vitest@^3` / `jsdom@^25` |
| 测试造非 pending 态(confirmed/in_service/done/no_show)方式未说清 | 🟡 | 切片01 P-1 AC 加:测试用 `db_session.add(Booking(...,status="confirmed"))` 直接 DB 写入造非 pending 态(既有范式) |
| `started_at`/`ended_at` 时间源措辞不一(D4 `utcnow()` vs §4.5 `datetime.now(timezone.utc)`) | 🟡 | D4 + §4.5 统一为 `datetime.now(timezone.utc)`(tz-aware,对齐 `DateTime(timezone=True)` 列定义) |
| §8 verification 回填只提 409→400,漏 JSONB→JSON + vitest 组件测两处 | 🟡 | 切片03 AC feature_list 回填条改为:修正 409→400 + JSONB→JSON + 补 vitest 组件测条目 |
| §4.5 `InvalidTransition` 措辞「对齐 ScopeError→422」误导(那是改状态码,本 feature 不改) | 🟢 | §4.5 改为:纯语义子类,走 BizError 默认 400,无需 handler |
| §4.2 `super_admin` 措辞「403」不准(实际走平台 bypass) | 🟢 | §4.2 改为:hq_staff 无 store role → 403;super_admin 走平台 bypass(HQ 视图只读不调写端点) |
| `confirmed` 行按钮是死代码(device-booking 永不写 confirmed) | 🟢 | 切片03 AC 加注解:`confirmed` 行按钮属防御性渲染(状态机允许,运行期不可达) |

---

## 0. 决策记录(需求烤清共识)

> 需求经 feature notes + `device-booking` plan 的边界声明已烤清(`/grill-with-docs` 跳过,直接落 spec)。本回环 12 个决策点,来源标注:`[feature notes]`(边界已定)/ `[先例]`(对齐仓库现状或 device-booking 范式)/ `[默认]`(推荐默认,可被覆盖)。

| # | 决策点 | 结论 | 来源 |
|---|---|---|---|
| D1 | 非法状态跳转 HTTP 码 | **400**(`BizError`),**不是 409** | `[先例]` 全仓库无 409 概念(`app/services/errors.py` 仅 `BizError` 400 / `NotFoundError` 404 / `PermissionError` 403);`device-booking` plan §8 已把同类「409」判为笔误;现有 `BookingService.cancel` 对「非 pending 不可取消」就是 `BizError` → 400。feature_list.json verification 写「409」是**同型笔误**,以本 plan 为准(实施完成回填修正) |
| D2 | 状态机合法跳转边集(6 条) | `start`: {pending, confirmed} → in_service(2);`end`: {in_service} → done(1);`no-show`: {pending, confirmed, in_service} → no_show(3) | `[feature notes]` 明确「6 条合法跳转」。`in_service → no_show` 语义 = 「服务已开始但中途放弃/客户离场」,店员可判定爽约;`pending/confirmed → no_show` = 「预约了但人没来」 |
| D3 | 状态机是否抽纯函数 | **是**,新建 `app/services/booking_state.py`(`transition(current, action) → new_state`,非法跳转 raise `InvalidTransition`) | 用户拍板 seam 选择(状态机 + unit 都要)。纯函数可独立复用 + 独立 unit 测,Service 层只负责「调状态机 + 写列」 |
| D4 | `started_at` / `ended_at` / `feedback` 写入 | `start` 写 `started_at = datetime.now(timezone.utc)`;`end` 写 `ended_at = datetime.now(timezone.utc)` + 可选 `feedback`(JSON dict) | `[feature notes]` 三列由 `device-booking` 已建 schema(`Booking.started_at/ended_at/feedback` nullable,列定义为 `DateTime(timezone=True)`),**本 feature 无新迁移**。v2:统一用 tz-aware `datetime.now(timezone.utc)`(非 naive `utcnow()`),对齐列定义 |
| D5 | `start` 权限 | customer(自己的 booking **且** `customer_id` 非空)**或** store owner(`bookings:update`);**walk-in**(`customer_id` 空)→ **仅 store owner** | `[feature notes]` 边界明确:避免匿名预约被冒认。v2:store 路径的 `:update` 码 `DEFAULT_OWNER_PERMS` + `DEFAULT_ADMIN_PERMS` 都有(owner/admin 均可),故 store owner/admin 均可 start 非 walk-in;walk-in 仅 owner(member 无 `:update`) |
| D6 | `end` / `no-show` 权限 | **仅 store owner**(`bookings:delete`);admin/member/customer/hq_staff 均无权 | `[feature notes]` 边界明确。v2 修正:`DEFAULT_ADMIN_PERMS` **不含** `bookings:delete`(对齐 customer/device admin 不可删业务记录约定,见 `permission_service.py` 注释「cancel reuses delete perm, so admin CANNOT cancel」),故 admin 调 end/no-show → **403**;只有 owner 持 `:delete` |
| D7 | customer `start` 的授权机制 | **不走** `require_permission`;改用 `current_user.customer_id` 存在性 + `== booking.customer_id` 双校验(先判 walk-in guard:`booking.customer_id is None` → 403;再判 `== current_user.customer_id`,不等 → 403) | `[先例]` `me.py` 的 `/me/bookings` 同款 anti-override 范式(id 从 principal 注入,不接受请求参数)。v2 修正(B1):**整个 `start` 端点不挂 router-level `require_permission`**,函数体内按 `current_user.customer_id is not None` 分叉 —— customer 路径走双校验,store 路径调 `permission_service.require(...,"bookings","update")`。若挂 router-level guard,customer(member 角色)在进入函数体前就被 403,到不了分叉。生产环境 customer principal 可能**完全无 tenant role**(`get_current_user` 只读 `customer_id` claim),这是绕过 require_permission 的根因;测试用 `customer_client_factory`(绑 member)但断言不依赖该角色 |
| D8 | 三个动作端点的 permission code | **复用现有码,不新增**:`start` store 路径 → `bookings:update`;`end` / `no-show` → `bookings:delete` | `[默认]` 对齐 `device-booking` 的 `/cancel` 复用 `:delete` 范式;避免膨胀 permission matrix + 免 backfill。v2 修正(B1):**三个端点都不挂 router-level `require_permission` 依赖**,改在函数体内调 `permission_service.require(...)`(对齐 `BookingService.list/get` 的 HQ 分叉范式)—— 因为 `start` 端点要同时服务 customer(无 tenant role)和 store principal,router-level guard 无法表达这种分叉。`end`/`no-show` 虽只服务 store principal,但为保持三端点风格一致 + 便于 P 章节 mock 也走函数体内 require |
| D9 | 动作端点返回码 | `start` / `end` → **200 + `BookingRead`**(客户端需读回 `started_at`/`ended_at` 刷新 UI);`no-show` → **204 无 body**(纯状态翻转,对齐 `/cancel` 范式) | `[默认]` `start`/`end` 有时间戳副作用且 UI 要反映;`no-show` 是终态翻转,与 cancel 同构 |
| D10 | `feedback` 入参 | `end` 端点 body 接受**可选** `feedback: dict`(JSON),写 `bookings.feedback` 列;`start` / `no-show` 无 body | `[feature notes]`「写 feedback JSONB」。schema 用通用 `dict`(对齐 `device-booking` 把该列建成 SQLAlchemy `JSON` 而非 PG-only `JSONB`,SQLite/PG 双库兼容) |
| D11 | 前端组件测试框架 | **vitest** + `@testing-library/react` + `jsdom`(本项目首个前端单测基建) | 用户拍板 seam 选择。React 19 + Vite 下的 de facto 默认栈;`npm run build` + `oxlint` 仍是构建/lint 闸门,`vitest run` 作为新增 component 测闸门 |
| D12 | 前端按钮范围 | customer `MyBookingsView`:加「确认开机」(`pending` 行,→ in_service);store `StoreView`:加「结束」(`in_service` 行,弹 feedback 可选输入 → done)+「爽约」(→ no_show) | `[feature notes]` 前端项:customer 端「确认开机」是 StorePilot 的 Toast 占位,本项目**必须补真调**;门店端结束/爽约是店员操作 |

---

## 1. Problem Statement

`device-booking`(系列 3/4)建好了预约订单的 schema 和 `pending ↔ cancelled` 流转,但**订单进入服务、结束服务、判定爽约**这三步状态机动作还无处触发 —— 客户到店后没法「确认开机」让订单从 pending 变成 in_service、记录开始时间;店员没法结束服务记录结束时间 + 反馈;客户没来也没法标记爽约。结果:订单永远停在 pending/cancelled,设备实际使用过程在系统里是黑箱。

`device-poweron`(系列 4/4 收官)填补这一层:把 `started_at` / `ended_at` / `feedback` 三列(已由 `device-booking` 建好 nullable schema)真正用起来,落地一个 6 态状态机 + 三个动作端点 + customer/store 两端操作按钮。

**为什么现在做**:`device-booking` 已 passing,`started_at` / `ended_at` / `feedback` 三列 + 6 态 `status` CHECK 都已就位,本 feature 是纯「填动作」—— 无新表、无新迁移、无新 permission code(全复用)。设备功能系列到此收官。

**为什么不含硬件下发**:与 StorePilot slice-30-d3-iot-static.md 阶段 1 妥协一致 —— 「点击开机 → 设备真开启」需要 MQTT broker / WebSocket 实时流 / 设备寻址下发,是独立的 IoT 基础设施层,本 SaaS 脚手架作为通用模板不该假设客户有此硬件链路。`devices` 表本次**不加** `mqtt_topic` / `hw_address` 字段(YAGNI,真上 IoT 时一次迁移补;`devices.serial_number` 已有,未来寻址可复用)。同样**不加** StorePilot 的 `risk_ack` / 血压采集前置(那是医疗特定业务合规要求,通用脚手架不假设)。

---

## 2. Solution

后端:一个纯函数状态机 `booking_state.py`(6 条合法跳转,非法 → `InvalidTransition`)+ `BookingService` 三个动作方法(`start`/`end`/`no_show`,各自调状态机 + 写对应时间列)+ 三个 `POST /bookings/{id}/{action}` 端点。**三个端点都不挂 router-level `require_permission`**,授权在函数体内手工分叉(B1 修正):`start` 按 `current_user.customer_id is not None` 分叉(customer 走 `customer_id` 双校验 D7;store 走 `permission_service.require(...,"bookings","update")`);`end`/`no-show` 函数体内调 `permission_service.require(...,"bookings","delete")`(仅 owner 通过,admin 无此码 → 403,B2 修正)。walk-in(`customer_id` 空)的 `start` 强制 store owner(D5)。

前端:customer `MyBookingsView` 的 `pending` 行加「确认开机」按钮真调 `startBooking()`(补 StorePilot 占位);store `StoreView` 的 `pending`/`confirmed` 行加「确认开机」(walk-in 散客预约用,B4 修正)、`in_service` 行加「结束」(弹 feedback 可选输入)、`pending`/`confirmed`/`in_service` 行加「爽约」按钮。引入 vitest + RTL + jsdom 对按钮做组件测(D11,首个前端单测基建)。

---

## 3. User Stories

1. 作为**客户**,我想在「我的预约」页面点「确认开机」把自己的 pending 预约推进到 in_service 并记录开始时间,以便到店后自助确认开始使用设备。
2. 作为**门店 owner**,我想对 in_service 的预约点「结束」记录结束时间 + 填写服务反馈,以便完成订单生命周期并沉淀服务记录。(注:admin 无 `bookings:delete` 权限,不能结束 —— 对齐 customer/device admin 不可删业务记录约定)
3. 作为**门店 owner**,我想对未到/中途放弃的预约点「爽约」标记为 no_show,以便区分真实使用与无效预约(影响排期释放与统计)。
4. 作为**门店 owner/admin**,我想对 walk-in 散客预约(customer_id 空)点「确认开机」推进到 in_service,以便处理到店即用、无预约记录的散客。(start 走 `:update`,owner/admin 均有此码)
5. 作为**门店 member**(只读),我不应看到任何状态机动作按钮(无 `:update`/`:delete` 权限)。
6. 作为 **hq_staff / super_admin**(跨租户只读),我不应能触发任何状态机动作(HQ 视图只读,写端点 router-level guard 拦截)。
7. 作为**系统**,非法状态跳转(如对 done 的预约 start、对 cancelled 的 end)必须拒绝(BizError 400),以便状态机不被绕过、订单生命周期不混乱。
8. 作为**安全审查者**,customer 不能 start 他人的预约、不能 start walk-in 预约(冒认防护);store_staff 不能跨租户操作(404 防 enumeration)。

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端 state machine | 1 新 | `app/services/booking_state.py`(`transition` 纯函数 + `InvalidTransition` 异常 + action/side-effect 常量) |
| 后端 service | 1 改 | `app/services/booking_service.py`(+`start` / `end` / `no_show` 三方法,各调 `booking_state.transition` + 写 `started_at`/`ended_at`/`feedback` + customer own / walk-in 校验) |
| 后端 api | 1 改 | `app/api/v1/bookings.py`(+`POST /{id}/start` / `/end` / `/no-show` 三端点) |
| 后端 schema | 1 改 | `app/schemas/booking.py`(+`BookingEndPayload{feedback: dict?}`,`start`/`no-show` 无 body) |
| alembic 迁移 | **0** | **无新迁移**(三列 + 6 态 CHECK 由 `device-booking` 已建) |
| 前端 types | 1 改 | `frontend/src/api/types.ts`(+`BookingEndPayload`) |
| 前端 endpoints | 1 改 | `frontend/src/api/endpoints.ts`(+`startBooking` / `endBooking` / `noShowBooking`) |
| 前端 hooks | 1 改 | `frontend/src/hooks/queries.ts`(+`useStartBooking`(切片02)+ `useEndBooking`/`useNoShowBooking`(切片03);三 mutation `onSuccess` 沿用 `BOOKING_WRITE_KEYS` 数组失效 `[qk.bookings, ["device-schedule"], qk.myBookings]`) |
| 前端页面 | 1 改 | `frontend/src/pages/bookings-page.tsx`(customer `MyBookingsView` +「确认开机」(切片02);store `StoreView` +「确认开机」(walk-in,pending/confirmed 行)+「结束」/「爽约」DropdownMenu 项 + feedback Dialog(切片03)) |
| 前端测试基建 | 4 新 | `frontend/vitest.config.ts`(或并入 vite.config 用 `/// <reference types="vitest/config" />`)+ `frontend/src/test/setup.ts`(jest-dom + cleanup)+ `frontend/src/test/test-utils.tsx`(`renderWithProviders`:QueryClient+ToastProvider)+ `package.json` devDeps(见切片02 锁版本) |
| 前端 tsconfig | 1 改 | `frontend/tsconfig.app.json`(`types` 加 `vitest/globals` + `@testing-library/jest-dom`,否则 `tsc -b` 红闸) |
| 后端集成测 | 1 改 | `tests/test_bookings_api.py`(+P 章节:6 合法跳转 + 非法 400 + 权限矩阵 + customer own + walk-in guard) |
| 后端 unit 测 | 1 新 | `tests/test_booking_state.py`(状态机纯函数全边覆盖) |
| 前端组件测 | 1 新 | `frontend/src/pages/__tests__/`(`my-bookings-view.test.tsx`(切片02)+ `store-view.test.tsx`(切片03)) |

### 4.2 多租户影响评估

- 新增租户 scoped 表?**NO**(复用 `bookings` 表)
- 修改现有租户隔离逻辑?**NO**(复用 `_get_live_booking`(tenant-scoped,跨租户/不存在 → NotFoundError 404 防 enumeration);customer principal 也有 `tenant_id`,`_get_live_booking` 对 customer/store 路径均生效)
- 引入跨租户访问点?**NO**(HQ 视图只读;三个动作端点函数体内调 `permission_service.require`,`hq_staff` 无 store role → 403;`super_admin` 走平台 bypass(`permission_service.check` 里 short-circuit 返回 True),但 HQ 视图本身只读不调写端点)
- 验证:P 章节 P-5(跨租户 start/end/no-show → 404,含 customer 路径)+ 权限矩阵覆盖 hq_staff 写 → 403

### 4.3 权限影响评估

- 新增 permission code?**NO**(D8 全复用:`start` store 路径 → `bookings:update`;`end`/`no-show` → `bookings:delete`)
- 修改 `DEFAULT_*_PERMS`?**NO**(`device-booking` 切片 02 已给 owner/admin 加 `bookings:create/read/update`、owner 加 `delete`;member 加 `bookings:read`;本 feature 不动)。⚠️ 注意:`DEFAULT_ADMIN_PERMS` **不含** `bookings:delete`(对齐 customer/device admin 不可删约定),故 admin 调 end/no-show → 403(B2 修正)
- 修改 `DEFAULT_MENU_PERMS`?**NO**
- 影响 60+ 处 `require_permission` caller?**NO**(只新增端点,不改现有)
- 影响 graph.py 工具内 check?**NO**
- **三端点都不挂 router-level `require_permission` 依赖**(B1 修正):授权在函数体内调 `permission_service.require(...)`。理由:`start` 端点要同时服务 customer(可能无 tenant role)和 store principal,router-level `require_permission` 会把 customer 在进入函数体前 403;为保持三端点风格一致,`end`/`no-show` 也走函数体内 require。对齐 `me.py`(`/me/bookings` 无 router-level guard)+ `BookingService.list/get`(HQ 分叉)范式
- customer `start` 路径(D7):**不走** `permission_service.require`,改用 principal `customer_id` 双校验(先 walk-in guard:`booking.customer_id is None` → 403;再 `== current_user.customer_id`,不等 → 403);store 路径的 `start` 在函数体内调 `permission_service.require(...,"bookings","update")`。端点函数体内按 `current_user.customer_id is not None` 分叉
- scope 闸门(API token):`bookings:update` / `bookings:delete` 自然纳入既有 scope gate(`{obj}:{act}` 匹配),无需改造

### 4.4 数据库表设计 checklist

**本 feature 不新建表、不加列、不加索引、不加迁移**(呼应 AGENTS.md 铁律 6「按需加,不预建空架子」)。`bookings` 表的 6 态 status CHECK + `started_at` / `ended_at` / `feedback` 三列已由 `device-booking` 切片 01 一次建齐(`alembic/versions/..._add_bookings_table.py`)。本 feature 只**写**这三列(`start`→`started_at`、`end`→`ended_at`+`feedback`),`status` 由动作端点经状态机推进。

`feedback` 列在 `device-booking` 建为 SQLAlchemy 通用 `JSON`(非 PG-only `JSONB`),SQLite 测试库与生产 PG 双库兼容 —— 本 feature 写入保持该类型不变(D10)。

### 4.5 其他实施决策

- **状态机纯函数设计**(D3):`booking_state.transition(current: str, action: str) -> str`,内部一张 `{(state, action): new_state}` 跳转表(6 条合法边)。非法组合 raise `InvalidTransition(current, action)`(子类化 `BizError`,→ 400,D1)。`BookingService.start/end/no_show` 各自先 `transition(booking.status, "start"/"end"/"no_show")` 再写列 —— Service 层不再 inline if/else 判状态,状态图唯一真相源在 `booking_state.py`。
- **`InvalidTransition(BizError)` 纯语义子类**(v2 修正措辞):走 `BizError` 默认 400,**不改状态码,无需新 handler**(main.py 的 BizError handler 自动覆盖子类)。子类化仅为语义清晰 + unit 测可 `pytest.raises(InvalidTransition)` 精确匹配。**不是** `ScopeError→422` 那种「子类化 + 注册专用 handler 覆盖状态码」的范式(那是改状态码才需要的)。
- **`started_at` / `ended_at` 时间源**(v2 统一):用 `datetime.now(timezone.utc)`(tz-aware,对齐 `DateTime(timezone=True)` 列定义;非 naive `utcnow()`,避免与 `scheduled_*` 的 tz-aware 值混用漂移)。仓库既有 `created_at`/`updated_at` 走 `func.now()` DB 端默认,但动作时间戳是业务事件时间,Service 层显式写更可控 + 可测。
- **customer `start` 端点分叉**(D7,v2 明确顺序):`POST /{id}/start` **不挂 router-level guard**,函数体内 —— 先 `booking = _get_live_booking(...)`(tenant-scoped,跨租户/不存在 → 404);若 `current_user.customer_id is not None`(customer principal):**先**判 `booking.customer_id is None` → 403(walk-in guard,D5;错误信息「walk-in 预约仅门店员工可开机」),**再**判 `booking.customer_id == current_user.customer_id`(不等 → 403,错误信息「无权操作他人预约」);否则(store principal):调 `permission_service.require(...,"bookings","update")`(member 无此码 → 403)。两条路径都不接受请求参数传 `customer_id`(anti-override)。
- **错误处理**:复用现有三件套(`BizError` 400 / `NotFoundError` 404 / `PermissionError` 403),全局 handler 已注册,无新增。
- **状态机不可逆**:`done` / `cancelled` / `no_show` 是终态,任何动作对其都 `InvalidTransition` 400(含 `/cancel` 对 in_service 的拒绝 —— 已由 `device-booking` 的 `cancel` 守卫:仅 pending 可取消)。

---

## 5. Testing Decisions

- **测试金字塔**:unit(状态机纯函数,N 条边)+ integration(API 端点行为,P 章节)+ component(前端按钮,D11 引入)。无 E2E。
- **seam 选择**(已与用户确认):
  1. **复用** `tests/test_bookings_api.py`(集成 seam,与 A–N 章节同层)—— 追加 **P 章节**:6 合法跳转 + 非法跳转 400 + 权限矩阵 + customer own 校验 + walk-in guard + 跨租户 404 + 时间戳/feedback 落库。
  2. **新增** `tests/test_booking_state.py`(窄 unit seam)—— 状态机纯函数全边覆盖(6 合法 × 断言新态 + 全部非法组合 × `InvalidTransition`)。纯函数无 DB,毫秒级。
  3. **新增** 前端组件测(D11,vitest + RTL)—— `MyBookingsView`「确认开机」+ `StoreView`「结束/爽约」按钮的渲染/调用/禁用/toast。
- **测试库**:后端 SQLite 内存库(conftest 既有 fixture,`feedback` 用通用 JSON 双库兼容);前端 jsdom。**无需真 PG**。
- **身份 fixture 来源**(复用 conftest 既有):`owner_client` / `admin_client` / `member_client` / `hq_staff_client` / `customer_client_factory(customer_id=...)` / 匿名 = 不带 Authorization header。无需新建 fixture。
- **造非 pending 态 booking**(v2 补):`device-booking` 永不写 confirmed/in_service/done/no_show 之外的态(create 永远 pending;cancel 只到 cancelled),但 6 态 CHECK 允许。P 章节测这些态时用 `db_session.add(Booking(..., status="confirmed"/"in_service"/...))` **直接 DB 写入**(既有范式:test_bookings_api.py:306/660/732 造跨租户/特殊态 booking 都这么写),不走 API(走不通)。
- **覆盖率目标**:不低于仓库基线 93%。新增 state machine / service 三方法 / 三端点全覆盖。
- **边界 case 清单**:
  - **6 合法跳转**(P-1):pending→in_service(start)、confirmed→in_service(start)、in_service→done(end)、pending→no_show、confirmed→no_show、in_service→no_show —— 各断言 status + 对应时间戳非空(非 pending 态 booking 用直接 DB 写入造,见上)
  - **非法跳转**(P-2):对 done/cancelled/no_show 调任意动作 → 400(`InvalidTransition`);对 in_service 调 start → 400(已在服务);对 pending 调 end → 400(未开始不可结束)
  - **`start` 权限矩阵**(P-3,v2 修正 admin 范围):customer(自己的 + customer_id 非空)→ 200;customer(他人的)→ 403;customer(walk-in 即 customer_id 空的 booking)→ 403(D5);owner → 200;admin → 200(start 走 `:update`,admin 有此码);member → 403(无 `:update`);hq_staff → 403;unauth → 401
  - **`end`/`no-show` 权限矩阵**(P-4,v2 修正 B2):owner → 200/204;**admin → 403**(无 `bookings:delete`,对齐 customer/device admin 不可删约定);customer → 403(D6);member → 403;hq_staff → 403
  - **跨租户**(P-5,v2 补 customer 路径):他租户 booking 的 start(end/no-show 同)→ 404(防 enumeration,`_get_live_booking` 同款);customer 路径跨租户(start 他租户 booking)→ 同样 404(customer principal 也有 `tenant_id`,`_get_live_booking` 对两条路径都生效)
  - **副作用落库**(P-6):start 后 `started_at` 非 None 且 `>=` 调用前;end 后 `ended_at` 非 None + `feedback` 落库(传 dict 对比);no-show 后 status=no_show 且 started_at/ended_at 保持原值(不写时间戳)
  - **状态机 unit**(test_booking_state.py):6 合法边各返正确新态;其余 `len(states)×len(actions) - 6` 非法组合各 raise `InvalidTransition`
- **多租户隔离测试**:P-5(跨租户操作 404,含 customer 路径)≥1 条。

---

## 6. Out of Scope(边界声明)

❌ **不做**(系列外,未来 backlog):
- **硬件下发链路**:MQTT broker / WebSocket 实时流 / 设备寻址下发 / `devices.mqtt_topic` / `devices.hw_address` 字段 —— 归 priority 65+ 的 IoT feature
- **`/bookings/{id}/confirm`** 端点(→ confirmed):confirmed 是 CHECK 占位态,`device-booking` plan D2 已声明本系列永不写入;补 confirm 是 backlog
- **`risk_ack` / 血压采集前置**:医疗特定业务合规,通用 SaaS 脚手架不假设(对齐 `device-booking` 边界)
- **预约提醒/通知**:无通知基础设施
- **预约导出/报表**

❌ **不做**(本 feature 边界,与 `device-booking` 已定边界一致):
- 新建表 / 加列 / 加迁移(`bookings` schema 已由 `device-booking` 建齐)
- 新增 permission code(D8 全复用)
- customer 自助创建/取消/结束预约(创建 + 结束 + 爽约是门店员工职责;customer 仅能 start 自己的)
- 修改 `device-booking` 已交付的 CRUD/cancel/schedule/HQ/customer-own 逻辑(只读引用)

---

## 7. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| customer 冒认 start 他人/walk-in 预约 | 高 | D7:`current_user.customer_id` 双校验(存在性 + `== booking.customer_id`);walk-in(`customer_id` 空)直接 403(D5)。端点不接受请求参数传 customer_id |
| 状态机被绕过(客户端直传 status) | 高 | `BookingCreate`/`BookingUpdate` schema 不含 status(`device-booking` 已守卫);本 feature 三动作端点也不接受 status body,只经 `booking_state.transition` 推进。DB 6 态 CHECK 是 backstop |
| 非法跳转返 409 与仓库惯例冲突 | 中 | D1:统一 400(`BizError`/`InvalidTransition`),修正 feature_list.json verification 的「409」笔误(同 `device-booking` §8 修正范式),实施完成回填 |
| `started_at` 时间源不一致(Service 写 vs DB 默认) | 低 | D4:动作时间戳统一 Service 层 `datetime.now(timezone.utc)` 显式写;`created_at`/`updated_at` 仍走 DB `func.now()`(语义不同:前者业务事件时间,后者记录审计时间) |
| 引入 vitest 基建增加前端构建复杂度 / CI 时长 | 中 | D11:devDeps 隔离(`vitest run` 独立 npm script,不并入 `build`);配置最小化(单 `vitest.config.ts` + setup.ts);组件测只覆盖两按钮,不铺开。`npm run build` + `oxlint` 仍是构建/lint 闸门不变 |
| customer principal 在生产无 tenant role 导致 start 端点 403 | 中 | D7:customer 路径显式绕过 `require_permission`;测试用 `customer_client_factory`(绑 `member`)覆盖,但断言不依赖该角色(只验 `customer_id` 校验路径) |
| `feedback` JSON 在 SQLite/PG 行为漂移 | 低 | `device-booking` 已建为通用 `JSON`(非 JSONB),双库兼容;本 feature 写 dict,读回对比即可,不依赖 JSONB 查询性能 |

---

## 8. 验收标准(同步 feature_list.json verification,以本 plan v2 修正版为准)

> ⚠️ feature_list.json verification 有**三处**需在实施完成回填修正(v2):① 第 1 条「ConflictError → HTTP 409」→ **400**(`InvalidTransition` 子类 `BizError`,同 `device-booking` 的 409 笔误);② 第 1 条「写 feedback **JSONB**」→ **通用 JSON**(`device-booking` 已建为 SQLAlchemy `JSON` 非 JSONB,双库兼容);③ 补加「vitest 前端组件测」条目(feature_list verification 原无此维度)。

1. 后端:`POST /api/v1/bookings/{id}/start`(pending/confirmed → in_service,写 `started_at`)+ `POST /api/v1/bookings/{id}/end`(in_service → done,写 `ended_at` + 可选 `feedback`)+ `POST /api/v1/bookings/{id}/no-show`(→ no_show);状态机纯函数 `booking_state.transition`(6 条合法跳转)+ 非法跳转 → **400**(`InvalidTransition` 子类 `BizError`,**不是 409**);**三端点均不挂 router-level `require_permission`**,授权在函数体内手工分叉(B1)
2. 权限(v2 修正 B2):`start` 可由 customer(自己的 + customer_id 非空)或 store owner/admin(`:update`);walk-in(customer_id 空)仅 store owner/admin start,customer 端无权;**`end`/`no-show` 仅 store owner**(`:delete`,admin 无此码 → 403);所有端点强制 tenant_id + customer_id(如适用)校验防越权
3. 前端(v2 修正 B4):customer 端 `MyBookingsView`「确认开机」按钮**真调 API**(补 StorePilot 的 Toast 占位);门店端 `StoreView` 预约列表的「确认开机」(walk-in 散客,pending/confirmed 行)+「结束」「爽约」操作按钮
4. pytest:覆盖 6 条合法跳转 + 非法跳转 **400** + 权限矩阵(**start: owner/admin 200、member 403;end/no-show: owner 200/204、admin/member/customer/hq_staff 403**)+ customer own 校验 + **walk-in booking(customer_id 空)customer start 应 403,store owner start 应 200** + `started_at`/`ended_at` 自动填充 + `feedback` 落库 + **alembic check 无 drift**(本 feature 无新迁移,head 链不变,依赖 CI)
5. 前端组件测(vitest + RTL,首个前端单测基建):customer「确认开机」+ store「结束/爽约」按钮的渲染/调用/禁用/toast 覆盖
6. `cd frontend && npm run build` 通过 + `oxlint` 0 warnings + `vitest run` 全绿
7. `./init.sh` 全绿(ruff + pytest 全章节 A–P + test_booking_state)

---

## 9. 不越界声明

本次改动**只**涉及:`booking_state.py`(新)+ `BookingService.start/end/no_show`(新方法)+ 三动作端点(新)+ `BookingEndPayload`(新 schema)+ 前端两处按钮 + vitest 基建 + 配套测试;**不**触碰 `device-booking` 已交付的 CRUD/cancel/schedule/HQ/customer-own 逻辑(只读引用其 Service/Repo/Schema)、**不**加 `bookings` 表任何列/索引/迁移、**不**加新 permission code、**不**实现硬件下发链路、**不**加 `risk_ack`/血压前置、**不**改 `devices` 表。

---

## 实施切片(3 个 tracer-bullet 垂直切片,每个切片一个 context window 完成)

> 切片原则:每切片是窄而全的垂直切片(状态机→Service→API→测试闭环,或 前端按钮→组件测闭环),不是按层水平切。每切片可独立 demo/verify。阻塞边明确,frontier 上无 blocker 的切片可立即开工。
>
> 实施节奏:一次一个切片,用 `/implement` 推进,切片间清 context。WIP=1 仍然适用 —— 同一时刻只在一个切片上 in_progress,该切片全绿才进下一个。**前置条件**:`device-booking` 全 passing ✅(已满足,`bookings` schema + 6 态 CHECK + 三列已就位)。

### 切片 01 — 后端地基:6 态状态机 + 三个动作端点 + customer/walk-in 授权 ✅(PR #114,commit 6e74073)

**Blocked by:** 无 —— 可立即开工(`device-booking` 已 passing,`bookings` schema 就位)

**What it delivers:** 一个 tenant 内的 customer 能「确认开机」把自己的 pending/confirmed 预约推进到 in_service(写 started_at);owner 能「结束」(in_service→done,写 ended_at + 可选 feedback)、「爽约」(pending/confirmed/in_service→no_show);admin 能 start(含 walk-in)但不能 end/no-show(无 `:delete`)。member/hq_staff/customer-越权/walk-in-customer 全部被拦。非法跳转 → 400。状态机是纯函数,独立 unit 测覆盖全边。

**Acceptance criteria:**
- [x] `app/services/booking_state.py`:`transition(current: str, action: str) -> str` 纯函数,内部 6 条合法跳转边表(D2);非法组合 raise `InvalidTransition(current, action)`(子类化 `BizError`);导出 `ACTIONS = {"start","end","no_show"}` 常量
- [x] `app/services/errors.py`:`InvalidTransition(BizError)` 子类(若不已有),无新全局 handler(走 BizError 默认 400,v2:不改状态码)
- [x] `app/services/booking_service.py`:新增 `start(actor_id, tenant_id, booking_id, *, platform_role, customer_id)` / `end(..., feedback=None)` / `no_show(...)` 三方法 —— 各自调 `booking_state.transition` + 写对应时间戳/feedback(用 `datetime.now(timezone.utc)`,v2)+ customer own / walk-in 校验(D5/D6/D7,walk-in guard 先于 own 校验);`end` 写 `feedback`(可选 dict);`no_show` 不写时间戳
- [x] `app/schemas/booking.py`:新增 `BookingEndPayload{feedback: dict | None = None}`(`start`/`no-show` 无 body,端点不带 payload 参数);`BookingRead` 已含 `started_at`/`ended_at`/`feedback`(device-booking 已建,本 feature 只读引用,**无需改**)
- [x] `app/api/v1/bookings.py`:新增 `POST /{id}/start`(200 + BookingRead)/ `POST /{id}/end`(200 + BookingRead,body=BookingEndPayload)/ `POST /{id}/no-show`(204 无 body);**三端点均不挂 router-level `require_permission` 依赖**(B1 修正)—— `start` 函数体内按 `current_user.customer_id is not None` 分叉(customer 走双校验 D7;store 调 `permission_service.require(...,"bookings","update")`);`end`/`no-show` 函数体内调 `permission_service.require(...,"bookings","delete")`
- [x] `tests/test_booking_state.py`:6 合法边各断言新态 + 全部非法组合各 `pytest.raises(InvalidTransition)`
- [x] `tests/test_bookings_api.py` P 章节(非 pending 态 booking 用 `db_session.add(Booking(...,status=...))` 直接 DB 写入造,v2):P-1(6 合法跳转 + 时间戳/feedback 断言)+ P-2(非法跳转 400)+ P-3(start 权限矩阵:customer own 200 / customer 他人 403 / customer walk-in 403 / owner 200 / admin 200 / member 403 / hq_staff 403 / unauth 401)+ P-4(end/no-show 权限矩阵:**owner 200/204、admin 403**、customer 403、member 403、hq_staff 403,v2 修正 B2)+ P-5(跨租户 start/end/no-show → 404,含 customer 路径)+ P-6(副作用落库:started_at/ended_at/feedback)
- [x] 本地 `./init.sh` 全绿(ruff + pytest,含 P 章节 + test_booking_state)

---

### 切片 02 — 前端基建:vitest + customer「确认开机」按钮 + 组件测

**Blocked by:** 01(`/start` 端点形状 + `BookingRead` 带 started_at 定型)

**What it delivers:** 引入本项目首个前端单测基建(vitest + RTL + jsdom);customer 在 `MyBookingsView` 的 `pending` 行看到「确认开机」按钮,点击真调 `startBooking()` → 成功 toast + 列表刷新(in_service);非 pending 行无按钮。组件测覆盖按钮渲染/调用/禁用/toast。**本切片只建 `start` 相关的 endpoint/hook**(`end`/`no-show` 留给切片03,避免预建空架子,铁律6)。

**Acceptance criteria:**
- [x] `frontend/package.json`:devDeps 加(锁最低版本,v2)`vitest@^3` / `@testing-library/react@^16.1.0`(React 19 支持)/ `@testing-library/jest-dom@^6` / `@testing-library/user-event@^14` / `jsdom@^25`;`scripts` 加 `"test": "vitest run"`(独立 script,不并入 build)
- [x] `frontend/vitest.config.ts`(或并入 `vite.config.ts` 顶部加 `/// <reference types="vitest/config" />` 后挂 `test:` 字段,二选一,v2 明确):`environment: 'jsdom'`、`setupFiles: ['./src/test/setup.ts']`、`globals: true`、复用 vite 的 `@vitejs/plugin-react` + alias `@`(用 `mergeConfig` 从 vite.config 引入,避免抄配置漂移)
- [x] `frontend/tsconfig.app.json`(v2 新增,否则 `tsc -b` 红闸):`types` 从 `["vite/client"]` 改为 `["vite/client","vitest/globals","@testing-library/jest-dom"]`
- [x] `frontend/src/test/setup.ts`:`import '@testing-library/jest-dom'` + `afterEach(cleanup)`
- [x] `frontend/src/test/test-utils.tsx`(v2 新增,组件测必需):导出 `renderWithProviders(ui)`,内含新建 `QueryClient`(`defaultOptions.queries.retry:false`、`staleTime:Infinity` 防 refetch)+ `ToastProvider`;组件测通过它 render,否则 `useMyBookings`/`useToast` 抛「must be used within Provider」
- [x] `frontend/src/api/types.ts`:加 `BookingEndPayload { feedback?: Record<string, unknown> }`(对齐后端,虽 02 不用但类型完整)
- [x] `frontend/src/api/endpoints.ts`:加 `startBooking(id)`(POST /start)—— **只建 start**(`endBooking`/`noShowBooking` 留切片03)
- [x] `frontend/src/hooks/queries.ts`:加 `useStartBooking()` mutation(`useApiMutation` 骨架),`onSuccess` 失效 `BOOKING_WRITE_KEYS`(`[qk.bookings, ["device-schedule"], qk.myBookings]`,v2 修正:用既有数组,非 `qk.deviceSchedule` 函数)
- [x] `frontend/src/pages/bookings-page.tsx` `MyBookingsView`:`pending` 行加「确认开机」`Button`(调 `useStartBooking`),成功 toast「已开机」+ 失败 toast `apiErrorMessage(err)`;非 pending 行不渲染按钮(in_service/done/cancelled/no_show/confirmed 无按钮)
- [x] `frontend/src/pages/__tests__/my-bookings-view.test.tsx`(用 `renderWithProviders` + `vi.mock("@/hooks/queries")` stub `useMyBookings`/`useStartBooking`,v2):`pending` 行渲染按钮 / 点击触发 `startBooking`(断言 mutation 调用)/ 成功 toast 出现 / 非 pending 行无按钮 / `isPending` 时按钮 disabled
- [x] `cd frontend && npm run build` + `npx oxlint` + `npx vitest run` 全绿(0 warnings/errors;若 oxlint 扫 test 目录报 warning,在 `.oxlintrc.json` 加 `overrides` 把 `**/*.test.tsx` 的 `no-unused-vars` 调为 `warn`/`off`)

---

### 切片 03 — store「确认开机(walk-in)/结束/爽约」按钮 + feature 收尾(末切片)

**Blocked by:** 02(vitest 基建 + customer 按钮模式 + `useStartBooking`/`startBooking` 定型)

**What it delivers:** store owner/admin 在 `StoreView` 的 `pending`/`confirmed` 行点「确认开机」(walk-in 散客预约用,→ in_service)、`in_service` 行点「结束」(弹 Dialog 填可选 feedback → done)、对 pending/confirmed/in_service 行点「爽约」(→ no_show);member/hq 视图无按钮。整 feature 走完收尾仪式。

> **切片内部分两段防过载**(v2,工程审查建议):先做 store 三按钮 + 配套 hooks/endpoints + 组件测全绿(本切片 AC 前 5 条),再跑收尾 7 步(后 7 条)。

**Acceptance criteria:**
- [ ] `frontend/src/api/endpoints.ts`:加 `endBooking(id, payload?)`(POST /end,返 Booking)+ `noShowBooking(id)`(POST /no-show)(v2:从切片02 移到此处,随 store 按钮一起建,避免预建空架子)
- [ ] `frontend/src/hooks/queries.ts`:加 `useEndBooking()` / `useNoShowBooking()` mutation(`useApiMutation` 骨架),`onSuccess` 失效 `BOOKING_WRITE_KEYS`
- [ ] `frontend/src/pages/bookings-page.tsx` `StoreView` 操作 `DropdownMenu`(v2 修正 B3 + B4):`pending`/`confirmed` 行加「确认开机」项(走 `useStartBooking`,守 `canUpdate`=`bookings:update`,owner/admin 可见);`in_service` 行加「结束」项(打开 feedback Dialog,可选 `<textarea>`(原生 + tailwind,沿用项目惯例,见 customers-page.tsx,不新增 ui/textarea)→ `endBooking(id, {feedback})`);`pending`/`confirmed`/`in_service` 行加「爽约」项(确认 Dialog → `noShowBooking(id)`);终态(done/cancelled/no_show)无动作项。**「结束」「爽约」都用 `canDelete`**(`hasPermission(me,"bookings","delete")`,沿用现有 `canCancel` 变量,B3 修正 —— 只有 owner 可见,admin 隐藏因无 `:delete`)
- [ ] **松绑 `MUTABLE_STATUS` 守卫**:`StoreView` 的 DropdownMenu 显示条件从 `MUTABLE_STATUS.has(b.status)` 改为允许动作态(pending/confirmed/in_service 显示对应动作项,终态隐藏)
- [ ] 成功 toast「已开机」/「已结束服务」/「已标记爽约」+ 失败 toast `apiErrorMessage(err)`(非法态 400 时透传后端信息)。`confirmed` 行按钮属**防御性渲染**(状态机允许跳转,但 device-booking 永不写 confirmed → 运行期不可达,加代码注释说明)
- [ ] `frontend/src/pages/__tests__/store-view.test.tsx`(用 `renderWithProviders` + `vi.mock("@/hooks/queries")`,v2):「确认开机」按钮在 pending 行渲染(walk-in 场景)/ 「结束」按钮在 in_service 行渲染 + 点击开 Dialog + 提交触发 `endBooking`(带 feedback)/ 「爽约」按钮 + 确认 / 终态行无按钮 / member 视图无写按钮(`canUpdate`/`canDelete` 均假)
- [ ] `./init.sh` 全绿(ruff + pytest 全章节 A–P + test_booking_state)
- [ ] `cd frontend && npm run build` + `npx oxlint` + `npx vitest run` 全绿
- [ ] `alembic upgrade head && alembic check` 本地通过(若本地 docker 起不来,依赖 CI;**本 feature 无新迁移**,迁移链 head 不变,依赖 CI 验无 drift)
- [ ] `feature_list.json`:`device-poweron` status=`passing` + `evidence` 字段写实测结果(P 章节数 + test_booking_state 边数 + 组件测数 + init.sh/npm build/oxlint/vitest 全绿)+ **修正 verification 三处笔误**(v2:① 409→400;② JSONB→JSON;③ 补 vitest 组件测条目)
- [ ] `./scripts/sync-active-features.sh` 刷新 active 视图
- [ ] `progress.md` 加 Session 记录 + 更新「当前最高优先级未完成功能」(device-poweron 收官 → 下一个 frontier)+ **设备功能系列(61-64)收官标记**
- [ ] 文档影响评估(4 行格式)
- [ ] **依赖解锁扫描**:扫 `feature_list.json`,凡 `depends_on` 指向 `device-poweron` 的下游 feature —— 本 feature 是系列 4/4 收官,**预期无下游**(若意外有,按 three-tier §5 置 in_progress)

---

### 切片依赖图

```
01 (后端地基:状态机 + 三端点 + customer/walk-in 授权 + unit/集成测) ──┬─→ 02 (前端基建 vitest + customer 确认开机按钮 + 组件测) ──┐
                                                                   └──────────────────────────────────────────────────→┤ 03 (store 三按钮 + 收尾)
```

**Frontier 推进策略**:01 完成后,02 与 03 **逻辑上可分叉**(都只 blocked by 01),但 WIP=1 下强制串行,推荐 02 → 03 顺序(03 复用 02 落地的 vitest 基建 + 按钮/mutation 模式)。01 是纯后端 tracer-bullet,独立可 demo(API 层验全);02 引入前端单测基建(基建成本随首个组件测落地,不单独切片);03 补 store 三按钮 + 末切片收尾仪式。

---

## EP2 plan 自检(three-tier §3,进 EP3 前的轻量 gate)

- [x] **切片依赖图无环**:01 → {02, 03},02 → 03(逻辑分叉但 WIP=1 串行),无循环依赖
- [x] **每片有 acceptance criteria**:每片 ≥7 条 `- [ ]` 可执行检查(文件级 + 行为级)
- [x] **首片可立即开工**:切片 01 `Blocked by: 无`(`device-booking` 已 passing,schema 就位)
- [x] **plan 主体决策已落定**:§0 决策记录 12 条全结论(D1–D12),§4 Implementation Decisions 无 `TODO`/`待定` 悬空项
- [x] **EP2 收尾动作**(B5 修正,three-tier §5 规则 2):回填 `feature_list.json` 的 `device-poweron.plan` 字段 → 指向本文档 + `status` 从 `not_started` 翻 `in_progress`(依赖 `device-booking` 已 passing,当前 frontier)。✅ **已执行(2026-07-24)**:plan 字段回填 + status 翻 `in_progress` + progress.md 记录 + 本文档 commit(见下方「EP2 收尾待执行」执行记录)

### EP2 收尾待执行(plan 批准后立即做,不进切片)

> 子智能体工程审查(B5)指出:plan 自检声明可进 EP3,但若不执行 feature_list.json 回填,§5 真相源规则失效(新会话读到 `not_started`+`plan` 空 会误判「未规划」重跑 grill)。故 plan 批准后、进 EP3 前执行:
> 1. `feature_list.json`:`device-poweron` 加 `"plan": "harness/docs/plan-device-poweron.md"` + `status: "not_started"` → `"in_progress"`
> 2. `progress.md`:顶部记「EP2 回环完成 + 三方审查修订 v2 + 当前 frontier = device-poweron 切片 01」

**✅ 执行记录(2026-07-24,本会话回归验证后补完)**:
1. ✅ `feature_list.json`:`device-poweron.plan` = `harness/docs/plan-device-poweron.md`、`status` = `in_progress`(字段顺序:notes 后插 plan)
2. ✅ `progress.md`:顶部「当前最高优先级未完成功能」+「EP3 断点」段更新为 EP2 回环完成 + frontier = 切片 01
3. ✅ 本文档 EP2 自检第 4 条勾选 + 本执行记录补登
4. ✅ commit 落盘(plan + feature_list + progress 三件一起)

---

## 调研证据(Explore + codegraph,2026-07-24)

| 关键论点 | 出处 |
|---|---|
| `BookingService.cancel` 已对非 pending 态 raise BizError 400,注释明说「那些状态 owned by device-poweron's action endpoints」 | `app/services/booking_service.py`(cancel 方法) |
| `_MUTABLE_STATUSES = {"pending"}` 是 update 守卫(PUT 仅 pending 可调,D10) | `app/services/booking_service.py:82` |
| `CurrentUser.customer_id` 已存在(slice 04),从 JWT claim `extract_customer_id` 解析,store-staff token 无此 claim → None | `app/api/deps.py:46-69,174` |
| `customer_client_factory` 把 customer principal 绑成 `member` 角色 + 注入 `customer_id`(测试 auth 基础) | `tests/conftest.py:445-530` |
| `/me/bookings` 端点 keying off `customer_id`(D7 anti-override 范式),store-staff → 403 | `app/api/v1/me.py`(list_my_bookings) |
| HQ 全景与 within-store 分叉在 Service `list`/`get` 内(`is_cross_tenant_viewer`);**既有**写端点(create/update/cancel)走 router-level `require_permission` —— 本 feature 三新端点**偏离**该范式(B1):改函数体内 require,因 start 要服务 customer principal | `app/api/v1/bookings.py`(create/update/cancel)+ `me.py`(无 guard 范式) |
| `/cancel` 复用 `require_permission("bookings","delete")`(D8 范式)+ 返 204(D9 no-show 同构范式) | `app/api/v1/bookings.py`(cancel_booking) |
| `DEFAULT_ADMIN_PERMS` 不含 `bookings:delete`(B2 核心证据,对齐 customer/device admin 不可删约定) | `app/services/permission_service.py`(DEFAULT_ADMIN_PERMS 注释) |
| `extract_customer_id` 真正的 claim 解析位置 | `app/core/security.py:166-176`(deps.py:174 调用它) |
| 全仓库无 409 ConceptError,冲突全走 `BizError` 400(`device-booking` D1 已定调) | `app/services/errors.py` + `app/main.py` 全局 handler |
| `feedback` 列在 `device-booking` 建为通用 `JSON`(非 JSONB),SQLite/PG 双库兼容 | `device-booking` plan §4.4 + `app/schemas/booking.py`(BookingRead.feedback: dict) |
| `bookings` 表 6 态 status CHECK + started_at/ended_at/feedback 三列已由 device-booking 切片 01 建齐(本 feature 无新迁移) | `device-booking` plan §4.4 + alembic `_add_bookings_table.py` |
| `MyBookingsView` 当前纯只读(无操作按钮),「确认开机」是 StorePilot 占位需补真调 | `frontend/src/pages/bookings-page.tsx`(MyBookingsView) |
| `StoreView` 操作用 `DropdownMenu` 模式(canUpdate/canCancel 守卫,cancel 已在其内) | `frontend/src/pages/bookings-page.tsx`(StoreView 操作列) |
| 前端目前 0 单测(只 build + oxlint),D11 引入 vitest 是首个前端单测基建 | `frontend/package.json`(无 test script)+ device-booking 切片 05-07 验证惯例 |
