# 计划:前端设计系统收口总纲(颜色 token + 间距卡片层级规范)

> 这是 **前端设计系统收口系列的总纲文档**(EP1,登记性质,grill 访谈成果固化)。
> 2026-07-30 Session 171 `/grill-with-docs` 收敛,7 个决策点全定。
> 本文档是后续 `/to-spec`(落各 feature 的 plan-<id>.md)+ `/to-tickets`(拆切片)的输入。
> 对应 feature_list.json 待登记的 `id`:`design-system-token-foundation` / `design-system-color-sweep` / `design-system-spacing-card-hierarchy`

---

## 背景:为什么要做设计系统收口

### 起点:一次新方向的 grill 访谈

用户提出「新加一个前端界面显示和交互的改造任务」,聚焦「全站视觉统一」,诉求含四项:视觉专业感 / 操作效率 / 一致性规范 / 移动端适配。经 `/grill-with-docs` 访谈,**三项剥离为独立后续系列**,本次 EP1 收敛为**纯「设计系统收口」**。

### 前端现状盘点(grill 前 Explore agent 扫描结论)

**基建扎实(不是从零建设计系统)**:

| 维度 | 现状 |
|---|---|
| UI 组件库 | shadcn/ui 自管源码 + 27 个已封装组件(`src/components/ui/`) |
| Token 体系 | Tailwind v3 + 完整 HSL CSS 变量(~25 个,`src/index.css` `:root`) |
| Token 覆盖 | ~80% 已 token 化(`text-muted` 285 / `bg-muted` 58 / `text-destructive` 54 等) |
| 暗色模式 | 完整链路(light/dark/system)+ theme-provider + toggle 已接(`src/components/theme/`) |
| 圆角/主色 | 单 `--radius: 0.625rem` token + 品牌蓝主色 + 白标 `--primary` 覆盖(`src/lib/theme.ts`) |

**渗透点明确(一致性的最后 20% 没收口)**:

| 问题 | 数据 |
|---|---|
| 硬编码调色板色 | **~70 处**散落(emerald/amber/rose/violet/cyan…),集中在 permissions/notifications/settings/billing 页 + ui/avatar + ui/badge dot + ui/toast + layout/notification-bell |
| 零 semantic token | **全仓没有 `--success`/`--warning`/`--info`**,成功/警告色直接用 emerald/amber 原色,绕过 token 层 |
| 暗色风险 | badge dot(`bg-emerald-500` 等)+ avatar 8 色环 + 业务页硬编码色**不随暗色 token 切换**,靠原色在深底可见性硬撑 |
| 字号任意值绕过 | `text-[10px]` ×7 / `text-[11px]` ×4 等散落(刻度不够细时的临时绕过) |
| 移动端适配 | **44 个页面绝大多数零响应式前缀**(全站 lg:/sm:/md: 合计 63 次,覆盖率 <5%)—— 🔴 最大空白,但**剥离为后续系列** |

---

## 总体方案(grill 7 个决策点)

### 决策记录

| # | 决策点 | 用户选择 |
|---|---|---|
| 1 | 移动端适配定位 | **剥离为独立后续 EP1 系列**(44 页面工程量巨大,单独成系列风险更低) |
| 2 | 操作效率(loading/空态/动效/反馈/点击步数)定位 | **剥离为独立后续 EP1 系列**(与 token 收口是正交工作域,混在 WIP=1 下会让 feature 拆分混乱) |
| 3 | ~70 处硬编码色处理 | **全收口 + 建 semantic token**(--success/--warning/--info 三 token + emerald→success 等语义映射) |
| 4 | semantic token 暗色协同 | **双色值**(亮 + 暗各一套,顺手解决硬编码色暗色风险) |
| 5 | 字号/间距/字体 | **只收口任意值绕过**(text-[10px] 等映射回默认刻度),不推全站字号 token 化 |
| 6 | feature 拆分粒度 | **3 个 feature**(基建 + 扫荡 + 间距卡片,详见下方子任务清单) |
| 7 | 交互反馈视觉(hover/active/focus)裁决 | **剥离为「操作效率」后续系列**(与已剥离项重叠,保持边界干净) |
| — | feature 执行顺序 | **A → B → C**(颜色链路先打通,间距卡片正交收尾) |
| — | 验收硬标准 | **grep 归零 + 暗色对比度验证**(WCAG AA)+ npm test/build 全绿 + oxlint 0/0(客观可验,不靠主观) |

### 目标架构(语义色 token 值已由 B3 变体定稿,见顶部「设计变体探索结论」)

```
index.css :root(亮色):
  ├── --success: 152 76% 36%   ← B3 定稿(用于正向/峰值/达成)
  ├── --warning:  35 92% 50%   ← B3 定稿(用于提醒/谷值)
  ├── --danger :   0 84% 60%   ← B3 定稿(危险;复用现有 destructive 语义)
  ├── --info   : 189 90% 42%   ← B3 定稿(信息/青)
  └── (现有 ~25 个 token 保留)

index.css .dark(暗色,提亮保高辨识度):
  ├── --success: 152 64% 48%   ← 暗色变体
  ├── --warning:  38 95% 58%   ← 暗色变体
  ├── --danger :   0 80% 64%   ← 暗色变体
  ├── --info   : 189 80% 55%   ← 暗色变体
  └── (现有暗色 token 保留)

tailwind.config.js theme.extend.colors:
  ├── success: { DEFAULT: hsl(var(--success)), foreground: ... }   ← 新增
  ├── warning: { ... }                                              ← 新增
  ├── danger:  { ... }   ← 新增(danger 与 destructive 并存:danger 是语义色 token,destructive 是现有命名)
  └── info: { ... }                                                 ← 新增

映射应用(语义色):
  emerald-500 → success    (成功态)
  amber-500   → warning    (警告态)
  red-500     → danger     (危险态)
  cyan-500    → info       (信息态)

保留为「有意的多色」(设计性,非语义):
  avatar.tsx 8 色环(bg-blue/emerald/amber/rose/violet/cyan/orange/pink-500)—— 头像背景色环,刻意多色,不动
  chart-1..5 数据可视化五色 —— 数据密集场景的多色维度区分,合法保留(spec §2.4)
```

### 边界规则(避免歧义)

- **语义色 vs 设计性多色**:只有表达 success/warning/info **语义**的硬编码色映射到 token;avatar 色环、badge dot 装饰性多色等「刻意多色」的设计性用法**保留不动**。
- **暗色协同**:建 semantic token 时同步定义暗色变体,一次性消除「硬编码色在暗色下靠原色硬撑」的风险。
- **字号只收口绕过**:不新增 fontSize token 体系,只把 `text-[10px]` 等任意像素值映射回 Tailwind 默认刻度。

---

## 子任务清单(WIP=1 顺序执行,共 3 个 feature)

| 顺序 | id | 范围 | 前置 | plan 文档(待 /to-spec 落) |
|------|----|------|------|----------|
| A | `design-system-token-foundation` | semantic token 基建:在 `index.css` + `tailwind.config.js` 建 `--success`/`--warning`/`--danger`/`--info` 四 token 双色值(亮+暗,值见上方「目标架构」B3 定稿)+ 把 `ui/` 组件库内部(button/badge/toast/stat-card 等)的硬编码色映射到新 token | 无 | `harness/docs/plan-design-system-token-foundation.md` |
| B | `design-system-color-sweep` | 业务页硬编码色扫荡:把 permissions/notifications/settings/billing/dashboard/users 等业务页 + layout/notification-bell + markdown-view 的硬编码色逐个映射到 semantic token | A | `harness/docs/plan-design-system-color-sweep.md` |
| C | `design-system-spacing-card-hierarchy` | 间距与卡片层级规范:建语义间距 token + 统一 shadow/border/背景层规范(Card 阴影 / Surface 背景)+ 顺手收口字号任意值绕过(text-[10px] 等映射回默认刻度) | 无(与 A/B 正交) | `harness/docs/plan-design-system-spacing-card-hierarchy.md` |

> 依赖关系:A 是地基(token 定义),B 依赖 A(A 提供的 token),C 与 A/B 正交可独立做。WIP=1 下顺序 A → B → C。

### 系列状态

🚧 **规划中**(2026-07-30 grill 完成 + 2026-07-31 设计变体探索 B3 定稿,待 `/to-spec` 落各 feature plan + 登记 feature_list.json)。

### 设计变体探索结论(2026-07-31,huashu-design 驱动)

用 `/huashu-design` 基于真实 design system 产出 6 份可交互 HTML 变体(A1/A2/A3 + B1/B2/B3,存 `design-demos/`),经多轮布局微调后**用户选定 B3「数据可视化质感」**作为设计系统收口方向。

- **为什么选 B3**:数据为尊(UI chrome 退到 1px hairline,数据本身发光)、chart-1..5 语义化绑定(每色承载维度信息)、精致 SVG 图表(参考线/峰值谷值标注/数据摘要带)—— 与本项目「多租户 AI SaaS + 数据看板」的产品调性最契合。
- **B3 定稿的语义色 HSL 值已固化为 Feature A 的 token 定义依据**(见上方「目标架构」段:`--success 152 76% 36%` / `--warning 35 92% 50%` / `--danger 0 84% 60%` / `--info 189 90% 42%`,暗色变体提亮值一并定稿)。
- **B3 还验证了「数据可视化正当多色」的边界**:chart-1..5 用于数据维度区分是合法的(非装饰 slop),这条边界规则已写入上方「保留为有意的多色」。
- **变体文件用途**:`design-demos/*.html` 是定稿前的探索产物(throwaway,不计入生产代码),保留作 Feature A/B/C 实施时的视觉参照。定稿的 B3.html 是「目标视觉」的具象化参照,实施时对照它确认 token 映射后的实际效果。

---

## 不做的事(系列边界,grill 明确排除)

- **🚫 移动端/响应式适配** —— 44 页面工程量巨大,剥离为独立后续 EP1 系列
- **🚫 操作效率优化**(loading 态 / 空状态 / 动效 / 反馈 / 点击步数)—— 与 token 收口正交,剥离为独立后续 EP1 系列
- **🚫 交互反馈视觉**(hover/active/focus 态统一)—— 归「操作效率」后续系列(决策 7 裁决,避免重叠)
- **🚫 全站字号 token 化**(语义命名 text-caption/text-body 等)—— 工程量大(需改上百处 className),只收口任意值绕过(决策 5)
- **🚫 字体自定义**(fontFamily 扩展 / Google Fonts)—— 保留 Tailwind 默认 sans 栈
- **🚫 avatar 8 色环 / badge dot 装饰性多色** —— 设计性多色保留不动(非语义色)
- **🚫 白标能力扩展** —— `--primary` 白标覆盖已实现,本系列不动白标逻辑

---

## 后续系列预告(grill 剥离出去的方向,待用户排期)

1. **移动端响应式适配系列** —— 44 页面按桌面单列写死,移动端内容适配基本缺失(壳子完整、内容为零)。工程量大,单独成系列。
2. **操作效率优化系列** —— loading 态 / 空状态 / 动效规范 / 交互反馈视觉(hover/active/focus)/ 点击步数优化。交互工程,与 token 收口正交。

---

## 参考文件(系列实施时对照)

| 参照 | 路径 |
|------|------|
| Tailwind 配置 | `frontend/tailwind.config.js` |
| 全局样式 + design tokens | `frontend/src/index.css`(`:root` + `.dark`) |
| 白标主题色 | `frontend/src/lib/theme.ts`(`applyThemeColor`) |
| 暗色 theme-provider | `frontend/src/components/theme/theme-provider.tsx` |
| 组件库(自管源码) | `frontend/src/components/ui/`(button/badge/avatar/toast/stat-card 等 27 个) |
| 响应式 shell(已完成) | `frontend/src/components/layout/dashboard-layout.tsx` |
| 硬编码色集中页 | `permissions-page.tsx`(9)/ `notifications-page.tsx`(8)/ `settings-page.tsx`(7)/ `billing-page.tsx`(6) |
| 响应式空白页(0 前缀) | `bookings/hq-view.tsx` / `roles-page.tsx` / `groups-page.tsx` / `knowledge-page.tsx` / `customers/store-view.tsx` / `notifications-page.tsx` |
| 路由/Provider 层级 | `frontend/src/App.tsx` |

## 行业实践参考(供 /to-spec 引用)

- WCAG 2.1 对比度标准(AA:正常文本 4.5:1,大文本 3:1)—— semantic token 暗色变体验证基准
- shadcn/ui 官方 semantic color 模式 —— token 命名与组织参考
- Tailwind CSS v3 主题扩展 —— `theme.extend.colors` + `hsl(var(--xxx))` 模式
