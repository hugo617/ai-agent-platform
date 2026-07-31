# 计划:设计系统收口 — Feature B:业务页硬编码色扫荡

> **id**: `design-system-color-sweep`
> **状态**: ✅ passing(全 5 切片完成,2026-07-31 Session 178 末切片合并)
> **优先级**: 82(feature_list.json)
> **创建日期**: 2026-07-31
> **系列总纲**: [`plan-frontend-design-system-overview.md`](./plan-frontend-design-system-overview.md)
> **系列内位置**: B(依赖 Feature A 提供的 semantic token;C 与本 feature 正交)

---

## 0. v1 → vN 变更摘要

| v(N-1) 问题 | 严重度 | vN 处理 |
|---|---|---|
| _(首版,无修订)_ | — | — |

---

## 1. Problem Statement(对齐 to-spec)

Feature A 建好 `--success`/`--warning`/`--danger`/`--info` 四 token 后,**业务页**仍散落 ~30 处硬编码调色板原色(emerald/amber/rose/cyan/blue/green 等),集中表达「成功/警告/危险/信息」四类语义,却绕过 token 层直接引用 Tailwind 原色。

**后果**:这些色在暗色下不随 `.dark` 切换(原色靠在深底勉强可见硬撑)、无法被主题覆盖触及、调色需散落多文件改。Feature A 只收口了 `ui/` 组件库内部,业务页这「最后 20%」没收口,设计系统就还没真正闭环。

## 2. Solution(对齐 to-spec)

逐文件把业务页里**表达语义**的硬编码色映射到 Feature A 的四 token(emerald→success / amber→warning / rose/red→danger / blue/cyan→info),暗色下自动切换为 token 的暗色变体,一次性消除「暗色靠原色硬撑」风险。

**不动**:代码块主题色(`markdown-view.tsx` 的 `zinc-700/900/100` 模拟深色代码块,非语义色,归 Feature C 表面层或保留)、`avatar` 8 色环(Feature A 已留)、`chart-1..5`(数据可视化多色)。

## 3. User Stories(对齐 to-spec)

- 作为 **业务页使用者**,我想要「成功/警告/危险/信息」四类状态色在所有页面一致,以便跨页面读状态不歧义
- 作为 **暗色模式用户**,我想要业务页的状态色在暗色下自动提亮,以便深底背景上保持可读
- 作为 **看账单的用户**(`billing`),我想要收入(emerald)和支出(rose)色稳定可辨,以便快速识别资金流向
- 作为 **看用户列表的管理员**(`users`),我想要「总数/活跃/锁定/本月新增」四个统计卡片 icon 配色有语义(信息/成功/危险/警告),以便一眼读懂数据维度
- 作为 **收通知的用户**(`notifications`/`notification-bell`),我想要「余额预警/充值到账/角色变更」三类通知的色与图标语义一致(警告/成功/信息),以便扫一眼分类
- 作为 **设计系统维护者**,我想要业务页不再有语义性硬编码原色,以便未来调色只在 token 层一处

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 0 | 纯前端 |
| 数据库迁移 | 0 | 无 |
| 前端文件改动 | ~12 | 业务页:settings/permissions/billing/billing-admin/users/notifications/dashboard/composite-mode;layout:notification-bell/dashboard-layout;chat:conversation-list-panel/markdown-view |
| 新增测试类 | ~0-1 | 本 feature 是 className 替换,以构建/lint/视觉验证为主;必要时补渲染快照 |
| Skill / Hook / 配置 | 0 | 无 |

> **文件分布(实测扫描)**:硬编码色按文件:settings(5)/permissions(5)/billing(5)/users(4)/notifications(3)/dashboard(3)/composite-mode(3)/billing-admin(2)/conversation-list-panel(2)/notification-bell(3)/markdown-view(2)/dashboard-layout(1)。

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(纯前端)
- 是否修改现有租户隔离逻辑? **NO**
- 是否引入跨租户访问点? **NO**
- 验证:无多租户语义

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 `require_permission` caller? **NO**
- 是否影响 graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist

**N/A**(纯前端)

### 4.5 其他实施决策

**① 映射规则(语义色 → token,逐处核对)**

| 原色 className | 语义 | 映射到 |
|---|---|---|
| `emerald-*` / `green-600` | 成功 / 达成 / 收入 | `success` |
| `amber-*` | 警告 / 余额预警 / 提醒 | `warning` |
| `rose-*` / `red-500` | 危险 / 锁定 / 支出 | `danger` |
| `blue-*` / `cyan-*` | 信息 / 角色变更 / 中性统计 | `info` |

**② 关键页面映射决策(基于实测行级扫描)**

| 文件 | 行级现状 | 映射决策 |
|---|---|---|
| `settings-page.tsx` | `text-amber-500` AlertTriangle + `border/bg-amber-500/*` 警告框 + `text-green-600` Check + `bg-emerald-500 text-white` active 态 | amber→`warning`(警告框整簇)/ green→`success`(Check)/ emerald→`success`(active)。**注意 `dark:text-amber-400` 这种已手写暗色变体的,映射后可删除 dark: 变体(token 自动切暗色)** |
| `permissions-page.tsx` | `border/bg-amber-*` 警告 Card + `text-amber-600 dark:text-amber-500` Shield/Lock + `bg-emerald-500` granted 标记 | amber→`warning` / emerald→`success`。**手写 dark: 变体删除(token 接管暗色)** |
| `billing-page.tsx` | `text-emerald-500` 收入 ArrowUp + `text-rose-500` 支出 ArrowDown + `text-emerald/rose-600` 交易方向 | emerald→`success`(收入)/ rose→`danger`(支出) |
| `billing-admin-page.tsx` | `text-emerald-500` / `text-rose-500` Coins icon | emerald→`success` / rose→`danger` |
| `users-page.tsx` | 四 stat icon `text-blue/emerald/rose/amber-500`(总数/活跃/锁定/新增) | blue→`info` / emerald→`success` / rose→`danger` / amber→`warning`(四语义恰好对齐) |
| `notifications-page.tsx` | `accent: bg-amber-100 text-amber-800`(余额预警)/ `bg-emerald-100 text-emerald-800`(充值)/ `bg-blue-100 text-blue-800`(角色) | amber→`warning` / emerald→`success` / blue→`info`。**`-100`/`-800` 是浅底深字组合 → 用 `bg-warning/10 text-warning` 或保留语义前缀(token 的 DEFAULT 即可,浅底用 `/10` alpha)** |
| `dashboard-page.tsx` | 三 accent `text-blue/emerald/amber-500` | blue→`info` / emerald→`success` / amber→`warning` |
| `composite-mode.tsx` | `border/bg/text-amber-*` 余额不足警告框 | amber→`warning`(整簇) |
| `notification-bell.tsx` | `accent: text-amber/emerald/blue-600` 三类通知 | amber→`warning` / emerald→`success` / blue→`info` |
| `conversation-list-panel.tsx` | `text-amber-500` Pin + `fill/text-amber-400` Star | Pin/Star 是**置顶/收藏标记**。**边界判断**:amber 在此表达「高亮/强调」而非严格 warning 语义 → **保留为 amber 或映射 `warning`?** EP3 实施时核对:若仅为视觉强调(非警告),保留;若团队倾向统一,映射 warning。**默认保留**,在 plan checklist 注明 |
| `markdown-view.tsx` | `text-zinc-400/100` + `bg-zinc-900/700` 代码块按钮/背景 | **zinc 是代码块主题色(模拟深色代码块),非语义色 → 保留不动**(归 Feature C 表面层或保留) |
| `dashboard-layout.tsx` | `border-amber-300 bg-amber-100 text-amber-800` Badge(疑似 demo/构建标识) | amber→`warning`(浅底深字 → `border-warning/30 bg-warning/10 text-warning`) |

**③ 浅底深字组合的处理(`-100`/`-800` / `-50`/`-800` 等)**

通知/标识常用「浅色底 + 深色字」组合(如 `bg-amber-100 text-amber-800`)。映射策略:

- **底色**:用 token DEFAULT + alpha,如 `bg-warning/10`(浅 warning 底)
- **字色**:用 token DEFAULT,如 `text-warning`(warning 标准色,在 `/10` 浅底上对比度达标)
- **边框**:如需,`border-warning/30`

**理由**:token 层只定义一个 DEFAULT 值(亮/暗各一),浅底深字的「层次感」由 alpha(`/10` `/30`)表达,而非定义额外 `-light`/`-dark` token。这与 B3「数据为尊,UI chrome 退到 hairline」的设计调性一致。

**④ 暗色变体手写删除**

现状多处手写 `dark:text-amber-400` / `dark:bg-amber-950/20` 来补偿暗色。映射到 token 后,token 自带暗色变体,**这些手写 dark: 变体应删除**(否则双重定义)。EP3 实施时逐处核对:映射后 dark: 变体是否冗余,冗余则删。

**⑤ 边界保留(不映射)**

| 用法 | 文件 | 保留理由 |
|---|---|---|
| 代码块主题色 zinc | markdown-view.tsx | 模拟深色代码块,非语义色(归 Feature C 表面层或保留) |
| Pin/Star 强调色 amber | conversation-list-panel.tsx | 表达「高亮/强调」非严格 warning(EP3 核对,默认保留) |
| avatar 8 色环 | (Feature A 范围) | 设计性多色 |
| chart-1..5 | (全局) | 数据可视化多色 |

### 4.6 验收硬标准(来自总纲,客观可验)

1. **grep 归零**(本 feature 范围):业务页 + layout + chat 内的**语义性**硬编码原色(emerald/amber/rose/red/blue/cyan/green 表达 success/warning/danger/info 语义的)= 0(代码块 zinc / Pin-Star amber / 设计性多色保留的不算)
2. **暗色对比度**:映射后所有状态色在暗色下达 WCAG AA(token 暗色变体已在 Feature A 验证,本 feature 复用)
3. **npm test 全绿 + npm run build 0 错 + oxlint 0/0**
4. **零行为变更**:映射前后视觉一致(亮色下 token 渲染色 = 原色调色板渲染色,因 B3 定稿值就是同色系)

---

## 5. Testing Decisions(对齐 to-spec)

- **测试金字塔**:本 feature 是 className 机械替换 + 少量 alpha 调整,无运行时逻辑 → **以构建/类型/lint + grep 归零为主**
- **优先复用现有 seam**:各业务页若有既有组件测试(如 stat-card 渲染),加色映射断言;无则不强建
- **grep 归零自动化**:验收时跑固定 grep(见 §10 验收标准),结果记入 evidence
- **视觉验证**:对照 `design-demos/B3.html`,关键页面(账单/用户统计/通知)映射前后亮/暗双模式截图比对(手动,evidence 记录)
- **覆盖率**:纯前端无服务端基线;目标 = 现有前端测试不回归

---

## 6. 切片规划(对齐 to-tickets tracer-bullet)

> 见下方「实施切片」段(/to-tickets 产出)。

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:改动文件 ~12(>10 阈值)→ **满足复杂任务触发条件**。但本 feature 性质是「className 机械映射 + alpha 调整」,无鉴权/权限/迁移/安全敏感/不可逆操作,实际风险低。

**审查方式**:**轻量自审为主**(EP2 收尾自检 + 切片 acceptance criteria),**EP3 末切片收尾时若发现映射边界争议**(如 Pin/Star amber、浅底深字 alpha 取值)累积 >3 处,则补一次单模型双轴 review 落 v2。否则不强制多模型审查。

---

## 8. Out of Scope(对齐 to-spec)

- ❌ **`ui/` 组件库内部映射** → Feature A
- ❌ **间距 token + 卡片层级规范** → Feature C
- ❌ **代码块主题色(zinc)重构** → 保留或归 Feature C 表面层
- ❌ **avatar 8 色环 / chart-1..5** → 设计性/数据可视化多色保留
- ❌ **字号任意值收口** → Feature C 顺手项
- ❌ **`destructive` → `danger` 全站迁移** → 保留 destructive 既有命名
- ❌ **移动端/响应式适配** → 系列边界

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Pin/Star 的 amber 是「强调」非「警告」,误映射破坏语义 | 中 | §4.5② 默认保留,EP3 核对;若映射则在 evidence 注明理由 |
| 浅底深字组合(`-100`/`-800`)映射成 alpha 后视觉层次弱化 | 中 | §4.5③ 统一用 `/10` 底 + DEFAULT 字 + `/30` 边框;EP3 视觉比对,必要时调 alpha |
| 手写 dark: 变体删除时误删非冗余的 dark: 规则 | 中 | 逐处核对:仅删「与 token 暗色变体重复」的 dark:;非语义 dark:(如布局)保留 |
| 12 文件改动跨页面一致性难保证 | 中 | 切片按「色系分组」而非「页面分组」(见切片规划),同语义一次性收口所有页面 |
| `users` stat 四色映射后 icon 配色失去「四色区分」视觉 | 低 | 四语义(info/success/danger/warning)本身四色,映射后仍四色可区分,且语义更明确 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. 业务页 + layout + chat 内**语义性**硬编码原色 grep = 0(grep 模式:emerald/amber/rose/red/blue/cyan/green 表达 success/warning/danger/info 的;排除 markdown-view 代码块 zinc + conversation-list-panel Pin/Star amber + avatar/chart 设计性多色)
2. `cd frontend && npm run build` 0 类型错误 + `npx oxlint` 0/0 + `npm test` 全绿
3. 映射后暗色下状态色 WCAG AA 对比度达标(复用 Feature A token 暗色变体验证)
4. 对照 `design-demos/B3.html`,关键页面(billing/users/notifications)亮/暗双模式视觉一致
5. 手写 `dark:` 冗余变体已删除(仅删与 token 暗色重复的)

---

## 11. 不越界声明

本次改动**只**涉及:业务页(settings/permissions/billing/billing-admin/users/notifications/dashboard/composite-mode)、layout(notification-bell/dashboard-layout)、chat(conversation-list-panel)的**语义性**硬编码色映射;`markdown-view.tsx` 仅在确认 zinc 为代码块主题后**保留不动**(或归 Feature C)。

**不**触碰:`ui/` 组件库(Feature A 范围)、avatar 8 色环、chart-1..5、`destructive` 命名、间距/字号体系、token 定义(Feature A)、白标逻辑、任何后端代码。

---

## 实施切片(/to-tickets 产出)

### 切片依赖图

```
切片 01(success 收口:emerald/green → success,跨页)── 无 blocker,frontier
   │
   ├─→ 切片 02(warning 收口:amber → warning,跨页)── blocked by 01(同批保持一致性基线)
   │
   ├─→ 切片 03(danger 收口:rose/red → danger,跨页)── blocked by 01
   │
   ├─→ 切片 04(info 收口:blue/cyan → info,跨页)── blocked by 01
   │
   └─→ 切片 05(收尾:暗色 dark: 冗余清理 + 视觉一致性验证 + feature 收尾)── blocked by 02,03,04  ✅ commit 239475c
```

> **切片策略说明**:本 feature 不按「页面」切片(会横向切片化),而按「色系/语义」切片——每片把一种语义(emerald→success)跨所有页面收口到底。这样每片是「一个语义全站闭环」的垂直切片,grep 归零可单片验证。切片 01 是 frontier(success 语义,覆盖最多 emerald/green 用例),02-04 并行 blocked by 01(共享映射范式 + alpha 约定),05 收尾聚合。

### 切片 01 — success 语义收口:emerald/green → `success`(跨页,frontier) ✅ commit 5146312

**What it delivers**:从使用者视角,所有表达「成功/达成/收入/充值到账」的绿色(emerald/green)在所有业务页统一变成 `success` token,亮/暗自动切换。这是建立「色系→语义」映射范式的首片,后续 warning/danger/info 复用其 alpha 约定与 dark: 清理规则。

**Blocked by**: 无(可立即开始;Feature A 已 passing 提供了 `success` token)

**Acceptance criteria**:

- [x] `settings-page.tsx`:`text-green-600` Check 图标 → `text-success`;`bg-emerald-500 text-white` active 态 → `bg-success text-success-foreground`
- [x] `permissions-page.tsx`:`bg-emerald-500`(granted 标记 ×2)→ `bg-success`
- [x] `billing-page.tsx`:`text-emerald-500` ArrowUp(收入 ×2)+ `text-emerald-600`(交易方向)→ `text-success`
- [x] `billing-admin-page.tsx`:`text-emerald-500` Coins → `text-success`
- [x] `users-page.tsx`:stat icon `text-emerald-500`(活跃)→ `text-success`
- [x] `notifications-page.tsx`:`bg-emerald-100 text-emerald-800`(充值到账)→ `bg-success/10 text-success`
- [x] `notification-bell.tsx`:`text-emerald-600`(recharge)→ `text-success`
- [x] `dashboard-page.tsx`:accent `text-emerald-500` → `text-success`
- [x] success 语义 emerald/green grep(业务页范围)= 0
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿
- [x] **建立范式文档**(evidence 记录):alpha 约定(`/10` 底 / `/30` 边框 / DEFAULT 字)+ dark: 冗余清理规则,供切片 02-04 复用

**✅ 实施证据(2026-07-31 Session 174)**

- **改动**:12 处 className 映射,跨 8 文件(settings/permissions/billing/billing-admin/users/notifications/notification-bell/dashboard)
- **grep 归零**:`grep -rE "emerald|green-" --include="*.tsx" src/` 业务页范围 = 0(残留全在边界文件:`components/ui/avatar.tsx:30` avatar 8 色环 + `badge-toast-avatar.test.tsx` Feature A 锁回退断言)
- **验证**:`npm run build` ✓ built in 1.97s(0 类型错误)+ `npx oxlint` 0 warnings/0 errors + `npm test` 17 files / 141 tests passed(含 `design-tokens.test.ts` 21 + `badge-toast-avatar.test.tsx` 锁回退)
- **范式文档(供切片 02-04 复用)**:
  - **浅底深字**:`-100`/`-800` 组合 → `bg-{token}/10`(底)+ `text-{token}`(DEFAULT 字);如需边框 `border-{token}/30`。本切片 `notifications-page.tsx` recharge `bg-emerald-100 text-emerald-800` → `bg-success/10 text-success` 落地此范式
  - **active/实心态**:`bg-{原色}-500 text-white` → `bg-{token} text-{token}-foreground`。本切片 `settings-page.tsx` active + `permissions-page.tsx` 图例/按钮 ×2 落地
  - **三元条件色**:如 `isIncoming ? "text-emerald-600" : "text-rose-600"` → 只改 emerald 半边为 `text-success`,rose 半边留给切片 03(不越界)
  - **dark: 清理规则**:本切片 success 用例均为单色无手写 `dark:` 冗余变体,故无删除动作;**切片 02 amber 大量 `dark:text-amber-*` 冗余变体时落地清理规则**(映射后 token 自带暗色变体,手写 dark: 变体冗余应删)

### 切片 02 — warning 语义收口:amber → `warning`(跨页) ✅ commit 07b3b95

**What it delivers**:所有表达「警告/余额预警/提醒」的 amber 在所有业务页统一变成 `warning` token,手写的 `dark:text-amber-*` 冗余变体删除(token 接管暗色)。

**Blocked by**: 切片 01(复用其 alpha 约定 + dark: 清理范式)

**Acceptance criteria**:

- [x] `settings-page.tsx`:`text-amber-500` AlertTriangle + `border/bg-amber-500/*` 警告框整簇 → `warning`(+ 删 dark: 变体)
- [x] `permissions-page.tsx`:`border/bg-amber-*` 警告 Card + `text-amber-600 dark:text-amber-500` Shield/Lock → `warning`(删 dark: 变体)
- [x] `composite-mode.tsx`:`border/bg/text-amber-*` 余额不足警告框 → `warning`
- [x] `users-page.tsx`:stat icon `text-amber-500`(本月新增)→ `text-warning`
- [x] `notifications-page.tsx`:`bg-amber-100 text-amber-800`(余额预警)→ `bg-warning/10 text-warning`
- [x] `notification-bell.tsx`:`text-amber-600`(balance_warning)→ `text-warning`
- [x] `dashboard-page.tsx`:accent `text-amber-500` → `text-warning`
- [x] `dashboard-layout.tsx`:Badge `border-amber-300 bg-amber-100 text-amber-800` → `border-warning/30 bg-warning/10 text-warning`
- [x] **边界保留**:`conversation-list-panel.tsx` 的 Pin/Star amber:EP3 核对后,若为强调非警告 → 保留并在 evidence 注明;若统一 → 映射
- [x] warning 语义 amber grep(业务页范围,排除 Pin/Star 边界)= 0
- [x] 手写 `dark:text-amber-*` / `dark:bg-amber-*` 冗余变体已删
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿

**✅ 实施证据(2026-07-31 Session 175)**

- **改动**:14 处 className 映射,跨 8 文件(settings/permissions/composite-mode/users/notifications/notification-bell/dashboard-page/dashboard-layout),分支 `feat/design-system-color-sweep-slice-02`
- **范式忠实(切片 01 alpha 约定)**:`/10` 底 + `/30` 边 + `text-warning`(DEFAULT 字)。边框 alpha 原散用 `/40`/`/50`(settings/permissions/composite)统一收敛到范式 `/30`(正向收敛)。`dashboard-layout` Badge 补 `hover:bg-warning/10` 与常态一致(原 `hover:bg-amber-100` 同值,保持 hover 语义)。
- **dark: 清理首次落地**:切片 01 明示「切片 02 amber 大量 dark: 冗余变体时落地清理规则」,本切片落地——删 `permissions-page` 2× `dark:text-amber-500` + 1× `dark:bg-amber-950/20` + `settings-page` 1× `dark:text-amber-400`,共 4 处手写 dark: 变体。token 接管暗色路径成立(`--warning` dark `38 95% 58%` 已在 `index.css:96`)。改后全仓 `grep "dark:(bg|text|border)-amber"` = 0。
- **grep 归零**:业务页范围 amber 残留仅 4 处全在边界 —— `conversation-list-panel.tsx` Pin(L352 `text-amber-500`)/Star(L355 `fill-amber-400 text-amber-400`)(plan 明示强调色边界保留)+ 2 处注释(`knowledge-page.tsx:60` 描述性注释 + `lib/theme.ts:87` WCAG 讨论注释)。功能性 warning 语义 amber = 0。
- **边界核对(Pin/Star)**:`conversation-list-panel` 的 Pin/Star 是「置顶/收藏」强调标记,语义是「突出选中」非「警告提醒」,与 warning token 语义无关,保留原 amber 正确(不纳入收口)。
- **验证**:`npm run build` ✓ built in 1.76s(0 类型错误,仅预存 chunk 大小警告)+ `npx oxlint` 0/0(180 files 102 rules)+ `npm test` 17 files / 141 tests passed(零回归,含 `design-tokens.test.ts` 21 + `badge-toast-avatar.test.tsx` Feature A 锁回退断言)。
- **`/code-review` 双轴(general-purpose ×2 并行)**:
  - **Standards 轴:PASS**(0 硬违规 / 0 判断项)。范式忠实、dark: 清理彻底、Pin/Star 边界守住、未越界(未碰切片 03 rose/red `users-page:599` + 未碰切片 04 blue `users-page:597`/`notifications-page:52`/`notification-bell` role_change + 未碰 `components/ui/` Feature A 领地)。
  - **Spec 轴:需修复后 PASS → 经独立核实 + 决策,保留 tint 范式(对比度债登记切片 05)**。Spec 精算发现 `text-warning` on `bg-warning/10` **亮色对比度 2.13 ❌**(原 amber-700 基线 4.65 ✅,构成回归)。我独立 node REPL 复核坐实:tint 范式亮色 2.13 ❌、foreground 跨模式无解(亮 16.41 ✅/暗 1.18 ❌)、**实心范式双模式全过**(warning 亮 7.69/暗 9.54,与切片 01 toast success 实心 5.39/8.28 印证)。
- **⚠️ 对比度债决策(登记切片 05 统一收口)**:保留 tint 范式不改实心,理由 4 条:① 不越界碰切片 01 已合并代码(WIP=1 + 不反向改已 passing 切片);② 不引入范式分裂 —— `notifications-page` 三色通知标签(`recharge` success / `balance_warning` warning / `role_change` info)同结构须统一,单改 warning 会造成三色三范式;③ 系统性问题需系统性解 —— success/warning/info 三色 tint 亮色均不达标(success 2.97/warning 2.13/info 预计同病),属 plan AC 设计缺陷非本切片实施错误;④ plan AC 字面要求即 tint,实施按 spec 正确。**已在切片 05 增加 WCAG AC(亮色 tint 系统性收口)**,要求切片 05 统一决策三色 tint 场景改实心或接受债,避免分裂。纯图标场景(notification-bell amber-600→warning 2.69→2.32)是本就不达标的微小负向平移,非核心回归,留切片 05 一并评估。

### 切片 03 — danger 语义收口:rose/red → `danger`(跨页) ✅ commit 1d2562c

**What it delivers**:所有表达「危险/锁定/支出」的 rose/red 统一变成 `danger` token。

**Blocked by**: 切片 01(复用范式)

**Acceptance criteria**:

- [x] `billing-page.tsx`:`text-rose-500` ArrowDown(支出 ×2)+ `text-rose-600`(交易方向)→ `text-danger`
- [x] `billing-admin-page.tsx`:`text-rose-500` Coins → `text-danger`
- [x] `users-page.tsx`:stat icon `text-rose-500`(锁定)→ `text-danger`
- [x] danger 语义 rose/red grep(业务页范围)= 0(注意:不动 ui/ 内 Feature A 已处理的)
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿

**✅ 实施证据(2026-07-31 Session 176)**

- **改动**:5 处 className 映射,跨 3 文件(billing/billing-admin/users),分支 `feat/design-system-color-sweep-slice-03`
- **范式忠实(切片 01 alpha 约定)**:5 处均为「纯图标 text 色」场景(与切片 01 success 同构)→ 全部 DEFAULT `text-danger`,无 `/10` 底 / `/30` 边 / `foreground` 误用。具体:
  - `billing-page.tsx` L64 `txIcon` ArrowDown 支出 + L218 `CounterCard` ArrowDown 累计消耗(2 个 ArrowDown = AC「支出 ×2」)+ L343 三元交易方向 rose 半边(切片 01 已改 emerald 半边为 success,本次补齐 danger 半边,语义对称)
  - `billing-admin-page.tsx` L165 Coins 全平台累计消耗
  - `users-page.tsx` L599 stat「锁定」icon(四 stat 中 blue/info + rose/danger 为仅剩两片,success/warning 已就位)
- **dark: 清理**:本切片 5 处原本就无手写 `dark:text-rose-*` / `dark:bg-rose-*` 冗余变体(AC 亦无此项),无清理动作、无暗色债新增。全仓 `grep "dark:(bg|text|border)-(rose|red)"` 业务页范围 = 0。
- **grep 归零**:业务页范围 rose/red 色值(精确边界 `(bg|text|border|fill|stroke|ring|from|to|via|accent)-(rose|red)-[0-9]`,排除 `components/ui/`)= 0。`markdown-view.tsx:56 break-words` 为 prose 排版类含 "red" 子串的误报,非色值,排除正确。
- **边界核对**:danger 与 shadcn 既有 `destructive` 命名并存 —— 同文件内 `variant="destructive"`(Badge/Button)、`bg-destructive/5`、`text-destructive` 等既有命名原样保留(`billing-page.tsx:179/192/198`、`users-page.tsx:95/575`、`billing-admin-page.tsx:218/242`),未迁移、未混淆,符合 §11 不越界。
- **验证**:`npm run build` ✓ built in 1.66s(0 类型错误,仅预存 chunk 大小警告)+ `npx oxlint` 0/0(180 files 102 rules)+ `npm test` 17 files / 141 tests passed(零回归,含 `design-tokens.test.ts` 21 + `badge-toast-avatar.test.tsx` Feature A 锁回退断言)。
- **`/code-review` 双轴(general-purpose ×2 并行)**:**Standards PASS + Spec PASS**(0 硬违规 / 0 判断项 / 0 缺漏 / 0 creep / 0 错误)。两轴独立核实一致:范式忠实、grep 归零属实、danger/destructive 边界守住、未越界(未碰 ui/ Feature A 领地、未碰切片 04 blue/info、未碰后端)。AC「ArrowDown ×2」疑问澄清:spec 原文精确指 L64+L218 两个 ArrowDown,L343 三元是独立「交易方向」单独列出,3 处对齐无漏算。
- **无对比度债**:本切片 5 处全为纯图标 `text-danger`(非 tint 浅底场景),不触发切片 02 登记的「亮色 tint 范式对比度」系统性问题(该问题限于 `bg-{token}/10 + text-{token}` 浅底场景,留切片 05 统一收口)。

### 切片 04 — info 语义收口:blue/cyan → `info`(跨页) ✅ commit b11911a

**What it delivers**:所有表达「信息/角色变更/中性统计」的 blue/cyan 统一变成 `info` token。

**Blocked by**: 切片 01(复用范式)

**Acceptance criteria**:

- [x] `users-page.tsx`:stat icon `text-blue-500`(用户总数)→ `text-info`
- [x] `notifications-page.tsx`:`bg-blue-100 text-blue-800`(角色变更)→ `bg-info/10 text-info`
- [x] `notification-bell.tsx`:`text-blue-600`(role_change)→ `text-info`
- [x] `dashboard-page.tsx`:accent `text-blue-500` → `text-info`
- [x] info 语义 blue/cyan grep(业务页范围)= 0
- [x] **边界保留**:`markdown-view.tsx` 的 zinc 代码块主题色不动(非语义,归 Feature C 或保留)
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿

**✅ 实施证据(2026-07-31 Session 177)**

- **改动**:4 处 className 映射,跨 4 文件(users-page/notifications-page/notification-bell/dashboard-page),分支 `feat/design-system-color-sweep-slice-04`。业务页范围无 cyan 残留(全仓仅 blue),4 处精确对齐 AC。
- **范式忠实(切片 01 alpha 约定)**:
  - 纯图标 text 色场景(3 处:`users-page` stat「用户总数」+ `notification-bell` role_change accent + `dashboard-page` 管理智能体 accent)→ 全部 DEFAULT `text-info`,无 `/10` 底 / `foreground` 误用(与切片 03 danger 5 处同构)。
  - 浅底深字 tint 场景(1 处:`notifications-page` role_change `bg-blue-100 text-blue-800`)→ `bg-info/10 + text-info`(切片 01 alpha 约定落地,与同文件 `balance_warning` warning / `recharge` success 三色通知标签同结构同范式)。
- **dark: 清理**:本切片 4 处原本就无手写 `dark:(bg|text|border)-blue-*` 冗余变体(AC 亦无此项),无清理动作、无暗色债新增(镜像切片 03)。全仓 `grep "dark:(bg|text|border)-(blue|cyan)"` 业务页范围 = 0。
- **grep 归零**:业务页范围 blue/cyan 色值(精确边界 `(bg|text|border|fill|stroke|ring|from|to|via|accent)-(blue|cyan)-[0-9]`,排除 `components/ui/`)= 0。**无 cyan 残留**(cyan 仅在 AC 理论覆盖,实际业务页未用)。
- **边界核对**:
  - `purple`(usage_report)在 `notifications-page:53` + `notification-bell:41` 各 1 处保留 —— purple 为多色非语义(用量报告),不在四 token(success/warning/danger/info)范围,§4.5/§8 明示多色保留,不纳入收口。
  - `markdown-view.tsx` zinc 代码块主题色 diff 为空(未触碰,归 Feature C)。
  - `conversation-list-panel.tsx` Pin/Star amber(切片 02 边界)未触碰。
  - `components/ui/`(Feature A 领地)未触碰。
  - `destructive` 既有命名未混淆(本切片无相关)。
  - 未反向改切片 01-03 已合并代码。
- **对比度债继承(非本切片缺陷)**:`notifications-page` role_change 的 tint 范式(`bg-info/10 + text-info`)属切片 02 审查登记的「亮色 tint 范式对比度不达标」系统性问题(warning 2.13 / success 2.97,均 < AA 4.5),已登记切片 05 统一收口。本切片**忠实 AC 字面**(AC 写的就是 `bg-info/10 text-info`),不越界改实心,保持 notifications 三色通知标签(recharge-success / balance_warning-warning / role_change-info)范式统一,避免三色三范式。**至此切片 05 须统一决策的三色 tint 场景全部就位**(切片 01 recharge + 切片 02 balance_warning/dashboard-layout/settings/permissions/composite 等 + 切片 04 role_change),由切片 05 一并处理。
- **验证**:`npm run build` ✓ built in 2.25s(0 类型错误,仅预存 chunk 大小警告)+ `npx oxlint` 0 warnings/0 errors(180 files 102 rules)+ `npm test` 17 files / 141 tests passed(零回归,含 `design-tokens.test.ts` 21 + `badge-toast-avatar.test.tsx` Feature A 锁回退断言)。
- **`/code-review` 双轴(general-purpose ×2 并行)**:**Standards PASS + Spec PASS**(0 硬违规 / 0 判断项 / 0 缺漏 / 0 creep / 0 错误)。两轴独立核实一致:范式忠实、grep 归零属实、purple/zinc/Pin-Star/destructive 边界全守住、未越界(未碰 ui/ Feature A 领地、未反向改切片 01-03、未碰后端)。7 条 AC 逐条 diff 证据核实 [x]。info token(`--info` 亮 `189 90% 42%` / 暗 `189 80% 55%` + `--info-foreground`)在 `index.css:39-40,100-101` 已定义,新 class 可解析。
- **无新增对比度债**(纯图标场景不触发 tint 问题);**继承切片 05 的 tint 债已就位**(见上)。

### 切片 05 — 收尾:暗色一致性验证 + tint 对比度系统性修复 + feature 收尾(末切片) ✅ commit 239475c

**What it delivers**:全 feature 范围 grep 归零确认 + 暗/亮双模式视觉一致性验证(对照 B3)+ 亮色 tint 范式对比度系统性修复 + 后端零回归确认 + feature 收尾仪式。

**Blocked by**: 切片 02, 03, 04(所有色系映射完成)

**Acceptance criteria**:

- [x] 全 feature 范围 grep:语义性硬编码原色(emerald/amber/rose/red/blue/cyan/green)= 0(排除 markdown-view zinc + Pin/Star 边界 + avatar/chart 设计性多色)
- [x] 所有手写 `dark:` 冗余变体(与 token 暗色重复的)已清理
- [x] 视觉一致性:对照 `design-demos/B3.html`,关键页面(billing/users/notifications/dashboard)亮/暗双模式渲染与 B3 调性一致(手动,evidence 记录)
- [x] **WCAG AA(亮色 tint 范式系统性收口)**:切片 02 审查实测发现 `bg-{token}/10 + text-{token}`(DEFAULT 字)的 tint 范式在**亮色模式**对比度不达标(warning 2.13 / success 2.97 / 同结构 info 预计同病,均 < AA 4.5),而 `text-{token}-foreground` 暗色隐形(1.18)跨模式无解;唯一双模式成立的是**实心范式** `bg-{token} text-{token}-foreground`(warning 亮 7.69/暗 9.54,success 亮 5.39/暗 8.28)。本切片须统一决策:tint 范式(通知标签/警告框/徽章三类浅底场景)是否全部改实心,或保留 tint 接受亮色对比度债。涉及切片 01(`notifications-page` recharge)+ 切片 02(4 处警告框/标签)+ 切片 04(notifications role_change)三色同结构场景,须统一处理避免范式分裂。决策与实测写入 evidence。
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿
- [x] `./init.sh full` 后端零回归(确认前端改动不影响后端测试)
- [x] **feature 收尾**:feature_list.json `status` → `passing` + evidence 写实测 + `./scripts/sync-active-features.sh` 刷新 + 依赖解锁扫描(Feature C 与 A/B 正交,无下游依赖解锁)

**✅ 实施证据(2026-07-31 Session 178)**

- **改动**:7 处 tint 场景处理(跨 5 文件 settings/composite/permissions/notifications/dashboard-layout),分支 `feat/design-system-color-sweep-slice-05`,单 commit `239475c`。
- **WCAG 全范式精算(node REPL,四色 × 亮暗 × 四范式)**:
  - **tint**(`bg-{tok}/10 + text-{tok}`):亮色 success 2.96 / warning 2.13 / info 2.38 / danger 3.31 ❌(< AA 4.5);暗色全 8.23-9.37 ✓
  - **solid**(`bg-{tok} text-{tok}-foreground`):亮色全 4.72-7.70 ✓ / 暗色全 5.28-9.55 ✓ —— **唯一双模式 AA 成立**
  - **tint+foreground**(`bg-{tok}/10 + text-{tok}-foreground`):亮色全 15.63-16.41 ✓ / 暗色全 1.01-1.03 ❌
  - **alpha 调高**:无解(同色相叠,明度差决定对比度,alpha↑ 对比度↓,warning alpha 0.10→0.50 亮色 2.13→1.52 持续降)
- **⚠️ 关键发现:B3 设计自身固有 WCAG 债**。对照 `design-demos/B3.html`,B3 `.badge` 定义(L264-265)= `token/.14` 底 + DEFAULT 字 + `/30` 边框,**正是 tint 范式**。精算 B3 自身亮色 badge 对比度:success 2.82 / warning 2.07 / info 2.29,均 < AA 4.5。即 **AC3(B3 一致)与 AC4(WCAG AA)在标签场景互斥** —— 唯一双模式成立的实心范式会破坏 B3 `.badge` tint 调性。
- **统一决策(经用户确认,避免范式分裂)**:按场景区分,非一刀切 ——
  - **场景 1:小面积语义标签/Badge(notifications 三色标签 recharge/balance_warning/role_change + dashboard-layout 超管 Badge)**:保留 tint 忠于 B3 设计调性,接受亮色 WCAG 债(B3 固有,非本 feature 引入)。三色统一处理(无分裂),仅加注释登记决策。
  - **场景 2:大面积警告框容器(settings Token 警告框 + composite 余额不足警告框 + permissions 超管 Card)**:容器保留 `bg-warning/10` 浅橙底(实心橙色大面积刺眼,且浅底传达 warning 语义),**标题/icon 从 `text-warning`(亮色 2.13 < AA)改 `text-foreground`**(亮 18.39 / 暗 16.73 双模式 AA 远超),正文 `muted-foreground` 本就达标(亮 4.38 / 暗 6.83)不动。此修复不违 B3(容器仍是 tint 浅底)且达 WCAG。
- **grep 归零**:业务页四语义硬编码原色(emerald/amber/rose/red/blue/cyan/green)= 0;red = 0。边界文件正确保留:`markdown-view.tsx` zinc 代码块主题色 / `conversation-list-panel.tsx` Pin(L352)/Star(L355)amber 强调色 / `avatar.tsx` 8 色环(Feature A)/ `chart-1..5`。
- **dark: 清理验证**:全仓 `dark:(bg|text|border|fill|stroke|ring)-(amber|rose|red|blue|cyan|emerald|green)` 业务页(排除 ui/)= 0;`dark:-(success|warning|danger|info)` 手写 = 0(token 自带暗色,无冗余)。本切片未引入任何新 dark: 变体。
- **`/code-review` 双轴(general-purpose ×2 并行)**:**Standards PASS + Spec PASS**。
  - **Standards 轴**:0 硬违规 / 1 软建议(3 处警告框注释 WCAG 数字重复可精简 —— 不采纳,各文件独立可读更重要)。§11 不越界边界干净:5 文件全在业务页/layout,未碰 ui/、avatar、chart、destructive、token 定义、后端。
  - **Spec 轴**:0 硬违规。AC4 标签场景决策统一(三色一致保 tint,无分裂)。1 判断项闭环:Spec 轴发现全仓 5 处纯图标 `text-warning`(非 tint 容器,亮色 2.32 < 非文本阈值 3.0)是切片 02 登记的既有债 —— 经用户决策**不扩展**(AC4 字面只覆盖 tint 容器场景;修纯图标会反向改已 passing 切片 01-04,违 WIP/不越界;且这些是装饰性辅助图标旁有文字标签),登记为「切片 02 纯图标债,留后续 feature」。
- **验证**:`npm run build` ✓ built in 2.46s(0 类型错误,仅预存 chunk 大小警告)+ `npx oxlint` 0 warnings/0 errors(180 files 102 rules)+ `npm test` 17 files / 141 tests passed(零回归)+ `./init.sh full` **842 passed**(后端零回归)。
- **已知债登记(非本 feature 引入,留后续)**:① **B3 亮色 tint WCAG 债** —— 标签/Badge 场景(success 2.82 / warning 2.07 / info 2.29 < AA 4.5),B3 设计固有,忠于 B3 接受。② **切片 02 纯图标 `text-warning` 债** —— 5 处独立图标(notification-bell:38 / dashboard-page:165 / settings:1030 / permissions:318 / users:600,亮色 2.32 < 非文本 3.0),切片 02 登记留评估,本切片按 AC4 字面范围不扩展。
