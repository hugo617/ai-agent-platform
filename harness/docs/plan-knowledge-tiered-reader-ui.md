# 计划:知识库分级 Feature C — 前端三栏可视化阅读页

> **id**: `knowledge-tiered-reader-ui`
> **状态**: draft v1(EP2 回环产物,待 `/to-tickets` 拆切片后进 EP3)
> **优先级**: 88(当前最高 not_started frontier;depends_on `knowledge-tiered-backend` p89 ✅ passing 已解锁)
> **创建日期**: 2026-08-07
> **来源**: Session 197 `/grill-with-docs` 收敛 7 决策(G1-G7)+ 测试 seam 确认
> **承接**: [`plan-knowledge-tiered-overview.md`](./plan-knowledge-tiered-overview.md)(系列总纲,D1-D12 决策)+ [`plan-knowledge-tiered-backend.md`](./plan-knowledge-tiered-backend.md)(Feature B ✅ passing,已交付后端 API)

---

## 1. Problem Statement

`knowledge-tiered-backend`(Feature B)已交付三级权限 + 分类 + 下发的完整后端,但**前端仍是 p57 时代的纯列表页**(`frontend/src/pages/knowledge-page.tsx`,458 行单文件):

1. **无分类目录树**:所有 Document 平铺成一张表,无 scope 分区(平台下发/集团下发/本店)、无 category 主题分组(产品手册/FAQ/话术混在一起)。门店 owner 无法「一眼看出这是平台下发的/集团的/我自己加的」。
2. **无在线阅读器**:文档只能看名称/状态/分块数,要看内容得靠检索调试页的零散片段。无 Markdown 渲染、无目录大纲、无全文搜索高亮。
3. **scope 来源不可视**:`DocumentRead` 后端已有 `scope`/`group_id`/`category_id` 字段,但前端类型层(`types.ts`)未扩展,列表未展示来源标识,「门店处理得非常好」(D7 原话)无法兑现。
4. **类型层未对齐**:`useDocuments()` 无参(无 scope/category 过滤)、`useKnowledgeCategories` hook 不存在、`KnowledgeCategoryRead` 类型不存在 —— 三栏阅读的前置数据管线缺一截。

**用户痛点(承接 overview 背景)**:门店是最小 OPC 产业单元,门店 owner 需要一个「直觉式」的知识库入口 —— 打开就看到三栏(左:这店能看哪些分类 / 中:这分类下有哪些文档 / 右:这篇文档讲什么),并通过 scope 三色徽章一眼区分知识来源(平台🔴/集团🟡/本店🟢)。

**为什么现在做**:backend 已 passing(987 测试零回归),依赖解锁;WIP=1 下 reader-ui(p88)是当前最高优先级 not_started frontier,优先于 admin-ui(p87)。本 feature 是分级管理价值「落到门店眼睛里」的最后一公里。

---

## 2. Solution

把 `knowledge-page.tsx` 单文件重构成 `knowledge/` 文件夹,**镜像 `devices/` 的 barrel 三栏 page-split 范式**(`devices-page.tsx` barrel + `index.tsx` 编排 + view 文件 + `shared.tsx` + `__tests__/`):

- **三栏布局**(`index.tsx` 编排):左 `CategoryTree`(scope 分区 + category 分组目录树)/ 中 `DocumentList`(文档卡片 + scope 实心徽章 + 状态 dot 徽章)/ 右 `MarkdownReader`(react-markdown 渲染 + 目录大纲 + 全文搜索高亮)
- **子组件自调 hook**(G1,对齐 `store-view` 范式):`CategoryTree` 自调 `useKnowledgeCategories()`、`DocumentList` 自调 `useDocuments({scope, category_id})`,`MarkdownReader` 纯渲染接收 `selectedDoc` prop;`index.tsx` 只管选中态(scope/categoryId/selectedDoc)+ 三栏编排,无 data fetching
- **类型层补齐**(G6):`DocumentRead` 加 `scope`/`group_id`/`category_id` + 新建 `KnowledgeCategoryRead` + `fetchKnowledgeCategories` + `useDocuments` 带参 + `useKnowledgeCategories` hook
- **scope 三色徽章**(G3):实心 `Badge` variant(platform→destructive 红 / group→warning 琉 / store→success 绿),与状态徽章(`dot-success`/`dot-warning`/`dot-destructive`)语义分层不混淆
- **搜索高亮**(G5):react-markdown `components` 自定义 text render + `<mark>` 高亮 + 上/下跳转 `scrollIntoView`,不引新依赖(react-markdown@10 + remark-gfm + rehype-highlight 已装)
- **响应式**(G4):`lg` 断点折叠,窄屏左栏变 Sheet 抽屉 + 中右纵叠
- **零行为回归**(G2):现有 CRUD(录入/删除 Dialog)+ RetrievalDebugCard 整体迁移进新结构;旧 `knowledge-page.tsx` 改 barrel re-export,App.tsx 零改动

**不做**(承接 overview Out of Scope):富文本编辑器 / PDF·Word 预览 / 完整移动端响应式(只做 lg 折叠)/ 下发·撤回操作 UI(归 Feature D admin-ui)/ Category 管理 CRUD(归 Feature D)。

---

## 3. User Stories

> 覆盖 overview D1 三级角色 + 门店核心视角。

**门店视角(核心)**:
1. 作为门店 owner,我想打开知识库页就看到三栏布局(分类树/文档列表/阅读器),以便直觉式浏览而不只看一张平铺表
2. 作为门店 owner,我想在文档卡片上看到 scope 来源徽章(平台🔴/集团🟡/本店🟢),以便一眼区分「这是下发的还是我自己加的」
3. 作为门店 owner,我想点击左栏分类树筛选文档,以便按主题(产品手册/FAQ/话术)快速定位
4. 作为门店 owner,我想点击文档后在右栏阅读 Markdown 全文(带目录大纲),以便完整阅读而不只是检索片段
5. 作为门店 owner,我想在阅读器里全文搜索关键词并高亮跳转,以便快速定位文档内的具体内容
6. 作为门店 owner,我想录入文档(手动文本/.txt 上传)并看到索引状态,以便管理本店知识库(保留现有 CRUD 零回归)
7. 作为门店 member,我想只读浏览三栏(无录入/删除按钮),以便查阅知识但不能改

**集团/平台视角(聚合)**:
8. 作为 group_admin(派生身份),我想看到聚合视图(本集团 group 级 + 本集团所有门店 store 级),以便统一查阅集团知识
9. 作为 super_admin,我想看到全局聚合视图(所有 scope),以便平台级知识治理

**跨场景**:
10. 作为窄屏用户(lg 以下),我想左栏目录树折叠成抽屉不挤占空间,以便在有限屏幕上仍可浏览列表+阅读器
11. 作为任意角色,我想用检索调试页验证 RAG 召回效果(保留 RetrievalDebugCard 零回归),以便上线前验证检索质量

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | **0** | 后端 API 由 backend feature 已交付,本 feature 纯前端消费 |
| 数据库迁移 | **0** | 无 schema 变化 |
| 前端文件改动 | ~10 | `pages/knowledge/` 文件夹新建(barrel + index + 三栏组件 + scope-badge + shared + retrieval-debug-card + tests);`pages/knowledge-page.tsx` 改 barrel;`api/types.ts` 扩;`api/endpoints/knowledge.ts` 扩;`hooks/queries/knowledge.ts` 扩 |
| 新增测试类 | ~6 | `category-tree.test.tsx` / `document-list.test.tsx` / `markdown-reader.test.tsx` / `scope-badge.test.tsx` / `knowledge-api.test.ts`(msw 集成)/ `index.test.tsx`(三栏 smoke) |
| 新增依赖 | 1 | `msw`(测试依赖,补 API 集成测试层)|
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(纯前端)
- 是否修改现有租户隔离逻辑? **NO**(前端只消费 backend 已隔离的 list API)
- 是否引入跨租户访问点? **NO**(scope/group_admin 聚合视图由 backend list API 按 role 过滤,前端只渲染返回结果)
- 验证:跨角色视图差异测试(member 只读 / owner CRUD / group_admin 聚合 / super_admin 全局)由组件测试 + 角色注入覆盖

### 4.3 权限影响评估

- 是否新增 permission code? **NO**(后端 backend feature 已加 `knowledge:distribute` 等;本 feature 只消费现有 `knowledge:create`/`knowledge:delete` 控制 CRUD 按钮显隐)
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(纯前端)
- 是否影响 graph.py 工具内 check? **NO**
- 按钮守卫:复用现有 `hasPermission(me, "knowledge", "create"|"delete")`,与旧 `knowledge-page.tsx` 一致

### 4.4 数据库表设计 checklist

N/A —— 纯前端,无新表。类型层只消费 backend 已有的 `DocumentRead`(后端已含 scope/group_id/category_id)。

### 4.5 核心实施决策(G1-G7 落地)

#### G1:组件 data 流 —— 子组件自调 hook(对齐 store-view 范式)

镜像 `devices/store-view.tsx`「子组件自调 hook」范式,**不是**父统一调:

```
knowledge/
├── knowledge-page.tsx        ← barrel re-export `export { KnowledgePage } from "./index"`(镜像 devices-page.tsx)
├── index.tsx                 ← 三栏布局编排 + 选中态 state({scope, categoryId, selectedDoc}),无 data fetching
├── category-tree.tsx         ← 左栏:自调 useKnowledgeCategories(),点击 → onSelect({scope, categoryId})
├── document-list.tsx         ← 中栏:自调 useDocuments({scope, category_id}),含 CRUD Dialog(录入/删除)
├── markdown-reader.tsx       ← 右栏:纯渲染,props { doc: DocumentRead | null },搜索高亮 + 目录大纲
├── retrieval-debug-card.tsx  ← 从旧 page 迁移(逻辑零变化)
├── scope-badge.tsx           ← scope 三色实心徽章(platform/group/store)
├── shared.tsx                ← statusBadge 等共享原语(从旧 page 抽)
└── __tests__/
```

**为什么右栏是例外**(纯渲染):阅读器只展示已选文档,无需独立 query,内容已在 `DocumentRead.content` 里(由 document-list 选中下传)。若 reader 自调 hook 会重复请求 + 选中态耦合。

**index.tsx 选中态职责**:
- `selectedScope` / `selectedCategoryId`:CategoryTree 点击后设置,下传给 DocumentList 作为 query 参数
- `selectedDoc`:DocumentList 点击文档卡片后设置,下传给 MarkdownReader
- 不持有任何 useQuery/useMutation

#### G2:旧页切割 —— 三栏 + 迁移 CRUD + 迁移 DebugCard

现有 `knowledge-page.tsx`(458 行)两段切割:
- `KnowledgePage` 主体(L158-377:列表 Table + 录入 Dialog + 删除 Dialog)→ 拆进 `document-list.tsx`(列表 + CRUD)+ `shared.tsx`(statusBadge)
- `RetrievalDebugCard`(L383-458:独立 Card,自调 `retrieveKnowledge`,无共享 state)→ 整体迁进 `retrieval-debug-card.tsx`,**逻辑零变化**

旧 `knowledge-page.tsx` 改成 barrel(镜像 `devices-page.tsx`):`export { KnowledgePage } from "./index"`,App.tsx 零改动。

**Feature D 边界**:本 feature 不做下发/撤回操作 UI、不做 Category 管理 CRUD(创建/编辑/删除 Category)。文档 CRUD(录入/删除)归本 feature(保留现有行为,零回归)。

#### G3:scope 徽章 —— 实心 variant,与状态 dot variant 分层

| 维度 | variant | token | 用途 |
|---|---|---|---|
| scope=platform | `destructive`(实心红) | `bg-destructive` | 平台下发 |
| scope=group | `warning`(实心琉) | `bg-warning` | 集团下发 |
| scope=store | `success`(实心绿) | `bg-success` | 本店自建 |
| 状态=indexed | `dot-success`(绿点) | `bg-success` | 已索引 |
| 状态=pending | `dot-warning`(琉点) | `bg-warning` | 待处理 |
| 状态=failed | `dot-destructive`(红点) | `bg-destructive` | 索引失败 |

**关键决策**:scope 用实心 badge(整块色),状态用 dot badge(点 + 文字)。两套语义不混淆 —— 用户看到实心红块 = 平台来源,看到红点 = 索引失败。对齐 design-system semantic token,**不硬编码色**。

> ⚠️ **偏离用户原话「平台🔴」的字面**:destructive 在系统语义 = 失败/危险。本决策用 destructive 表 platform 是因为它是现有 badge 变体里唯一的红色实心选项,且通过「实心 vs dot」的视觉分层避开了与状态徽章的语义冲突。若后续 design-system 新增语义更中性的红色 variant(如 `info`/`brand`),可平滑迁移。

#### G4:响应式 —— lg 断点折叠,左栏 Sheet 抽屉

- 断点:`lg`(1024px),对齐 overview Out of Scope「仅做 lg 折叠,完整移动端归移动端系列」
- `lg 及以上`:三栏并排(grid 或 flex,左栏固定宽 + 中栏 flex + 右栏固定宽)
- `lg 以下`:左栏 `CategoryTree` 收进 `Sheet`(shadcn Sheet 组件,默认关,顶部汉堡按钮展开覆盖层);中栏 `DocumentList` + 右栏 `MarkdownReader` 纵向堆叠(列表在上、阅读器在下)

#### G5:搜索高亮 —— react-markdown components 自定义 render + `<mark>`

react-markdown@10 的 `components` prop 允许自定义节点 render:
- 搜索框输入关键词 → 用 `components.text` 自定义 render,把含关键词的文本节点拆成「前 + `<mark>`关键词`</mark>` + 后」
- 高亮全部匹配 + 计数(「3/7 处」)+ 上一个/下一个按钮 → 用 `ref` 收集所有 `<mark>` 元素 + `scrollIntoView({behavior:"smooth", block:"center"})`
- 关键词为空时正常渲染(无 `<mark>` 包裹)
- **不引新依赖**:不用 rehype-highlight-text / remark-highlight-words(react-markdown@10 的 rehype 插件适配有版本坑,且现有 remark-gfm/rehype-highlight 已够用)

#### G6:类型层补齐(本 feature 范围内)

现状偏差(feature verification 写「已含」与仓库不符):
- `DocumentRead` 当前**不含** `scope`/`group_id`/`category_id`(types.ts L245)
- `KnowledgeCategoryRead` 类型**不存在**
- `useDocuments()` 当前**无参**(queries/knowledge.ts L18)
- `useKnowledgeCategories` hook **不存在**
- `fetchKnowledgeCategories` endpoint **不存在**

本 feature 补齐(切片 01 地基):
- `api/types.ts`:`DocumentRead` 加 `scope: "platform"|"group"|"store"` + `group_id: string|null` + `category_id: string|null`;新建 `KnowledgeCategoryRead { id, name, scope, group_id, tenant_id, sort_order, created_at, updated_at }`
- `api/endpoints/knowledge.ts`:`fetchDocuments` 加可选参数 `{scope?, category_id?}`(query string);新增 `fetchKnowledgeCategories()`
- `hooks/queries/knowledge.ts`:`useDocuments(opts?)` 接 opts 透传;qk 加 `knowledgeCategories` key;新增 `useKnowledgeCategories()`

> 后端 API 已支持这些参数(backend feature 交付),前端只是接上。

#### G7:目录大纲 —— 前端正则提取标题

`MarkdownReader` 在渲染前对 `doc.content` 做正则提取:
- 匹配 `/^(#{2,3})\s+(.+)$/gm`(## / ### 标题,h1 不进大纲避免冗余)
- 生成 `[{level: 2|3, text, anchor}]`,anchor 用标题文本 slugify 或按出现顺序生成 id
- react-markdown 的 `components.h2`/`components.h3` 自定义 render 时给对应标题加 `id={anchor}`
- 点大纲项 → `document.getElementById(anchor)?.scrollIntoView(...)`
- **不依赖后端字段**(后端 DocumentRead 无 outline/toc 字段,也不为本 feature 加)

### 4.6 测试 seam 决策

**两个 seam**(用户确认引入 msw,偏离既有 mock-hook 范式):

1. **组件渲染测试**(主 seam,镜像 `devices/__tests__/`):
   - `renderWithProviders`(包 QueryClient + ToastProvider)+ `vi.mock("@/hooks/queries")` stub hooks + `vi.mock("@/components/auth/auth-context")` 注入角色
   - 按文件分:`category-tree.test.tsx`(树渲染 + scope 分区 + 点击筛选)/ `document-list.test.tsx`(卡片 + scope 徽章 + 状态徽章 + CRUD + 角色守卫)/ `markdown-reader.test.tsx`(渲染 + 目录大纲 + 搜索高亮 + 跳转)/ `scope-badge.test.tsx`(三色映射)/ `index.test.tsx`(三栏 smoke + 空态 + 跨角色视图差异)

2. **msw API 集成测试**(新 seam,本 feature 引入):
   - `knowledge-api.test.ts`:用 msw `setupServer` mock 后端 HTTP,测 `fetchDocuments({scope, category_id})` / `fetchKnowledgeCategories()` 的请求构造 + 响应解析 + 类型层契约
   - 覆盖前端类型层与后端契约的连接点(既有 mock-hook 范式不覆盖这层)
   - 引入 msw 作为 devDependency,搭 `setupServer` + `beforeEach resetHandlers` 基建,后续 feature 可复用

> **偏离范式声明**:项目现有前端测试(devices/bookings/chat/customers)全部用 mock-hook 范式,无 msw。本 feature 引入 msw 是经用户确认的显式决策 —— 补「前端类型层 ↔ 后端 API 契约」的集成测试层,作为前端测试基建的演进起点。后续 feature 可选择沿用 mock-hook 或升级到 msw。

### 4.7 镜像范式对照

| 范式点 | devices/(参照) | knowledge/(本 feature) |
|---|---|---|
| barrel | `devices-page.tsx` re-export | `knowledge-page.tsx` re-export |
| 路由入口 | `index.tsx`(super/hq vs store 二叉) | `index.tsx`(三栏编排,无角色二叉 —— 角色差异在 list 数据层) |
| view 文件 | `store-view.tsx` / `hq-view.tsx` | `category-tree.tsx` / `document-list.tsx` / `markdown-reader.tsx`(三栏而非双视图) |
| shared | `shared.tsx`(statusBadge 等) | `shared.tsx`(statusBadge)+ `scope-badge.tsx` |
| 测试 | `__tests__/store-view.test.tsx` + `hq-view.test.tsx` | `__tests__/{category-tree,document-list,markdown-reader,scope-badge,index}.test.tsx` + `knowledge-api.test.ts`(msw) |

**差异**:devices 是「双视图(super/hq vs store)」按角色二叉路由;knowledge 是「三栏布局」所有角色同结构(差异在 list 返回数据,backend 按 role 过滤)。故 index.tsx 不做角色分支,三栏对所有角色一致渲染。

---

## 5. Testing Decisions

- **测试金字塔**:unit/组件 ~15 用例(主 seam)+ API 集成 ~5 用例(msw seam)= ~20 用例
- **不测**:后端契约(backend feature 987 测试已覆盖)、E2E(项目无 E2E 基建)
- **覆盖率目标**:三栏组件每个有独立 test 文件;scope 徽章三色映射有专门断言;搜索高亮 + 目录大纲有行为断言(非实现细节)
- **prior art**:`devices/__tests__/store-view.test.tsx`(组件渲染 + mock hooks + 角色注入范式)、`bookings/__tests__/`(同款)
- **边界 case 清单**:
  - 空态(categories 空 / documents 空 / selectedDoc null)
  - 跨角色视图差异(member 无 CRUD 按钮 / owner 有 / group_admin 聚合 / super_admin 全局)
  - scope 徽章三色正确映射(platform/group/store)+ 状态徽章三态(indexed/pending/failed)
  - 搜索高亮(有关键词 / 无关键词 / 多匹配跳转)
  - 目录大纲(有标题 / 无标题 / 点击跳转)
  - 响应式(lg 以上三栏 / lg 以下左栏 Sheet)
- **回归**:旧 `knowledge-page.tsx` 行为零变化(CRUD + RetrievalDebugCard 迁移后行为不变,断言检索调试页仍工作)

---

## 6. 切片规划(对齐 to-tickets tracer-bullet)

> **切片策略**:纯前端 feature,每片切穿「类型层 → hook → 组件 → test」全栈,单片可独立 demo/verify。3 切片线性依赖(01→02→03),首片无 blocker 可立即开工。
>
> **切片依赖图**:
> ```
> 01(地基:类型层+msw+barrel+列表+scope徽章) ──→ 02(左栏树+右栏阅读器+响应式) ──→ 03(CRUD+调试页迁移+收尾)
> ```
>
> **AC 覆盖映射**(对照 §10 验收标准 7 条):切片 01 覆盖 AC1(barrel/文件夹)+ AC2(types)+ AC3(endpoints)+ AC4(hooks)+ AC5(scope 徽章);切片 02 覆盖 AC1(三栏组件齐)+ AC6 部分(三栏渲染+树筛选+阅读器+大纲+高亮+响应式);切片 03 覆盖 AC1(DebugCard)+ AC6(跨角色+空态)+ AC7(零回归)+ 全量验证收尾。

### 切片 01 — 地基:类型层补齐 + msw 基建 + barrel 骨架 + DocumentList + scope 徽章 ✅(分支 feat/knowledge-tiered-reader-ui-slice-01,11/11 AC 全绿;双轴 review:Standards 1 hard(cn() 替代 join)+ 3 judgement 全修 / Spec 1 implemented-but-wrong(index.tsx onSelectDoc 错误接线)已修;npm test 158 green / tsc 0 / build 0 / oxlint 0-0)

- **What it delivers**:门店 owner 打开知识库页,看到新的三栏布局空壳(左/中/右三栏占位),中栏已渲染文档列表卡片 —— 每卡显示标题 + scope 来源实心徽章(平台🔴/集团🟡/本店🟢)+ 状态 dot 徽章(indexed/failed/pending)+ 更新时间 + chunk 数。这是「分级知识库落到门店眼睛里」的第一公里:scope 来源可视化。类型层(types/endpoints/hooks)对齐 backend 已交付字段,为切片 02/03 的三栏交互铺好数据管线。配套 msw 集成测试基建首次落地(后续 feature 可复用)。

- **Blocked by**: 无(可立即开工)

- **Acceptance criteria**:
  - [x] `frontend/src/api/types.ts`:`DocumentRead` 加 `scope: "platform"|"group"|"store"` + `group_id: string|null` + `category_id: string|null`;新建 `KnowledgeCategoryRead`(id/name/scope/group_id/tenant_id/sort_order/created_at/updated_at)
  - [x] `frontend/src/api/endpoints/knowledge.ts`:`fetchDocuments` 加可选参数 `{scope?, category_id?}`(query string 透传);新增 `fetchKnowledgeCategories()`
  - [x] `frontend/src/hooks/queries/knowledge.ts`:`useDocuments(opts?)` 接 opts 透传给 fetchDocuments;qk 加 `knowledgeCategories` key;新增 `useKnowledgeCategories()`
  - [x] `frontend/src/pages/knowledge/` 文件夹建立:`knowledge-page.tsx`(barrel re-export `export { KnowledgePage } from "./index"`,镜像 devices-page.tsx)+ `index.tsx`(三栏布局编排空壳,左/右栏占位「待实现」)+ `document-list.tsx`(中栏:自调 useDocuments,卡片 + scope 徽章 + 状态徽章)+ `scope-badge.tsx`(scope→实心 badge variant 映射)+ `shared.tsx`(statusBadge 从旧 page 抽)
  - [x] 旧 `frontend/src/pages/knowledge-page.tsx` 改 barrel 或被新 barrel 接管,App.tsx import 零改动(保持 `@/pages/knowledge-page` 路径)
  - [x] `scope-badge.tsx`:platform→`destructive` 实心 / group→`warning` 实心 / store→`success` 实心(对齐 design-system token,不硬编码色)
  - [x] msw 引入:`package.json` devDependency 加 `msw`;搭 `setupServer` + `beforeEach resetHandlers` 基建(放 `src/test/` 或 `__tests__/` 共享)
  - [x] `__tests__/scope-badge.test.tsx`:三色映射断言(platform/group/store → 对应 variant)
  - [x] `__tests__/document-list.test.tsx`:列表渲染(卡片显示标题/scope 徽章/状态徽章/时间/chunk 数)+ 空态 + mock useDocuments 范式(镜像 devices store-view.test)
  - [x] `__tests__/knowledge-api.test.ts`(msw 集成):fetchDocuments({scope, category_id}) 请求构造正确 + fetchKnowledgeCategories 响应解析 + DocumentRead 新字段类型契约
  - [x] 验证:`npm test` 全绿(新测试 + 零回归)+ `npm run build` 0 错 + `tsc -b` 0 错 + `oxlint` 0/0

### 切片 02 — 左栏目录树 + 右栏 Markdown 阅读器 + 响应式折叠

- **What it delivers**:门店 owner 看到完整三栏:左栏分类目录树(scope 分区「平台下发/集团下发/本店」+ 每个 scope 下 category 分组,树形导航点击筛选中栏);右栏点击文档后渲染 Markdown 全文 —— 带目录大纲(自动从 ## / ### 提取,点击跳转 scrollIntoView)+ 全文搜索高亮(输入关键词 → 匹配处 `<mark>` 高亮 + 计数 + 上/下跳转)。窄屏(lg 以下)左栏自动收进 Sheet 抽屉 + 中右纵叠。三栏阅读形态(D7)完整兑现。

- **Blocked by**: 切片 01(消费类型层 + scope-badge + barrel 骨架 + msw 基建)

- **Acceptance criteria**:
  - [ ] `category-tree.tsx`:自调 `useKnowledgeCategories()`;按 scope 分区(平台🔴/集团🟡/本店🟢 分组,用 scope-badge 标识)+ 每个 scope 下 category 分组(按 sort_order);树形渲染(支持 category 折叠/展开);点击 category → `onSelect({scope, categoryId})` 回调通知父层
  - [ ] `index.tsx`:接 CategoryTree 的 onSelect → 设置 selectedScope/selectedCategoryId → 下传给 DocumentList 作为 useDocuments 参数;DocumentList 选中文档 → 设置 selectedDoc → 下传给 MarkdownReader
  - [ ] `markdown-reader.tsx`:纯渲染组件,props `{ doc: DocumentRead | null }`;用 react-markdown(`components` 自定义 h2/h3 加 id)+ remark-gfm + rehype-highlight 渲染 `doc.content`;空态(doc=null)显示「选择左侧文档查看」
  - [ ] 目录大纲(G7):正则 `/^(#{2,3})\s+(.+)$/gm` 提取标题生成大纲列表;react-markdown `components.h2`/`components.h3` render 时加 `id={anchor}`;点大纲项 → `getElementById(anchor).scrollIntoView({behavior:"smooth"})`;无标题时大纲区空
  - [ ] 搜索高亮(G5):阅读器顶部搜索框 + 关键词 state;`components.text` 自定义 render 把含关键词文本拆「前 + `<mark>` + 后」;高亮计数(「N/M」)+ 上一个/下一个按钮 → 收集所有 `<mark>` ref + scrollIntoView 跳转;关键词空时正常渲染无 `<mark>`;**不引新依赖**(用现有 react-markdown components,不加 rehype/remark 插件)
  - [ ] 响应式(G4):`lg` 断点;`lg+` 三栏并排(grid/flex);`lg-` 左栏收进 Sheet(shadcn Sheet,默认关,汉堡按钮展开)+ 中右纵叠(列表上阅读器下)
  - [ ] `__tests__/category-tree.test.tsx`:树渲染 + scope 三分区显示 + category 分组 + 点击触发 onSelect 回调 + 空态(无 category)
  - [ ] `__tests__/markdown-reader.test.tsx`:Markdown 渲染(标题/段落/代码块)+ 目录大纲提取(有标题/无标题)+ 点击大纲跳转 + 搜索高亮(有关键词 `<mark>` 出现 + 计数 + 无关键词无 mark)+ 空态(doc=null)
  - [ ] `__tests__/index.test.tsx`:三栏 smoke(三栏均渲染)+ CategoryTree 点击 → DocumentList 过滤 + DocumentList 点击 → MarkdownReader 显示
  - [ ] 验证:`npm test` 全绿 + `npm run build` 0 错 + `oxlint` 0/0

### 切片 03 — CRUD Dialog 迁移 + 检索调试页迁移 + 跨角色测试 + feature 收尾(末切片)

- **What it delivers**:现有知识库的全部行为在新三栏结构里完整保留 —— 录入文档(手动文本/.txt 上传)与删除的 Dialog 迁进 DocumentList(门店 owner 看到「录入文档」按钮 + 删除菜单,member 只读无写按钮);检索调试页(RetrievalDebugCard)迁移进新结构底部,行为零变化。跨角色视图测试补全(member/owner/group_admin/super_admin)。全量验证 + feature 收尾(状态 passing + 依赖解锁 admin-ui)。

- **Blocked by**: 切片 01 + 切片 02(三栏主体已完成,本片迁移现有功能进新结构 + 收尾)

- **Acceptance criteria**:
  - [ ] `document-list.tsx`:从旧 `knowledge-page.tsx` 迁入录入 Dialog(name/sourceType/textContent/upload 字段 + handleFilePick + handleCreate)+ 删除确认 Dialog + DropdownMenu 删除项;按钮守卫 `hasPermission(me, "knowledge", "create"|"delete")`(member 只读,与旧页一致);CRUD 行为零回归(录入流程/校验/toast/索引触发一致)
  - [ ] `retrieval-debug-card.tsx`:从旧 `knowledge-page.tsx` 整体迁入 `RetrievalDebugCard`(query state + handleSearch + retrieveKnowledge 调用 + hits 渲染),**逻辑零变化**;在 `index.tsx` 底部渲染
  - [ ] `__tests__/document-list.test.tsx` 扩 CRUD:录入 Dialog 弹出 + 填表提交触发 useCreateDocument.mutateAsync + 删除菜单触发 useDeleteDocument + member 角色无写按钮守卫(对齐 devices store-view 范式)
  - [ ] 跨角色视图测试(group_admin/super_admin 聚合视图由 backend list 返回不同数据,前端渲染一致 —— 测试 mock 不同 useDocuments 返回值断言渲染差异);member 只读守卫
  - [ ] 空态完整覆盖(categories 空 + documents 空 + selectedDoc null)
  - [ ] grep 残留:`pages/knowledge-page` 旧路径外部 import 仅 App.tsx barrel;旧 knowledge-page.tsx 已改 barrel 或删除
  - [ ] 验证(plan §10 AC 全绿):`npm test` 全绿(目标 ~20 用例,三栏渲染 + scope 分区 + category 树筛选 + 文档卡片徽章 + Markdown 阅读器 + 目录大纲 + 搜索高亮 + 空态 + 跨角色视图差异 + 响应式窄屏折叠 + msw API 契约)+ `npm run build` 0 错 + `oxlint` 0/0 + `./init.sh full` 后端零回归(纯前端 feature,后端测试数不变)
  - [ ] feature 收尾仪式(three-tier §4 第1-7步):`./init.sh full` 全绿 + feature_list.json status `in_progress → passing` + evidence + sync-active 刷新 + progress.md 更新 + 文档影响评估 + 依赖解锁扫描(admin-ui p87 depends_on backend 已满足)

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:
- 改动文件 ~10(>10 边界)→ 接近触发
- 涉及鉴权/权限/数据迁移/跨服务? **NO**(纯前端)
- 涉及安全敏感操作? **NO**
- 涉及不可逆操作? **NO**

**结论**:**本 feature 为纯前端结构重构 + 类型层接通,不属于复杂任务**(改动文件接近但未超阈值,且无鉴权/迁移/安全/不可逆因素)。v1 阶段**不强制**对抗式审查;若 `/to-tickets` 后切片数 ≥3 或实施中发现风险点,再触发 v2 审查。

> 实施期每个切片仍走 `/code-review` 双轴(Standards + Spec),这是 EP3 的硬规则,与本节 v1→v2 审查独立。

---

## 8. Out of Scope

承接 overview Out of Scope + 本 feature 边界:

- ❌ 富文本/Markdown 文档**编辑器**(只做阅读 + 文档 CRUD 用现有 textarea,编辑留后续)
- ❌ PDF/Word 在线预览(现有 source_type=text/upload 仅 .txt)
- ❌ **下发/撤回操作 UI**(归 Feature D admin-ui;本 feature 只展示下发来的文档,不做下发动作)
- ❌ **Category 管理 CRUD**(创建/编辑/删除 Category,归 Feature D;本 feature 只读消费 Category 做目录树)
- ❌ 完整移动端响应式(仅 lg 折叠,完整移动端归移动端系列)
- ❌ 文档版本树 / 历史版本(下发是引用,上级改门店即时看到,不做版本)
- ❌ 后端 API 改动(backend feature 已交付,本 feature 纯消费)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| scope 用 destructive(红)与状态徽章语义混淆(用户误以为红 = 失败) | 中 | G3 实心 vs dot 视觉分层 + scope-badge 独立组件 + 测试断言三色映射;plan §4.5 G3 已标注偏离原话的理由 |
| msw 引入偏离既有范式,后续 feature 不一致 | 中 | §4.6 显式声明偏离理由 + 作为基建起点;后续 feature 自行选择,不强推 |
| react-markdown@10 components 自定义 render 搜索高亮性能(大文档) | 低 | 防抖搜索输入 + 关键词为空时跳过 `<mark>` 包裹;测试覆盖大文档场景由后端 content 长度自然限制 |
| 类型层补齐与后端契约不一致(后端字段名/可选性) | 中 | 切片 01 msw 集成测试锁契约 + 对照 backend feature 的 DocumentRead/KnowledgeCategoryRead schema |
| 旧 RetrievalDebugCard 迁移引入行为回归 | 低 | 整体迁移逻辑零变化 + 保留检索调试测试断言 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `frontend/src/pages/knowledge/` 文件夹建立:`knowledge-page.tsx`(barrel)+ `index.tsx`(三栏编排)+ `category-tree.tsx` + `document-list.tsx` + `markdown-reader.tsx` + `retrieval-debug-card.tsx` + `scope-badge.tsx` + `shared.tsx`
2. `frontend/src/api/types.ts`:`DocumentRead` 加 `scope`/`group_id`/`category_id` + 新建 `KnowledgeCategoryRead`
3. `frontend/src/api/endpoints/knowledge.ts`:`fetchDocuments` 带过滤参数 + `fetchKnowledgeCategories`
4. `frontend/src/hooks/queries/knowledge.ts`:`useDocuments(opts?)` 带参 + `useKnowledgeCategories`
5. scope 来源标识组件:platform🔴/group🟡/store🟢 实心徽章(对齐 design-system token,复用 semantic token 不硬编码色)
6. 测试 ~20 用例(三栏渲染 + scope 分区 + category 树点击筛选 + 文档卡片 scope/状态徽章 + Markdown 阅读器渲染 + 目录大纲 + 搜索高亮 + 空态 + 跨角色视图差异 + 响应式窄屏折叠 + msw API 契约)+ `npm test` 全绿 + `npm run build` 0 错 + `oxlint` 0/0
7. 现有 `knowledge-page.tsx` 零行为回归(检索调试页保留 + CRUD 行为不变;旧文件改 barrel,App.tsx 零改动)

---

## 11. 不越界声明

本次改动**只**涉及:
- `frontend/src/pages/knowledge/` 新文件夹 + `knowledge-page.tsx` 改 barrel
- `frontend/src/api/types.ts` + `api/endpoints/knowledge.ts` + `hooks/queries/knowledge.ts` 类型层扩展
- `frontend/package.json` 加 msw devDependency + 测试基建
- `frontend/src/pages/knowledge/__tests__/` 测试文件

**不**触碰:
- 后端任何文件(app/ 下零改动)
- 数据库 migration
- 权限码 / casbin 策略
- Feature D admin-ui 的范畴(下发/撤回操作 + Category 管理 CRUD)
- 其他前端 page(books/devices/chat/customers 等)
