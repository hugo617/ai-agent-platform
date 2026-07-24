# 计划:bookings-page 按视图拆 module

> **id**: bookings-page-split
> **状态**: passing(Session 139 实施完成,vitest 15/15 + build + oxlint + tsc + init.sh 全绿;/code-review 双轴通过 + 处置 1 spec 内部冲突 + 订正文字瑕疵)
> **优先级**: 65(新登记,「工程化」area,巡检产出)
> **创建日期**: 2026-07-25
> **来源**: [codebase-health-log.md](./codebase-health-log.md) 2026-07-25 巡检 · 候选 1(Strong)

---

## 1. Problem Statement

`frontend/src/pages/bookings-page.tsx` **1373 行**,内含 3 个完整视图(`StoreView` 683 行 / `HqView` 106 行 / `MyBookingsView` 103 行)+ 4 个 Dialog + 8 个本地 helper + `ScheduleGridCard` —— 比 `settings-page`(1188)还大,是前端最大 fat file。

friction:
- **locality 缺失**:改一个 view 要在 1373 行文件里上下跳,helper 与 view 在同一作用域无 seam 隔离。
- **测试 surface 大**:vitest 已 `export StoreView` 供组件测,但 import 路径指向 1373 行的胖文件,改 unrelated 部分有副作用风险。
- 这是 [codebase-health-log.md](./codebase-health-log.md) 2026-07-25 巡检识别的 **Strong** friction 点(Top recommendation 之一),deletion test 通过(纯 locality 收益,无抽象成本)。

## 2. Solution

按 view 边界把 `bookings-page.tsx` 拆成 `frontend/src/pages/bookings/` 文件夹:1 个入口(`index.tsx` 三叉路由 ~15 行)+ 3 个 view module + 1 个 shared module(STATUS_META / FILTER / date helpers / `BookingStatusBadge` 等)。**零行为变更,纯代码搬运**。现有 12 个 vitest 测试全绿验证 carry 正确性,顺便给零测试的 HqView 补 smoke test。

## 3. User Stories

- 作为**前端开发者**,我想改 StoreView 时只在一个 < 700 行的 module 里操作,以便不污染其他 view 的认知负荷。
- 作为**测试编写者**,我想 `import { HqView } from "./hq-view"` 直接拿到独立 module,以便给它写 smoke test 不用先 export。
- 作为**巡检 follow-up 执行者**,我想这次拆分独立可提交,以便候选 2(cancel 并入状态机)和候选 8(union endpoint 拆双 hook)各自独立切片不被混淆。

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 0 | 纯前端重构 |
| 数据库迁移 | 0 | — |
| 前端文件改动 | 6 新建 + 1 删 + 2 改 | 新建 `bookings/{index,store-view,hq-view,my-bookings-view,shared}.tsx`(shared 含 JSX 故 .tsx)+ `bookings/__tests__/hq-view.test.tsx`;删 `pages/bookings-page.tsx`;改 `pages/__tests__/{store-view,my-bookings-view}.test.tsx`(挪位置 + 改 import) |
| 新增测试类 | 1 | `hq-view.test.tsx`(smoke,~3 tests) |
| 路由改动 | 0 | `App.tsx` lazy import 路径改 `@/pages/bookings/bookings-page` 仍 re-export `BookingsPage`(D-路由 不动决策) |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(纯文件搬运,view 内的 `useBookings`/`useMyBookings` 调用不变)
- 验证:无新增多租户测试(行为零变更,现有 12 测试覆盖)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 `require_permission` caller? **NO**(纯前端,`hasPermission(me, ...)` 调用原样搬)
- 验证:store-view.test.tsx 现有「member 视图无写按钮」测试不变

### 4.4 数据库表设计 checklist

**N/A** —— 无数据库改动。

### 4.5 其他实施决策

#### D1:目录结构(grill D2 决策)

新建 `frontend/src/pages/bookings/` 子文件夹。**项目首个 page 子文件夹**(目前所有 page 是 `xxx-page.tsx` 平铺,只有 `__tests__/`),但 bookings 1373 行的体量 + 5 个内聚 module 的拆分需要 justify 这个先例。

```
frontend/src/pages/bookings/
├── __tests__/
│   ├── store-view.test.tsx          # 挪自 pages/__tests__/,改 import
│   ├── my-bookings-view.test.tsx    # 挪自 pages/__tests__/,改 import
│   └── hq-view.test.tsx             # 新建 smoke
├── bookings-page.tsx                # 入口:re-export BookingsPage(保路由 lazy import 兼容)
├── store-view.tsx                   # ~680 行(列表 + 4 Dialog + DropdownMenu)
├── hq-view.tsx                      # ~105 行(跨店只读表)
├── my-bookings-view.tsx             # ~105 行(customer 自助 + 确认开机)
└── shared.tsx                       # ~360 行(STATUS_META / NONE / MUTABLE_STATUS / ACTIONABLE_STATUS / BookingFilter / FILTER_OPTIONS / FilterChips / BookingStatusBadge / deviceNameOf / date helpers / applyBookingFilter / slotTone / ScheduleGridCard + ScheduleSlot)
```

> **已知 smell(2026-07-25 code-review 发现)**:`shared.tsx` 有轻微 `Divergent Change` —— `ScheduleGridCard` + 其私有 date helpers(slotTone/dayLabel/hhmm 等)只被 StoreView 消费,却混在所有 view 共享的文件里。本次不拆(plan 守纯 locality 范围),登记为独立后续候选(可叫 `bookings-shared-split`)。

**路由保持兼容**:`App.tsx:39-40` 的 `lazy(() => import("@/pages/bookings-page"))` 改为 `import("@/pages/bookings/bookings-page")`。新入口 `bookings-page.tsx` 仅 re-export `BookingsPage`:
```ts
export { BookingsPage } from "./index";
```

> **为什么不直接让 index.tsx 叫 bookings-page.tsx**:入口文件名与文件夹名同名易混;`index.tsx` 是 React 子文件夹入口的通用约定;`bookings-page.tsx` 作 barrel re-export 保持「page 命名 = 路由名」的现有惯例。

#### D2:测试位置(grill D4 决策)

测试跟 view 走(`bookings/__tests__/`)。理由:改 `store-view.tsx` 时隔壁就是 `store-view.test.tsx`,locality 强于「所有 page 测试集中在 pages/__tests__/」。其他 page 的测试仍留原处(不强制改动,只 bookings 这一个 domain 跟进)。

import 路径变更:
```ts
// 旧:from "../bookings-page"
// 新:
import { StoreView } from "../store-view";
import { MyBookingsView } from "../my-bookings-view";
```

#### D3:范围边界(grill D6 决策)

**只拆分,不碰逻辑**。以下明确**不做**(各自是独立巡检候选):
- ❌ 处理 7 处 `as BookingHqRead[]` / `as Booking[]` / `as Device[]` cast(候选 8 范围,union endpoint 拆双 hook)
- ❌ 把 `submitEnd` 的 `JSON.parse` fallback 搬到 endpoint 层(候选 7 范围)
- ❌ cancel 并入状态机(候选 2 范围,后端)

cast 在拆分后**原样搬到各自 view 文件**(共 7 处:hq-view 保留 `as BookingHqRead[]` ×1,my-bookings-view 保留 `as Booking[]` ×1,store-view 保留 `as Booking[]` ×1 + `as Device[]` ×3 + `as Device` 类型守卫 ×1;原文件就是 7 处,非 plan 早期草稿写的「5 处」)。代码注释标注「cast 保留,委托 candidate 8」。

#### D4:验证策略(grill D7 决策)

- 现有 12 个 vitest(store-view 6 + my-bookings-view 6)**必须全绿**(零行为变更,测试不该断)
- 新增 `hq-view.test.tsx` smoke(~3 tests:渲染跨店表 + 空态 + 列头)
- `npm run build` 绿
- `npx oxlint` 0 warning
- `tsc -b` 绿

---

## 5. Testing Decisions

- 测试金字塔:component 3 新增(hq-view smoke)+ 现有 12 全绿
- 测试用 jsdom(沿用 device-poweron 切片 02 引入的 vitest 基建)
- 覆盖率目标:N/A(纯重构,覆盖率不变)
- 边界 case:`hq-view.test.tsx` 至少覆盖:① 渲染跨店表 + 列头;② 空态 EmptyState;③ tenant_name/device_name/customer_name 显示(含 null fallback)

---

## 6. 切片规划

**wide refactor 例外**(机械搬运 + 爆炸半径单一文件)—— 不做垂直切片,单切片完成(对齐 prd-template.md §2.2 例外段)。

### Ticket 1:bookings-page 按视图拆 module(唯一切片)✅(Session 139,待 PR)

- **What to build**:把 `bookings-page.tsx` 1373 行按 view 边界拆成 5 个 module + 入口 barrel,补 HqView smoke test,验证零行为变更。
- **Blocked by**: 无
- **文件清单**: 6 新建 + 1 删 + 2 改 + 1 路由改 = 10 文件
- **验证命令**:
  ```bash
  cd frontend
  npx vitest run           # 15/15 绿(12 现有 + 3 新 HqView)
  npm run build            # 绿
  npx oxlint               # 0 warning
  npx tsc -b               # 绿
  ```

---

## 7. v1 → v2 对抗式审查段

**跳过** —— 非复杂任务(改动文件 ≈10 但都是机械搬运,无鉴权/迁移/跨服务/不可逆操作,§7 触发条件均不满足)。grill 决策树已覆盖所有 decision(D1-D4)。

---

## 8. Out of Scope

- ❌ 处理 7 处 `as` cast(候选 8,独立后续任务)
- ❌ `submitEnd` JSON.parse fallback 搬 endpoint 层(候选 7)
- ❌ cancel 并入 `booking_state`(候选 2,后端)
- ❌ 给 store-view/my-bookings-view 补更多测试(候选 4 整体前端补测范围)
- ❌ 拆 `queries.ts` / `endpoints.ts` / `types.ts`(候选 5,独立 fat file 拆分)
- ❌ 抽 `CrossTenantReadOnlyTable` 共享组件(候选 7,4 page 共性抽取)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 拆分时遗漏某个 helper / 常量,build 断 | 中 | tsc -b + npm run build 双闸门;shared.ts 集中导出,view 从 shared import |
| 测试 import 路径改错 | 低 | vitest run 立即报错;2 个测试文件 grep 全替换 |
| 引入项目首个 page 子文件夹,后续 page 跟风 | 低 | 本次只在 bookings(1373 行体量 justify);其他 page 不强制跟进,保留 `xxx-page.tsx` 惯例 |
| HqView smoke test 写法不当,与 store-view 测试模式不一致 | 低 | 复用 `renderWithProviders + vi.mock("@/hooks/queries")` 现成模板 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `frontend/src/pages/bookings-page.tsx` **已删除**
2. `frontend/src/pages/bookings/` 文件夹存在,含 5 个 .tsx + 1 个 __tests__/(3 测试文件)
3. `App.tsx` lazy import 指向 `@/pages/bookings/bookings-page`,路由 `/bookings` 仍正常
4. `cd frontend && npx vitest run` → **15/15 绿**(12 现有 + 3 新 HqView smoke)
5. `cd frontend && npm run build` 绿
6. `cd frontend && npx oxlint` 0 warning
7. `cd frontend && npx tsc -b` 绿
8. `./init.sh` 全绿(后端无改动,基线不应回归)
9. 7 处 `as` cast 原样保留在各自 view(代码注释 `Note(candidate-8)` 标注,用 Note 不用 TODO 避免触发 IDE 扫描器)
10. 无新 TODO/FIXME 引入(基线 2 处 Logto 占位不变)

---

## 11. 不越界声明

本次改动**只**涉及 `frontend/src/pages/bookings-page.tsx` 的机械拆分(→ `bookings/` 文件夹)+ 测试位置调整 + 路由 lazy import 路径更新 + HqView smoke test 新增;**不**触碰:
- 任何后端文件(app/ / alembic/)
- `queries.ts` / `endpoints.ts` / `types.ts`(候选 5 范围)
- 任何 view 内的业务逻辑(cast / JSON.parse / 状态判断原样保留)
- 其他 page(devices / customers / settings 等)
