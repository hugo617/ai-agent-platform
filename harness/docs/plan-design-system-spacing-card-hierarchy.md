# 计划:设计系统收口 — Feature C:间距与卡片层级规范

> **id**: `design-system-spacing-card-hierarchy`
> **状态**: passing(2026-07-31 Session 180,切片 01 + 切片 02 末切片全完成)
> **优先级**: 83(feature_list.json)
> **创建日期**: 2026-07-31
> **系列总纲**: [`plan-frontend-design-system-overview.md`](./plan-frontend-design-system-overview.md)
> **系列内位置**: C(与 A/B 正交,可在 A/B 之后独立做;不依赖 A/B 的 token)

---

## 0. v1 → vN 变更摘要

| v(N-1) 问题 | 严重度 | vN 处理 |
|---|---|---|
| v1 命名 `boxShadow.card` 与 `colors.card` 命名空间碰撞 | 高(视觉 bug) | v2:卡片层语义名 `card` → `surface`(`shadow-surface`/`shadow-overlay`)。详见 §4.5① 与 §9。 |
| v1 §4.6/§10 措辞「Card 与浮层零行为变更」对 select/dropdown-content 不成立 | 中(措辞不实) | v2:区分记录——Card 230 处真零变化;dialog/toast 零变化(原 shadow-lg);**select/dropdown-content 是有意抬升**(原 shadow-md→overlay=shadow-lg,plan 本就要求的统一)。 |

### v2 变更详情(切片 01 实施期发现)

**命名碰撞复盘(2026-07-31,切片 01 EP3)**:原 plan §4.5① 钦定 `boxShadow` 键名 `card`/`overlay`。实施后 `/code-review` Spec 子轴发现:`colors.card` 已存在(亮 `0 0% 100%`/暗 `222.2 84% 4.9%`),Tailwind 据此为 `shadow-{color}` 颜色工具类**预生成** `.shadow-card{--tw-shadow-color:hsl(var(--card))}`,该规则在 size 工具类规则之后,同特异性后者胜出 → `--tw-shadow-color` 被设为 card 背景色(亮色=纯白)。**Playwright 实测确认**:改前 `shadow-card` 渲染 `rgb(255,255,255) 0px 1px 2px` ≠ `shadow-sm` 的 `rgba(0,0,0,0.05) ...`,230 处 `<Card` 阴影从 5%黑变纯白(视觉破坏)。`overlay` 无 `colors.overlay` 故无碰撞。

**决策(用户 2026-07-31 选定)**:卡片层语义名 `card` → **`surface`**(`shadow-surface`)。理由:① `surface` 不与任何 color token 碰撞;② 语义仍贴切(「卡片这类内容表面层」);③ 保 plan 意图(命名层级概念),只换词。`overlay` 保持不变。改名后 Playwright 复测:`shadow-surface === shadow-sm` 为 TRUE,230 处 Card 真零视觉变化坐实。

**措辞订正**:`shadow-overlay` 值逐字等价 `shadow-lg`,故 dialog/toast(原 shadow-lg)真零变化;但 select/dropdown-content 原用 `shadow-md`,统一到 overlay 是**有意抬升**(切片 01 acceptance 第 218 行本就要求 `shadow-md`/`shadow-lg`→`shadow-overlay`),非「零行为变更」。§4.6/§10 相关措辞据此订正。

---

## 1. Problem Statement(对齐 to-spec)

Feature A/B 收口了颜色,但**布局层级的视觉一致性**仍有两个缺口:

1. **卡片层级无语义命名**:`Card` 组件用 `shadow-sm`、浮层(Dialog/Dropdown/Toast)用 `shadow-lg/md`,层级**已隐含存在**但无语义 token 收口——调阴影需散落改 className,且「Card 弱阴影 vs 浮层强阴影」的层级约定只活在代码里未命名。230 处 `<Card` 用法依赖这个隐含约定。
2. **字号任意值绕过刻度**:11 处 `text-[10px]` / `text-[11px]` 散落(layout/notification-bell/command-menu/permissions/composite-mode/conversation-list-panel),是「默认刻度不够细时的临时绕过」,绕过了 Tailwind 字号体系。

> **间距任意值不是问题**:实测 `p-/m-/gap-` 任意值 = 0,`rounded-[` 任意值 = 0,`shadow-[` 任意值 = 0。所以「间距 token」在本 feature 的真实含义是**补语义间距/层级 token 命名**,不是收口任意值。

## 2. Solution(对齐 to-spec)

**轻量补全**:为卡片/浮层的阴影层级建语义 token(`--shadow-card` / `--shadow-overlay` 之类,或用 Tailwind shadow 命名扩展),把 Card 与浮层组件的 `shadow-*` 统一引用,让「层级」成为命名概念。同时把 11 处字号任意值映射回 Tailwind 默认刻度(`text-[10px]`→`text-xs` 或新增 `text-2xs` 扩展,决策见 §4.5)。

**克制原则**(总纲决策 5):不推全站字号 token 化(工程量大),只收口这 11 处绕过;间距/圆角任意值为 0,无需收口。Feature C 是「正交收尾」,改动面小。

## 3. User Stories(对齐 to-spec)

- 作为 **组件库使用者**,我想要「Card 层 / 浮层层」的阴影有语义命名,以便新组件一眼知道用哪个层级
- 作为 **看数据看板的用户**,我想要卡片与浮层有稳定的层级感(弱阴影 vs 强阴影),以便视觉焦点落在数据上(B3「数据为尊,UI chrome 退到 hairline」)
- 作为 **开发**,我想要字号不再出现 `text-[10px]` 任意值,以便统一走刻度
- 作为 **设计系统维护者**,我想要层级约定从「代码隐含」变成「token 命名」,以便未来调整层级只改一处

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 0 | 纯前端 |
| 数据库迁移 | 0 | 无 |
| 前端文件改动 | ~8 | `src/index.css`(阴影 token,若走 CSS 变量路线)+ `tailwind.config.js`(shadow/fontSize 扩展)+ `card.tsx`(引用语义阴影)+ 含字号任意值的 6 文件(layout/notification-bell/command-menu/permissions-page/composite-mode/conversation-list-panel)|
| 新增测试类 | ~0-1 | 以构建/lint 为主,必要时补 |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
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

**① 卡片/浮层层级语义化(核心)**

现状层级已隐含:
- **Card 层**(弱阴影):`card.tsx` `default: shadow-sm`
- **浮层层**(强阴影):`dialog/dropdown-menu/select/toast` 用 `shadow-lg` / `shadow-md`
- **交互层**(中):`switch` thumb `shadow-lg`、`command-menu/global-search-box` `shadow-lg`

**方案选择**(EP3 实施时定,本 plan 给倾向):

- **方案 A(Tailwind theme.extend.shadow 命名)**:在 `tailwind.config.js` 加 `shadow: { card: "...", overlay: "..." }`,Card 引用 `shadow-card`、浮层引用 `shadow-overlay`。**倾向此方案**(与现有 `colors` extend 范式一致,不改 CSS 变量,改动面最小)。
- **方案 B(CSS 变量 + hsl 模式)**:在 `index.css` 加 `--shadow-card` / `--shadow-overlay`,Tailwind 引用。改动面更大,且 shadow 不是颜色,CSS 变量模式收益不明显。

**默认走方案 A**。Tailwind shadow 扩展(示例):

```js
// tailwind.config.js theme.extend
boxShadow: {
  surface: "0 1px 2px 0 rgb(0 0 0 / 0.05)",      // 等价 shadow-sm,Card 层
  overlay: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",  // 等价 shadow-lg,浮层层
}
```

> **v2 命名注**:原 v1 钦定键名 `card`,但与 `colors.card` 命名空间碰撞(Tailwind 预生成 `shadow-card` color 工具类覆盖 size 工具类,实测 Card 阴影变纯白),v2 改为 `surface`(详见 §0 v2 详情)。`overlay` 无碰撞,保持不变。

> **B3 调性对齐**:B3「数据为尊,UI chrome 退到 1px hairline」——Card 层用极弱阴影(`shadow-surface` 近 hairline),浮层用 `shadow-overlay` 拉出层级。命名让这个调性显式化。

**② 字号任意值收口(顺手项,总纲决策 5)**

11 处分布(实测):

| 文件 | 行 | 现状 | 用途 | 映射 |
|---|---|---|---|---|
| `dashboard-layout.tsx` | 149 | `text-[10px]` | kbd 快捷键 | → `text-2xs`(若扩展)或 `text-xs` |
| `notification-bell.tsx` | 88 | `text-[10px]` | badge 数字 | → `text-2xs` 或 `text-xs` |
| `notification-bell.tsx` | 143 | `text-[11px]` | 副文本 | → `text-xs` |
| `command-menu.tsx` | 135 | `text-[10px]` | kbd | → `text-2xs` 或 `text-xs` |
| `permissions-page.tsx` | 214,404 | `text-[10px]` ×2 | 微标签 | → `text-2xs` 或 `text-xs` |
| `composite-mode.tsx` | 412 | `text-[11px]` | 副文本 | → `text-xs` |
| `conversation-list-panel.tsx` | 363,387,514 | `text-[10px]`×2 + `text-[11px]`×1 | badge/微标签 | → `text-2xs`/`text-xs` |

**决策(二选一,EP3 实施时定)**:

- **选项 1(扩展 `text-2xs`)**:在 `tailwind.config.js` `fontSize` 加 `'2xs': ['10px', {...}]`,把 `text-[10px]`→`text-2xs`、`text-[11px]`→`text-xs`(Tailwind `xs`=12px,11px 近似 xs)。**倾向此方案**(11px 与 xs 12px 视觉差可忽略;10px 频繁出现值得一个命名刻度)。
- **选项 2(全映射 xs)**:`text-[10px]`/`text-[11px]` 全 → `text-xs`(12px)。更简单,但 10px→12px 视觉放大略明显(badge 数字、kbd 会变大)。

**默认走选项 1**(扩展 `text-2xs`),保视觉一致性。这是「字号只收口绕过,不推全站 token 化」(决策 5)的精确落地:新增一个刻度,11 处归零,不动其他字号。

**③ 边界保留**

- `markdown-view.tsx` 的 zinc 代码块主题色:Feature B 已判定保留,本 feature 也不动(非字号/阴影/间距语义)
- 间距/圆角任意值为 0,无需收口

### 4.6 验收硬标准(来自总纲,客观可验)

1. **字号任意值归零**:`text-[NNpx]` grep = 0(11 处全映射)
2. **卡片层级语义化**:`card.tsx` + 浮层组件引用语义 shadow 名(`shadow-surface`/`shadow-overlay`,v2 命名见 §0),不再裸用 `shadow-sm`/`shadow-lg`(ui/ 内组件统一)
3. **npm test 全绿 + npm run build 0 错 + oxlint 0/0**
4. **视觉变化(v2 订正措辞)**:Card 层阴影视觉 = 原 `shadow-sm`(`shadow-surface` 逐字等价,230 处真零变化);dialog/toast 零变化(`shadow-overlay`≡`shadow-lg`,原本即 shadow-lg);**select/dropdown-content 是有意抬升**(原 `shadow-md`→`shadow-overlay`≡`shadow-lg`,切片 01 acceptance 要求的统一,非零变化);字号 `text-2xs` 渲染 = 原 `text-[10px]`(切片 02)

---

## 5. Testing Decisions(对齐 to-spec)

- **测试金字塔**:token/className 映射 + Tailwind 扩展,无运行时逻辑 → **以构建/lint + grep 归零为主**
- **优先复用现有 seam**:看是否有 card/stat-card 组件测试;有则加层级渲染断言
- **字号视觉验证**:`text-2xs` 扩展后,11 处替换的视觉与原 `text-[10px]` 一致(手动,evidence 记录)
- **覆盖率**:纯前端无服务端基线;目标 = 现有前端测试不回归

---

## 6. 切片规划(对齐 to-tickets tracer-bullet)

> 见下方「实施切片」段(/to-tickets 产出)。

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:改动文件 ~8、纯前端、无鉴权/权限/迁移/安全敏感/不可逆 → **不满足复杂任务触发条件**。

**审查方式**:**轻量自审**(EP2 收尾自检 + 切片 acceptance criteria)。本 feature 风险点在「Card 默认 shadow 改动影响 230 处 `<Card`」——EP3 切片 01 验收时必须确认 230 处视觉零变化,若有回归则回本 plan 补 v2。

---

## 8. Out of Scope(对齐 to-spec)

- ❌ **全站字号 token 化**(语义命名 text-caption/text-body 等)→ 决策 5 明确排除,工程量大
- ❌ **间距 token 化全站推行** → 实测间距任意值为 0,无收口对象;本 feature 只补层级语义命名
- ❌ **字体自定义**(fontFamily / Google Fonts)→ 保留 Tailwind 默认 sans 栈
- ❌ **颜色 token**(semantic color)→ Feature A
- ❌ **业务页硬编码色扫荡** → Feature B
- ❌ **代码块主题色 zinc 重构** → 保留
- ❌ **移动端/响应式适配** → 系列边界

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Card 默认 shadow 改动影响 230 处 `<Card` 视觉 | 高 | §4.5① `shadow-surface`(v2 命名)值**逐字等价 `shadow-sm`**;切片 01 已 Playwright 实测 `shadow-surface===shadow-sm` 为 TRUE,230 处真零变化坐实 |
| **命名碰撞:`boxShadow.card` vs `colors.card`**(v2 新增) | 高 | v1 命名 `card` 实测触发 Tailwind 预生成 `shadow-card` color 工具类覆盖 size,Card 阴影变纯白。**v2 已闭环**:改名 `surface`(用户 2026-07-31 选定),无 `colors.surface` 故无碰撞;实测复验通过。详见 §0 v2 详情 |
| 浮层组件改 shadow 名后视觉微变 | 中 | dialog/toast 用 `shadow-overlay`(≡原 `shadow-lg`,零变化);**select/dropdown-content 原 `shadow-md`→`shadow-overlay`(≡`shadow-lg`)是有意抬升**(切片 01 acceptance 要求的浮层统一,非零变化)|
| `text-2xs` 扩展后 11px 处映射 xs(12px)视觉放大 | 中 | §4.5② 选项 1:11px→xs 可接受;10px→2xs 保一致。EP3 视觉比对,若 11px 处不可接受则也走 2xs |
| 层级命名(`surface`/`overlay`)与团队心智不符 | 低 | v1 已因碰撞改 `card`→`surface`;若团队偏好别的命名,再补 vN 摘要 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `text-[NNpx]` grep = 0(11 处字号任意值全映射)
2. `tailwind.config.js` 含 `boxShadow` 语义命名(`surface`/`overlay`,v2 命名见 §0)或等价 CSS 变量方案;`card.tsx` + 浮层组件引用语义名
3. 230 处 `<Card` 视觉零变化(`shadow-surface` 值逐字等价 `shadow-sm`,切片 01 已 Playwright 实测为 TRUE)
4. `cd frontend && npm run build` 0 类型错误 + `npx oxlint` 0/0 + `npm test` 全绿
5. 对照 `design-demos/B3.html`,卡片层级与 B3「数据为尊 + hairline chrome」调性一致

---

## 11. 不越界声明

本次改动**只**涉及:`tailwind.config.js`(boxShadow/fontSize 扩展)、`src/components/ui/card.tsx`(引用语义阴影)+ 浮层组件(dialog/dropdown-menu/select/toast,引用 `shadow-overlay`)、6 个含字号任意值的文件(layout/notification-bell/command-menu/permissions-page/composite-mode/conversation-list-panel)。

**不**触碰:颜色 token(Feature A/B)、业务页语义色、avatar/chart、代码块 zinc、间距/圆角(无任意值)、字体族、白标逻辑、任何后端代码。

---

## 实施切片(/to-tickets 产出)

### 切片依赖图

```
切片 01(卡片层级语义化:shadow surface/overlay + Card/浮层引用)✅ ── 无 blocker,frontier(已完成)
   └──→ 切片 02(字号任意值收口:text-2xs 扩展 + 11 处映射 + feature 收尾)── blocked by 01
```

> **切片策略**:切片 01 是层级语义基建(改 Card + 浮层,影响面大需先稳),切片 02 是字号收口(独立小改,01 之后做避免 context 切换)。两片都是「垂直闭环」:01 = 层级 token 落地 + 所有相关组件引用 + 视觉零变化验证;02 = 字号扩展 + 11 处归零 + 视觉验证。

### 切片 01 — 卡片层级语义化:`shadow-surface`/`shadow-overlay` + Card/浮层引用(frontier)✅

> **完成证据**:feat 分支 `feat/design-system-card-hierarchy-slice01`,merge commit 见 git log(2026-07-31)。`shadow-surface`(v2 命名,原 `card` 因碰撞改名见 §0)+ `shadow-overlay` 落地;Playwright 实测 `shadow-surface===shadow-sm` / `shadow-overlay===shadow-lg` 均 TRUE;build ✓ + oxlint 0/0 + npm test 141/141。`/code-review` 双轴:Standards clean、Spec 满足(命名碰撞已 v2 闭环)。

**What it delivers**:从组件库使用者视角,「Card 层 / 浮层层」的阴影有了语义命名——新组件一眼知道用 `shadow-surface`(弱阴影,内容卡)还是 `shadow-overlay`(强阴影,浮层)。Card 与现有浮层组件统一引用语义名,230 处 `<Card` 视觉零变化(Playwright 实测坐实)。

**Blocked by**: 无(可立即开始;本 feature 与 A/B 正交,不依赖 token)

**Acceptance criteria**:

- [x] `tailwind.config.js` `theme.extend.boxShadow` 含 `surface`(值等价 `shadow-sm`:`0 1px 2px 0 rgb(0 0 0 / 0.05)`)+ `overlay`(值等价 `shadow-lg`)— v2:键名 `card`→`surface`(碰撞,见 §0)
- [x] `src/components/ui/card.tsx`:`default` variant 的 `shadow-sm` → `shadow-surface`;`glow` variant 评估结论 = **也用 `shadow-surface` 基底**(两者同属 Card 层,glow 额外 ring/glow-border 不变)
- [x] 浮层组件引用 `shadow-overlay`:`dialog.tsx`(`shadow-lg`→`shadow-overlay`)、`dropdown-menu.tsx`(`shadow-md`/`shadow-lg`→`shadow-overlay`)、`select.tsx`(`shadow-md`→`shadow-overlay`)、`toast.tsx`(`shadow-lg`→`shadow-overlay`)
- [x] 230 处 `<Card` 视觉零变化验证:Playwright 实测 `shadow-surface === shadow-sm` 为 TRUE(等价 `rgba(0,0,0,0.05)` 弱阴影);无任何 `<Card>` 叠加裸 shadow 覆盖,230 处全跟随 cardVariants
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 141/141 全绿

### 切片 02 — 字号任意值收口:`text-2xs` 扩展 + 11 处映射(末切片,feature 收尾)✅

> **完成证据**(Session 180,commit aa01a7a):`tailwind.config.js theme.extend.fontSize` 加 `'2xs':['10px',{lineHeight:'14px'}]`(注释范式对齐切片 01 boxShadow 块 header+bullet);11 处散落映射全归零(实测 6 处 10px + 5 处 11px,含本表下方表格漏记的 `conversation-list-panel:369` text-[11px])。`text-[NNpx]` grep(全 frontend/src)= 0(grep exit 1 无匹配);编译产物 `.text-2xs{font-size:10px;line-height:14px}` 逐字等价原 `text-[10px]`;`npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 141/141;`./init.sh full` 842 passed 后端零回归。`/code-review` 双轴:Standards clean(注释风格 nit 已修)、Spec clean(无越界/无缺失)。

**What it delivers**:从开发视角,全站不再有 `text-[NNpx]` 任意值绕过——10px 有命名刻度 `text-2xs`,11px 归 `text-xs`,11 处全部走 Tailwind 刻度体系。

**Blocked by**: 切片 01(同 feature 内先稳层级,再收字号,避免 context 切换)

**Acceptance criteria**:

- [x] `tailwind.config.js` `theme.extend.fontSize` 含 `'2xs': ['10px', { lineHeight: '14px', ... }]`(参考 Tailwind `xs`=12px/16px 的 lineHeight 比例)— lineHeight 14px(14/10=1.4,贴近 xs 16/12≈1.33 的比例;spec checklist 权威值)
- [x] `dashboard-layout.tsx:149` `text-[10px]` → `text-2xs`
- [x] `notification-bell.tsx:88` `text-[10px]` → `text-2xs`;`:143` `text-[11px]` → `text-xs`
- [x] `command-menu.tsx:135` `text-[10px]` → `text-2xs`
- [x] `permissions-page.tsx:214,404` `text-[10px]` ×2 → `text-2xs`(实际行号 217,407,行号漂移)
- [x] `composite-mode.tsx:412` `text-[11px]` → `text-xs`(实际行号 415,漂移)
- [x] `conversation-list-panel.tsx:363,387,514` `text-[10px]`×2 → `text-2xs`、`text-[11px]` → `text-xs`(注意 `:363` 是 px-1.5 py-0 内的,`:387/:514` 是 px-1.5 py-px badge 内的)— **额外发现**:本表漏记 `:369` 一处 `text-[11px]`(customer-name span),一并映射 → `text-xs`(实测以 grep 为准)
- [x] `text-[NNpx]` grep(全 frontend/src)= 0 — grep exit 1 无匹配,确认归零
- [x] 视觉验证:`text-2xs` 渲染 = 原 `text-[10px]`;11px→xs 处视觉可接受(手动,evidence 记录)— 编译产物 CSS 实测 `.text-2xs{font-size:10px;line-height:14px}` 逐字等价原 `text-[10px]`(只补 lineHeight 14px ≈ xs 比例,视觉无放大);11px→xs(12px)差 1px,副文本/badge 不可见
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿 — build ✓(0 类型错误)/ oxlint 0 warnings 0 errors / npm test 141/141
- [x] `./init.sh full` 后端零回归(确认前端改动不影响后端测试)— 842 passed,0 失败(331s)
- [x] **feature 收尾**:feature_list.json `status` → `passing` + evidence 写实测 + `./scripts/sync-active-features.sh` 刷新 + 依赖解锁扫描(本 feature 无下游依赖,A/B 已 passing 则系列收官,overview 追加「系列状态:✅ 全部完成」)— 依赖解锁扫描:无下游;A+B passing → 系列收官
- [x] **系列收官检查**:若 Feature A + B 均已 passing,在本 feature 收尾时同步更新总纲 [`plan-frontend-design-system-overview.md`](./plan-frontend-design-system-overview.md) 的「系列状态」段为 ✅ 全部完成(three-tier §5 规则 ④)— 已更新
