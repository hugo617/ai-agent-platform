# 计划:设备型号目录管理页(super_admin 后台前端页)

> **状态**:草案 v1(已拆 2 个实施切片,待 `/implement` 推进)
> **feature_list.json ID**:`device-models-admin-ui`(priority 66,设备功能系列补遗)
> **前置**:`device-models-crud`(priority 61,已 passing)—— `DeviceModel` 表 / 后端 CRUD API 全齐
> **同类先例**:`plan-groups-api.md` + `frontend/src/pages/groups-page.tsx`(同平台级 super_admin 资源范式) / `plan-devices-crud-ui.md`(同设备系列前端范式)
> **依赖链**:device-models-crud ✅ → **device-models-admin-ui(本文档,纯前端补遗)**

---

## 1. Problem Statement

**缺口溯源**:feature 61(`device-models-crud`)的 verification 字段明确写了「前端:后台型号管理页(路由 `/device-models`,`RequireSuperAdmin` 守卫)」,但其 evidence 最后一条范围决策把它剥离给了 62;62(`devices-crud-ui`)实际只做了门店「设备入库」下拉,从未交付 super_admin 管理页。

**后果**:`device_models` 表无任何 UI 可建型号(super_admin 现在只能 curl),门店入库下拉永远为空,链路从源头断掉。后端 CRUD 已端到端实测通过(2026-07-25 Session:super_admin token 建型号 → 门店 owner 建设备 → 列表回读全通),**本 feature 仅做前端**。

**为何现在做**:这是 61 的范围漂移修复,补齐设备功能系列最后一环,让 super_admin 有图形化入口维护型号目录。

---

## 2. Solution

在 super_admin 后台新增 `/device-models` 路由 + `DeviceModelsAdminPage` 页面,复用既有 `RequireSuperAdmin` 守卫 + 平台 nav 分组。页面提供完整 CRUD(列表 / 新增 / 编辑 / 软删),`specs` 自由 JSON 字段用结构化 key-value 行编辑器编辑(支持 string/number/boolean 多类型),`unit_cost` 货币格式呈现。对齐 `groups-page.tsx` 平台级资源前端范式,但 `specs` 编辑器是本 feature 超出 groups 范式的新组件(`KeySpecRows`)。

---

## 3. User Stories

- 作为 **super_admin**,我想在后台侧边栏看到「设备型号」入口,以便快速进入型号目录管理页(不必 curl)
- 作为 **super_admin**,我想新增设备型号(填名称 / 品牌 / 供应商 / 单位成本 / 规格),以便门店 owner 入库时有型号可选
- 作为 **super_admin**,我想编辑已有型号(改规格、调成本),以便目录随业务演进
- 作为 **super_admin**,我想软删型号(误建 / 退役),以便目录保持整洁(软删后名称可被新型号复用,已被设备引用的型号不会被硬删 —— 后端 `ondelete=RESTRICT` 是死保险绳,真实守卫是软删语义)
- 作为 **super_admin**,我想按名称 / 品牌搜索型号,以便表变大时快速定位
- 作为 **门店 owner / admin / member**,我**不**应该看到此入口 / 此路由(非 super_admin 重定向到首页),以便平台级资源与租户级资源严格隔离

---

## 4. Implementation Decisions

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | **0** | 后端 CRUD 全齐(`app/api/v1/device_models.py` / `app/schemas/device_model.py` / `app/services/device_model_service.py`),本 feature 不触碰 |
| 数据库迁移 | **0** | 无 schema 变化 |
| 前端文件改动 | **6 改 + 2 新** | 改:`api/types.ts` / `api/endpoints.ts` / `hooks/queries.ts` / `App.tsx` / `components/layout/nav-items.ts` / `lib/format.ts`(可选,见 §4.5)。新:`pages/device-models-page.tsx` / `components/ui/key-spec-rows.tsx` |
| 新增测试类 | **1** | `components/ui/key-spec-rows.test.tsx`(vitest 单测,序列化逻辑) |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO** —— `device_models` 是**平台级**表(无 `tenant_id`),与 `Group` 同范式
- 是否修改现有租户隔离逻辑? **NO** —— 本 feature 仅前端
- 是否引入跨租户访问点? **NO** —— 本 feature 反而**收紧**:只有 super_admin 能进此页(hq_staff 都不能,因为型号目录维护是平台级写权限)。后端 `POST/PUT/DELETE` 已守 `require_super_admin()`,前端守卫与之对齐
- 验证:本 feature 无后端测试,仅前端类型检查 + build。多租户语义已被 61 的后端测试覆盖(`tests/test_device_models_api.py`)

### 4.3 权限影响评估

- 是否新增 permission code? **NO** —— `device_models` **故意不在** `DEFAULT_*_PERMS` 和 casbin seed 里(对齐 groups 平台级资源范式)。守卫**不走 casbin**,直接 `require_super_admin()` + 前端 `RequireSuperAdmin`
- 是否修改 `DEFAULT_*_PERMS`? **NO**
- 是否影响 60+ 处 `require_permission` caller? **NO** —— `device_models` 不走 `require_permission`
- 是否影响 graph.py 工具内 check? **NO**
- scope 闸门:不涉及 API Token

### 4.4 数据库表设计 checklist

**不适用** —— 本 feature 无表改动。`device_models` 表已在 61 落地(含 `is_deleted` + 部分唯一索引 `uq_device_models_name_active` + `Numeric(12,2)` unit_cost + `JSONB` specs)。

### 4.5 其他实施决策

| 议题 | 决策 | 理由 |
|---|---|---|
| **路由 + 守卫** | `/device-models` + `RequireSuperAdmin`(裸挂,非 `RequireApiPermission`) | 对齐 `/tenants` 范式(`App.tsx:162-165`);后端写端点已 `require_super_admin()`,前端守卫是 UX 层 |
| **nav 挂载位置** | 「平台」分组新增第 3 项,`platformOnly: true`,放在 `/tenants` 和 `/billing/admin` 之间或之后 | 对齐现有 2 个平台级 nav 项的 `platformOnly` 范式(`nav-items.ts:144-147`)。普通租户角色 `canSeeItem` 直接返 false |
| **菜单图标** | `lucide-react` 的 `Cpu`(平台级资源目录语义,落定单选) | 参照 `/tenants` 用 `Store`、`/billing/admin` 用 `Coins` 的图标语义惯例;`Cpu` 与 `/devices` 的 `Monitor` 区分度更高,且型号本质是硬件规格目录 |
| **前端 types 命名** | 新增 `DeviceModelRead` / `DeviceModelCreate` / `DeviceModelUpdate`,**与现有 `DeviceModelPublic` 并存** | `DeviceModelPublic`({id,name,specs})是门店下拉视图,本 feature 用完整字段 {id,name,brand,supplier,unit_cost,specs,created_at,updated_at};二者不冲突,共存于 `api/types.ts` |
| **`unit_cost` TS 类型** | `string`(后端 `Decimal` 序列化到 JSON 是 string 如 `"299.00"`) | 后端 `Numeric(12,2)` 经 FastAPI 默认 JSON encoder 落到前端是字符串。表单 Input text + zod `.refine(v => /^\d+(\.\d{1,2})?$/.test(v) && Number(v) >= 0)`;**列表用内联 `` `¥${Number(m.unit_cost).toFixed(2)}` ``**(不用 `formatCurrency`,见下行) |
| **`specs` 编辑器** | 新增 `KeySpecRows` 组件,每行 = key Input + value Input + type Select(string/number/boolean) + 删除按钮 | 后端 schema 是 `dict[str, Any]`,堵住 string 单类型会与契约不一致。type Select 按 type 序列化:string 原样、number → `Number(v)`、boolean → `v === "true"` |
| **`specs` 序列化边界** | 空 key 过滤;重复 key 后者覆盖前者(不报错,因为 dict 字面量语义就是后者覆盖) | 边界低、可预测;JSON 字面量赋值也是覆盖语义 |
| **`specs` 反序列化** | 编辑 Dialog 打开时从 `model.specs` 反推每行 `{key, value, type}`:typeof 探测(string/number/boolean)→ type 选项锁定 + value 文本化(boolean → "true"/"false") | 让用户改完保存 round-trip 不丢类型 |
| **`specs` 列表摘要** | 取 `specs.form_factor`(后端惯例 key,驱动门店下拉分组),无则 `JSON.stringify(specs).slice(0, 40) + "…"` | form_factor 是后端 schema doc 点名 convention-used 的 key;无则兜底截断 |
| **`brand` datalist 联想** | Input + 原生 `<datalist>`,options 从当前型号列表 unique brands 提取 | HTML 原生无需新组件;减少重复输入;不影响后端契约(仍是 str \| None) |
| **`supplier`** | 纯 Input,无联想 | YAGNI;supplier 通常自由文本 |
| **列表搜索框** | 顶部一个 Input + client-side filter:`list.filter(m => [m.name, m.brand, m.supplier].some(x => x?.toLowerCase().includes(q.toLowerCase())))` | device_models 预期表小,client filter 足够;参照 groups-ui 无分页范式 |
| **列表分页** | **无** | 同 groups-ui / devices-page;后端 GET 不分页,YAGNI |
| **表单方案** | react-hook-form + zodResolver(参照 groups-page.tsx 范式),`KeySpecRows` 用 `Controller` 包裹纳入表单 state | groups-page 已有完整 react-hook-form + zod 范式可抄;specs 是动态行数组,用 Controller 隔离内部 state |
| **`specs` 必填?** | **否**(可空,后端 default `{}`) | 与后端 schema 一致;空 specs 合法(简单型号无需规格) |
| **软删确认话术** | 「确定删除型号「{name}」?该操作为软删除,已被设备引用的型号不会被硬删(仅从目录中隐藏),名称可被新型号复用。」 | 准确传达软删语义,避免用户误以为硬删 |
| **写按钮守卫** | 页内不再加 `canManage` 判断(整页只 super_admin 能进,守卫已在路由层) | 与 groups-page 不同:groups 允许租户 owner 只读,本页非 super_admin 直接重定向,故无只读分支 |
| **缓存失效** | mutation 失效 `qk.deviceModels`(已有 key,与门店下拉共用) | create/update/delete 都会让门店入库下拉同步刷新(型号增减),共用 key 是正确语义 |
| **`unit_cost` 列表呈现** | **内联** `` `¥${Number(m.unit_cost).toFixed(2)}` ``,**不复用** `formatCurrency` | `formatCurrency`(`lib/format.ts:65`)实现是 `toFixed(4)`(为 token/wallet cost 设计的 4 位小数),`unit_cost` 是 `Numeric(12,2)` 货币(2 位小数),复用会渲染 `¥299.5000`。改既有 helper 有副作用(其他调用方依赖 4 位),故本 feature 内联 2 位小数渲染。表单 Input 用 raw string 不格式化,只有列表展示格式化 |
| **GET 列表 hook 命名** | 新增 `useDeviceModelsAdmin()`(返回 `DeviceModelRead[]`,完整字段),**不**改既有 `useDeviceModels()`(仍返 `DeviceModelPublic[]` 供门店下拉) | 两个 hook 拉同一端点但 type 不同:super_admin 拿完整字段(含 unit_cost)、门店下拉只需 {id,name,specs}。cache key 共用 `qk.deviceModels`,因为同一 URL 数据;type 区别仅在 caller 端 narrow |

### 4.6 已查证事实(避免 EP3 返工)

| 事实 | 来源 |
|---|---|
| 后端 `POST/PUT/DELETE /device-models` 守 `require_super_admin()`,`GET` 开放按 `platform_role` 分叉(super_admin **和 hq_staff** 都拿 `DeviceModelRead` 全字段,门店角色拿 `DeviceModelPublicRead`) | `app/api/v1/device_models.py:36-104` + `app/services/device_model_service.py` |
| `DeviceModelCreate` 字段:`name(min1,max200) / brand(可空,max200) / supplier(可空,max200) / unit_cost(Decimal,必填) / specs(dict 默认 {})` | `app/schemas/device_model.py:17-31` |
| `DeviceModelUpdate`:全字段可选(部分更新语义),`specs` 是 whole-replace | `app/schemas/device_model.py:34-39` |
| `DeviceModelRead`:继承 base 全字段 + `id/created_at/updated_at` | `app/schemas/device_model.py:42-49` |
| `RequireSuperAdmin` 已存在,`me.platform_role !== "super_admin"` → `Navigate to="/"` | `frontend/src/components/auth/require-super-admin.tsx:14-31` |
| 平台 nav 分组当前 2 项(`platformOnly: true`):`/tenants` `/billing/admin` | `frontend/src/components/layout/nav-items.ts:144-147` |
| `useApiMutation<TVars, TData>(fn, [invalidateKeys])` 签名 | `frontend/src/hooks/queries.ts:260` |
| `qk.deviceModels` key 已存在(供门店 `useDeviceModels` 用) | `frontend/src/hooks/queries.ts:208` |
| `formatCurrency(n)` 实现是 `toFixed(4)`(token/wallet cost 用),**不适合** `Numeric(12,2)` 货币列 → 本 feature 内联 `toFixed(2)` | `frontend/src/lib/format.ts:60-67` |
| react-hook-form + zodResolver + Controller 范式 | `frontend/src/pages/groups-page.tsx:1-127` |

---

## 5. Testing Decisions

- **测试金字塔**:本 feature 仅前端,unit 1 个(`KeySpecRows` 序列化)+ 集成 0(参照 devices-page 未测)
- **覆盖目标**:`KeySpecRows` 的核心序列化逻辑必须测:
  - 空 key 过滤
  - 重复 key 后者覆盖
  - string/number/boolean 按 type 序列化(number → `Number("80")`、boolean → `"true" === true`)
  - 反序列化:从 `{form_factor:"ring", threshold:80, enabled:true}` 反推 3 行 + 正确 type
- **不做**:page 级集成测(对齐 devices-page 现状,且 mock useAuth/useQuery/router 成本高)
- **回归**:跑 `tests/test_device_models_api.py` 确认后端 714 测试中相关用例仍全绿(本 feature 不改后端,预期无影响)
- **构建验证**:`cd frontend && npm run build` + `npx oxlint src/` 0 warnings

---

## 6. 切片规划(tracer-bullet)

> **切片原则**:每片切穿 types→endpoints→hooks→page→route→nav 全栈(本 feature 无后端),单片可独立 verify。
>
> 本节是**简表概览**,完整 acceptance criteria checklist 见文末「[实施切片](#实施切片2-个-tracer-bullet-垂直切片每个切片一个-context-window-完成)」段(EP3 实施时以文末详表为准勾选)。

### 切片 01 — 前端地基:types + endpoints + hooks
- **What to build**:补齐前端 API 层完整字段契约 —— 新增 `DeviceModelRead/Create/Update` 类型 + admin 版 fetch/create/update/delete 函数与 hooks
- **Blocked by**:无(frontier)
- **验证**:`tsc` 通过 + 切片 02 的依赖就绪

### 切片 02 — UI 层:page + 路由 + nav + `KeySpecRows` 组件
- **What to build**:落地可见的管理页 + 守卫 + 入口;`KeySpecRows` 是本 feature 新组件
- **Blocked by**:01(消费其 types/hooks)
- **验证**:build + oxlint + vitest + 手测

---

## 7. 对抗式审查段

**触发条件自评**:改动文件 6 改 + 2 新(< 10)、不涉及鉴权 / 权限 / 数据迁移 / 跨服务 / 安全敏感 / 不可逆操作。**不达复杂任务阈值,跳过对抗式审查段**。

> 但仍做轻量自评(EP2 收尾 gate 会跑):① `RequireSuperAdmin` 守卫是 UX 层,后端 `require_super_admin()` 才是硬边界(已落地);② `specs` whole-replace 语义与后端 `DeviceModelUpdate` 一致;③ 软删语义传达准确(已在话术里);④ `qk.deviceModels` 共用 key 会让门店下拉同步刷新(预期行为,型号增减本就该让下拉更新)。

---

## 8. Out of Scope(不越界声明)

- ❌ **不补 seed 脚本**(种子数据是 dev 体验问题,非产品能力,留给用户按需 curl 或独立 seed feature)
- ❌ **不进权限矩阵 UI**(`device_models` 不走 casbin,对齐 groups 平台级资源范式)
- ❌ **不重构现有 devices-page 的型号下拉**(已正常工作,`DeviceModelPublic` 类型不动)
- ❌ **不加分页 / 服务端搜索**(表预期小,client-side filter 足够)
- ❌ **不加导出 / 批量导入**(YAGNI,补遗范围外)
- ❌ **不补后端测试**(后端 CRUD 已被 device-models-crud 覆盖)
- ❌ **不补 page 级集成测**(对齐 devices-page 现状)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| `KeySpecRows` 序列化 / 反序列化逻辑 bug(类型 round-trip 丢精度) | 中 | vitest 单测覆盖空 key / 重复 key / 三类型序列化 / 反序列化 4 类 case |
| `unit_cost` Decimal→string→Number 转换精度问题(如 `"299.10"`) | 低 | `Number("299.10") === 299.1` 安全;**列表内联 `toFixed(2)`**(不用 `formatCurrency`,它 `toFixed(4)` 是 token cost 设计) |
| `specs` whole-replace 误删用户不想改的字段 | 中 | 编辑 Dialog 预填当前 specs(反序列化展示),用户主动删行才丢;话术不强调但行为可预测 |
| `qk.deviceModels` 共用 cache key 导致门店下拉突变刷新 | 低 | 实际型号增减本就该让下拉更新,共用是正确语义;react-query staleTime 30s 自然收敛 |
| **`qk.deviceModels` 同 key 异型**:super_admin 会话内,门店下拉 `useDeviceModels()`(声明 `DeviceModelPublic[]`)运行时收到完整 `DeviceModelRead[]` | 低 | 下拉只取 `id/name/specs` 不崩;此乃既有范式延续(`useDevices` 也这样,见 `queries.ts:417-428` 注释);不修(改要拆 key,影响门店 hook 签名,超补遗范围)。EP3 实施者知晓即可 |
| 非 super_admin 误进路由(直接输 URL) | 低 | `RequireSuperAdmin` 已重定向到 `/`;后端写端点 403 双保险 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. **前端路由 + 守卫**:新增 `/device-models` 路由 + `DeviceModelsAdminPage`,挂 `RequireSuperAdmin`(非 super_admin 重定向到 `/`)
2. **页面 CRUD**:列表(名称 / 品牌 / 规格摘要 / 单位成本 / 更新时间 / 操作)+ 新增 Dialog + 编辑 Dialog + 软删确认 Dialog
3. **前端导航**:平台分组下挂「设备型号」菜单项(`platformOnly: true`);普通租户角色看不到
4. **前端 hooks/endpoints**:`useDeviceModelsAdmin`(拉完整字段)+ `useCreateDeviceModel` / `useUpdateDeviceModel` / `useDeleteDeviceModel`(对应 POST/PUT/DELETE `/api/v1/device-models`,需 super_admin token)
5. **`KeySpecRows` 组件**:支持 string/number/boolean 三类型,空 key 过滤,重复 key 后者覆盖,vitest 单测全绿
6. **构建验证**:`cd frontend && npm run build` 通过 + `npx oxlint src/` 0 warnings + vitest 通过
7. **后端回归**:`tests/test_device_models_api.py` 仍全绿(本 feature 不改后端,预期无影响)

---

## 11. 不越界声明

本次改动**只**涉及前端 6 改 + 2 新(`api/types.ts` / `api/endpoints.ts` / `hooks/queries.ts` / `App.tsx` / `components/layout/nav-items.ts` / `pages/device-models-page.tsx` 新 / `components/ui/key-spec-rows.tsx` 新 / `components/ui/key-spec-rows.test.tsx` 新);**不**触碰后端(`app/`)、**不**触碰 alembic 迁移、**不**触碰 `device-models-crud` 已落地代码、**不**重构 `devices-page.tsx` 的型号下拉、**不**进权限矩阵 UI、**不**补 seed 脚本。

---

## 实施切片(2 个 tracer-bullet 垂直切片,每个切片一个 context window 完成)

> 切片原则:每切片是窄而全的垂直切片(types→endpoints→hooks→page→route→nav 闭环),不按层水平切。每切片可独立 verify。阻塞边明确,WIP=1 下一次一片。
>
> 实施节奏:一次一个切片,用 `/implement` 推进,切片间清 context。本 feature 仅前端 + 后端齐备,故切片粒度比 devices-crud-ui(7 片全栈)轻得多。

### 切片 01 — 前端地基:types + endpoints + hooks(无 blocker,frontier)

**Blocked by:** 无 —— 可立即开工

**What it delivers:** 前端 API 层完整字段契约就位 —— `DeviceModelRead/Create/Update` 类型、admin 版 CRUD endpoints、四个 hooks(useDeviceModelsAdmin + useCreate/Update/DeleteDeviceModel)。本片**不含**任何 UI,产物是「切片 02 的 page 能直接 import 这些符号编译通过」。

**Acceptance criteria:**
- [x] `frontend/src/api/types.ts`:新增 `DeviceModelRead` / `DeviceModelCreate` / `DeviceModelUpdate` 三 interface,与后端 `app/schemas/device_model.py` 字段对齐(`unit_cost: string` 因 Decimal 序列化、`specs: Record<string, unknown>`);**保留**既有 `DeviceModelPublic`(门店下拉用,不动)
- [x] `frontend/src/api/endpoints.ts`:新增 `fetchDeviceModelsAdmin(): Promise<DeviceModelRead[]>` + `createDeviceModel(payload: DeviceModelCreate)` + `updateDeviceModel(id, payload: DeviceModelUpdate)` + `deleteDeviceModel(id): Promise<void>`,路径 `/device-models/` 与 `/device-models/{id}`
- [x] `frontend/src/hooks/queries.ts`:新增 `useDeviceModelsAdmin()`(queryKey 复用 `qk.deviceModels`,与门店下拉共用 cache);新增 `useCreateDeviceModel` / `useUpdateDeviceModel` / `useDeleteDeviceModel` 三个 `useApiMutation`,失效 `qk.deviceModels`
- [x] `cd frontend && npx tsc --noEmit` 通过(无类型错;此时 page 还没建,hooks 暂未被消费但导出即可)
- [x] `npx oxlint src/` 0 warnings

---

### 切片 02 — UI 层:page + 路由 + nav + KeySpecRows 组件(blocked by 01)

**Blocked by:** 01(消费其 types/endpoints/hooks)

**What it delivers:** super_admin 在后台侧边栏点「设备型号」进入管理页,能看到完整型号列表(可搜索),新增 / 编辑 / 软删型号,`specs` 用结构化 key-value 行编辑器编辑(支持 string/number/boolean),`unit_cost` 货币格式。非 super_admin 进 `/device-models` 重定向到 `/`。

**Acceptance criteria:**
- [ ] `frontend/src/components/ui/key-spec-rows.tsx` 新增:`KeySpecRows` 组件,props `{ value: SpecRow[]; onChange: (rows: SpecRow[]) => void }`,`SpecRow = { key: string; value: string; type: "string"|"number"|"boolean" }`;内部 render 每行 key Input + value Input + type Select + 删除按钮 + 底部「+ 添加规格」按钮
- [ ] `KeySpecRows` 序列化函数 `serializeSpecs(rows): Record<string, unknown>`:空 key 过滤、重复 key 后者覆盖、按 type 序列化(string 原样 / number → `Number(v)` / boolean → `v === "true"`)
- [ ] `KeySpecRows` 反序列化函数 `deserializeSpecs(specs): SpecRow[]`:按 typeof 推断 type,number→type:"number"、boolean→type:"boolean" 且 value 文本化为 "true"/"false"、其他→type:"string"
- [ ] `frontend/src/components/ui/key-spec-rows.test.tsx`:vitest 单测覆盖①空 key 过滤 ②重复 key 后者覆盖 ③三类型序列化 ④反序列化 round-trip
- [ ] `frontend/src/pages/device-models-page.tsx` 新增:`DeviceModelsAdminPage` 组件,参照 `groups-page.tsx` 骨架(PageHeader + Card + Table + 3 Dialog),用 react-hook-form + zodResolver + Controller 包 `KeySpecRows`;列表列:名称 / 品牌 / 规格摘要(`specs.form_factor ?? JSON.stringify(specs).slice(0,40)+"…"`) / 单位成本(**内联 `` `¥${Number(m.unit_cost).toFixed(2)}` ``,不复用 `formatCurrency`**) / 更新时间 / 操作;顶部搜索框 client-side filter
- [ ] **brand datalist 联想**:brand Input 挂原生 `<datalist id="device-model-brands">`,options 从 `useDeviceModelsAdmin()` 已拉型号列表 unique brands 提取(`<option>{m.brand}</option>`,过滤 null/空)。`useMemo` 派生避免每次 render 重算
- [ ] `frontend/src/App.tsx`:lazy import `DeviceModelsPage` + 在 `<Route element={<RequireSuperAdmin />}>` 块内新增 `<Route path="/device-models" element={<DeviceModelsPage />} />`
- [ ] `frontend/src/components/layout/nav-items.ts`:`ITEMS` 数组「平台」段新增 `{ to: "/device-models", label: "设备型号", icon: Cpu, platformOnly: true }`
- [ ] `cd frontend && npm run build` 通过 + `npx oxlint src/` 0 warnings + `npx vitest run` 通过
- [ ] 手测(进 EP3 实施时跑):super_admin 登录 → 侧边栏见「设备型号」→ 列表 / 新增(填 specs 三类型) / 编辑(round-trip 类型保持) / 软删 → 普通租户角色无此入口 + 直接访问 `/device-models` 重定向到 `/`

---

### 切片依赖图

```
切片 01 (types+endpoints+hooks)  ── 无 blocker (frontier)
        │
        ▼
切片 02 (page+route+nav+KeySpecRows+test)
```

线性串行,无环,无并行。WIP=1 下一次一片,切片 01 完成进切片 02。

---

### EP2 收尾自检(进 EP3 前的轻量 gate)

- [x] **切片依赖图无环**:01 → 02 线性
- [x] **每片有 acceptance criteria**:01 有 5 条、02 有 15 条(含 brand datalist 联想 + KeySpecRows 组件/序列化/反序列化/单测/page/route/nav/构建/手测),均 `- [ ]` 可执行
- [x] **首片可立即开工**:切片 01 `Blocked by: 无`
- [x] **plan 主体决策已落定**:§4.5 决策表 18 行无 `TODO`/`待定`,§4.6 已查证事实 10 行落地
