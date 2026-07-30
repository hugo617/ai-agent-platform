# 计划:前端 customers-page 拆 store-view/hq-view(镜像 bookings/devices/chat split 范式)

> **状态**: ✅ passing(2026-07-30,切片 01 + 02 全完成 + code-review 双轴通过)
> **feature id**: `customers-page-split` · **priority**: 79 · **area**: 工程化
> **来源**: 第 8 次代码健康巡检(`~/.cache/ai-agent-platform-architecture-reviews/2026-07-30-v2.html` 候选 ④)
> **范式先例**: bookings-page-split(65)/ union-cast-split(75) 切片03 / chat-page-split(76) / devices-page-split(78)

---

## §0 背景与动机

`frontend/src/pages/customers-page.tsx`(834 行)是 **store-vs-hq 双视图范式第 4 个未拆实例**(前 3 个:bookings/devices/chat 已全部 passing)。

现状:单文件 4 组件 —— `CustomersPage`(8 行 route)→ `StoreView`(405 行,本店 CRUD)+ `HqView`(172 行,跨店聚合只读)+ `CustomerUsageDialog`(89 行,跨 view 共享)+ `Metric`(19 行)。

**friction**(deletion test 通过):
1. **locality 差**:store CRUD 与 hq 跨店聚合是两个独立 read 模型(连 endpoint 都分 `fetchCustomerProfiles` store / `fetchCustomers` HQ),却挤一个文件。
2. **不可测**:**零单测**,而所有已拆文件夹(bookings/chat/devices)都有 `__tests__/`。split 是解锁测试的前提。
3. **范式不统一**:第 4 个未拆实例,与已验证 3 次的 split 范式割裂。

**核心**:纯前端结构重构,**零行为变更**。完全镜像 bookings/devices split 范式,运行时行为零变化。

---

## §1 决策表(grill 结果)

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| D1 | 文件夹结构 | **建 `customers/` 文件夹 + 双 entry barrel** | 镜像 bookings(`index.tsx` route + `bookings-page.tsx` barrel) + devices + chat,范式第 4 实例 |
| D2 | CustomerUsageDialog 归属 | **独立文件 `customer-usage-dialog.tsx`** | 跨 store/hq 共享(store 传 `storeScoped` / hq 传 `storeScoped={false}`),不能塞任一 view。Metric 小组件留在该文件内(只它用) |
| D3 | 共享常量/helper 归属 | **`shared.tsx`**:`statusBadge` + `formSchema` + `FormValues`/`EMPTY_FORM` + `GENDERS`/`GENDER_LABEL`/`STATUSES` | 镜像 bookings/shared.tsx + devices/shared.tsx。statusBadge 跨 store/hq 用;schema/常量只 store 用但放 shared 对称 |
| D4 | tags-JSON 解析 | **抽纯函数 `parseTagsJson(raw): {tags, error}` 到 `shared.tsx`(或 `parse-tags.ts`)** | 用户决策「抽」。解锁不可测纯逻辑(像 chat/build-working-list)。3 边界:合法 JSON / 非法 JSON / 空字符串。StoreView 调它,onError 时 toast |
| D5 | 搜索过滤逻辑 | **各 view 自留 client-side filter** | store 和 hq 的 filter 字段不同(store: name+identity_key+remark+status / hq: name+identity_key),非共享,各自内联 |
| D6 | 切片粒度 | **2 切片**(镜像 devices-page-split) | 切片1 建文件夹+迁移+smoke;切片2 补完整测试收尾 |
| D7 | 测试 | **store-view.test.tsx + hq-view.test.tsx 双测试** | 镜像 devices(5 store + 8 hq) + bookings 范式 |

---

## §2 目标文件结构(镜像 bookings/devices)

```
frontend/src/pages/
├── customers-page.tsx              ← 改成 barrel(16 行,re-export from customers/index)
└── customers/                      ← 新建文件夹
    ├── index.tsx                   ← route 入口(3 行:isSuperAdmin? HqView : StoreView)
    ├── store-view.tsx              ← 本店 CRUD(从旧 StoreView 搬,~410 行)
    ├── hq-view.tsx                 ← 跨店聚合只读(从旧 HqView 搬,~175 行)
    ├── customer-usage-dialog.tsx   ← AI 用量 Dialog + Metric(从旧 CustomerUsageDialog+Metric 搬)
    ├── shared.tsx                  ← statusBadge + formSchema + FormValues + 常量 + parseTagsJson
    └── __tests__/
        ├── store-view.test.tsx     ← 切片2 补
        └── hq-view.test.tsx        ← 切片2 补
```

**App.tsx 改动**:L34 `import("@/pages/customers-page")` 路径**不变**(barrel 保路由零改动,镜像 bookings)。

---

## §3 parseTagsJson 纯函数设计(D4)

```typescript
// customers/shared.tsx
export type ParseTagsResult = {
  tags: Record<string, unknown> | undefined;
  error?: string; // 非法 JSON 时的错误文案
};

/** 解析客户档案的 tags-JSON 输入。空串/纯空白 → undefined(不修改)。 */
export function parseTagsJson(raw: string | undefined): ParseTagsResult {
  const trimmed = raw?.trim();
  if (!trimmed) return { tags: undefined };
  try {
    return { tags: JSON.parse(trimmed) as Record<string, unknown> };
  } catch {
    return { tags: undefined, error: "标签 JSON 格式错误" };
  }
}
```

StoreView 的 `buildPayload` 改调:
```typescript
const buildPayload = (values: FormValues) => {
  const { tags, error } = parseTagsJson(values.tags_json);
  if (error) { toast.error(error); return null; }
  return { ...values, tags };
};
```

**行为等价性**:原 buildPayload 用 `JSON.parse(raw)` + `catch { toast.error; return null }`;新实现错误路径文案逐字相同(「标签 JSON 格式错误」),合法/空路径行为不变。

---

## §4 零行为变更契约(不可违反)

1. **路由零改动**:App.tsx L34 `import("@/pages/customers-page")` 不变,barrel `export { CustomersPage } from "./customers/index"` 接管。
2. **运行时行为零变化**:store CRUD / hq 聚合 / usage dialog / tags 解析 / 搜索过滤 —— 全部逻辑逐字搬移,不改任何业务分支。
3. **toast 文案逐字不变**:`parseTagsJson` 的 error 文案 = 原 buildPayload 的 `「标签 JSON 格式错误」`。
4. **import 路径**:所有外部消费者(customers-page.tsx barrel)只 import `CustomersPage`,内部 view 互相 import 用相对路径(`./store-view`)。

---

## §5 实施切片

### 切片 01:建 customers/ 文件夹 + 迁移组件 + tenantId/role smoke(非末切片)✅ PR commit 347af5f

**expand 阶段,不 git mv**(镜像 chat-page-split 切片01/02 范式,跨目录 import 成立):

- [x] 1.1 新建 `customers/index.tsx`(route: `isSuperAdmin(me) ? <HqView/> : <StoreView/>`,从旧 CustomersPage L120-128 搬)
- [x] 1.2 新建 `customers/shared.tsx`(`statusBadge` + `formSchema` + `FormValues`/`EMPTY_FORM` + `GENDERS`/`GENDER_LABEL``STATUSES` + `parseTagsJson` 纯函数)
- [x] 1.3 新建 `customers/customer-usage-dialog.tsx`(`CustomerUsageDialog` + `Metric` 从旧文件搬,内部 import Metric)
- [x] 1.4 新建 `customers/store-view.tsx`(从旧 StoreView L134-538 搬,改调 `parseTagsJson`,import shared 的 schema/常量/statusBadge,import customer-usage-dialog)
- [x] 1.5 新建 `customers/hq-view.tsx`(从旧 HqView L659-830 搬,import shared 的 GENDER_LABEL/statusBadge,import customer-usage-dialog)
- [x] 1.6 **`git mv pages/customers-page.tsx → pages/customers-page.tsx`(原地保留改内容)**:customers-page.tsx 改成 barrel(`export { CustomersPage } from "./customers/index"`,镜像 bookings-page.tsx)
- [x] 1.7 App.tsx 不改(barrel 保路径);grep 确认无其他 `pages/customers-page` 残留外部引用
- [x] 1.8 新建 `customers/__tests__/hq-view.test.tsx` smoke(2-3 tests):route 渲染 super_admin → HqView / 非 super_admin → StoreView(镜像 devices 切片1 v2 smoke 前移,消除空窗)
- [x] 1.9 **验证**:`npm run build` 0 错 + `npm test` 全绿(基线 + smoke)+ `oxlint` 0/0 + grep `pages/customers-page` 外部 import 残留 = 0 + customers/ 文件夹 6 文件

**切片 01 完成标志**:customers/ 文件夹 6 文件就位 + 旧 customers-page.tsx 变 barrel + smoke 锁住 route 分支 + build/test 全绿。

### 切片 02:补完整 store-view + hq-view 单测(末切片)✅ commit 85a969a + code-review 修复 8356c64

- [x] 2.1 新建 `customers/__tests__/store-view.test.tsx`(镜像 devices/store-view.test.tsx 范式,~5-6 tests):
  - [x] 2.1.1 列表渲染(profile name / identity_key / status 徽章 / gender 标签)
  - [x] 2.1.2 空态(无 profile → EmptyState)
  - [x] 2.1.3 member 只读守卫(canCreate=false → 无「新增」按钮 + 无操作列)
  - [x] 2.1.4 owner 创建 Dialog 填表提交触发 useCreateCustomerProfile(**断言 payload tags 经 parseTagsJson 正确解析**)
  - [x] 2.1.5 编辑菜单触发(openEdit 填充 form + 提交触发 updateMut)
  - [x] 2.1.6 删除菜单触发(deleteMut.mutateAsync 被调)
- [x] 2.2 扩展 `hq-view.test.tsx`(切片1 smoke → 完整 ~5-6 tests):
  - [x] 2.2.1 跨店表渲染(customer name / identity_key / profile_count 徽章 / gender)
  - [x] 2.2.2 空态
  - [x] 2.2.3 行展开(toggle → 显示 profiles 明细子行,含 tenant.name + statusBadge)
  - [x] 2.2.4 搜索过滤(?search= 过滤 name/identity_key)
  - [x] 2.2.5 AI 用量按钮触发(setUsageTarget → CustomerUsageDialog storeScoped={false})
- [x] 2.3 新建 `customers/__tests__/parse-tags.test.ts`(D4 纯函数,3 边界用例):
  - [x] 2.3.1 合法 JSON `{"level":"vip"}` → {tags: {level:"vip"}}
  - [x] 2.3.2 非法 JSON `{broken` → {tags: undefined, error: "标签 JSON 格式错误"}
  - [x] 2.3.3 空字符串/纯空白 → {tags: undefined}(无 error)
- [x] 2.4 **验证**(plan §10 AC 全绿):`npm test` 全绿(基线 + 5 store + 5 hq + 3 parse-tags)+ `npm run build` 0 错 + `oxlint` 0/0 + grep 残留旧路径 = 0 + `./init.sh full` 后端零回归(纯前端)
- [x] 2.5 **feature 收尾仪式**(three-tier §4 第1-8步):见 §6

**切片 02 完成标志**:store-view 5-6 tests + hq-view 5-6 tests + parse-tags 3 tests 全绿 + feature 收尾。

---

## §6 feature 收尾仪式(末切片,three-tier §4 第1-8步)

- [x] ① `./init.sh full` 全绿 + 前端 npm test + build + oxlint 全绿
- [x] ② `feature_list.json` status `not_started → passing` + evidence 4 条(切片1/2 + parseTagsJson + 收尾条)
- [x] ③ `./scripts/sync-active-features.sh` 刷新 active 视图
- [x] ④ `progress.md` 顶部 frontier 清空 + 本条记录
- [x] ⑤ `clean-state-checklist` 逐项 ✅
- [x] ⑥ 文档影响评估:纯前端结构重构,**无新增/改动文档**(AGENTS.md/项目指南/铁律均不受影响)
- [x] ⑦ **末切片依赖解锁扫描**:无任何 feature `depends_on` 指向 customers-page-split(纯重构无下游)→ 无需推进
- [x] ⑧ 分支清理:PR 合并后删本地+远端 feature 分支

---

## §7 风险点

| 风险 | 缓解 |
|---|---|
| parseTagsJson 行为偏离原 buildPayload | 错误文案逐字锁定「标签 JSON 格式错误」;3 边界测试覆盖 |
| CustomerUsageDialog 跨 view 共享时 storeScoped prop 传错 | smoke 测试锁住 store=true / hq=false 两条路径 |
| Metric 组件作用域 | 留 customer-usage-dialog.tsx 内(非 export,只它用),不外溢 shared |
| App.tsx 路由 barrel 失效 | grep 验证 `pages/customers-page` import 路径不变 + build 通过 |

---

## §8 AC 验收标准(plan §10 统一验收)

1. customers/ 文件夹 7 文件(index/store-view/hq-view/customer-usage-dialog/shared + 2 测试 + parse-tags 测试)
2. 旧 customers-page.tsx 变 barrel(≤16 行,re-export)
3. App.tsx 零改动
4. `npm run build` 0 类型错误
5. `npm test` 全绿(基线 + store 5-6 + hq 5-6 + parse-tags 3)
6. `oxlint` 0 warning 0 error
7. grep `pages/customers-page` 外部 import 残留 = 0(除 barrel 自身)
8. `./init.sh full` 后端零回归(纯前端改动)
9. 零行为变更:store CRUD / hq 聚合 / usage dialog / tags 解析 全部逻辑等价
