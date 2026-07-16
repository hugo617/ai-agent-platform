# 前端 UI/UX 全面改造计划

> **文档性质**:待审查的实施计划。写于 2026-07-16,尚未执行。
> **审查方式**:在新会话中独立审查本文档(不依赖原会话上下文)。
> **审查重点**:设计参考是否真实可查证、改造方案是否合理、是否越界、风险是否可控。

---

## 0. 本文档是「自包含」的 —— 只读这一份就能审查

本文档包含审查所需的全部信息:
- 改造目标(第 1 节)
- 设计参考来源 + 可查证方式(第 2 节)
- 当前前端现状摘要(第 3 节)
- 已和用户确认的方向(第 4 节)
- 完整实施计划(第 5 节)
- 约束、风险、执行策略(第 6-8 节)

**审查者需要做的**:
1. 读第 2 节,逐一打开参考站 URL 核对(防止参考来源造假)
2. 读第 3 节,对照真实代码验证「现状描述」是否准确
3. 读第 5 节,判断改造方案是否合理、有无遗漏或越界
4. 读第 6-8 节,判断风险控制是否充分

---

## 1. 改造目标

对现有 **React 19 + Vite + TanStack Query + Tailwind + shadcn 风格组件** 的前端做 UI/UX 全面升级,覆盖全部 19 个页面。目标:

- **视觉**:从「朴素实用」升级为「精致现代」,亮色为主 + 暗色可选
- **体验**:引入键盘优先的 Command 菜单、骨架屏、动效、专业图表
- **一致性**:统一页面骨架,消除 19 个页面重复手写的头部/加载态/空态

---

## 2. 设计参考来源(可查证,非编造)

> **审查必做**:逐一打开下面的 URL,核对参考站是否真实存在、描述是否属实。
> 这些是抓取时(2026-07-16)的真实内容。原会话用 `curl` 抓取了 HTML,提取了 title/meta/关键词作为「真实存在」的证据。

| 参考站 | URL | 抓取到的真实内容 | 借鉴什么 |
|---|---|---|---|
| **shadcn/ui Blocks** | https://ui.shadcn.com/blocks | title="Building Blocks for the Web - shadcn/ui";HTML 里含成套 block:`dashboard-01`、`sidebar-03`、`sidebar-07`、`login-03`、`login-04` | 直接套用布局骨架(侧边栏分组、登录页分栏、仪表盘结构) |
| **Magic UI** | https://magicui.design | meta description="Beautiful UI components and templates to make your landing page look stunning.";招牌动画组件(Border Beam 流光边框、Number Ticker 数字滚动) | 适度点缀(Dashboard 指标卡流光边框、数字滚动动画) |
| **Tremor** | https://tremor.so | title="Tremor – Copy-and-Paste Tailwind CSS UI Components for Charts and Dashboards";提供 Area/Bar/Donut Chart | 图表组件的视觉参考(本项目实际用 recharts 实现,因 recharts 生态更通用) |
| **Linear** | https://linear.app | title="Linear – The system for product development";meta description 含 "Purpose-built for planning and building products with AI agents"(连 Linear 都在往 AI Agent 方向靠,和本项目定位契合);招牌 Command Menu + 键盘优先 + 精致暗色配比 | Command 菜单(⌘K)交互、暗色 token 配比、整体精致度标杆 |
| **Aceternity UI** | https://ui.aceternity.com/components | title 含 "Free React & Next.js Components — Tailwind CSS & Framer Motion";组件列表含 `/components/bento-grid`、`/components/background-beams`、`/components/card-spotlight`、`/components/aurora-background` | Bento Grid 布局(Dashboard 快速操作区)、背景渐变(克制使用,仅 Dashboard/空状态/404) |

### 关于参考来源的诚实说明

- 原会话期间,**WebSearch 和 webReader 两个 MCP 工具配额耗尽**(MCP error -429,2026-08-05 重置)。因此改用 `curl` 直接抓取上述 URL 的 HTML,从 HTML 中提取了 title/meta/关键词作为「真实存在」的证据。
- 抓取的是 HTML 文本(非截图),所以**视觉细节(具体的配色数值、间距、动画效果)无法从抓取内容中完全还原**。实施时需要打开真实站点看视觉细节。
- 上述 5 个站点都是业内长期稳定存在的知名站点,URL 不会变动,审查时可随时打开核对。

---

## 3. 当前前端现状(审查时可对照真实代码验证)

前端代码位于 `frontend/`,关键事实:

### 3.1 技术栈(`frontend/package.json`)
- React 19.2 + Vite 8 + TypeScript 6
- TanStack Query 5.101(数据层)+ TanStack Table 8.21(**已装但全站零使用**,所有表格都是手写 `<Table>` 原语)
- Tailwind 3.4 + Radix UI primitives + shadcn 风格组件(手抄,非 CLI 生成)
- react-hook-form + zod(表单)、react-markdown(Chat 渲染)
- 图标:lucide-react(唯一图标库)

### 3.2 设计系统
- **唯一全局样式文件**:`frontend/src/index.css`(60 行),`@tailwind base/components/utilities` + `:root`/`.dark` token + body 基础样式
- **颜色全走 CSS 变量**(`hsl(var(--xxx))`),Tailwind 配置在 `frontend/tailwind.config.js` 映射这些变量
- **当前 primary**:`222.2 47.4% 11.2%`(深蓝黑,偏保守)
- **圆角**:`--radius: 0.5rem`
- **暗色模式**:`darkMode: ["class"]` 已配,`.dark` token 已写全,**但全仓库无任何代码给 `<html>` 加 `.dark` 类,无主题切换 UI** —— 暗色模式是「配了但没接线」的半成品

### 3.3 组件库(`frontend/src/components/ui/`,**22 个**组件)

> ⚠️ 审查修正:原稿写「17 个」有误,实测 `frontend/src/components/ui/` 下 `*.tsx` 实有 **22 个**。

标准 shadcn 风格(forwardRef + cva),完整清单(按字母序):

| 类别 | 组件 |
|---|---|
| **基础控件** | `button`、`input`、`label`、`checkbox`、`switch`、`select`、`separator`、`textarea`(如有) |
| **布局/容器** | `card`、`dialog`、`dropdown-menu`、`tabs` |
| **展示** | `avatar`、`badge`、`table`、`stat-card`(数字指标卡)、`secure-image`(鉴权图片,带 token 刷新) |
| **表单** | `form-field`、`file-upload`、`export-csv-button`(内部用 toast 反馈结果) |
| **状态反馈** | `toast`(自研,**Context + `useToast()` hook 模式**,非全局 `toast()` 函数)、`skeleton`(骨架屏)、`list-state`(loading/empty/error 包装器)、`pagination` |

完整 22 个文件列表(实测):`avatar`、`badge`、`button`、`card`、`checkbox`、`dialog`、`dropdown-menu`、`export-csv-button`、`file-upload`、`form-field`、`input`、`label`、`list-state`、`pagination`、`secure-image`、`select`、`separator`、`skeleton`、`stat-card`、`switch`、`table`、`toast`。

值得注意:
- `list-state.tsx` —— 统一的 loading/empty/error 包装器,但**实测仅 3 个文件在用**,而 **14 个页面手写「加载中…」文字**(grep 确认)
- `skeleton.tsx` —— 骨架屏组件存在,**实测仅 1 个文件在用**(无骨架屏)
- `toast.tsx` —— **自研轻量 toast**,**Context + `useToast()` hook 模式**(挂在 `App.tsx` 的 `<ToastProvider>`),固定右下角(`fixed bottom-4 right-4`)、4 秒自动消失。**当前 17 个文件、共 163 处调用**(含 `useToast()` 取值 + `t.success()/t.error()` 调用)—— 这是评估 Toast 迁移成本的关键数字
- `stat-card.tsx` —— 数字指标卡
- `secure-image.tsx` —— 带 token 刷新的鉴权图片(头像/文档缩略图用),改造时需保留其鉴权逻辑

### 3.4 布局(`frontend/src/components/layout/dashboard-layout.tsx`,260 行)
- 经典「左侧固定侧边栏(w-64)+ 顶栏(h-16)+ 主内容」三段式
- 侧边栏:品牌区 + 导航项(`NAV_ITEMS` 数组,16 项硬编码,用 `NavLink` 渲染)
- **导航未分组**,16 项扁平排列
- 顶栏:移动端汉堡 + `GlobalSearchBox`(自研防抖搜索)+ `NotificationBell` + 超管 Badge + 用户头像下拉
- 移动端侧边栏是 drawer(`translate-x` 过渡),无动画库

### 3.5 页面清单(19 个,全在 `frontend/src/pages/`)
登录、概览(分 StoreView/HqView)、智能体、对话、组织、客户、知识库、个人中心、通知、费用、审计日志、门店、计费管理、用户、角色、权限矩阵、成员、设置、404。

页面体量差异大:404 仅 14 行,而 `chat-page.tsx`(**940 行**)、`settings-page.tsx`(**966 行**)很大。

### 3.6 视觉特征(当前)
- 几乎所有页面同一套头:`h1 text-3xl font-bold` + `text-muted-foreground` 副标题 + 右上角操作按钮(每个页面手写一遍)—— grep `text-3xl font-bold|font-semibold` **命中 16 处**(含 StoreView/HqView 两个 Dashboard 视图)
- 列表页统一:`Card > CardHeader > CardContent(Table)`——**实测 13 个页面**用 `ui/table`:agents、billing、billing-admin、customers、groups、knowledge、logs、members、permissions、roles、settings、tenants、users
- **加载态几乎全是纯文字「加载中…」**(**14 个页面**),无骨架屏
- 空态:垂直居中 + lucide 大图标 + 一行小灰字
- **无动画库**(无 framer-motion),只有 Tailwind 的 `transition-colors`/`animate-spin`
- **无图表库**,Dashboard 趋势图是纯 CSS 手写柱状条(`flex items-end gap-1` + `height: ${p.conversations/convMax*100}%`)
- **无 Command 菜单**,全局搜索是自研防抖 input(`GlobalSearchBox`)

### 3.7 租户白标(不能破坏的现有逻辑)
- `frontend/src/lib/theme.ts`(**95 行**):运行时把租户 `theme_color`(`#RRGGBB`)转 HSL 写进 `:root --primary`,按 WCAG 亮度自动选 `--primary-foreground`(近黑或近白二选一)
- 通过 `useApplyTenantTheme()` hook 应用,**只有 primary 一个色被租户覆盖**
- ⚠️ **审查发现的关键风险**:`applyThemeColor` 选前景色时(line 91-94)**只看租户色亮度,不看当前是否暗色模式** —— 切暗色后,租户 primary 配近黑/近白前景,对比度可能崩。这是阶段 0 必须解决的问题(见第 7 节风险 1)

---

## 4. 已和用户确认的方向

在原会话中,通过 AskUserQuestion 确认了三项:

1. **视觉风格** → 「混合:亮色为主 + 暗色可选 + 适度动效」
   (备选有:Linear 精致暗色风 / shadcn 极简亮色风 / Magic UI 炫酷动效风)
2. **改造范围** → 「全面改造(所有 19 个页面)」
3. **新增依赖** → 全部允许:
   - `recharts`(图表库)
   - `motion`(framer-motion v11+ 的新包名,动画库)
   - `sonner`(Toast 库,shadcn 官方推荐)
   - `cmdk`(Command 菜单库,shadcn 官方有封装)

---

## 5. 实施计划(分 4 阶段,每阶段可独立验证 + 提交)

### 阶段 0:基础设施(无破坏性,先铺地基)

> ⚠️ 本阶段是全部后续工作的地基,**必须先过 P0 风险验证**(见第 7 节)才能进入阶段 1。

| # | 动作 | 文件 | 细节 |
|---|---|---|---|
| 0.1 | 安装 4 个依赖 | `frontend/package.json` | `recharts`、`motion`、`sonner`、`cmdk`。**装完先做 P0-3 兼容性验证**(见下)再继续。 |
| 0.2 | 启用暗色模式:自写轻量 ThemeProvider | 新建 `frontend/src/components/theme/theme-provider.tsx`、`theme-toggle.tsx`;改 `App.tsx` | 实现:localStorage 持久化(键名 `theme`,值 `light`/`dark`/`system`)+ 给 `document.documentElement` 加/移 `.dark` 类 + 监听 `prefers-color-scheme`。**不引入 next-themes**(那是 Next.js 的)。Provider 挂在 `App.tsx` 的 `QueryClientProvider` 内、`ToastProvider` 外(主题切换不应触发 toast 重渲染)。 |
| 0.3 | 升级设计 token | `frontend/src/index.css` | (a) `--primary` 从 `222.2 47.4% 11.2%`(深蓝黑)换更有品牌感的蓝,建议 `221.2 83.2% 53.3%`(类 Linear/Stripe 蓝);(b) 新增 `--sidebar`、`--sidebar-foreground`、`--sidebar-border`、`--sidebar-accent`(亮/暗各一组);(c) 新增 `--chart-1`~`--chart-5`(5 个图表色,亮暗各一组,从 recharts/Tremor 调色板挑);(d) `--radius` 从 `0.5rem` 微调到 `0.625rem`(更现代,非必须)。 |
| 0.4 | 扩展 Tailwind 配置 | `frontend/tailwind.config.js` | 在 `extend.colors` 加 `sidebar: { DEFAULT, foreground, border, accent }` 和 `chart: { 1..5 }`,都走 `hsl(var(--xxx))`。**当前 config 里完全没有 sidebar/chart 映射**(实测确认),必须新增。动画 keyframes 见 0.5。 |
| 0.5 | 动画 keyframes(配合 motion,但纯 CSS 能做的用 CSS) | `frontend/tailwind.config.js` | 仅定义 4 类:`fade-in`、`slide-in-right`(drawer)、`slide-in-up`(列表 stagger)、`shimmer`(骨架屏微光)。其余动效走 `motion`。 |

**阶段 0 验证(P0 硬门槛,全部通过才进阶段 1):**

1. ✅ `npm run build`(tsc + vite build)无报错、无新 deprecation 警告
2. ✅ `npm run lint`(oxlint)无新错误
3. ✅ **P0-3 motion 兼容性**:`npm ls motion` 无 peer 依赖冲突警告;`motion` 在 React 19.2 下写一个 `<motion.div>` demo 页无运行时报错(控制台干净)
4. ✅ 暗色切换:`ThemeToggle` 点击后 `<html>` 出现/消失 `.dark` 类,刷新页面主题保持(localStorage 生效)
5. ✅ **P0-2 暗色 × 租户白标冲突验证(最高优先级)**:
   - 构造一个自定义 `theme_color`(如 `#E63946` 红、`#10B981` 绿)的租户环境
   - 在该环境下切换暗色,用浏览器 DevTools 的对比度检查(Lighthouse 或 WebAIM 在线工具)校验:
     - **正文文本 ≥ 4.5:1**,**大字/图标 ≥ 3:1**(WCAG AA)
     - 重点查 `primary` 背景 + `primary-foreground` 文字的按钮、`sidebar` 背景 + `sidebar-foreground` 文字
   - 若不达标:`theme.ts` 的 `applyThemeColor` 当前在暗色下会把 `--primary-foreground` 设成近黑/近白二选一(实测确认),**需要补暗色分支逻辑**(见第 7 节风险 1 的应对)
6. ✅ 19 个页面手动点一遍,暗/亮都不崩(纯视觉,不要求精致)

---

---

### 阶段 1:全局骨架改造(影响所有页面)

| # | 动作 | 文件 | 细节 |
|---|---|---|---|
| 1.1 | 重做侧边栏(参考 shadcn sidebar-07) | `dashboard-layout.tsx` | 把 `NAV_ITEMS`(16 项扁平)改为分组结构:① **工作台**(Dashboard、Chat、Knowledge、Agents)② **管理**(Groups、Customers、Users、Members、Roles、Permissions、Settings、Notifications、Billing、Logs)③ **平台**(Tenants、Billing-admin),按权限过滤后渲染。底部加用户卡(头像 + 名字 + 租户 + 退出)。移动端 drawer 用 `motion` 的 `AnimatePresence` + `motion.div` 做平滑滑入(替代当前 `translate-x` 过渡)。 |
| 1.2 | 重做顶栏 | `dashboard-layout.tsx` | 左侧:移动端汉堡 + ⌘K 触发按钮(显示快捷键提示 `⌘K`)。右侧:`ThemeToggle`(暗/亮/跟随系统下拉)+ `NotificationBell` + 超管 Badge + 用户头像 dropdown。保留现有 `GlobalSearchBox`(后续阶段 3 考虑并入 ⌘K,本阶段不动)。 |
| 1.3 | 新增 Command 菜单(参考 Linear ⌘K) | 新建 `frontend/src/components/layout/command-menu.tsx` | 用 `cmdk` + Radix Dialog 封装。三组命令:① **导航**(列出所有可访问路由,复用 `NAV_ITEMS` + 权守卫过滤)② **搜索**(输入 ≥2 字符时,复用现有 `/agents`、`/customers` 的 query,调 `useQuery` 展示前 5 条,回车跳转)③ **快捷操作**(切换主题、退出登录)。全局监听 `⌘K`/`Ctrl+K` 触发。 |
| 1.4 | 提取统一的 PageHeader | 新建 `frontend/src/components/layout/page-header.tsx` | API:`<PageHeader title subtitle actions />`。消除 19 个页面重复手写的「h1 text-3xl + 副标题 + 右上角操作」(grep 确认 16 处重复)。**本阶段只新建组件 + 在 Dashboard 试点接入,不批量替换**(批量替换放阶段 3 各批次)。 |
| 1.5 | 统一 ListState + EmptyState 的状态展示职责 | 改 `list-state.tsx`;新建 `frontend/src/components/ui/empty-state.tsx`(若阶段 2 未建) | **职责去重**(P2-11):`ListState` 专注「列表/表格区」的 loading(骨架)/empty/error;`EmptyState` 专注「整页空状态/首屏引导」(大插图+标题+描述+主操作 CTA)。两者不互相替代。`ListState` 扩展支持 `loadingVariant="skeleton"`,渲染 `<Skeleton>` 行(行数可配,默认 5)。 |

**阶段 1 验证:**

1. ✅ `npm run build && npm run lint` 通过
2. ✅ 侧边栏分组正确(3 组),按权限过滤(普通 member 看不到平台组)
3. ✅ ⌘K 在 Mac / Ctrl+K 在 Windows 触发;能跳转、能搜索、能切主题
4. ✅ 移动端 drawer 滑入/滑出动画流畅(无闪烁)
5. ✅ Dashboard 接入新 `PageHeader` 后视觉正常
6. ✅ `ListState` 骨架模式在某个列表页(如 Agents)loading 时显示骨架行
7. ✅ **P1-7 e2e 主动约束**:`npm run e2e` 全过 —— 改 layout 时**必须保留** `main-flow.spec.ts` 依赖的所有 `data-testid`(`login-identifier`/`login-password`/`login-submit`/`create-agent-btn`/`agent-name-input`/`agent-submit`/`message-input`/`send-btn`/`assistant-message`)和 `aria-label="选择会话"`

---

### 阶段 2:核心组件库升级(`components/ui/`)

> 本阶段涉及两个**待决策项**(第 9 节 #4 Toast、#5 Table),下方给出明确推荐 + 依据。

| # | 动作 | 文件 | 细节 / 决策 |
|---|---|---|---|
| 2.1 | Card 升级 | `card.tsx` | hover 微交互(用 `motion` 的 `whileHover={{ y: -2 }}`,**仅 Dashboard 指标卡、快速操作卡用**;普通内容卡不动,避免列表抖动)。可选流光边框(Border Beam 风格)做成 `variant="glow"`,默认关闭。 |
| 2.2 | Button 升级 | `button.tsx` | (a) focus ring 统一走 `--ring` token,确保暗色可见;(b) 新增 `loading` prop,内置 spinner(替代各页面手写 disabled+文字)。 |
| 2.3 | Badge 升级 | `badge.tsx` | 加 `dot` 变体(状态指示用小圆点,如「运行中」「已停用」),用 `::before` 伪元素画点。 |
| 2.4 | **Toast 决策(见下)** | — | **推荐:保留自研 toast,不引入 sonner**(除非满足触发条件)。详见下方「Toast 决策」。 |
| 2.5 | 新增图表组件 | 新建 `frontend/src/components/ui/chart.tsx` | 基于 recharts 封装 3 个组件:`AreaChart`(趋势)、`BarChart`(对比,支持横向)、`DonutChart`(占比)。配色强制走 `--chart-1~5` token,**监听暗色变化重渲染**(recharts 默认不响应 CSS 变量变化,需在 ThemeProvider 里 force re-render 或用 `useTheme` 触发)。 |
| 2.6 | EmptyState 组件 | 新建 `frontend/src/components/ui/empty-state.tsx` | API:`<EmptyState icon title description action />`。参考 Linear/Vercel 空状态(克制,不要 Aceternity 那种重背景)。与 `ListState` 职责分工见 1.5。 |

#### Toast 决策(P1-4)

**推荐:保留自研 toast,阶段 2 不做 sonner 替换。** 依据:

| 维度 | 现状(自研) | sonner 迁移成本 |
|---|---|---|
| 调用模式 | Context + `useToast()` hook | 全局 `toast.success()` 函数 |
| 影响范围 | **17 个文件、163 处调用**(实测) | 需改全部 17 个文件的 import + 调用方式 |
| App 挂载点 | `<ToastProvider>` 包在 `App.tsx` | 需改挂 `<Toaster />` + 调整 Provider 层级 |
| 现有能力 | success/error/default、4 秒自动消失、右下角 | sonner 多了:promise、堆叠、拖拽关闭、动画 |
| 缺失痛点 | 无 promise、无堆叠动画 | — |

**触发替换的条件(满足其一才换)**:① 计划中确实要用 `toast.promise`(如异步导出、长任务);② 产品反馈需要堆叠/拖拽关闭。当前计划没有刚需。

**若决定保留**:阶段 2.4 改为「给自研 toast 加可选的 `toast.promise(fn, msgs)` 辅助方法 + 进入动画(用 0.5 阶段的 `slide-in-up` keyframe)」,投入远小于全量迁移。

#### TanStack Table 决策(P1-5)

**推荐:阶段 2 不做通用封装,改为「阶段 3 第一批在 Agents 列表试点 → 验证 → 再决定是否推广」。砍掉原稿「保留手写 Table 作为 fallback」的暧昧表述。** 依据:

- 原稿的「保留 fallback + 新表格做独立组件」会导致**两套 Table 并存**,维护更重,违背「单一事实来源」。
- TanStack Table 已装未用,接入有真实收益(排序/列宽/视图切换),但收益要在真实页面上验证才知道值不值。
- **试点路径**:阶段 3 第一批改 Agents 列表时,用 TanStack Table 重写,验证排序/列宽/卡片-表格视图切换是否如预期;若效果好,第二批的 Users/Members/Roles 推广;若发现复杂度上升不划算,停止推广,Agents 页保持,其余页继续手写 Table。

**阶段 2.7(新增,仅当 Table 决策为推广)**:新建 `frontend/src/components/ui/data-table.tsx`,基于 TanStack Table 封装通用表格(列定义 + 排序 + 分页 + 可选列可见性)。

**阶段 2 验证:**

1. ✅ `npm run build && npm run lint` 通过
2. ✅ Card/Button/Badge 单独在 storybook 风格的 demo 页(或 Dashboard 试点)验证可用
3. ✅ 图表组件在亮/暗切换下颜色正确(recharts 响应 token 变化)
4. ✅ EmptyState 在某个空列表页(如无数据的 Tenants)显示正常
5. ✅ 若保留自研 toast:`toast.promise` 辅助方法可用;若换 sonner:`grep -rn "useToast\|ToastProvider" src/` 仅剩封装文件,**163 处调用 0 遗漏**

---

### 阶段 3:19 个页面逐一精修(分 3 批,带 GO/NO-GO 闸门)

> ⚠️ **P1-6 关键约束**:第一批(5 页)改完是硬性 GO/NO-GO 检查点。必须评估通过才启动第二批。

#### 第一批 —— 高频核心(5 页)

| 页面 | 现状 | 改造内容 | 关键依赖 |
|---|---|---|---|
| **Dashboard** | StoreView/HqView 双视图,纯 CSS 柱状条 | (a) 指标卡(`stat-card`)加 Number Ticker 数字滚动动画(`motion`)+ 流光边框(`card` glow variant);(b) 趋势图纯 CSS → recharts `AreaChart`;(c) HqView Top10 → recharts 横向 `BarChart`;(d) 「快速操作」改 Bento Grid 布局(参考 Aceternity bento-grid,克制用);(e) 接入 `PageHeader` | recharts、motion、card |
| **Agents** | 手写 Table | (a) 试点接入 TanStack Table(见阶段 2 决策):列排序、列宽、卡片/表格视图切换;(b) 接入 `PageHeader` + 骨架屏 | TanStack Table、ListState |
| **Chat**(940 行) | 无消息动画、无打字指示器 | (a) 消息进入用 `motion` stagger(每条延迟 30ms);(b) 加打字指示器(三点跳动,纯 CSS);(c) 消息流精致化(用户/助手气泡区分、代码块高亮已有);(d) **保留所有 `data-testid`**(`message-input`/`send-btn`/`assistant-message`) | motion |
| **Knowledge** | 文档列表 | (a) 文档列表状态可视化(已处理/处理中/失败 用 Badge dot);(b) 检索调试面板改卡片网格;(c) 接入 `PageHeader` + 骨架屏 | Badge、PageHeader |
| **Login** | 单列表单 | 参考 shadcn login-04:左品牌区(产品名 + slogan + 装饰图)+ 右表单区。**保留 `data-testid`**(`login-identifier`/`login-password`/`login-submit`) | 无新依赖 |

**第一批验证(= GO/NO-GO 检查点):**

1. ✅ `npm run build && npm run lint` 通过
2. ✅ `npm run e2e`(`main-flow.spec.ts`)全过 —— 5 页涉及的 testid 全部保留
3. ✅ **GO/NO-GO 评估**(由人决策,记录到 `progress.md`):
   - 视觉升级是否达标?(对照第 1 节目标自评)
   - 有无引入性能回归?(Lighthouse Performance 不低于改前)
   - TanStack Table 试点是否值得推广?(影响第二批决策)
   - 动效是否克制、无过度?(对照第 7 节"适度动效"原则)
4. ✅ **只有评估 GO,才启动第二批**

#### 第二批 —— 管理类(7 页)

| 页面 | 改造内容 |
|---|---|
| **Users / Members / Roles** | 统一 `PageHeader` + 表格(若 TanStack Table 试点 GO 则推广,否则手写 Table 精修)+ 骨架屏 |
| **Permissions** | 权限矩阵网格可视化(角色 × 权限 的勾选矩阵,参考 Linear 的设置页) |
| **Groups / Customers** | `PageHeader` + 表格 + 骨架屏 + EmptyState |
| **Settings**(966 行) | 改左侧 tab 导航(Radix Tabs,已有依赖)+ 右侧内容;`PageHeader`;各 tab 内容分块卡片化 |

#### 第三批 —— 平台/低频(7 页)

| 页面 | 改造内容 |
|---|---|
| **Tenants** | `PageHeader` + 表格 + 骨架屏;白标配置区加颜色预览(实时应用 `theme_color`) |
| **Billing / Billing-admin** | `PageHeader` + 消费趋势 recharts 图表 + 账单表格 |
| **Logs** | `PageHeader` + 表格 + 筛选器精修 |
| **Notifications** | `PageHeader` + 列表 + 已读/未读视觉区分(Badge dot) |
| **Profile** | `PageHeader` + 表单卡片化 |
| **NotFound**(404,14 行) | 重做精致页:大字号 404 + 装饰背景(克制用 Aceternity aurora-background)+ 返回首页 CTA |

**阶段 3 整体验证:**
每批改完跑 `npm run build && npm run lint && npm run e2e`;手动点查每页视觉。

---

## 6. 约束(项目铁律对齐)

- **不越界**:只改前端 `frontend/` 目录,不碰后端 API/数据库/RBAC 逻辑。后端 `endpoints.ts` 的现有接口是唯一数据来源。
- **依赖单向**:前端只调现有 API(`src/api/endpoints.ts`),不新增后端接口。
- **保留租户白标**:`useApplyTenantTheme`(`theme.ts` 的 `applyThemeColor`)逻辑不动;新 token 体系(`--sidebar*`/`--chart-*`)**必须兼容**租户 primary 覆盖 —— 租户色只覆盖 `--primary`,新 token 不被租户逻辑误清。
- **保留权限守卫**:`ProtectedRoute`/`RequireApiPermission`/`RequireUserManagement`/`RequireSuperAdmin`(实测 `App.tsx` 路由层级里有这 4 个守卫)逻辑不动,只改视觉。侧边栏分组后的权限过滤必须复用现有守卫逻辑,不能另造一套。
- **e2e 不破(P1-7 主动约束)**:页面改造**必须保留**现有所有 `data-testid`,新增组件不得复用已存在的 testid。当前 `main-flow.spec.ts` 依赖的 testid 清单:`login-identifier`、`login-password`、`login-submit`、`create-agent-btn`、`agent-name-input`、`agent-submit`、`message-input`、`send-btn`、`assistant-message`,以及 `aria-label="选择会话"`。改造前先跑一遍 `npm run e2e` 建基线,改造后再跑确认全绿。
- **motion 范围限定(P1-8)**:动效**仅限**这 4 类,不扩散:① 消息进入 stagger(Chat)② hover 微交互(仅 Dashboard 指标卡/快速操作卡)③ drawer 滑入(移动端侧边栏)④ Number Ticker 数字滚动(Dashboard 指标卡)。其余一律用 CSS transition/keyframes。
- **每阶段独立 PR**:不全憋一个大 PR。每阶段一个 PR,合入前 e2e 回归。

---

## 7. 风险与回退

| # | 风险 | 等级 | 应对(具体化) |
|---|---|---|---|
| 1 | **🔴 租户白标 × 暗色 token 冲突**(原稿漏) | **P0** | `theme.ts` 的 `applyThemeColor` 当前在暗色下会把 `--primary-foreground` 设成近黑/近白二选一(实测确认 line 91-94),**不考虑 `.dark` 背景**,自定义租户色切暗色后对比度可能崩。**应对**:阶段 0.2 的 ThemeProvider 落地后,在 `applyThemeColor` 里读取当前主题(`document.documentElement.classList.contains('dark')`),为暗色背景单独算前景色;或限定租户 primary 仅影响强调元素(按钮、链接),不覆盖大背景。阶段 0 验证项 5 是硬门槛。 |
| 2 | **🔴 motion 对 React 19.2 兼容性**(原稿漏) | **P0** | `package.json` 现是 React 19.2.7。`motion`(framer-motion v11+)对新 React 版本有滞后。**应对**:阶段 0.1 装完依赖先做 `npm ls motion` 查 peer 警告 + 写 demo 验证;若有冲突,退回到纯 CSS keyframes(阶段 0.5 的 4 类动画已覆盖大部分场景)。 |
| 3 | 暗色 token 配比不当,对比度差 | P1 | **工具**:浏览器 DevTools 的颜色选择器自带对比率,或 WebAIM Contrast Checker(在线)。**门槛**:正文文本 ≥ 4.5:1,大字/图标 ≥ 3:1(WCAG AA)。写进阶段 0 验证项 5。 |
| 4 | TanStack Table 接入改变现有表格行为 | P1 | **砍掉原稿「保留手写 Table 作 fallback」的暧昧方案**(两套并存维护更重)。改为阶段 3 第一批 Agents 页试点,验证后决定是否推广(见阶段 2 决策)。 |
| 5 | Toast 迁移漏改 | P1 | 原稿说「约 20+ 处」严重低估。**实测:17 个文件、163 处调用**,模式是 `useToast()` hook(非 `toast()` 函数)。**若决定换 sonner**:验收命令 `grep -rn "useToast\|ToastProvider\|from \"@/components/ui/toast\"" src/` 应仅剩封装文件,其余 0 命中。**当前推荐保留自研**(见阶段 2.4 决策),此项风险消除。 |
| 6 | 动效过度影响性能/体验 | P1 | motion 范围限定 4 类(见第 6 节)。Lighthouse Performance 不低于改前基线(阶段 3 GO/NO-GO 校验)。不加无意义持续动画。 |
| 7 | recharts 不响应 CSS 变量变化,暗色切换图表色不更新 | P2 | recharts 默认读 token 只在挂载时生效。**应对**:在 ThemeProvider 里用 `key={theme}` 强制重渲染图表,或在 chart 组件里 `useTheme()` 订阅主题变化重算配色。 |
| 8 | oxlint 新规则卡新依赖/新模式 | P2 | 阶段 0 装依赖后立即跑 `npm run lint`,发现新规则报错先评估是改代码还是 `// oxlint-disable`(优先改代码)。 |
| 9 | 改动量大,中途出问题 | P1 | 每阶段一个 PR(非 commit),合入前 `npm run build && npm run lint && npm run e2e` 全绿。可整体 `git revert` merge 或回退单个 PR。阶段 3 第一批后设 GO/NO-GO 闸门。 |

---

## 8. 执行策略

分阶段提交,**每阶段一个 PR**(非 commit),顺序执行。每个 PR 合入前必须 `npm run build && npm run lint && npm run e2e` 全绿。

| 顺序 | PR 内容 | 合入前门禁 | 备注 |
|---|---|---|---|
| 1 | **阶段 0**(地基:依赖 + 暗色 + token) | 阶段 0 的 6 项验证全过(含 P0-2/P0-3) | **P0 风险在此 PR 验证,不过则不进阶段 1** |
| 2 | **阶段 1**(全局骨架:侧边栏 + 顶栏 + ⌘K + PageHeader + ListState) | 阶段 1 的 7 项验证全过 | e2e 必须全绿(testid 保留) |
| 3 | **阶段 2**(组件库:Card/Button/Badge/Chart/EmptyState + Toast/Table 决策落地) | 阶段 2 的 5 项验证全过 | Toast/Table 决策在此 PR 定调 |
| 4 | **阶段 3 第一批**(Dashboard/Agents/Chat/Knowledge/Login) | 阶段 3 第一批 4 项验证全过 | **GO/NO-GO 闸门**:评估通过才启动第二批 |
| 5 | **阶段 3 第二批**(Users/Members/Roles/Permissions/Groups/Customers/Settings) | build + lint + e2e 全绿 | |
| 6 | **阶段 3 第三批**(Tenants/Billing/Billing-admin/Logs/Notifications/Profile/404) | build + lint + e2e 全绿 | 最后整体回归 |

**回退单元是 PR**(merge commit 可整体 revert),不是单个 commit。

---

## 9. 决策结论(原「待审查决策点」,审查后已逐项定调)

> 第 5/6/7 节已嵌入具体决策,这里集中记录结论 + 依据,供执行时对照。

| # | 决策点 | 结论 | 依据 |
|---|---|---|---|
| 1 | 设计参考真实性 | ✅ **全部真实** | 独立审查已逐一 curl 5 个 URL,title/meta/组件 slug 全部属实(含 Linear 的 AI agent 措辞)。 |
| 2 | 4 个新库是否必要 | **recharts/cmdk 必要;motion 条件必要;sonner 不必要(见 #5)** | recharts 是图表刚需(现状手写柱状条);cmdk 是 ⌘K 核心卖点,shadcn 官方封装;motion 仅 4 类动效用,纯 CSS 也能做,引入需过 P0-3 兼容验证。 |
| 3 | 暗色模式实现 | ✅ **自写 ThemeProvider** | 需求就是持久化 + 切 `.dark` 类,自写 <30 行,不为这个引第三方。挂在 `QueryClientProvider` 内、`ToastProvider` 外。 |
| 4 | TanStack Table 接入 | **试点 → 验证 → 再决定推广**,砍掉 fallback 方案 | 已装未用是沉没成本,接入有收益但需真实页面验证。阶段 3 第一批 Agents 页试点,GO/NO-GO 闸门决定第二批是否推广。不做"两套 Table 并存"。 |
| 5 | Toast 替换 | **推荐保留自研,不换 sonner** | 实测 17 文件/163 处调用,迁移成本高;现有 toast 仅缺 promise 和堆叠动画,当前计划无刚需。若要用 promise,给自研 toast 加辅助方法即可。 |
| 6 | 改造粒度 | **19 页全改,但分批 + GO/NO-GO 闸门** | 阶段 3 第一批 5 页改完是硬检查点,评估通过才启动第二批。不做"先做 5 页看效果"的退缩方案(那样第二批永远启动不了),但保留闸门兜底。 |
| 7 | 是否越界 | ✅ **不越界** | 约束明确(第 6 节):只改 frontend/,不动后端/权限/租户逻辑,e2e testid 主动保留。 |

---

## 附:原会话上下文

- 原任务:用户要求「去相关网站找 React 前端优秀设计,综合各优点(必须有真实来源可查证),然后改造前端 UI/UX」
- WebSearch/webReader MCP 工具配额耗尽(2026-08-05 重置),原会话改用 `curl` 抓取参考站 HTML
- 本计划已通过 ExitPlanMode 提交给用户审批,用户选择「先写成文档在新会话审查」而非立即执行
