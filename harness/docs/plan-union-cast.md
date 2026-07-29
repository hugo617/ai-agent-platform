# 计划:前端 union-cast 扩散消解 — 拆 role-specific hook

> **id**: `union-cast-split`
> **状态**: draft v1
> **优先级**: 75(当前最高 passing = twoscope-config 74,本任务接其位)
> **创建日期**: 2026-07-29
> **来源**: 第 6 次代码健康度巡检候选 B(Top recommendation)+ grill 8 决策共识

---

## 1. Problem Statement(对齐 to-spec)

**问题**:前端 `endpoints.ts` 的 5 个 role-branching hook 返回 union 类型(`Device[] | DeviceHqRead[]` 等),反映「同一 endpoint 按 token 里的 platform_role 返回不同 shape」的后端行为。但 union 的**窄化**散落在 5 个 view 文件,靠 `as` 断言强制转换(巡检时笼统计 ~12 处,审查后精确四分类:A 类 10 处 + B 类 2 处 + C 类 5 处 + D 类 1 处,仅 A+D 类属本次范围)。

**cast 四分类**(审查后精确化,区别对待):

| 类别 | 含义 | 处理 | 本次涉及处 |
|---|---|---|---|
| **A. role-branching 窄化** | hook 返回 union,view 按 role 断言窄化(`as Device[]`/`as DeviceHqRead[]`/`as Booking[]`/`as BookingHqRead[]`/`as DeviceModelRead[]`) | ✅ **本次消解**(拆 role-specific hook) | 10 处(见下表) |
| **B. 组件 props 适配 cast** | 共享组件签名接 base type,hq-view 借用时边界 cast(`b as Booking` 传给接 `Booking` 的 BookingRowMenu) | ❌ **不纳入**(改组件签名是独立重构) | 2 处(hq-view L520/523) |
| **C. 字段投影 cast** | 取公共子集字段(`as ModelOption[]` 取 `{id,name}`)+ enum cast(`as DeviceStatus`) | ❌ **不纳入**(决策 D2) | 5 处(devices-page:ModelOption 4 + DeviceStatus 1) |
| **D. 多余死 cast** | hook 已返回窄类型,cast 冗余(useMyBookings 返 `Booking[]` 非 union,L63 是 bookings-page-split 遗留) | ✅ **本次顺手删**(零风险,纯删冗余) | 1 处(my-bookings-view L63) |

**A 类(role-branching 窄化)精确清单 —— 本次消解目标(10 处)**:

| view 文件 | 行 | cast | 所属 domain | 切片 |
|---|---|---|---|---|
| `hq-view.tsx` | 143 | `as BookingHqRead[]` | bookings | 切片 1 |
| `hq-view.tsx` | 163 | `as DeviceHqRead[]` | devices | 切片 2 |
| `store-view.tsx` | 152 | `as Device[]` | devices | 切片 2 |
| `store-view.tsx` | 186 | `as Booking[]` | bookings | 切片 1 |
| `store-view.tsx` | 356 | `as Device[]` | devices | 切片 2 |
| `store-view.tsx` | 366 | `as Device[]` | devices | 切片 2 |
| `devices-page.tsx` | 192 | `as Device[]`(StoreView 组件) | devices | 切片 2 |
| `devices-page.tsx` | 422 | `as DeviceHqRead[]`(HqView 组件) | devices | 切片 2 |
| `device-models-page.tsx` | 149 | `as DeviceModelRead[]` | devices | 切片 2 |
| `device-models-page.tsx` | 216 | `as DeviceModelRead[]` | devices | 切片 2 |

> **注**:`my-bookings-view.tsx:63` 的 `as Booking[]` 不在 A 类 —— `useMyBookings` 返回 `Promise<Booking[]>`(走 `/me/bookings` 独立端点,非 union),该 cast 是 D 类多余死 cast(bookings-page-split 拆分时原样保留的冗余),切片 1 直接删除即可,不需拆 hook。

> **注**:`devices-page.tsx` 是**单文件含 StoreView(L148)+ HqView(L411)双组件**,两组件都调 `useDevices()` 但期望不同窄类型(DevicesPage L144 三叉路由只渲染其一,故仍只有一个被调,D5 queryKey 共享前提成立)。切片 2 需改这两个调用点。

> **B 类不消解的理由**(hq-view L520/523):`BookingRowMenu`(shared-dialog.tsx:589)props.booking 签名为 `Booking`(store 共享组件)。hq-view 的 `b` 是 `BookingHqRead`(`extends Booking`),`b as Booking` 是安全向下窄化(注释 L513-515 已明示:menu logic 只用 status,在 base type 上)。消这俩要改 BookingRowMenu 签名为泛型/union,属组件重构,超出本次范围。

**friction**:
1. **无 locality**:role 判断散在 4 个 view(hq-view/store-view/devices-page/device-models-page),删/改一个 hook 签名要同步改多文件
2. **静默 downcast 安全隐患**:`as` 是编译期断言,运行时不校验,若后端返回 shape 与断言不符会静默错乱
3. **债标记已就位**:`hq-view.tsx:142` + `my-bookings-view.tsx:62` 已有 `// Note(candidate-8): split fetchBookings → fetchBookingsHq to drop this cast` 注释,指向同一解法但未执行

**为什么现在做**:第 6 次巡检(2026-07-29)复评,union-cast 从第 5 次的 ~10 处**微增到 12 处**,是当前唯一「恶化」的候选。且 twoscope-config(后端同类范式重构)已收官 passing,前端这是自然的 leverage 延续。

---

## 2. Solution(对齐 to-spec)

把 union 消灭从「view 边界」上移到「hook 层」:每个 role-branching hook 拆成 store 版 + platform-wide 版(`useDevices`/`useDevicesAll`),内部各自调用同一 endpoint(后端按 token role 自动分流),返回**窄类型**。view 直接调对应 hook,0 cast。

**核心洞察**:view 顶层已经做了 role 三叉路由(`devices-page.tsx:144` `isSuperAdmin||isHQStaff ? HqView : StoreView`),role 信号(`isSuperAdmin`/`isHQStaff`/`hasCustomerIdentity`)现成。hook 层只是把这个已有的 role 信号用来**定形返回类型**,而非让 union 漏到 view 再窄化。

---

## 3. User Stories

- 作为 **store 门店角色**(owner/admin/member),我调 `useDevices()` 直接拿到 `Device[]`,无需 `as` 断言,类型自描述我看到的 scoped 数据
- 作为 **平台角色**(super_admin/hq_staff),我调 `useDevicesAll()` 直接拿到 `DeviceHqRead[]`,panorama 全字段类型安全
- 作为 **开发者**,我改一个 hook 的返回 shape 只动一处(hook 定义),不必 grep 全仓 `as` 断言同步改 4 文件
- 作为 **未来巡检 agent**,我看到的是「已裁决的 role-specific hook 设计」而非「散落的 cast 待消解」

---

## 4. Implementation Decisions

### 4.0 grill 8 决策汇总(一次一问共识)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1 | union 消灭策略 | **拆 role-specific hook**(fetchDevices/fetchDevicesAll 两套) | 与代码现有 `Note(candidate-8)` 倾向一致;leverage 最高;role 判断从 4 view 收口到 hook 层 |
| D2 | `as ModelOption[]`(devices-page 4 处)+ `as DeviceStatus`(1 处) | **不纳入本次** | 字段投影(取 `{id,name}` 交集)/ enum cast,非 role 窄化,与本次正交;避免范围蠕变 |
| D3 | 拆哪些 hook | **只拆 3 个有调用的**(useDevices/useBookings/useDeviceModels) | useDevice/useBooking 零调用点(死代码),拆了无业务验证路径 |
| D4 | 切片形状 | **按 domain 分 3 切片**(bookings / devices / 收尾) | 每 domain 可独立验证,跨 endpoint+queries+view+test 一致 |
| D5 | queryKey | **共享同一 key**(`qk.devices`/`qk.bookings`) | 同一用户角色固定,store/hq hook 永远只一个被调,缓存不冲突;写失效逻辑不变 |
| D6 | 命名 | **All 后缀**(fetchDevicesAll/useDevicesAll) | 随 `useAllTenants`/`fetchAllTenants` 先例(platform-wide 变体统一用 All) |
| D7 | 测试 | **改 mock 名 + tsc 验证 + grep 0 cast** | 现有 vi.mock stub 策略保留,改 mock 名即可;tsc 是类型重构的测试 |
| D8 | ADR | **不提,plan 记录足够** | 纯前端类型重构,非范式基类;现有 2 ADR 均后端架构基类,前端无 ADR 先例 |

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | **0** | 纯前端类型重构,后端 endpoint 不动(role 分流仍由后端按 token 自动完成) |
| 数据库迁移 | **0** | 无 schema 变化 |
| 前端文件改动 | **8** | `api/endpoints.ts`(+3 fetch All 函数)+ `hooks/queries.ts`(+3 hook)+ `pages/bookings/hq-view.tsx`(跨切片1+2)+ `pages/bookings/store-view.tsx`(跨切片1+2)+ `pages/bookings/my-bookings-view.tsx`(切片1)+ `pages/devices-page.tsx`(切片2)+ `pages/device-models-page.tsx`(切片2)+ `pages/bookings/__tests__/hq-view.test.tsx`(切片1 mock 改名) |
| 新增测试类 | **0 新文件** | 仅改 1 个现有 view test 的 mock 名(`hq-view.test.tsx`:useBookings→useBookingsAll + 返回值收窄为 `BookingHqRead[]`)。`store-view.test.tsx` **不改**(其 mock 用 `makeBooking()` 构造 `Booking[]`,本就是 store 类型,useDevices/useBookings 返回类型从 union 收窄为 `Device[]`/`Booking[]` 后天然兼容) |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(后端不动,前端只是类型收窄)
- 是否引入跨租户访问点? **NO**(role 分流逻辑不变,只是把窄化从 view 移到 hook)
- 验证:无多租户测试需求(纯类型层,运行时行为零变化)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 60+ 处 `require_permission` caller? **NO**(后端零改动)
- 是否影响 graph.py 工具内 check? **NO**

### 4.5 其他实施决策

**useDeviceModels 的特殊处理**(基于深挖事实):

`useDeviceModels` 的两个消费点性质不同:
- `device-models-page.tsx`(L149/216):`as DeviceModelRead[]` —— **真 role 窄化**(整页在 RequireSuperAdmin 守卫内,恒为 admin 视角)→ 改调 `useDeviceModelsAll()`,消 2 处 cast
- `devices-page.tsx`(L168/369/452/659):`as ModelOption[]` —— **字段投影**(取 `{id,name}` 给 dropdown,任何 role 都一样)→ **保持不变**(决策 D2 已排除)

因此:`useDeviceModels` hook **保留 union 返回**(给 devices-page 的 dropdown 投影用),新增 `useDeviceModelsAll`(给 admin 页用)。`fetchDeviceModels` endpoint 函数同理保留 union,新增 `fetchDeviceModelsAll`(类型上声明返回 `DeviceModelRead[]`,运行时同一 endpoint)。

> **注**:`fetchDeviceModelsAll` 与 `fetchDeviceModels` 调同一 URL,只是返回**类型注解**不同(后者 union,前者窄为 `DeviceModelRead[]`)。运行时完全等价 —— 这正是「union 在 hook 层消灭」的体现:类型在 seam 处定形,运行时无开销。

---

## 5. Testing Decisions

- **测试金字塔**:unit 0 / integration 0 / E2E 0 新增 —— 纯类型重构,tsc 编译即测试
- **现有测试改动**:2 个 view test 改 mock 名
  - `hq-view.test.tsx`:`useDevices`→`useDevicesAll` / `useBookings`→`useBookingsAll`(hq-view 改调新 hook),mock 返回值类型从 union 收窄为 `BookingHqRead[]`/`DeviceHqRead[]`
  - `store-view.test.tsx`:**不变**(store-view 仍调原 `useDevices`/`useBookings`,返回 `Device[]`/`Booking[]`)
- **验证命令**:
  - `cd frontend && npm run build`(tsc 0 类型错误 —— 类型重构的核心验证)
  - `cd frontend && npm test`(现有 vitest 全绿,确认行为零回归)
  - `cd frontend && npx oxlint .`(0 warning)
  - `grep -rn 'as Device\[\]\|as DeviceHqRead\[\]\|as Booking\[\]\|as BookingHqRead\[\]' frontend/src/pages/`(**核心 AC**:A 类 role 窄化 cast 归 0 —— 只匹数组形式,排除 hq-view L520/523 单数 props cast[B 类保留])
- **覆盖率目标**:不适用(类型重构,无新逻辑分支)
- **边界 case**:无(零运行时行为变化)

---

## 6. 切片规划(tracer-bullet,按 domain 分)

### Ticket 1: bookings domain(useBookings → useBookingsAll) ✅

- **What to build**:bookings 视角的 A 类 union-cast 消解 + D 类死 cast 清理。新增 `fetchBookingsAll`/`useBookingsAll`(返回 `BookingHqRead[]`)。hq-view 改调 `useBookingsAll` 消 L143(A 类);store-view 改 useBookings 返回窄类型后消 L186(A 类);my-bookings-view 删 L63 多余 cast(D 类,useMyBookings 已返回 `Booking[]` 非 union,不需拆 hook)。**跨 domain 文件中间态说明**:hq-view 与 store-view 同时消费 bookings + devices 数据,本切片只改它们的 bookings 调用 + 消 booking cast,devices 调用 + device cast 留切片 2(切片间 hq-view/store-view 会暂存「bookings 已窄化、devices 仍 union」的中间态,可编译可运行,切片 2 补齐)。
- **Blocked by**: 无(frontier 切片)
- **本切片消解的 cast**(2 处 A 类 + 1 处 D 类):hq-view L143(A)/ store-view L186(A)/ my-bookings-view L63(D 死 cast)
- **文件清单**(6):
  - `frontend/src/api/endpoints.ts`(+`fetchBookingsAll`,返回 `Promise<BookingHqRead[]>`,调同一 `/bookings/` URL,类型注解窄化)
  - `frontend/src/hooks/queries.ts`(+`useBookingsAll`,queryKey 共享 `qk.bookings`)
  - `frontend/src/pages/bookings/hq-view.tsx`(改调 `useBookingsAll`,消 L143 `as BookingHqRead[]`;**不动** L163 device cast / L520-523 props cast[B 类,留原样])
  - `frontend/src/pages/bookings/store-view.tsx`(useBookings 返回窄 `Booking[]` 后,消 L186 `as Booking[]`;**不动** L152/356/366 device cast[留切片 2])
  - `frontend/src/pages/bookings/my-bookings-view.tsx`(**删** L63 多余 `as Booking[]` cast[D 类死 cast,useMyBookings 已返 `Booking[]`]+ 删 L62 `Note(candidate-8)` 注释)
  - `frontend/src/pages/bookings/__tests__/hq-view.test.tsx`(mock 改名 `useBookings`→`useBookingsAll` + 返回值收窄为 `BookingHqRead[]`)
- **验证命令**:
  - `cd frontend && npm run build`(0 类型错误,核心验证)
  - `cd frontend && npm test`(全绿,零行为回归)
  - `grep -rn 'as Booking\[\]\|as BookingHqRead\[\]' frontend/src/pages/bookings/`(hq-view L143/store-view L186 两处 A 类应消失;my-bookings L63 D 类也消失)
- **AC**:
  - [x] `fetchBookingsAll`/`useBookingsAll` 新增,queryKey 用 `qk.bookings`(共享,非新 key)
  - [x] hq-view 改调 `useBookingsAll`,消 L143 A 类 cast
  - [x] store-view 消 L186 A 类 cast(useBookings 返回已窄 `Booking[]`)
  - [x] my-bookings-view **删** L63 D 类死 cast(useMyBookings 已返 `Booking[]`,cast 冗余)+ 删 `Note(candidate-8)` 注释
  - [x] hq-view L520/523(B 类 props cast)**保持不动**(验证未误删)
  - [x] hq-view.test.tsx mock 改名 + 返回值收窄为 `BookingHqRead[]`
  - [x] `npm run build` 0 类型错误
  - [x] `npm test` 全绿(零行为回归)

### Ticket 2: devices domain(useDevices → useDevicesAll + useDeviceModels → useDeviceModelsAll)

- **What to build**:devices 视角的 A 类 union-cast 消解。新增 `fetchDevicesAll`/`useDevicesAll`(返回 `DeviceHqRead[]`)+ `fetchDeviceModelsAll`/`useDeviceModelsAll`(返回 `DeviceModelRead[]`)。hq-view 改调 `useDevicesAll` 消 L163(接切片1遗留);store-view 消 L152/356/366;devices-page **单文件双组件**:StoreView L192 改调 useDevices(返回窄 `Device[]`)消 cast + HqView L422 改调 `useDevicesAll` 消 cast;device-models-page 改调 `useDeviceModelsAll` 消 L149/216。devices-page 的 C 类 `as ModelOption[]`(4 处)+ `as DeviceStatus`(1 处)保持不动。
- **Blocked by**: Ticket 1(bookings 先行验证范式 + 跨 domain 文件的 bookings 侧已收口)
- **本切片消解的 A 类 cast**(8 处):hq-view L163 / store-view L152+356+366(3 处)/ devices-page L192+422(2 处)/ device-models-page L149+216(2 处)
- **文件清单**(5):
  - `frontend/src/api/endpoints.ts`(+`fetchDevicesAll` 返回 `DeviceHqRead[]` + `fetchDeviceModelsAll` 返回 `DeviceModelRead[]`,均调同一 URL,类型注解窄化)
  - `frontend/src/hooks/queries.ts`(+`useDevicesAll` queryKey=`qk.devices` + `useDeviceModelsAll` queryKey=`qk.deviceModels`,均共享)
  - `frontend/src/pages/bookings/hq-view.tsx`(改调 `useDevicesAll`,消 L163 `as DeviceHqRead[]` —— 接切片1遗留;此时 hq-view 的 bookings+devices 双侧都收口)
  - `frontend/src/pages/bookings/store-view.tsx`(useDevices 返回窄 `Device[]` 后,消 L152/356/366 三处 `as Device[]`;此时 store-view 双侧都收口)
  - `frontend/src/pages/devices-page.tsx`(**双组件双改**:StoreView L192 改调 `useDevices`(返回已窄 `Device[]`)消 cast + HqView L422 改调 `useDevicesAll` 消 cast;**不动** 4 处 `as ModelOption[]` + 1 处 `as DeviceStatus`[C 类])
  - `frontend/src/pages/device-models-page.tsx`(改调 `useDeviceModelsAll`,消 L149/216 `as DeviceModelRead[]`)
- **验证命令**:
  - `cd frontend && npm run build`(0 类型错误)
  - `cd frontend && npm test`(全绿)
  - `grep -rn 'as Device\[\]\|as DeviceHqRead\[\]\|as DeviceModelRead\[\]' frontend/src/pages/`(A 类 device cast 应归 0;devices-page 的 `as ModelOption[]` 不匹此 grep,保留)
- **AC**:
  - [ ] `fetchDevicesAll`/`useDevicesAll` + `fetchDeviceModelsAll`/`useDeviceModelsAll` 新增,queryKey 共享
  - [ ] hq-view 消 L163 `as DeviceHqRead[]`(接切片1遗留,bookings+devices 双侧收口)
  - [ ] store-view 消 L152/356/366 三处 `as Device[]`(双侧收口)
  - [ ] devices-page StoreView L192 + HqView L422 双组件 cast 消解
  - [ ] device-models-page 消 L149/216 `as DeviceModelRead[]`(2 处)
  - [ ] devices-page 的 `as ModelOption[]`(4 处)+ `as DeviceStatus`(1 处)C 类**保持不动**(验证未误删)
  - [ ] `npm run build` 0 类型错误
  - [ ] `npm test` 全绿

### Ticket 3: 收尾验证(A 类 cast 审计 + 文档)

- **What to build**:全仓 grep 审计 **A 类 role-branching 窄化 cast** 归 0(数组形式 `as Xxx[]` / `as XxxHqRead[]`),确认 B 类(props 适配,hq-view L520/523 `b as Booking` 单数形式)与 C 类(`as ModelOption[]` 投影、`as DeviceStatus` L1043 enum cast)等非 role cast 不受影响。清理残余 `Note(candidate-8)` 注释。feature 收尾。
- **Blocked by**: Ticket 1 + Ticket 2
- **文件清单**(0-1,可能仅清理注释):
  - 全仓 grep 验证(无源码改动)
  - 若有残余 `Note(candidate-8)` 注释则清理(hq-view + my-bookings-view 共 2 处,切片1 应已删 my-bookings 那处,本切片确认 hq-view 那处也清)
- **验证命令**:
  - `grep -rn 'as Device\[\]\|as DeviceHqRead\[\]\|as Booking\[\]\|as BookingHqRead\[\]\|as DeviceModelRead\[\]' frontend/src/pages/`(**核心 AC:A 类 role 窄化 cast 归 0** —— 只匹数组形式,不误匹 L520 `b as Booking` 单数 props cast)
  - `grep -rn 'as ModelOption\[\]\|as DeviceStatus' frontend/src/pages/`(C 类应仍在,验证未误删)
  - `grep -rn 'Note(candidate-8)' frontend/src/`(注释全清)
  - `cd frontend && npm run build && npm test && npx oxlint .`
- **AC**:
  - [ ] A 类 role 窄化 cast(数组形式)在 `frontend/src/pages/` 归 0
  - [ ] B 类 props cast(hq-view L520 `b as Booking` / L523 `bk as BookingHqRead` 单数形式)**保留**(grep 确认仍在,验证未误删)
  - [ ] C 类投影/enum cast(`as ModelOption[]` / `as DeviceStatus`)不受影响(grep 确认仍在)
  - [ ] `Note(candidate-8)` 注释全清
  - [ ] `npm run build` 0 类型错误 + `npm test` 全绿 + oxlint 0 warning
  - [ ] feature 收尾:feature_list.json status → passing + evidence + sync-active + progress.md 更新
  - [ ] 文档影响评估执行

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:
- 改动文件 ~7(< 10)✓ 不触发
- 涉及鉴权/权限/数据迁移/跨服务?**NO** ✓ 不触发
- 涉及安全敏感操作?**NO** ✓ 不触发
- 涉及不可逆操作?**NO** ✓ 不触发

**结论**:本任务**不满足复杂任务任一触发条件**,为纯前端类型重构(零后端、零 schema、零运行时行为变化)。**不走对抗式审查**,draft v1 直接进实施。

> 若实施中发现 union 拆分引发非预期的类型推断问题(如泛型纠缠),再回头补审查。

---

## 8. Out of Scope

- ❌ **`as ModelOption[]`(devices-page 4 处)+ `as DeviceStatus`(1 处)**:字段投影 cast(取 `{id,name}` 公共子集)/ enum cast,非 role 窄化。与本次正交,留给独立后续候选(若未来投影也需消,可抽 `pickModelOptions()` helper)
- ❌ **`as DeviceStatus`**(devices-page L1043):enum cast(Select onValueChange 的 string→enum),非 role 窄化,非本次范围
- ❌ **useDevice/useBooking**(单数详情 hook):零调用点死代码,拆了无验证路径。若要清理死代码是独立决策
- ❌ **后端改动**:本次纯前端,后端 endpoint 的 role 分流逻辑完全不动
- ❌ **ADR**:不提(决策 D8),plan 记录足够
- ❌ **queryKey 按 role 拆**:不做(决策 D5),共享 key 即可

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| `useDevicesAll` 与 `useDevices` 共享 `qk.devices` 导致缓存串味 | 低 | 同一用户角色固定(store 或 hq),两个 hook 永远只一个被调,缓存不可能同时存在两种 shape。tsc + 行为测试兜底 |
| 拆 hook 后 mock 改名遗漏导致 test 静默 pass(vi.mock 未匹配返回 undefined) | 中 | 切片 1/2 AC 明确要求 test 改 mock 名 + 返回值收窄;`npm test` 必须全绿且断言真实渲染(mock undefined 会导致渲染空,断言失败) |
| devices-page StoreView 分支的 `as Device[]`(L192)消掉后,原 `useDevices` 返回类型是否真为 `Device[]` | 中 | 拆 hook 后 `useDevices` 返回类型改为 `Device[]`(非 union),L192 cast 自然消。需确认 `fetchDevices` 也改返回 `Promise<Device[]>`(store 视角) |
| `fetchDevicesAll`/`fetchDevices` 调同一 URL,review 时被质疑「重复」 | 低 | 注释明示:类型在 seam 处定形,运行时等价;这是「union 在 hook 层消灭」的体现,非重复 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `cd frontend && npm run build` 0 类型错误(tsc 是类型重构的核心测试)
2. `cd frontend && npm test` 全绿(现有 vitest 零行为回归,65 tests)
3. `cd frontend && npx oxlint .` 0 warning 0 error
4. `grep -rn 'as Device\[\]\|as DeviceHqRead\[\]\|as Booking\[\]\|as BookingHqRead\[\]\|as DeviceModelRead\[\]' frontend/src/pages/` **归 0**(A 类 role 窄化 cast 消解 —— 只匹数组形式,排除单数 props cast)
5. B 类 props cast(hq-view L520 `b as Booking` / L523 `bk as BookingHqRead` 单数形式)**保留**;C 类 `as ModelOption[]`(4 处)与 `as DeviceStatus`(1 处)不受影响(grep 确认仍在 —— 验证未误删非本次范围 cast)
6. `Note(candidate-8)` 注释全清(2 处:hq-view + my-bookings-view)
7. 切片 1/2/3 checklist 全勾 + feature 收尾(status=passing + evidence + sync-active + progress.md)

---

## 11. 不越界声明

本次改动**只**涉及:
- 前端 `api/endpoints.ts` + `hooks/queries.ts` 新增 role-specific hook/fetch(3 套:Devices/Bookings/DeviceModels 的 All 变体)
- 前端 4 个 view 文件改调对应 hook 消 role 窄化 cast
- 前端 2 个 view test 改 mock 名

**不**触碰:
- 后端任何文件(endpoint / service / repository / model / schema 全不动)
- 数据库(无 migration)
- `as ModelOption[]` 字段投影 cast(决策 D2 排除)
- `as DeviceStatus` enum cast(非本次范围)
- useDevice/useBooking 死代码(独立决策)
