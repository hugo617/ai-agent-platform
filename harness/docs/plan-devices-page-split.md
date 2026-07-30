# 计划:前端 devices-page 拆 store-view / hq-view(镜像 bookings/ 范式)

> **id**: `devices-page-split`
> **状态**: not_started v2(经 opus 对抗式审查修订,规划就绪待实施)
> **优先级**: 78(当前最高 passing = union-cast-split 75,本任务与 chat-page-split 76 / perm-backfill-dedupe 77 同批;第 7 次巡检候选 ②)
> **创建日期**: 2026-07-30
> **最后修订**: 2026-07-30(v2)
> **来源**: 第 7 次代码健康度巡检候选 ②(Strong + PERSISTING)+ grill 5 决策共识

---

## 0. v1 → v2 变更摘要(对抗式审查修订)

opus 双轴审查(真相核查 + 设计质量)发现 v1 的 tenantId 安全测试设计有真实漏洞 + AC 不可验证 + 对「4 Dialog 共享机制」事实描述错误,本轮修订:

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| **tenantId 安全空窗**:Ticket 1 的「65 测试零回归」对 tenantId **零捕获**(现有 65 测试不含任何 devices 测试),tenantId 测试在 Ticket 2 才补 | 🔴 RED | Ticket 1 前移一个 tenantId smoke 测试(HqView 选 target → 捕获 Create payload 含 tenant_id);或 Ticket 1 不删旧文件直到 Ticket 2 测试绿 |
| **「4 Dialog 通过 tenantId prop 区分」事实错误**:实际只有 Create/Edit 有 tenantId prop,Bind/Delete 是 hook closure 机制(`useBindDeviceCustomer(targetTenantId)`) | 🔴 RED | §1/§2/§4.5 修正:明确只有 Create/Edit 两 Dialog 有 tenantId prop;Bind/Delete 走 hook closure |
| **hq-view.test 无法断言 tenantId prop**:按 plan 现设计 mock queries 后,Dialog 的 tenantId prop 流不可观测 | 🔴 RED | §5 引入 spy-on-children / payload 捕获接缝(参照 bookings hq-view.test 的 `createDialogCalls` 范式) |
| **AC「devices/ 结构对称于 bookings/」不可客观验证**(bookings 13 文件 vs devices 7 文件,本就不对称) | 🔴 RED | §10 改为显式 `test -f` 文件存在性清单(7 个文件) |
| **git mv 保留 blame 对单文件内多符号拆分不成立**(仅整文件 rename 保 blame) | 🟡 YELLOW | §4.1/§9 修正:拆分部分 blame 会断,仅整体移动部分保留 |
| 「完全镜像」措辞夸大(devices 无 customer view/排期网格,文件数少于 bookings) | 🟡 YELLOW | 改为「核心骨架对称,业务文件按需」 |
| StoreView/HqView 搬迁后需加 `export`(plan 未明说) | 🟡 YELLOW | §6 文件清单明示加 export |
| barrel bundle 体积 / 循环依赖风险未提 | 🟡 YELLOW | §9 补:barrel 已被 bookings 验证无 bundle 问题;提示 import 顺序避循环 |

> **注**:审查确认 devices 的双 entry(barrel + index)**正确镜像了 bookings**(GREEN)。v1 与同批 chat-page 的范式分叉问题,已在 chat-page-split v2 修正(统一为双 entry)。本 plan 的双 entry 设计无需改动。

---

## 1. Problem Statement(对齐 to-spec)

**问题**:`frontend/src/pages/devices-page.tsx` 是一个 **1083 行的单文件**,内含三叉路由 + 双视图组件 + 4 个共享 Dialog + 多个 helper,全部 module-level 但挤在一个文件里:

- `DevicesPage`(`DevicesPage` 函数)—— 二叉路由(`isSuperAdmin||isHQStaff ? HqView : StoreView`)
- `StoreView`(`StoreView` 函数,~263 行)—— 门店视角 CRUD,调 `useDevices()`(返 `Device[]`)+ 6 mutation hooks
- `HqView`(`HqView` 函数,~285 行)—— 跨租户 panorama 写,调 `useDevicesAll()`(返 `DeviceHqRead[]`)
- `DeviceCreateDialog` / `DeviceEditDialog` / `DeviceBindDialog` / `DeviceDeleteDialog` —— 4 个共享 Dialog,被 StoreView + HqView 双视图复用。**v2 修正 tenantId 机制**:只有 **Create/Edit 两 Dialog** 通过 `tenantId` prop 区分(StoreView 传 `undefined` → 后端用 user.tenant_id;HqView 传目标 id);**Bind/Delete 两 Dialog 无 tenantId prop**,它们的跨租户写是通过 **hook closure 机制**实现(HqView 调 `useBindDeviceCustomer(targetTenantId)` / `useDeleteDevice(targetTenantId)`,targetTenantId 闭包绑定进 hook,非 Dialog prop)。
- `StatusSelect` / `StatusBadge` / `customerNameOf` + 纯数据 `STATUS_META`/`STATUS_OPTIONS`/`NONE` —— 共享 helper

**friction**(对照 `/codebase-design` 词汇):

1. **无 locality**:改 StoreView 的 CRUD 逻辑要在 1083 行里定位,与 HqView + 4 Dialog + helper 纠缠。`bookings/` 已拆成独立文件可独立阅读,devices-page 没有这层 locality。
2. **范式不一致**:`bookings/` 早已拆成 `store-view.tsx` / `hq-view.tsx` / `my-bookings-view.tsx` / `shared-dialog.tsx` / `status-meta.ts` / `shared.tsx` 独立文件 + `__tests__/`。devices-page 是同款「双视图 + 共享 Dialog + helper」page 里**唯一未拆**的 —— 两套范式并存,认知负担翻倍。
3. **测试面已存在但未用**:巡检发现 StoreView/HqView **已是 module-level 命名函数**(L152/L417),本可直接 `import { StoreView } from "devices-page"` 单测,但因为没有独立文件 + 测试基建,实际零单测(devices-page 是 6 个零单测大 page 之一)。

**为什么 +346 行不是 rot**:增长来自 `platform-cross-tenant-write` feature(HqView 从只读升为可写)。新代码**强化了**现有双视图 seam 而非破坏它 —— 4 Dialog 被 lift 到 module-level 共享,tenantId prop 是干净的 adapter。结构是健康的,只是文件未拆。

**deletion test**:**中性偏正**(纯文件移动 + barrel re-export,行为零变化)。拆分后每个 view 独立可读 / 可测,范式与 bookings/ 对称。删除这个拆分会让 devices-page 继续是 1083 行单文件,与 bookings/ 范式分叉。

**为什么现在做**:第 7 次巡检(2026-07-30)候选 ②,**Strong + PERSISTING**。是「Ready for the same split template」—— bookings/ 已验证的拆分范式可直接套用,风险最低(纯 locality move,git mv 保留历史,零行为变更)。与候选① chat-page 同批规划,三个前端结构重构形成一致的 folder 范式。

---

## 2. Solution(对齐 to-spec)

完全镜像 `bookings/` 已验证的拆分模板,把 devices-page 拆成 **devices/ 文件夹**:

- `devices-page.tsx`(barrel re-export)+ `index.tsx`(二叉路由)—— 双 entry 对齐 bookings
- `store-view.tsx` + `hq-view.tsx` —— 双视图独立
- `device-dialogs.tsx` —— 4 共享 Dialog(对应 `bookings/shared-dialog.tsx`)
- `device-status-meta.ts`(纯数据)+ `shared.tsx`(React 显示原语 + 函数)—— 按职责拆,对齐 bookings
- `__tests__/store-view.test.tsx` + `hq-view.test.tsx` —— 补单测,对齐 bookings 测试范式

**核心洞察**:devices-page 的结构本来就健康(双视图 + 共享 Dialog + helper 都是 module-level),只是「文件未拆」这一维 friction。这是纯 locality move —— 不改任何逻辑,只移动代码到对称的文件夹结构,让 devices/ 与 bookings/ 范式一致,并补上缺失的单测。

---

## 3. User Stories(对齐 to-spec)

- 作为 **store 门店角色**(owner/admin/member),我在设备页看到的 CRUD 行为**零变化**(纯结构重构)
- 作为 **平台角色**(super_admin/hq_staff),我的跨租户 panorama 写 + tenantId 传递**零变化**
- 作为 **开发者**,我改 StoreView 的 CRUD 只读 `store-view.tsx`(~263 行),不必在 1083 行里定位
- 作为 **开发者**,我改 HqView 的跨租户写只读 `hq-view.tsx`,与 StoreView 解耦
- 作为 **开发者**,我改 4 个 Dialog 只读 `device-dialogs.tsx` 一处(两视图共享)
- 作为 **开发者**,我能给 StoreView/HqView 写单测(目前零单测),回归有保护
- 作为 **未来加功能的开发者**,给 devices 加新交互只需在对应 view 文件改,范式与 bookings 一致
- 作为 **未来巡检 agent**,我看到 devices/ 与 bookings/ 结构对称,不再标「单文件膨胀」候选

---

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.0 grill 5 决策汇总(一次一问共识)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| **D1** | 拆分目标结构 | **完全镜像 bookings/** | devices/ 文件夹 + 双 entry(barrel + index)+ view + dialogs + helper + tests;与 bookings 结构完全对称,认知负担最低 |
| **D2** | 4 共享 Dialog 归属 | **device-dialogs.tsx** | 对应 `bookings/shared-dialog.tsx`;4 Dialog 已被 StoreView+HqView 双视图共享(各调 4 次),放共享模块符合现有调用模式 |
| **D3** | 共享 helper 拆分 | **按职责拆两文件** | 纯数据(STATUS_META/STATUS_OPTIONS/NONE)→ `device-status-meta.ts`(对应 `bookings/status-meta.ts`);React 组件(StatusSelect/StatusBadge)+ 函数(customerNameOf)→ `shared.tsx`(对应 `bookings/shared.tsx`) |
| **D4** | 测试范围 | **store+hq 两测试** | 对齐 `bookings/store-view.test` + `hq-view.test`;补现有零单测缺口;StoreView/HqView 已是 module-level,测试面已存在只是没写 |
| **D5** | router import 路径 | **devices/devices-page.tsx barrel** | 对齐 `bookings/bookings-page.tsx` + ① chat-page 的 D9;App.tsx L37 改 `@/pages/devices-page` → `@/pages/devices/devices-page` |

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | **0** | 纯前端重构,零后端零 schema 零 API |
| 数据库迁移 | **0** | 无 |
| 前端文件改动 | **8 新建 + 1 改 + 1 删** | 新建:`devices/devices-page.tsx`(barrel)+ `devices/index.tsx`(路由)+ `devices/store-view.tsx` + `devices/hq-view.tsx` + `devices/device-dialogs.tsx` + `devices/device-status-meta.ts` + `devices/shared.tsx` + `devices/__tests__/{store,hq}-view.test.tsx`;改:`App.tsx`(import 路径);删:旧 `pages/devices-page.tsx` |
| 新增测试类 | **2** | store-view.test.tsx + hq-view.test.tsx |
| Skill / Hook / 配置 | **0** | 无 |

> **git mv 保留历史**:主组件用 `git mv` 拆分到对应文件(bookings-page-split 已验证此范式保留 blame)。

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(纯前端)
- 是否修改现有租户隔离逻辑? **NO**(前端只是展示层;HqView 的跨租户写靠后端 `require_cross_tenant_viewer` 守卫,前端 `tenantId` prop 传递逻辑原样保留)
- 是否引入跨租户访问点? **NO**(`isSuperAdmin`/`isHQStaff` 路由判断原样搬迁,HqView 的 panorama 数据来自 `useDevicesAll()`,守卫不变)
- 验证:hq-view.test.tsx 覆盖跨租户写守卫(tenantId 传递 + super_admin/hq_staff 才见 HqView)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(纯前端)
- 是否影响 graph.py 工具内 check? **NO**
- scope 闸门:不涉及

### 4.4 数据库表设计 checklist

**N/A** —— 纯前端重构,无表改动。

### 4.5 其他实施决策

- **ModelOption type**(L137 forward declaration):`type ModelOption = { id: string; name: string }` 是 device-models dropdown 的局部类型,随 StoreView/HqView 移到对应 view 文件(谁用谁留,或放 shared.tsx 若两视图都用 —— 实施时确认,倾向放 shared.tsx 因两视图的 model dropdown 结构相同)。
- **modelMap useMemo**(L170):StoreView 的 `model_id → live model` 映射,留 StoreView 内部(只它用)。
- **零行为变更约束**:所有逻辑原样搬迁,只改文件位置 + import 路径。不引入 useMemo/useCallback 优化(纯 locality move)。
- **Dialog 的 tenantId prop 机制保留**:4 Dialog 的 `tenantId` 参数(StoreView 传 undefined → backend 用 user.tenant_id;HqView 传目标 id)是 platform-cross-tenant-write 的核心 adapter,原样保留,只改文件位置。

---

## 5. Testing Decisions(对齐 to-spec)

### 测试 seam

| Seam | 层级 | 测什么 | 先例 |
|---|---|---|---|
| **seam A: `StoreView` 组件** | 组件级 | `renderWithProviders` + `vi.mock("@/hooks/queries")`,断言列表渲染 + CRUD 按钮权限守卫 + Dialog 弹出 | `bookings/store-view.test.tsx` |
| **seam B: `HqView` 组件** | 组件级 | mock `useDevicesAll`,断言 panorama 列表 + 跨租户写守卫(tenantId 传递) | `bookings/hq-view.test.tsx` |

**seam 总数 = 2**,都是组件级(StoreView/HqView 已是 module-level,测试面已存在)。不测 DevicesPage 整体(二叉路由逻辑简单,由两个 view 测试覆盖)。

### store-view.test.tsx 覆盖(对齐 store-view.test 范式)

- `renderWithProviders` + `vi.mock("@/hooks/queries")` + `vi.mock("@/components/auth/auth-context")`
- 列表渲染:devices 数组 → 渲染对应行(StatusBadge 状态徽章正确)
- 空状态:devices = [] → 显示空状态
- 创建 Dialog:点「新建」→ DeviceCreateDialog 弹出 → 提交 → useCreateDevice 被调
- 编辑/删除按钮守卫:owner 可见 canUpdate/canDelete;member 只读(按钮隐藏/禁用)
- model dropdown:ModelOption 投影渲染正确

### hq-view.test.tsx 覆盖(对齐 hq-view.test 范式,**v2 补 tenantId 断言接缝**)

- mock `useDevicesAll`(返 `DeviceHqRead[]`)
- panorama 列表渲染(跨租户 device)
- **跨租户写守卫 tenantId 断言(v2 关键)**:tenantId 传递有两条路径,测试要分别覆盖:
  - **Create/Edit 的 tenantId prop 路径**:Dialog 的 `tenantId` prop 流入 `DeviceCreate.tenant_id` body 字段 → 被 `useCreateDevice().mutateAsync(payload)` 吞掉。mock queries 后 mutateAsync 是空 stub,payload 不可直接观测。**必须引入 spy-on-children 接缝**(参照 `bookings/__tests__/hq-view.test.tsx` 的 `createDialogCalls` 范式):渲染 HqView 时用 spy 包装 DeviceCreateDialog,捕获它的 props(含 `tenantId`),断言 HqView 传了目标 id(非 undefined)。
  - **Bind/Delete 的 hook closure 路径**:`useBindDeviceCustomer(targetTenantId)` 的 targetTenantId 闭包绑定。mock 这个 hook,断言它被以 `targetTenantId` 参数调用(参照 bookings hq-view.test 断言 `startMut.mutateAsync` 调用的范式)。
- bind/unbind customer 的跨租户路径

### 测试金字塔

- **unit 2 文件**:store-view.test.tsx + hq-view.test.tsx
- **integration 0**:不新增
- **E2E 0**:不新增(现有 Playwright 覆盖回归)

### 覆盖率目标

- 项目前端基线:65 tests / 8 files;本任务后预期 ~75+ tests / 10 files(与 chat-page-split 叠加后 ~80+)
- 后端覆盖率不受影响

---

## 6. 切片规划(对齐 to-tickets)

> **切片策略**:纯前端 locality move,非功能开发。按「依赖顺序」分 2 片:先建文件夹 + 迁移组件(expand)→ 再补测试 + router 收尾。因是机械移动,可考虑单片完成,但分 2 片利于隔离风险 + 每片独立验证。

### Ticket 1: 建 devices/ 文件夹 + 迁移组件 + tenantId smoke + router(expand + migrate,**v2 前移 smoke**) ✅ 切片 1 完成

- **What to build**:新建 `devices/` 文件夹,用 git mv + 拆分把 devices-page.tsx 的内容迁到对应文件:`devices-page.tsx`(barrel)+ `index.tsx`(二叉路由)+ `store-view.tsx`(`export StoreView` + 其 modelMap)+ `hq-view.tsx`(`export HqView`)+ `device-dialogs.tsx`(4 Dialog)+ `device-status-meta.ts`(STATUS_META/STATUS_OPTIONS/NONE)+ `shared.tsx`(StatusSelect/StatusBadge/customerNameOf/ModelOption)。**v2 关键:StoreView/HqView 搬迁后必须加 `export`**(原代码是 module-level 但未 export)。改 App.tsx import 路径。删旧 `pages/devices-page.tsx`。**v2 前移 tenantId smoke**:此切片补一个最小 tenantId 回归测试(HqView 选 target → DeviceCreateDialog 收到 tenantId prop 非 undefined),避免 Ticket 1 完成时 tenantId 安全零捕获(现有 65 测试不含 devices)。
- **Blocked by**: 无(可立即开始)
- **文件清单**(8 新建 + 1 改 + 1 删 + 1 smoke):
  - 新建 `devices/devices-page.tsx` + `devices/index.tsx` + `devices/store-view.tsx` + `devices/hq-view.tsx` + `devices/device-dialogs.tsx` + `devices/device-status-meta.ts` + `devices/shared.tsx`
  - 改 `frontend/src/App.tsx`(import 路径)
  - 删 `frontend/src/pages/devices-page.tsx`
  - 新建 `devices/__tests__/hq-view-tenantid-smoke.test.tsx`(最小 tenantId 回归,v2 前移)
- **验证命令**:
  - `cd frontend && npm run build`(0 类型错误)
  - `cd frontend && npm test`(65 现有 + 1 smoke 全绿,零行为回归)
  - `cd frontend && npx oxlint .`(0 warning)
  - `grep -rn "from.*pages/devices-page['\"]" frontend/src/ | grep -v "pages/devices/"`(归 0,无残留旧路径)
- **AC**:
  - [x] devices/ 文件夹 7 文件就位(§10 `test -f` 清单全通过)
  - [x] StoreView/HqView 已加 `export`
  - [x] App.tsx import 指向 devices/devices-page
  - [x] 旧 pages/devices-page.tsx 已删
  - [x] 无残留旧路径 import(grep 归 0)
  - [x] **tenantId smoke 测试就位并绿**(HqView 传 tenantId 非 undefined)
  - [x] build 0 类型错误 + 83(81+2 smoke)测试零回归 + oxlint 0 warning

### Ticket 2: 补完整 store-view + hq-view 单测(测试 + 收尾)

- **What to build**:新建 `devices/__tests__/store-view.test.tsx` + 把 Ticket 1 的 smoke 扩展成完整 `hq-view.test.tsx`(加 spy-on-children 接缝覆盖 tenantId prop + hook closure 双路径),对齐 bookings 测试范式(renderWithProviders + mock queries)。覆盖列表渲染 + CRUD 守卫 + Dialog 弹出 + HQ 跨租户写守卫全路径。feature 收尾。
- **Blocked by**: Ticket 1
- **文件清单**(2 新建 + 1 改):
  - 新建 `devices/__tests__/store-view.test.tsx`
  - 改 `devices/__tests__/hq-view-tenantid-smoke.test.tsx` → 扩展为完整 `hq-view.test.tsx`(加 spy-on-children)
- **验证命令**:
  - `cd frontend && npx vitest run src/pages/devices/__tests__/`(两测试绿)
  - `cd frontend && npm run build && npm test && npx oxlint .`(全绿)
  - `./init.sh full`(全量后端 + 前端,零回归)
- **AC**:
  - [ ] store-view.test.tsx 覆盖列表渲染 + CRUD 守卫 + 创建 Dialog
  - [ ] hq-view.test.tsx 覆盖 panorama 渲染 + **跨租户写守卫双路径**(Create/Edit 的 tenantId prop via spy-on-children + Bind/Delete 的 hook closure)
  - [ ] 两测试全绿
  - [ ] npm run build + npm test + oxlint 全绿
  - [ ] ./init.sh full 全量绿(840 passed + 前端全绿)
  - [ ] feature 收尾:feature_list.json status → passing + evidence + sync-active + progress.md
  - [ ] 文档影响评估执行

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:
- 改动文件 8 新建 + 1 改 + 1 删 = 10(边界,< 10 的阈值,但接近)✓ 倾向不触发
- 涉及鉴权/权限/数据迁移/跨服务? **NO**(纯前端,HqView 跨租户写守卫原样保留)
- 涉及安全敏感操作? **NO**
- 涉及不可逆操作? **NO**

**结论**:**不触发对抗式审查**(纯前端 locality move,跨租户写守卫零变化)。走单模型 `/code-review` 双轴即可。但 `/code-review` 时**重点审查 HqView 的 tenantId 传递**(platform-cross-tenant-write 的核心 adapter,确保搬迁后 tenantId 仍正确区分 store/HQ 路径)。

---

## 8. Out of Scope(对齐 to-spec)

- ❌ **不改任何逻辑**:纯 locality move,StoreView/HqView/Dialog/helper 的实现原样搬迁
- ❌ **不引入 useMemo/useCallback**:本次只做文件拆分,不做性能优化
- ❌ **不碰 ModelOption 的 C 类 cast**:union-cast-split 已裁决(D2),`as ModelOption[]` 是字段投影 cast,保留原样
- ❌ **不改 device-models-page.tsx**:那是独立 page(443 行),不在本次范围
- ❌ **不碰候选① chat-page / 候选③ permission backfill**:独立 feature,本轮不碰
- ❌ **不重构 4 Dialog 的 tenantId 机制**:原样保留(platform-cross-tenant-write 的 adapter)

---

## 9. 风险与缓解(v2 补遗漏 + 修正)

| 风险 | 严重度 | 缓解 |
|---|---|---|
| HqView 跨租户写 tenantId 传递在搬迁后错乱(StoreView 误传 id / HqView 误传 undefined)→ 跨租户越权写 | **高** | **v2 前移**:Ticket 1 补 tenantId smoke 测试(不再等 Ticket 2);Ticket 2 hq-view.test 用 spy-on-children 覆盖 Create/Edit prop 路径 + hook closure 路径;`/code-review` 重点审 HqView |
| ~~Ticket 1 完成时 tenantId 安全零捕获~~(v1 已修正) | ~~高~~ → 已消除 | v2:Ticket 1 前移 tenantId smoke 测试,空窗消除 |
| **git mv 对单文件内多符号拆分 blame 会断**(v2 修正) | 中 | §4.1 修正:git mv 只对整文件 rename 保 blame;把一个文件的 7 个符号拆到 7 个新文件是复制+删除,blame 会断。接受这个代价(与 bookings-page-split 早期一致),靠 plan 文档记录迁移来源 |
| ModelOption type 归属判断错(两视图是否都用) | 低 | §4.5 已确认放 shared.tsx(grep 验证两视图都用) |
| Dialog 测试时序(DropdownMenu portal 异步) | 中 | 对齐 store-view.test 范式:`await findByText` + user-event@14 |
| 测试 mock 面大(useDevicesAll vs useDevices 区分) | 中 | hq-view.test mock useDevicesAll,store-view.test mock useDevices,两者隔离 |
| **barrel bundle 体积 / 循环依赖**(v2 补) | 低 | barrel re-export 已被 bookings 验证无 bundle 体积问题(tree-shaking + 同 chunk 合并);store-view.tsx/hq-view.tsx 都 import device-dialogs.tsx → shared.tsx,注意 import 顺序避循环(参照 bookings 已规避的顺序) |

---

## 10. 验收标准(同步 feature_list.json verification,v2 AC 客观化)

1. `cd frontend && npm run build` —— 0 类型错误
2. `cd frontend && npm test` —— 全绿(65 现有 + ~10 新增 = ~75+),零行为回归
3. `cd frontend && npx oxlint .` —— 0 warning 0 error
4. `grep -rn "from.*pages/devices-page['\"]" frontend/src/ | grep -v "pages/devices/"` —— 归 0(无残留旧路径)
5. **文件存在性清单(v2 客观化,替代「对称于 bookings/」)**:
   ```
   test -f frontend/src/pages/devices/devices-page.tsx && \
   test -f frontend/src/pages/devices/index.tsx && \
   test -f frontend/src/pages/devices/store-view.tsx && \
   test -f frontend/src/pages/devices/hq-view.tsx && \
   test -f frontend/src/pages/devices/device-dialogs.tsx && \
   test -f frontend/src/pages/devices/device-status-meta.ts && \
   test -f frontend/src/pages/devices/shared.tsx
   ```
   全部存在(exit 0)
6. `./init.sh full` —— 后端 840 passed + 前端全绿,零回归
7. `grep -n "export function StoreView\|export function HqView" frontend/src/pages/devices/{store,hq}-view.tsx` —— 两个 view 已 export
8. hq-view.test 覆盖 tenantId 传递**双路径**(Create/Edit prop via spy-on-children + Bind/Delete hook closure,跨租户写守卫契约)

---

## 11. 不越界声明

本次改动**只**涉及 `frontend/src/pages/devices-page.tsx` 的结构拆分(拆成 devices/ 文件夹下的 barrel + 路由 + view + dialogs + helper + tests)+ `App.tsx` 一行 import 路径;

**不**触碰:
- 后端任何文件(app/ 零改动)
- 数据库 / schema / migration
- bookings/ 现有结构(只对齐范式,不改)
- 任何 API 端点 / 类型定义(`api/types.ts` / `api/endpoints.ts` / `hooks/queries.ts` 零改动)
- 4 Dialog 的 tenantId 机制(原样保留)
- ModelOption 的 C 类 cast(union-cast-split 已裁决保留)
- device-models-page.tsx(独立 page)
- 候选① chat-page / 候选③ permission backfill(独立 feature)
