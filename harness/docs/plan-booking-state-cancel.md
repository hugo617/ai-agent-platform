# 计划:cancel 动作并入 booking 状态机

> **id**: booking-state-cancel
> **状态**: passing(EP3 切片 01 已合并,2026-07-25)
> **优先级**: 68(原 67,2026-07-25 Session 144 因新任务 platform-cross-tenant-write 优先级更高而让位到 68,「工程化」area,巡检候选 2 收尾债)
> **创建日期**: 2026-07-25
> **来源**: [codebase-health-log.md](./codebase-health-log.md) 2026-07-25 巡检 · 候选 2(Strong,后端 deep module 收尾债)

---

## 1. Problem Statement

`booking_state.transition()` 是 device-poweron 切片 01 建立的「booking 生命周期单一真相源」—— 一个纯函数 `_TRANSITIONS` 表管 `start`/`end`/`no_show` 三动作 6 条边,service 层只调 `transition(current, action)` 一行,不内联 `if status == ...`。

但 `cancel` 动作(device-booking 时期写的,**早于** 状态机抽象)没并进来:`BookingService.cancel()` 内联了完整的状态判断(line 504-510):

```python
if booking.status == "cancelled":
    return True                                    # idempotent 早退
if booking.status != "pending":
    raise BizError("仅 pending 状态的预约可取消,当前状态: {status}")  # 400
booking.status = "cancelled"                        # flip
```

**状态图被劈两半**:状态机的 6 条边在 `booking_state.py`,cancel 的 6 个状态分支(5 拒 + 1 翻)在 `booking_service.py`。新人改状态要翻两个文件,且 cancel 的错误用 `BizError`(通用),而其他三动作用 `InvalidTransition`(状态机专用),错误语言不统一。

friction:
- **single source of truth 缺失**:状态图分两处,cancel 不走 `transition()`。
- **错误语言不一致**:cancel 用 `BizError("仅 pending…")`,start/end/no_show 用 `InvalidTransition("非法状态跳转…")`。
- 这是 [codebase-health-log.md](./codebase-health-log.md) 2026-07-25 巡检识别的 **Strong** friction 点(deletion test:把 cancel 判断搬进状态机后,booking_service 反而更瘦,无抽象成本)。

> **溯源**:cancel 在 device-booking feature 时期建立,**早于** device-poweron 切片 01 的状态机抽象。切片 01 建状态机时为了 narrow-scope,故意没并 cancel(其 `end` 方法注释明确写:"cancel in device-booking uses the opposite order; this slice does NOT change it — narrow-scope, leave cancel alone")。本任务就是这个债的收尾。

## 2. Solution

把 cancel 动作的**状态跳转**部分并入 `booking_state._TRANSITIONS` 表:加 `("pending","cancel"):"cancelled"` 一条边,`ACTIONS` 加 `"cancel"`。`BookingService.cancel()` 中间 5 行 if/elif/else 塌缩为「1 行 idempotent 早退 + 1 行 `transition()` 调用」。**零行为变更**(状态码 / API 契约 / idempotency 全保留),唯一的文字变化是错误消息从 `BizError("仅 pending…")` 升级为 `InvalidTransition("非法状态跳转…")`(状态码仍 400,异常类更精确,与 start/end/no_show 统一错误语言)。

## 3. User Stories

- 作为**后端开发者**,我想 booking 的所有状态跳转都在 `booking_state.py` 一个文件里看到,以便改状态机时不用翻 `booking_service.py` 找散落的 `if status ==`。
- 作为**新人 onboarding 者**,我想 cancel 的非法跳转报 `InvalidTransition`(和 start/end/no_show 一样),以便错误日志/排查用同一套状态机词汇。
- 作为**巡检 follow-up 执行者**,我想这次 cancel 并表独立可提交,以便候选 7(submitEnd JSON.parse 搬 endpoint)/候选 8(union cast 拆双 hook)各自独立切片不被混淆。

---

## 4. Implementation Decisions

### 4.0 grill 共识(D1-D6,本 plan 决策真相源)

| # | 决策 | 锁定值 |
|---|---|---|
| **D1** | cancel 边进状态表的形态 | **B**:只 `("pending","cancel"):"cancelled"` 进 `_TRANSITIONS`;service 层保留「已 cancelled 早退」一行;纯函数不污染(不引入自环/NOOP 标记/多态返回) |
| **D2** | idempotent 早退位置 | `require` 后 + `_get_live_booking` 后(唯一可行位置:不取数拿不到 status,不能挪到 require 前否则破坏权限契约) |
| **D3** | require/get_live_booking 顺序对齐 | **不对齐**。cancel 保持现状 `require → _get_live_booking` 顺序(守硬约束 1 字面零行为变更)。切片 01 的 start/end/no_show 是 `get_live_booking → require`(跨租户统一 404),cancel 与之顺序不同,但切片 01 注释已解释此差异。**顺序对齐债留给独立 feature**(若做会让 member 跨租户 cancel 从 403→404,属行为变更,超出本任务范围) |
| **D4** | 错误消息变化 | 接受。`confirmed`/`in_service`/`done`/`no_show` 态 cancel 的错误从 `BizError("仅 pending 状态的预约可取消,当前状态: X")` → `InvalidTransition("非法状态跳转:当前状态「X」不能执行动作「cancel」")`。**状态码 400 不变**,异常类升级为更精确的 `InvalidTransition` 子类(与 start/end/no_show 统一)。无任何 caller 依赖原消息文本(已全仓核实) |
| **D5** | 测试增量 | `test_booking_state.py`:改 3 数字常量(6→7 合法边 / 12→17 非法对)+ 改 2 函数名(`..._is_six`→`..._is_seven`,`..._is_twelve`→`..._is_seventeen`)+ 加 1 命名测试 `test_cancel_only_from_pending`(parametrize 5 个非 pending 态 × cancel 断言 InvalidTransition)+ 1 段双层语义注释(cancelled×cancel 在纯函数层是 illegal 但 service 层早退 204)。`test_bookings_api.py` E1/E2/E3 不回归(零行为变更),不加 service 层 idempotency 单测(E3 API 层已覆盖) |
| **D6** | 切片粒度 | **单切片**。原子性(状态机加边 + service 消费 + 测试同步必须同一次 commit,否则中间态让测试红)+ 改动量 < 50 行 + 无跨层依赖 + 无设计决策留待切片期(D1-D5 已全落定) |

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 2 | `app/services/booking_state.py`(ACTIONS + _TRANSITIONS + docstring)、`app/services/booking_service.py`(`cancel()` 中间段塌缩) |
| 数据库迁移 | 0 | — |
| 前端文件改动 | 0 | 纯后端 |
| 新增测试类 | 0(改现有) | `tests/test_booking_state.py`(改常量 + 加命名测试) |
| API 契约改动 | 0 | POST /bookings/{id}/cancel 返回值/状态码不变(204 + idempotent + 400 不变) |
| 错误消息改动 | 1 | 仅 cancel 的非 pending 非 cancelled 态错误消息文字变更(D4,状态码不变) |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(cancel 仍走 `_get_live_booking` 租户隔离 + `require("bookings","delete")`,D3 不对齐顺序,跨租户行为零变更)
- 验证:`test_b_cross_tenant_get_put_cancel_returns_404`(owner 跨租户 cancel → 404)原样绿

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 `require_permission` caller? **NO**(cancel 仍用 `bookings:delete`,不动)
- 验证:`test_a_admin_can_create_update_but_not_cancel`(admin 无 delete → cancel 403)、`test_f_member_read_only`(member → 403)原样绿

### 4.4 数据库表设计 checklist

**N/A** —— 无数据库改动,无 schema 变化,迁移链 head 不变。

### 4.5 其他实施决策

#### cancel 并表后的目标形态(`booking_state.py`)

```python
ACTIONS: frozenset[str] = frozenset({"start", "end", "no_show", "cancel"})

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("pending", "start"): "in_service",
    ("confirmed", "start"): "in_service",
    ("in_service", "end"): "done",
    ("pending", "no_show"): "no_show",
    ("confirmed", "no_show"): "no_show",
    ("in_service", "no_show"): "no_show",
    # cancel: a pending booking is abandoned before service. Idempotency
    # (already-cancelled → 204 no-op) is a SERVICE-layer contract, NOT a
    # state-machine edge — transition("cancelled","cancel") still raises
    # InvalidTransition like every other terminal-state action; the service
    # early-returns before calling transition() when it sees status=="cancelled".
    ("pending", "cancel"): "cancelled",
}
```

`transition()` 函数体**不变**(还是 `try: return _TRANSITIONS[...] except KeyError: raise InvalidTransition`)。边数从 6 → 7,动作数从 3 → 4,但函数逻辑零改动 —— 这正是状态机抽象的价值(加边不动函数)。

#### cancel 并表后的目标形态(`booking_service.cancel()`)

```python
async def cancel(self, actor_id, tenant_id, booking_id, platform_role=None) -> bool:
    await permission_service.require(actor_id, tenant_id, "bookings", "delete", ...)
    booking = await self._get_live_booking(booking_id, tenant_id)
    if booking.status == "cancelled":
        return True                                    # idempotent 早退(D1/D2:service 层契约,不进状态机)
    booking.status = transition(booking.status, "cancel")  # pending→cancelled;其他态自动 InvalidTransition→400
    await self.db.flush()
    await self.db.commit()
    return False
```

中间 5 行 `if/elif/else + raise BizError + 直接赋值` → 塌缩为 **2 行**(早退 + transition)。`confirmed`/`in_service`/`done`/`no_show` 态由 `transition()` 表查不到 → 自动 `InvalidTransition → 400`(D4 消息变化)。

#### 双层语义自洽性(D1 的关键论证)

`(cancelled, cancel)` 在两层有不同表现,自洽:
- **状态机层(纯函数)**:`transition("cancelled","cancel")` → `InvalidTransition`(cancelled 是 terminal,拒所有动作,与其他 terminal 态一致)
- **service 层**:cancel 已 cancelled booking → 早退 return True(不调状态机)→ endpoint 返回 204(idempotent)

这两层不冲突:service 层的 idempotent 早退**保证** `transition("cancelled","cancel")` 永远不会被调用。纯函数保持「terminal 拒所有」的对称性,service 层独自承担 HTTP idempotency 契约。`test_booking_state.py` 的 `_illegal_pairs()` 笛卡尔积会自动把 `(cancelled,cancel)` 列为非法对(断言 InvalidTransition),这是**纯函数层**的正确预期,与 service 层早退不矛盾 —— 测试文件顶部注释会显式说明这个双层语义。

---

## 5. Testing Decisions

- 测试金字塔:**unit 为主**(test_booking_state.py 纯函数毫秒级)+ **integration 回归**(test_bookings_api.py E1/E2/E3 不回归)
- 测试用 SQLite 内存库(`./init.sh` 路径),不涉及 PG 专有类型
- 覆盖率目标:不降基线(本任务改动小,纯函数测试覆盖反而因笛卡尔积自动扩展而提升)
- 边界 case 清单(纯函数层):
  - `("pending","cancel")` → `"cancelled"`(新合法边)
  - `(cancelled, cancel)` → InvalidTransition(纯函数层,与 service 早退不矛盾)
  - `(done, cancel)` / `(no_show, cancel)` / `(in_service, cancel)` / `(confirmed, cancel)` → InvalidTransition(笛卡尔积自动覆盖 + 命名测试显式锁定)
- API 层回归(E1/E2/E3,零行为变更):
  - E1 pending → cancel → 204,GET shows cancelled
  - E2 cancelled → PUT reschedule → 400(D10 terminal)
  - E3 cancelled → cancel again → 204(idempotent no-op)

---

## 6. 切片规划(单切片,tracer-bullet)

### 切片 01 — cancel 边并入 booking 状态机 ✅ PR #127 commit a6baa6f(分支 feat/booking-state-cancel-slice01,2026-07-25)

- **What it delivers**:cancel 动作的状态跳转从 `booking_service.cancel()` 内联判断搬到 `booking_state._TRANSITIONS` 表。改后:① `booking_state.py` 的 ACTIONS 加 `"cancel"`,_TRANSITIONS 加 `("pending","cancel"):"cancelled"` 一条边;② `booking_service.cancel()` 中间 5 行 if/elif/else 塌缩为「1 行 idempotent 早退 + 1 行 `transition()` 调用」;③ `test_booking_state.py` 同步:合法边 6→7、非法对 12→17、加命名测试 `test_cancel_only_from_pending`、加双层语义注释。行为零变更(cancel 已 cancelled → 204 早退保留;非 pending 非 cancelled → 400,异常类从 BizError 升级为 InvalidTransition,消息文字变化但状态码不变)。
- **Blocked by**: 无(frontier,首片可立即开工)
- **文件清单**(估算 < 50 行改动):
  - `app/services/booking_state.py`(+~6 行:ACTIONS 加 cancel + _TRANSITIONS 加 1 边 + 注释)
  - `app/services/booking_service.py`(-5/+2 行:cancel 中间段塌缩)
  - `tests/test_booking_state.py`(+~20 行:改 3 常量 + 改 2 函数名 + 加 1 命名测试 + 注释)
- **Acceptance criteria**:
  - [x] `ACTIONS` frozenset 含 `"cancel"`(4 元素)
  - [x] `_TRANSITIONS` 含 `("pending","cancel"):"cancelled"`(7 条边)
  - [x] `transition("pending","cancel")` 返回 `"cancelled"`
  - [x] `transition()` 函数体未改(仍是 try/except KeyError → InvalidTransition)
  - [x] `BookingService.cancel()` 中间段无 `if booking.status != "pending"` 内联判断,改为 `booking.status = transition(booking.status, "cancel")`
  - [x] `BookingService.cancel()` 保留 `if booking.status == "cancelled": return True` idempotent 早退(D1/D2)
  - [x] `BookingService.cancel()` 的 `require` → `_get_live_booking` 顺序未变(D3 不对齐)
  - [x] `test_booking_state.py`:`_LEGAL_EDGES` 含 `("pending","cancel"):"cancelled"`
  - [x] `test_booking_state.py`:`test_legal_edges_count_*` 断言 == 7(原 6)
  - [x] `test_booking_state.py`:`test_illegal_pairs_count_*` 断言 == 17(原 12,6×4−7)
  - [x] `test_booking_state.py`:新增 `test_cancel_only_from_pending` parametrize(done/cancelled/no_show/in_service/confirmed × cancel → InvalidTransition)
  - [x] `test_booking_state.py`:顶部或新增测试旁有注释说明 `(cancelled,cancel)` 纯函数层 illegal vs service 层早退 204 的双层语义
  - [x] `test_bookings_api.py` E1/E2/E3 原样绿(零行为变更)
  - [x] `test_bookings_api.py` B(跨租户 cancel 404)/ A-admin(admin cancel 403)/ F(member cancel 403)原样绿
  - [x] `./init.sh` 全绿(ruff + pytest,含 test_booking_state + test_bookings_api)
  - [x] 无新 TODO/FIXME,无 schema/迁移/API 契约变化
- **验证命令**:`./init.sh`(ruff + pytest 全绿,含 test_booking_state.py 17 非法 + 7 合法 + 命名测试 + test_bookings_api.py A-F + E1/E2/E3 回归)

---

## 7. Out of Scope(不做,避免越界)

- **不对齐 cancel 的 require/get_live_booking 顺序**(D3):切片 01 的 start/end/no_show 是 get_live_booking 先(跨租户统一 404),cancel 是 require 先。对齐会让 member 跨租户 cancel 从 403→404,属行为变更,留给独立 feature `booking-action-order-unify`。
- **不碰 update 的 pending 守卫(D10)**:`update()` 的 `if booking.status not in _MUTABLE_STATUSES: raise BizError` 保持原样(硬约束 2)。
- **不动 API 契约**:POST /bookings/{id}/cancel 的返回值(204)、状态码、idempotency 全保留(硬约束 3)。
- **不碰前端**(硬约束 4,纯后端任务)。
- **不补 service 层 idempotency 单测**(D5):E3 API 层已覆盖 idempotency,service 层早退是实现细节,加单测是冗余。
- **不动 `cancel()` 的 docstring 核心语义**(idempotent / 非 pending 拒绝),仅同步描述「现在走 transition()」。

---

## 8. plan 自检(EP2 §3.6 进 EP3 前的轻量 gate)

- [x] **切片依赖图无环**:单切片,Blocked by 无,无环
- [x] **每片有 acceptance criteria**:切片 01 含 16 条 `- [ ]` 可执行检查(文件级 + 行为级)
- [x] **首片可立即开工**:切片 01 `Blocked by: 无`,是 frontier
- [x] **plan 主体决策已落定**:§4.0 grill 共识 D1-D6 全锁定,§4 实施决策无 TODO/待定悬空项
