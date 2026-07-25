# 计划:总部平台角色解锁设备/预约跨店全写权限

> **id**: platform-cross-tenant-write
> **状态**: draft v1(EP2 回环产出,待 EP3 实施)
> **优先级**: 67(新登记,「权限」area;`booking-state-cancel` 让位到 68 推迟)
> **创建日期**: 2026-07-25
> **来源**:设备/预约功能系列(61-66)收官后的平台角色权限升格需求;grill 6 决策回环产出

---

## 1. Problem Statement

设备/预约功能系列(61-66)收官后,平台角色(`super_admin` + `hq_staff`)在 devices + bookings 两个模块的权限是「**跨店只读**」:

- `permission_service.check`:super_admin 全 bypass;hq_staff 仅 `read` short-circuit → True,写动作 fall through 到 casbin → hq_staff 无任何 tenant role → **写必 403**
- service body:`require("devices"/"bookings", <act>")` + `_get_live_*(id, user.tenant_id)` —— 平台用户 `user.tenant_id` 为空,即便 super_admin 进了 require bypass,`_get_live_booking(id, None)` 也直接 404

**业务诉求**:总部平台角色需要代门店做全权运营(建/改/删设备、创建/改/取消预约、代客户开机/结束/爽约),现状把他们卡在只读视图。本任务把两个平台角色从「跨店只读」**升格**为「跨店全权运营」。

**核心摩擦**:
- 平台角色跨店写时,service body 里的 owner-only / customer-only / `_get_live_*(id, user.tenant_id)` 分支全部撞墙
- 现有 `start` 的 customer/store 双分支没有第三条「平台写角色」路径
- 前端 HqView 是纯只读表,无写控件、无目标店选择

**鉴权零回归底线**:门店角色(owner/admin/member/customer)现有契约零变化 —— 不带 `tenant_id` 时从 `user.tenant_id` 取;**门店角色不能伪造 `tenant_id` 跨店写**。

## 2. Solution

引入 helper `is_platform_writer(platform_role) = platform_role in {"super_admin", "hq_staff"}`(与 `is_cross_tenant_viewer` 同边界)。在 devices + bookings 的写路径上:

1. **目标租户解析**:`body.tenant_id` 字段(平台角色必填,门店角色禁带→400 BizError);`effective_tenant_id = payload.tenant_id or user.tenant_id`
2. **service body 三分支**(参照 `booking.start` 现有范式):`if customer_id / elif is_platform_writer / else require(...)`;平台角色分支 skip require + 用 `effective_tenant_id` 取实体
3. **状态机 4 守卫**(start/end/no_show/cancel):平台角色走 elif 分支 bypass require,等价「增强版 store principal」(start 可开 walk-in,不进 customer ownership)
4. **前端 HqView 增强**:加 target tenant 下拉 + 行内写动作 DropdownMenu + 复用 StoreView 的 Dialog(参数化 `tenant_id`)

**DataScope 零改动** —— 平台角色已在 `DataScopeService.resolve()` 被 `is_cross_tenant_viewer` bypass 到 `scope="all"`,本任务无新需求。**状态机零改动** —— `_TRANSITIONS` 表 / ACTIONS 不动,平台角色只是新加一条鉴权路径。

## 3. User Stories

- 作为 **super_admin**,我想在总部视图直接给某门店建/改/删设备、建/改/取消预约、代客户开机/结束/爽约,以便不必切到门店账号或临时挂 owner 角色就能跨店运营。
- 作为 **hq_staff**(总部业务员),我想拥有与 super_admin 同等的 devices/bookings 跨店写权,以便代门店做日常运营(建预约、开机、结束、标记爽约)。
- 作为 **门店 owner**,我想我现有的契约(不带 tenant_id、行为不变)完全不被影响,以便本任务上线对我的门店视角零感知。
- 作为 **平台安全负责人**,我想门店角色无法通过伪造 `body.tenant_id` 跨店写,以便多租户隔离不被破坏。

---

## 4. Implementation Decisions

### 4.0 grill 共识(D1-D6,本 plan 决策真相源)

| # | 决策 | 锁定值 |
|---|---|---|
| **D1** | 目标租户选择机制 | **A**:body 显式 `tenant_id` 字段。平台角色必填(不带→400);门店角色禁带(带了→400 BizError,防伪造);`effective_tenant_id = payload.tenant_id or user.tenant_id`。与 groups 的 `tenant_ids` 范式同源;最小侵入,不动 router 前缀 |
| **D2** | `customer_id` 跨店绑定 | **(a) 沿用现有字段 + (ii) 手填/留空**。`DeviceCreate.customer_id` 保持 `str \| None`;守卫用 `effective_tenant_id`。customers 模块零改动;平台角色跨店建/绑设备时 `customer_id` 手填全局 ID 或留空(走「先建后绑」),绑定留给门店 owner。代价:平台角色看不到目标店客户列表(UX 略糙),换取硬约束「不动 customers」 |
| **D3** | 状态机 4 守卫重写 | **D3-1 三分支 elif + D3-2 增强 store principal + D3-3 bypass require**。延续 `start` 现有范式:`if customer_id / elif is_platform_writer / else require(...)`。平台角色 = 增强版 store principal(start 可开 walk-in,不进 ownership);bypass require 不引临时 owner。**D3-4 状态机零改动**(平台角色只是新加鉴权路径,`_TRANSITIONS` 表不动) |
| **D4** | DataScope / `is_platform_writer` 边界 | **两角色都算 platform_writer**,与 `is_cross_tenant_viewer` 同边界(`{super_admin, hq_staff}`)。DataScope / Role.data_scope **零改动** —— 平台角色已在 `resolve()` 被 bypass 到 `all`,无新档需求 |
| **D5** | 前端 HqView 改造形态 | **D5-1 HqView 行内 + 复用 StoreView Dialog / D5-2 行内 DropdownMenu**。HqView 表头加「目标门店」下拉(拉 `fetchAllTenants`),选定后行内出现写动作(DropdownMenu 三点菜单,按 status 显隐);点击复用 StoreView 的 Dialog(参数化 `tenant_id`)。不新建视图、不动路由/nav |
| **D6** | 测试覆盖矩阵 | **D6-1 全矩阵 + 边界**(28-32 用例,**11 写动作**(含 bind/unbind,见 §4.5.5)× 2 角色 = 22 正向 + 6-10 边界)+ **D6-2 门店伪造拒(owner/admin/member/customer 四角色各一次)+ 旧断言改写**(`test_hq_platform_role.py` 中 `hq_staff 写 → 403` 旧断言改为 `带 tenant_id 写 → 201/200`)+ **D6-3 不动现有章节**(test_bookings_api / test_devices_api 现有 A-F 章全保留,只加新章节) |

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 6 | `app/services/permission_service.py`(加 `is_platform_writer`)、`app/schemas/device.py`(`DeviceCreate/Update.tenant_id` 可选)、`app/schemas/booking.py`(`BookingCreate/Update.tenant_id` 可选)、`app/services/device_service.py`(create/update/delete/bind/unbind 加 platform_writer 分支 + effective_tenant_id)、`app/services/booking_service.py`(create/update/cancel/start/end/no_show 加 platform_writer 分支 + effective_tenant_id)、`app/services/_tenant_target.py`(**新文件** `resolve_target_tenant` 共享 helper) |
| 数据库迁移 | 0 | 无 schema 变化(`tenant_id` 仅是请求字段,不入库;实体的 `tenant_id` 列已存在) |
| 前端文件改动 | 7 | `frontend/src/api/types.ts`(DeviceCreate/BookingCreate 加 `tenant_id?`)、`frontend/src/api/endpoints.ts`(写动作 mut 透传 tenant_id)、`frontend/src/hooks/queries.ts`(useDevices/useBookings 写 mut 参数)、`frontend/src/pages/devices-page.tsx`(HqView 加 target 下拉 + 写动作)、`frontend/src/pages/bookings/hq-view.tsx`(同上 + 行内 DropdownMenu)、`frontend/src/pages/bookings/store-view.tsx`(Dialog 抽出共享 + 参数化 tenant_id)、`frontend/src/pages/bookings/shared-dialog.tsx`(**新文件**,从 store-view 抽出的共享 Dialog 组件) |
| router 文件改动 | **0** | `app/api/v1/devices.py` + `bookings.py` **签名零改动** —— 现状 router 已把整个 `payload` 透传给 service,service 自己读 `payload.tenant_id`,无需 router 改签名。§4.5.4 说明 |
| 新增/改测试类 | 3 | `tests/test_devices_api.py`(加平台角色跨店写章节)、`tests/test_bookings_api.py`(加平台角色跨店写 + 状态机 4 守卫章节)、`tests/test_hq_platform_role.py`(旧断言改写 + 反向伪造拒) |
| API 契约改动 | 字段级(向后兼容) | 写动作 body 加 optional `tenant_id`;门店角色不带 = 行为不变;平台角色必带;**router 路径/方法/响应 schema 全不变** |
| 权限基础设施改动 | 0 | 不动 DEFAULT_*_PERMS、不动 Role.data_scope、不动 casbin policy、不动 require_permission caller 列表 |
| 新增/改测试类 | 3 | `tests/test_devices_api.py`(加平台角色跨店写章节)、`tests/test_bookings_api.py`(加平台角色跨店写 + 状态机 4 守卫章节)、`tests/test_hq_platform_role.py`(旧断言改写 + 反向伪造拒) |
| API 契约改动 | 字段级(向后兼容) | 写动作 body 加 optional `tenant_id`;门店角色不带 = 行为不变;平台角色必带 |
| 权限基础设施改动 | 0 | 不动 DEFAULT_*_PERMS、不动 Role.data_scope、不动 casbin policy、不动 require_permission caller 列表 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **YES,但仅扩展不破坏**:
  - `_get_live_device` / `_get_live_booking` 现状用入参 `tenant_id` —— 平台角色传入 `effective_tenant_id`(目标店),仍走同一租户隔离查询(`get_for_tenant` 过滤),不破坏隔离
  - 门店角色路径完全不变(`effective_tenant_id = user.tenant_id`)
- 是否引入跨租户访问点? **YES(刻意)**:平台角色可写任意目标店 —— 守卫方式:
  1. router `require_permission` 已 bypass super_admin;hq_staff 由 service body 的 `is_platform_writer` 分支放行
  2. 门店角色带 `body.tenant_id` → 400 BizError(D1-2,防伪造)
  3. 平台角色不带 `body.tenant_id` → 400(必填)
- 验证:多租户伪造拒测试 N 条(D6-2,见 §5)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 `require_permission` caller? **NO** —— router 层 `require_permission("devices"/"bookings", <act>)` 不动;super_admin 在 `check` 内 bypass,hq_staff 由 service body 放行
- 是否新增 helper? **YES**:`is_platform_writer(platform_role)` 加在 `permission_service.py`,与 `is_cross_tenant_viewer` 并列(语义:`{super_admin, hq_staff}`)
- 是否影响 DataScope? **NO**(D4)
- API token scope 闸门:**不动** —— restricted token 仍按 scopes 限流;super_admin 全 bypass 在 scope gate **之后**(scope gate 在 check 最前),restricted 的 super_admin/hq_staff token 仍受 scopes 约束(与本任务无关,保持现状)

### 4.4 数据库表设计 checklist

**N/A** —— 无数据库改动,无 schema 变化,迁移链 head 不变。`tenant_id` 是请求字段(payload),不是新列;实体的 `tenant_id` 列(`devices.tenant_id` / `bookings.tenant_id`)已存在且本任务不碰。

### 4.5 其他实施决策

#### 4.5.1 `is_platform_writer` helper 形态

```python
# app/services/permission_service.py —— 与 CROSS_TENANT_VIEWER_ROLES 并列
# Platform roles that can WRITE across tenants (HQ operators). Same boundary as
# CROSS_TENANT_VIEWER_ROLES — both super_admin and hq_staff unlock cross-tenant
# writes on devices/bookings. Service bodies branch on this to skip the casbin
# require (hq_staff has no tenant role) and resolve the target tenant from
# payload.tenant_id instead of user.tenant_id.
PLATFORM_WRITER_ROLES: tuple[str, ...] = ("super_admin", "hq_staff")


def is_platform_writer(platform_role: str | None) -> bool:
    """True if the role grants cross-tenant WRITE access on devices/bookings."""
    return platform_role in PLATFORM_WRITER_ROLES
```

> 注:与 `is_cross_tenant_viewer` 边界完全相同(都 `{super_admin, hq_staff}`)。语义分两个 helper 是为可读性 —— 读路径问「是不是跨店 viewer」,写路径问「是不是跨店 writer」,即便边界暂时一致,后续若分化(如只让 super_admin 写、hq_staff 仍只读)只需改 `PLATFORM_WRITER_ROLES`。

#### 4.5.2 effective_tenant_id 解析范式(所有写动作共用)

```python
def _resolve_target_tenant(
    self, user_tenant_id: str | None, payload_tenant_id: str | None,
    platform_role: str | None,
) -> str:
    """Resolve the tenant a write action targets.

    - Platform writers: MUST carry payload.tenant_id (target store); missing → 400.
    - Store roles: MUST NOT carry payload.tenant_id (anti-forgery); present → 400.
      Effective tenant is always user.tenant_id.
    """
    if is_platform_writer(platform_role):
        if not payload_tenant_id:
            raise BizError("平台角色跨店写必须指定目标门店(tenant_id)")
        return payload_tenant_id
    # store role
    if payload_tenant_id is not None:
        raise BizError("门店角色不可指定目标租户(tenant_id)")
    if not user_tenant_id:
        # defensive — store principals always have a tenant; reaches here only
        # on misconfigured tokens
        raise BizError("缺少门店归属,无法执行写操作")
    return user_tenant_id
```

**落点决策(锁定)**:抽到 `app/services/_tenant_target.py` 共享(单文件,~25 行)。理由:DeviceService 和 BookingService 用的是**完全相同**的逻辑(签名一字不差),各放一份必然漂移;独立模块也便于切片 01 落地后切片 02/03 直接 import,无重复改文件风险。helper 是纯函数(无 self 依赖),去掉签名里的 `self` 即可。

```python
# app/services/_tenant_target.py(新文件,切片 01 落地)
from app.services.errors import BizError
from app.services.permission_service import is_platform_writer


def resolve_target_tenant(
    user_tenant_id: str | None,
    payload_tenant_id: str | None,
    platform_role: str | None,
) -> str:
    """Resolve the tenant a devices/bookings write action targets. See plan §4.5.2."""
    if is_platform_writer(platform_role):
        if not payload_tenant_id:
            raise BizError("平台角色跨店写必须指定目标门店(tenant_id)")
        return payload_tenant_id
    if payload_tenant_id is not None:
        raise BizError("门店角色不可指定目标租户(tenant_id)")
    if not user_tenant_id:
        raise BizError("缺少门店归属,无法执行写操作")
    return user_tenant_id
```

DeviceService / BookingService 各自 `from app.services._tenant_target import resolve_target_tenant`,在写动作开头调一次。

#### 4.5.3 service body 三分支范式(以 booking.start 为参照)

```python
# booking.start 改造后
async def start(self, actor_id, user_tenant_id, booking_id, *,
                platform_role=None, customer_id=None, payload_tenant_id=None):
    effective_tenant = self._resolve_target_tenant(
        user_tenant_id, payload_tenant_id, platform_role)

    booking = await self._get_live_booking(booking_id, effective_tenant)

    if customer_id is not None:
        # Customer principal — ownership check, no casbin require.(原有路径)
        if booking.customer_id is None:
            raise PermissionError("walk-in 预约仅门店员工可开机")
        if booking.customer_id != customer_id:
            raise PermissionError("无权操作他人预约")
    elif is_platform_writer(platform_role):
        # Platform writer — skip require, treat as enhanced store principal.
        # Can start walk-in (booking.customer_id None) just like store staff.
        pass
    else:
        # Store principal — casbin require on bookings:update.(原有路径)
        await permission_service.require(
            actor_id, effective_tenant, self.OBJECT, "update",
            platform_role=platform_role)

    booking.status = booking_transition(booking.status, "start")
    ...
```

`end` / `no_show` / `cancel` / device `create`/`update`/`delete`/`bind`/`unbind` / booking `create`/`update` 同范式(elif 分支夹在中间,两端原路径不变)。

#### 4.5.4 router 透传(签名零改动)

`payload.tenant_id` 已在 body 里,router 现状已把整个 `payload` 透传给 service(见 `bookings.py:112` `DeviceService(db).create(..., payload, ...)`),service 自己读 `payload.tenant_id`。**router 签名/路径/方法/dependencies 全不变** —— `require_permission("devices"/"bookings", <act>)` 不动(super_admin 在 `check` 内 bypass,hq_staff 由 service body 放行),`@router.post("/"){...}` 路由声明不动。**这是 §4.1 影响面清单把 router 排除(0 文件改动)的依据。**

##### 4.5.4a 实施期补丁(切片 01/02 落地发现的 plan 盲点,2026-07-25)

切片 01/02 实施时发现 §4.5.4 与现状代码有 5 处脱节,以下补丁记录实际落地的形态(切片 04-05 沿用):

**补丁 1 — DELETE/unbind 用 query 参数(非 body)透传 tenant_id**
- **盲点**:plan §4.5.4 假设所有写动作都透传 `payload.tenant_id`,但 **DELETE 请求无 body**(REST 规范),`unbind`(DELETE /devices/{id}/bind)和 `delete`(DELETE /devices/{id})无法用 body 传 tenant_id。
- **落地**:这两个 endpoint 加 `tenant_id: str | None = Query(default=None)` 查询参数,service 接受 `target_tenant_id: str | None = None` keyword 参数。**路径/方法/dependencies/响应 schema 全不变**(只加 query 参数,符合 §4.5.4 字面「URL 前缀/方法不变」)。
- **影响面清单更新**:§4.1 「router 文件改动 0」→ **「router 文件改动 1」**(`app/api/v1/devices.py` delete/unbind 加 query + bind body 已含 tenant_id)。§11 不越界声明同步松绑。

**补丁 2 — `permission_service.check` 加 platform_writer bypass for devices**
- **盲点**:plan §4.5.4 说「hq_staff 由 service body 放行」,但现状 `check` 只对 `hq_staff + read` short-circuit,**写动作 fall through 到 casbin**(hq_staff 的 member 角色)→ 403,根本到不了 service body。router 的 `require_permission` dependency 在 endpoint 之前跑,直接调 `check`。
- **落地**:`check` 加 `if is_platform_writer(platform_role) and obj == "devices": return True`(切片 01 只对 devices;切片 02/03 再扩展到 bookings)。**这不违反 §4.3「不动 require_permission caller」** —— caller 列表不变,改的是 `check` 内部 bypass 逻辑(与现有 `super_admin` / `hq_staff + read` bypass 同范式)。也不违反 §4.3「不动 DEFAULT_*_PERMS / casbin policy」—— 那些真没动。
- **影响面清单更新**:§4.1 新增「`permission_service.check` 内部 +4 行 bypass」(文件已在清单内,改的是 check 函数体)。

**补丁 3 — D6-2「门店四角色带 tenant_id → 400」对 member/customer 实际是 403**
- **盲点**:plan §5 测试矩阵说「门店 owner/admin/member/customer 各一次带 tenant_id → 400」(D1-2 防伪造)。但 **member/customer 在 router `require_permission` dependency 就被 casbin 403**(他们没有 devices:create),根本到不了 service body 的 anti-forgery 400 守卫。
- **落地**:test_p7 拆成两组 —— owner/admin → **400**(service body anti-forgery 守卫生效,他们有 devices:create)+ member/customer → **403**(router casbin 拒,与 tenant_id 无关)。**这反而更安全**:伪造 tenant_id **不能**给 member/customer 解锁 create(router casbin 是第一道闸)。
- **AC 更新**:切片 01 AC「门店 owner/admin/member/customer 各一次 POST 带 tenant_id → 400」→ **「owner/admin → 400;member/customer → 403(router casbin 拒,与 tenant_id 无关)」**。

**补丁 4(切片 01 必要) — E 章 `test_hq_staff_writes_are_403` 改写**
- **盲点**:plan D6-2 说「旧断言改写在切片 05」。但补丁 2 让 hq_staff 写 devices 不再 403(变成 400 必填守卫),**切片 01 init.sh 必须绿**,所以这个测试必须在切片 01 改,不能推到切片 05。
- **落地**:E 章 `test_hq_staff_writes_are_403` → `test_hq_staff_write_without_tenant_id_400`,断言从 403 改为 400(hq_staff 不带 tenant_id → D1 必填守卫)。测试语义保留(「hq_staff 不能在没 target 的情况下写」),只是失败码从 casbin-deny 变成 missing-target-tenant。

**补丁 5(切片 02 必要) — 切片 02+03 合并(check bypass 原子性)**
- **盲点**:plan §6 把 bookings 改动切成 02(CRUD:create/update/cancel)+ 03(状态机:start/end/no_show),假设 check bypass 可以只对 CRUD 生效。但补丁 2 的 check bypass 是**按 obj 作用域**(不能按 act):
  - create 用 `bookings:create`(CRUD 独占)
  - **update 用 `bookings:update`** —— CRUD 的 update **和状态机的 start 共用**
  - **delete 用 `bookings:delete`** —— cancel **和 end/no_show 共用**
  - 所以 `check` bypass 对 `obj=="bookings"` 放行后,无法用 act 白名单只放行 CRUD 而拦状态机(act 重叠)。
- **更深问题**:若切片 02 只改 CRUD service body 不改状态机,hq_staff 带 `?tenant_id=` 调 start/end/no_show 会进 service body(check 放行)→ 现状 service 用 `user.tenant_id`(忽略 query 的 target_tenant_id)→ **静默写错店**(平台角色以为写目标店,实际写了自己的 user.tenant_id)。这是数据正确性 bug,不可接受。
- **落地**:**切片 02 一次性改 6 个写动作**(create/update/cancel/start/end/no_show)的 service body + check bypass 扩展到 `obj in ("devices","bookings")`。切片 03 实质并入切片 02(service body 部分),切片 03 原计划的「状态机测试」由 Q4-Q8 覆盖(walk-in start 边界 + InvalidTransition 守卫 + 6 写动作矩阵)。
- **切片 03 状态**:**已合并入切片 02**(标记为 deprecated,见 §6 切片 03 标题)。
- **bookings 端点 tenant_id 透传**:
  - create / update:body 字段(BookingCreate/Update.tenant_id)
  - cancel / start / end / no-show:**query 参数**(`?tenant_id=<target>`),因为 cancel/start/no-show 是 POST 无 body;end 的 body 是 BookingEndPayload(只含 feedback),tenant_id 走 query 与之正交。**路径/方法/dependencies/响应 schema 全不变**。
- **影响面清单更新**:§4.1 「router 文件改动」进一步含 `app/api/v1/bookings.py`(cancel/start/end/no-show 加 query + import Query)。§11 不越界声明同步松绑(devices/bookings router 同范式)。

#### 4.5.5 写动作范围(11 个,含 bind/unbind)

本任务解锁写的动作**共 11 个**:

| 模块 | 动作 | 权限 | router 依赖 |
|---|---|---|---|
| devices | POST(create)/PUT(update)/DELETE(delete) | `devices:create/update/delete` | `require_permission` |
| devices | POST `/{id}/customer`(bind)/DELETE `/{id}/customer`(unbind) | `devices:update` | `require_permission` |
| bookings | POST(create)/PUT(update)/POST `/{id}/cancel` | `bookings:create/update/delete` | `require_permission` |
| bookings | POST `/{id}/start`/`end`/`no_show` | body 内鉴权 | **无 router-level dep**(授权在 body) |

bind/unbind 是 device 的 customer 子资源绑定(状态机外的写动作),属于 device 写范畴,平台角色必须能代做(否则跨店建的设备无法绑客户)。§5 测试矩阵**补 bind/unbind 4 用例**(平台角色 × 2 动作)。

#### 4.5.5 前端 HqView target tenant 下拉 + 复用 Dialog

- 拉全租户:`fetchAllTenants()`(已有,`GET /tenants/all`,super_admin 限定)
- 选定 target → 行内写按钮根据 row.status 显隐(bookings:pending→取消/开机;in_service→结束/爽约;cancelled/done/no_show→无)
- 点击 → 打开 StoreView 已有的 Dialog(创建/编辑)或确认弹窗(删除/状态机动作),参数化 `tenant_id = selectedTarget`
- StoreView 的 Dialog 需抽出为共享组件(接受 `tenantId` prop),HqView 和 StoreView 都用 —— 这是切片 ④ 的主要工作量

---

## 5. Testing Decisions

- 测试金字塔:**integration 为主**(API 层覆盖鉴权 + 状态机 + 跨租户)+ 少量 unit(`is_platform_writer` 纯函数契约)
- 测试用 SQLite 内存库(`./init.sh`),不涉及 PG 专有类型
- 覆盖率目标:不低于项目基线(本任务新增逻辑主要集中在鉴权分支,API 层测试覆盖率高)
- 测试矩阵(D6-1 全矩阵 + 边界,约 28-32 用例;**含 bind/unbind 11 动作范围**,见 §4.5.5):

**正向矩阵(平台角色 × 11 写动作 = 22 用例)**:

| 模块 | 动作 | super_admin 跨店 | hq_staff 跨店 |
|---|---|---|---|
| devices | POST(带 tenant_id + 必填字段) | 201 | 201 |
| devices | PUT(改目标店设备) | 200 | 200 |
| devices | DELETE(删目标店设备) | 204 | 204 |
| devices | POST `/{id}/customer`(bind 目标店设备) | 200 | 200 |
| devices | DELETE `/{id}/customer`(unbind 目标店设备) | 204 | 204 |
| bookings | POST(带 tenant_id 创建) | 201 | 201 |
| bookings | PUT(改目标店预约) | 200 | 200 |
| bookings | POST /cancel(目标店预约) | 204 | 204 |
| bookings | POST /start(目标店预约,含 walk-in) | 200 | 200 |
| bookings | POST /end(目标店预约) | 200 | 200 |
| bookings | POST /no_show(目标店预约) | 204 | 204 |

**边界场景(6-10 用例)**:
- 平台角色不带 tenant_id → 400(D1 必填守卫)
- 门店角色(owner/admin/member/customer)**各一次**带 tenant_id → 400(D1-2 防伪造,4 用例)
- 平台角色跨店建设备 customer_id 手填目标店全局 ID → 201(D2-ii);customer_id 填不存在的 → 400
- 平台角色 start walk-in 预约(customer_id=null)→ 200(D3-2 增强 store principal)
- 平台角色 cancel 已 cancelled 预约 → 204 idempotent(状态机契约保留)
- 平台角色 start 已 done 预约 → 400 InvalidTransition(状态机守卫不动)
- 平台角色跨店写不存在的 tenant_id → 400/404(目标店不存在)
- restricted super_admin token(scopes 不含 `devices:create`)跨店 POST → 403(scope gate 在 bypass 前,预期行为)

**反向安全(D6-2,合并进边界场景)**:
- 门店 owner/admin/member/customer × 带 `tenant_id=<他店>` → 400(防伪造跨店写,4 用例,见上)
- `test_hq_platform_role.py` 旧断言处理:`hq_staff POST /customers/profiles/ → 403`(customers 不在范围,**保留**)+ 新增 `hq_staff POST /devices/ {tenant_id} → 201` / `hq_staff POST /bookings/ {tenant_id} → 201`(改写)

**门店回归(D6-3,不动现有章节)**:
- `test_devices_api.py` A-F 章(门店 owner/admin/member 端到端)原样绿
- `test_bookings_api.py` A-F + E1-E3 章原样绿
- 关键回归点:门店 owner 不带 tenant_id → effective = user.tenant_id(行为零变化)

---

## 6. 切片规划(5 切片,tracer-bullet + 鉴权敏感任务按模块/层级切)

> 切片策略:鉴权敏感任务 + 改动 >10 文件 + 跨多模块,按「后端 devices → 后端 bookings CRUD → 后端 bookings 状态机 → 前端 → 联调」5 片切。每片垂直可独立验证(后端片有 API 测试护栏,前端片有 vitest 护栏)。依赖图线性无环。

### 切片 01 — 后端 devices 跨店写 + tenant_id 守卫 + 共享 helper + 测试 ✅ PR 待提交(分支 feat/platform-cross-tenant-write-slice01,2026-07-25)

- **What it delivers**:平台角色(super_admin + hq_staff)可跨店 POST/PUT/DELETE/bind/unbind 设备;引入 `is_platform_writer` helper + **新文件 `_tenant_target.py`(共享 `resolve_target_tenant` 函数)**;`DeviceCreate/Update.tenant_id` 加 optional 字段;门店角色带 tenant_id → 400(防伪造);平台角色不带 → 400(必填)。bind/unbind 也走同套 effective_tenant_id 解析。
- **Blocked by**: 无(frontier,首片可立即开工)
- **文件清单**:
  - `app/services/permission_service.py`(+~6 行:`PLATFORM_WRITER_ROLES` + `is_platform_writer`)
  - `app/schemas/device.py`(+~2 行:`DeviceCreate.tenant_id: str | None = None`,`DeviceUpdate` 同)
  - `app/services/_tenant_target.py`(**新文件**,~25 行:`resolve_target_tenant` 共享纯函数,§4.5.2)
  - `app/services/device_service.py`(+~30 行:`from app.services._tenant_target import resolve_target_tenant`;create/update/delete/bind/unbind 开头调一次解析 + 加 `elif is_platform_writer` 分支)
  - `app/services/permission_service.py`(+~10 行:`PLATFORM_WRITER_ROLES` + `is_platform_writer` helper + `check` 内 platform_writer bypass for devices,见补丁 2)
  - `tests/test_devices_api.py`(+~520 行:新章节「平台角色跨店写」P0-P9 含 bind/unbind + 反向伪造拒 + E 章 hq_staff 旧断言改写 403→400)
  - `app/api/v1/devices.py`(+~10 行:delete/unbind 加 query 参数 `tenant_id: str | None = Query(default=None)`;bind body 已含 tenant_id 透传,见补丁 1)
- **Acceptance criteria**:
  - [x] `is_platform_writer("super_admin")` / `is_platform_writer("hq_staff")` → True;其他 → False(契约测试)— `test_p0_helper_contract`
  - [x] `app/services/_tenant_target.py` 新文件存在,导出 `resolve_target_tenant(user_tenant_id, payload_tenant_id, platform_role)` 纯函数(无 self)
  - [x] `resolve_target_tenant`:平台角色带 tenant_id → 返回该 id;不带 → BizError 400;门店角色带 → BizError 400;门店角色不带 → 返回 user.tenant_id — `test_p0_helper_contract` 4 组合全覆盖
  - [x] `DeviceCreate` / `DeviceUpdate` schema 有 optional `tenant_id` 字段(`DeviceBindRequest` 同步加,见补丁 1)
  - [x] `DeviceService.create/update/delete/bind/unbind` 调用 `resolve_target_tenant(...)` 得到 `effective_tenant_id`,替代直接用 `user.tenant_id`
  - [x] 平台角色 create/update/delete/bind/unbind 路径:skip `require(...)`,直接走业务守卫(model_live / serial_unique / customer_in_tenant,均用 effective_tenant_id)
  - [x] super_admin POST /devices/ {tenant_id, model_id, serial_number} → 201 — `test_p1_platform_writer_create_cross_tenant`
  - [x] hq_staff POST /devices/ {tenant_id, model_id, serial_number} → 201 — `test_p1_platform_writer_create_cross_tenant`
  - [x] super_admin PUT /devices/{id}(目标店设备)→ 200 — `test_p2_platform_writer_update_cross_tenant`
  - [x] super_admin DELETE /devices/{id}(目标店设备)→ 204 — `test_p3_platform_writer_delete_cross_tenant`(DELETE 用 query 透传 tenant_id,见补丁 1)
  - [x] super_admin/hq_staff POST /devices/{id}/customer(bind 目标店设备 + customer_id 目标店全局 ID)→ 200 — `test_p4_platform_writer_bind_cross_tenant`
  - [x] super_admin/hq_staff DELETE /devices/{id}/customer(unbind 目标店设备)→ 204 — `test_p5_platform_writer_unbind_cross_tenant`(DELETE 用 query 透传,见补丁 1)
  - [x] 平台角色 POST /devices/ {tenant_id, customer_id=<目标店 customer 全局 ID>} → 201(D2-ii:customer_in_tenant 守卫用 effective_tenant_id 通过)— `test_p8_platform_writer_create_with_target_customer_201`
  - [x] 平台角色 POST /devices/ {tenant_id, customer_id=<不存在>} → 400(守卫正确拒)— `test_p9_platform_writer_create_with_nonexistent_customer_400`
  - [x] 平台角色 POST 不带 tenant_id → 400(D1 必填守卫)— `test_p6_platform_writer_create_without_tenant_id_400` + E 章 `test_hq_staff_write_without_tenant_id_400`(旧 `test_hq_staff_writes_are_403` 改写,见补丁 4)
  - [x] 门店 owner/admin 带 tenant_id → 400(D1-2 防伪造,service body 守卫)— `test_p7_owner_create_with_tenant_id_400` / `test_p7_admin_create_with_tenant_id_400`;**member/customer 带 tenant_id → 403**(router casbin 拒,与 tenant_id 无关,见补丁 3)— `test_p7_member_create_with_tenant_id_403` / `test_p7_customer_create_with_tenant_id_403`
  - [x] test_devices_api.py A-F 章(门店角色)原样绿 — 43 passed(30 原 + 13 新 P 章节)
  - [x] `./init.sh` 全绿(ruff + pytest)— 727 passed(基线 714 + 13 P 章节,bookings/hq_platform_role 零回归)
- **验证命令**:`./init.sh`(ruff + pytest 全绿,含新平台角色章节 + A-F 回归)

### 切片 02 — 后端 bookings CRUD 跨店写 + 测试 ✅(合并切片 03,PR 待提交 feat/platform-cross-tenant-write-slice02,2026-07-25)

- **What it delivers**:平台角色可跨店 POST 创建 / PUT 更新 / POST cancel 预约;`BookingCreate/Update.tenant_id` 加 optional;复用切片 01 的 `_resolve_target_tenant` + `is_platform_writer`(BookingService 引入同款 helper,或抽到共享模块)。
- **Blocked by**: 切片 01(复用 `is_platform_writer` + `_resolve_target_tenant` 范式)
- **文件清单**(合并切片 03 service body):
  - `app/schemas/booking.py`(+~6 行:`BookingCreate/Update.tenant_id: str | None = None`)
  - `app/services/permission_service.py`(+~6 行:`check` 的 platform_writer bypass 扩展到 `obj in ("devices","bookings")`)
  - `app/services/booking_service.py`(+~100 行:`from app/services/_tenant_target import resolve_target_tenant` + `is_platform_writer` import;**全 6 写动作**(create/update/cancel/start/end/no_show)加 platform_writer 分支 + effective_tenant 贯穿业务守卫)
  - `app/api/v1/bookings.py`(+~12 行:cancel/start/end/no-show 加 query 参数 `tenant_id: str | None = Query(default=None)`;import Query)
  - `tests/test_bookings_api.py`(+~470 行:新 Q 章节 10 用例 + 改 4 个 hq_staff 旧测试断言 403→400)
- **Acceptance criteria**:
  - [x] `BookingCreate` / `BookingUpdate` schema 有 optional `tenant_id` 字段
  - [x] `BookingService.create/update/cancel` 调用 `resolve_target_tenant(...)`(复用切片 01 的共享 helper,不重复定义)— start/end/no_show 也同步加(补丁 5 合并)
  - [x] create:平台角色带 tenant_id + device_id(目标店设备)→ 201;`_assert_device_in_tenant` / `_assert_customer_in_tenant` / `_assert_no_overlap` 用 effective_tenant_id(**create 不调 `_get_live_booking`**,新建无实体)— `test_q1_platform_writer_create_cross_tenant`
  - [x] update:平台角色改目标店预约 → 200;**仅 pending 状态可修改的 BizError 守卫保留**(原 plan-bookings-page-split §D10,与状态机 D3-4 无关,本任务不碰)— `test_q2_platform_writer_update_cross_tenant`
  - [x] cancel:平台角色取消目标店预约 → 204;idempotent 早退(已 cancelled)保留;非 pending → 400 保留 — `test_q3_platform_writer_cancel_cross_tenant`
  - [x] **cancel 现有 require/get_live_booking 顺序不动**(现状「先 require 后 get」;本切片只夹 elif 分支让平台角色 bypass require,**不借机对齐** start/end/no_show 的「先 get 后 require」顺序 —— 对齐是 `booking-action-order-unify` 独立 feature 的事,见 §8 Out of Scope)— 代码核对 cancel 仍是 resolve→require→get 顺序
  - [x] super_admin/hq_staff × create/update/cancel 全绿(6 用例)— `test_q1`/`q2`/`q3` 各含 super_admin + hq_staff
  - [x] 平台角色 POST 不带 tenant_id → 400;门店角色带 → 400 — F/HQ4 改写 + `test_q9_owner_create_with_tenant_id_400`;member 在状态动作上是 400(无 router dep,anti-forgery 先触发,`test_q9_member_state_action_with_tenant_id_400`)
  - [x] test_bookings_api.py A-F + E1-E3 章原样绿 — 90 passed(76 原 + 10 Q 章节 + 4 个 hq_staff 旧测试改写)
  - [x] `./init.sh` 全绿 — 737 passed(基线 727 + 10 Q 章节)
- **验证命令**:`./init.sh`

### 切片 03 — 后端 bookings 状态机 3 守卫(start/end/no_show)重写 + 测试 ✅ **已并入切片 02**(见 §4.5.4a 补丁 5:check bypass 按 obj 作用域,update/delete act 被 CRUD 与状态机共用,无法用 act 白名单拆分;且若只改 CRUD 不改状态机会导致 hq_staff 带 tenant_id 调 start/end/no_show 静默写错店。切片 02 一次性改 6 写动作 + Q4-Q8 覆盖状态机测试)

- **What it delivers**:start/end/no_show 3 个状态机动作加 platform_writer 分支(cancel 已在切片 02 落地);start 平台角色 = 增强 store principal(可开 walk-in);end/no_show 平台角色 bypass owner-only require。**状态机 `_TRANSITIONS` 表不动**(D3-4)。
- **Blocked by**: 切片 02(复用切片 02 落地的 `resolve_target_tenant` import + `is_platform_writer`)
- **文件清单**:
  - `app/services/booking_service.py`(+~25 行:start/end/no_show 加 `elif is_platform_writer` 分支)
  - `tests/test_bookings_api.py`(+~70 行:新章节「平台角色状态机 3 守卫」+ walk-in start 边界)
- **Acceptance criteria**(全部由切片 02 落地,见 §4.5.4a 补丁 5):
  - [x] `booking_state._TRANSITIONS` / `ACTIONS` / `transition()` 函数体零改动(D3-4)— 切片 02 未碰 booking_state.py
  - [x] `start`:平台角色走 elif 分支,skip require,可开 walk-in(booking.customer_id None 不报错);不进 customer ownership 分支 — `test_q4_platform_writer_start_cross_tenant` + `test_q5_platform_writer_start_walkin_cross_tenant`
  - [x] `end`:平台角色 bypass `require("bookings","delete")`(owner-only);走状态机 `in_service→done` — `test_q6_platform_writer_end_cross_tenant`
  - [x] `no_show`:同 end;走 `pending|confirmed|in_service→no_show` — `test_q7_platform_writer_no_show_cross_tenant`
  - [x] `cancel`:平台角色 bypass require(切片 02 已加);状态机契约保留(已 cancelled→204,非 pending→400)— `test_q3`
  - [x] super_admin/hq_staff × start/end/no_show 全绿(6 用例 + cancel 在切片 02)— `test_q4`/`q6`/`q7` 各含 super_admin + hq_staff
  - [x] 平台角色 start walk-in 预约 → 200(D3-2 边界)— `test_q5_platform_writer_start_walkin_cross_tenant`
  - [x] 平台角色 start 已 done 预约 → 400 InvalidTransition(状态机守卫不动)— `test_q8_platform_writer_state_machine_guards_preserved`
  - [x] 平台角色 end 非 in_service 预约 → 400 InvalidTransition — `test_q8`
  - [x] test_bookings_api.py A-F + E1-E3 章原样绿 — 90 passed
  - [x] `./init.sh` 全绿 — 737 passed
- **验证命令**:`./init.sh`

### 切片 04 — 前端 HqView target tenant 下拉 + 写按钮 + 复用 Dialog ✅ PR 待提交(分支 feat/platform-cross-tenant-write-slice02,commit dc880b3,2026-07-25)

- **What it delivers**:devices-page 和 bookings/hq-view 两个 HqView 加「目标门店」下拉(拉 `fetchAllTenants`)+ 行内写动作(devices:编辑/删除;bookings:DropdownMenu 三点菜单按 status 显隐取消/开机/结束/爽约);StoreView 的 Dialog 抽出为共享组件(参数化 `tenantId`),HqView 复用。API 类型 + endpoints + hooks 同步加 `tenant_id` 参数。
- **Blocked by**: 切片 01+02(只需后端 API 契约稳定:devices/bookings 的 schema 加了 `tenant_id` + CRUD 写动作就位。**切片 03 的状态机 API(start/end/no_show)早已存在,前端调用路径不变**,故 04 不必等 03 —— 04 可与 03 并行,缩短关键路径)
- **文件清单**:
  - `frontend/src/api/types.ts`(+~4 行:DeviceCreate/BookingCreate/Update 加 `tenant_id?: string`)
  - `frontend/src/api/endpoints.ts`(+~0 行:写动作 mut 透传 tenant_id,在 payload 里)
  - `frontend/src/hooks/queries.ts`(+~0 行:useDevices/useBookings 写 mut 类型同步)
  - `frontend/src/pages/devices-page.tsx`(+~60 行:HqView 加 target 下拉 + 行内编辑/删除按钮 + 接共享 Dialog)
  - `frontend/src/pages/bookings/hq-view.tsx`(+~80 行:HqView 加 target 下拉 + 行内 DropdownMenu + 接共享 Dialog)
  - `frontend/src/pages/bookings/store-view.tsx`(重构:Dialog 抽出到 `frontend/src/pages/bookings/shared-dialog.tsx`,接受 `tenantId` prop)
  - `frontend/src/pages/bookings/shared-dialog.tsx`(**新文件**,~100 行,从 store-view 抽出)
  - 前端测试:`frontend/src/pages/bookings/__tests__/hq-view.test.tsx`(+平台角色写控件渲染 + DropdownMenu 显隐)+ `store-view.test.tsx` 原断言保留(回归护栏)
- **Acceptance criteria**:
  - [x] `DeviceCreate` / `BookingCreate` / `Update` TS 类型有 optional `tenant_id?: string` — `frontend/src/api/types.ts`(DeviceCreate/Update + BookingCreate/Update + DeviceBindRequest 均加 optional tenant_id)
  - [x] 写动作 mut(`createDevice`/`updateDevice`/`deleteDevice`/`bindDeviceCustomer`/`unbindDeviceCustomer` + `createBooking`/`updateBooking`/`cancelBooking`/`startBooking`/`endBooking`/`noShowBooking`)payload 透传 `tenant_id` — `frontend/src/api/endpoints.ts`(create/update/bind 走 body;delete/unbind/cancel/start/end/no_show 走 ?tenant_id= query,plan §4.5.4a 补丁 1+5)+ `queries.ts`(6 个 id-only hook 加 tenantId 闭包参数)
  - [x] HqView(devices + bookings)顶部渲染「目标门店」下拉,选项来自 `fetchAllTenants` — `devices-page.tsx` HqView + `bookings/hq-view.tsx` 都用 `useAllTenants()`
  - [x] 选定 target 后,行内出现写动作控件(devices:编辑/删除/绑定;bookings:DropdownMenu)— `canWrite = !!targetTenantId` 守卫操作列 + 创建按钮
  - [x] bookings HqView DropdownMenu 按 status 显隐:pending→取消/开机;in_service→结束/爽约;其他→无 — 复用 `BookingRowMenu`(MUTABLE_STATUS + ACTIONABLE_STATUS);`hq-view.test.tsx` AC5 in_service + 终态两用例覆盖
  - [x] 点击写动作打开共享 Dialog(从 store-view 抽出),提交时 payload 带 `tenant_id = selectedTarget` — `bookings/shared-dialog.tsx`(新文件,5 Dialog + BookingRowMenu)+ `devices-page.tsx` 内抽 4 个 Device Dialog 模块级组件
  - [x] **HqView 切 target 后 React Query cache key 含 target**(避免切换后显示错店数据,见 §9 风险表);或调 `invalidateQueries` 强刷 — `onTargetChange` 调 `qc.invalidateQueries({ queryKey: qk.bookings / qk.devices })`(列表数据其实不变,作保险)
  - [x] **StoreView 现有 vitest 测试(`store-view.test.tsx`)全绿**(门店角色路径不带 tenant_id,Dialog 共享组件 tenantId 默认 undefined → 后端用 user.tenant_id;用现有测试当回归护栏,而非模糊的「行为零变化」)— `store-view.test.tsx` 6/6 全绿(回归护栏,关键证据:闭包模式让 store caller 调用形态零变化 → 测试断言零修改)
  - [x] 平台角色未选 target 时写按钮 disabled / 隐藏 — `canWrite = !!targetTenantId` 守卫;`hq-view.test.tsx` AC9 用例断言"未选 target 时无操作列 + 无创建预约按钮 + 无菜单项"
  - [x] vitest 全绿(含 hq-view.test.tsx 新断言 + store-view.test.tsx 回归)— 27/27(8 hq-view 含 5 新写控件 + 6 store-view 回归 + 6 my-bookings + 7 key-spec-rows)
  - [x] `cd frontend && npm run build` 通过 — tsc -b + vite build 全绿(bookings-page 22.55 kB / devices-page 15.06 kB,oxlint 0 warnings)
- **验证命令**:`cd frontend && npm test && npm run build` ✅ 全绿

### 切片 05 — 端到端联调 + 旧断言改写 + 收尾

- **What it delivers**:`test_hq_platform_role.py` 旧断言改写(hq_staff 写 customers 仍 403,但写 devices/bookings 带 tenant_id → 201/200);端到端联调跑 `./init.sh` 全绿;feature_list.json status → passing(本任务 EP3 实施完成后由 EP3 收尾,本 EP2 回环只产 plan,不实施)。
- **Blocked by**: 切片 01+02+03+04
- **文件清单**:
  - `tests/test_hq_platform_role.py`(+~40 行:hq_staff devices/bookings 写正向 + 保留 customers 写 403)
  - (无新源码,纯联调 + 测试补全)
- **Acceptance criteria**:
  - [ ] `test_hq_platform_role.py`:hq_staff POST /devices/ {tenant_id} → 201(新)
  - [ ] `test_hq_platform_role.py`:hq_staff POST /bookings/ {tenant_id} → 201(新)
  - [ ] `test_hq_platform_role.py`:hq_staff POST /customers/profiles/ → 403(保留,customers 不在范围)
  - [ ] `test_hq_platform_role.py`:hq_staff POST /groups/ → 403(保留,require_super_admin 不动)
  - [ ] `./init.sh` 全绿(ruff + pytest 全量)
  - [ ] `cd frontend && npm test && npm run build` 全绿
  - [ ] **文档影响评估**完成(具体清单,非悬空):① `feature_list.json` status → passing + evidence 填验证证据 + sync-active 刷新;② `progress.md` 顶部「最高优先级未完成功能」更新;③ 若新增了 `is_platform_writer` helper,检查 `项目指南/02-后端架构/06-权限模型RBAC.md` 是否需补「平台角色写权限」说明(本任务预期**不需要** —— helper 与 `is_cross_tenant_viewer` 同范式,文档已有覆盖);④ `harness/docs/plan-platform-cross-tenant-write.md` 状态从 draft v1 → passing。**不动 README**(平台角色写权限是内部鉴权细节,非用户文档范畴)
- **验证命令**:`./init.sh && cd frontend && npm test && npm run build`

---

## 7. 切片依赖图(无环验证)

```
切片 01 (devices 后端) ──→ 切片 02 (bookings CRUD 后端) ──┬→ 切片 03 (bookings 状态机后端) ──┐
                                                          │                                  │
                                                          └→ 切片 04 (前端,可与 03 并行) ───┴→ 切片 05 (联调收尾)
```

- **线性无环**:01 → 02 → {03, 04 并行} → 05
- **切片 04 依赖 01+02**(非 01-03):前端只需后端 API 契约稳定(devices/bookings schema 加了 `tenant_id` + CRUD 写就位);切片 03 改的是 service 内部分支,API 路径/schema 不变,故 04 可与 03 并行,缩短关键路径
- **首片 frontier**:切片 01 `Blocked by: 无`,可立即开工
- **每片垂直可验证**:后端片有 pytest 护栏,前端片有 vitest + build 护栏

---

## 8. Out of Scope(不做,避免越界)

- **不动 customers 模块**:customers 的 HqView 仍是只读;平台角色跨店建/绑设备时 `customer_id` 手填或留空(D2-ii);customers 后端 API 不加 `tenant_id` 参数。
- **不动 groups / device_models / 其他模块**:仅 devices + bookings 两个模块解锁写。
- **不动状态机 `_TRANSITIONS` 表**:平台角色只是新加鉴权路径,状态跳转规则零改动(D3-4)。
- **不动 DEFAULT_*_PERMS / Role.data_scope / casbin policy / require_permission caller**:权限基础设施零改动(D4)。
- **不动 router 前缀 / URL 契约**:`tenant_id` 走 body 字段,不走 URL 子资源(D1)。
- **不引「临时 owner」概念**:平台角色 bypass require,不伪装成 owner(D3-3)。
- **不重写 test_bookings_api / test_devices_api 现有 A-F 章节**:门店契约不动,测试镜像也不动(D6-3);只加新章节。
- **不做 `customer_id` 跨店选择器 UX**:平台角色看不到目标店客户列表(D2-ii 代价);若后续要做,需独立 feature 扩 customers 后端 + 前端 hook。
- **不抽 `booking-action-order-unify`**:与 `booking-state-cancel` plan 的 Out of Scope 一致,cancel 的 require/get_live_booking 顺序不对齐债留独立 feature。
- **不做「hq_staff 仅 super_admin 可写」分化**:`is_platform_writer` 边界与 `is_cross_tenant_viewer` 同;若未来要分化,改 `PLATFORM_WRITER_ROLES` 一处即可(预留扩展点)。

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 门店角色伪造 `body.tenant_id` 跨店写(硬约束 #5) | 🔴 高 | D1-2 守卫:门店角色带 tenant_id → 400 BizError;D6-2 反向测试覆盖(owner/admin/member/customer × 带 tenant_id → 400) |
| `effective_tenant_id` 解析漏点(某写动作忘改) | 🟡 中 | `resolve_target_tenant` 抽共享 helper(`_tenant_target.py`),所有写动作强制走它;切片 01/02/03 AC 逐动作 checklist |
| 平台用户 `user.tenant_id` 残留导致 `_get_live_*` 误用 | 🟡 中 | service body 全部用 `effective_tenant_id`,**不直接读 `user.tenant_id`**;code review 双轴(Standards + Spec)查 |
| 前端 StoreView Dialog 抽共享组件破坏门店视角 | 🟡 中 | 共享组件 `tenantId` 默认 undefined → 后端 effective = user.tenant_id(门店角色路径);切片 04 AC 锁定 `store-view.test.tsx` 全绿当回归护栏 |
| 旧测试断言 `hq_staff 写 → 403` 漏改导致 CI 红 | 🟢 低 | 切片 05 显式清单 `test_hq_platform_role.py` 改写点;CI 红即暴露,无隐藏风险 |
| `is_platform_writer` 与 `is_cross_tenant_viewer` 边界漂移 | 🟢 低 | 两者注释互引;若分化需同步评估 read/write 一致性;预留扩展点(改常量一处) |
| restricted super_admin/hq_staff token 跨店写受 scopes 约束 | 🟡 中 | 预期行为(scope gate 在 platform bypass 之前,见 §4.3):restricted token 即便平台角色也受 scopes 限。§5 边界场景加测试 `restricted super_admin token (scopes 不含 devices:create) 跨店 POST → 403` 锁定 |
| casbin enforcer 缓存导致 `is_platform_writer` 新 helper 失效 | 🟢 低 | **已排除**:`permission_service.check` 每次 `get_enforcer()` 新建(无缓存),`is_platform_writer` 是纯函数无状态。无需缓解,列此行说明已确认 |
| 前端 HqView 切 target 后 React Query cache 显示错店数据 | 🟡 中 | 切片 04 AC:cache key 含 target tenant,或切 target 时 `invalidateQueries` 强刷;vitest 测试覆盖「切 target → 列表刷新」 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `is_platform_writer` helper 存在,边界 = `{super_admin, hq_staff}`,契约测试绿
2. `app/services/_tenant_target.py` 新文件存在,导出 `resolve_target_tenant` 共享纯函数
3. `DeviceCreate/Update` + `BookingCreate/Update` schema 有 optional `tenant_id` 字段
4. `DeviceService` + `BookingService` 所有写动作用 `resolve_target_tenant`(共享 helper)解析 effective_tenant_id,不直接读 `user.tenant_id`
5. devices POST/PUT/DELETE/bind/unbind + bookings POST/PUT/cancel/start/end/no_show 共 **11 个写动作**,平台角色(super_admin + hq_staff)跨店正向全绿(**22 用例** + 边界 6-10)
6. 门店角色(owner/admin/member/customer)带 `body.tenant_id` → 400(防伪造,**4 用例**,每角色一次)
7. 门店角色不带 `tenant_id` → 行为零变化(test_devices_api / test_bookings_api A-F + E1-E3 原样绿)
8. 状态机 `_TRANSITIONS` 表 / ACTIONS / `transition()` 函数体零改动
9. DataScope / Role.data_scope / DEFAULT_*_PERMS / casbin policy / `require_permission` caller 列表 零改动
10. **router 文件零改动**(`app/api/v1/devices.py` + `bookings.py` 签名/路径/方法/dependencies 全不变,§4.5.4)
11. 前端 HqView(devices + bookings)有 target tenant 下拉 + 行内写动作,复用 StoreView Dialog(共享组件参数化 tenantId);`store-view.test.tsx` 原断言全绿(回归护栏);切 target 时 React Query cache 正确刷新
12. `./init.sh` 全绿(ruff + pytest 全量)
13. `cd frontend && npm test && npm run build` 全绿(含 `store-view.test.tsx` 回归)
14. 文档影响评估完成(具体清单见切片 05 AC:feature_list.json status + progress.md + plan 状态 + 检查 RBAC 文档是否需补;不动 README)

---

## 11. 不越界声明

本次改动**只**涉及:
- 后端:`app/services/permission_service.py`(加 helper)、`app/schemas/{device,booking}.py`(加 optional tenant_id)、`app/services/_tenant_target.py`(**新文件** 共享 helper)、`app/services/{device,booking}_service.py`(写动作加 platform_writer 分支)
- 前端:`frontend/src/api/types.ts`、`frontend/src/api/endpoints.ts`、`frontend/src/hooks/queries.ts`、`frontend/src/pages/devices-page.tsx`、`frontend/src/pages/bookings/{hq-view,store-view,shared-dialog}.tsx`(shared-dialog.tsx 为**新文件**)
- 测试:`tests/test_{devices,bookings,hq_platform_role}_api.py`(加章节 + 改旧断言)

**不**触碰:
- customers / groups / device_models /其他业务模块
- 状态机 `booking_state.py` 的 `_TRANSITIONS` / ACTIONS / `transition()` 函数体
- 权限基础设施(DEFAULT_*_PERMS / Role.data_scope / casbin policy / `require_permission` caller)
- **router 文件**(`app/api/v1/devices.py` + `bookings.py` **路径/方法/dependencies/响应 schema 全不变**;DELETE/unbind 加 `tenant_id` query 参数是切片 01 必要补丁,见 §4.5.4a 补丁 1 —— DELETE 无 body,query 是唯一 RESTful 透传方式。OpenAPI 路径契约不变,只是加可选 query 参数)
- router URL 前缀 / OpenAPI 路径契约
- 数据库 schema / 迁移链
- API token scope gate 逻辑(restricted token 仍按 scopes 限流,平台角色 bypass 在 scope gate 之后,§4.3)
- `booking-action-order-unify`(cancel 的 require/get_live_booking 顺序对齐债,独立 feature —— 切片 02 改 cancel 时**只夹 elif 分支,不借机对齐顺序**)
