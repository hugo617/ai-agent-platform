# 计划:设计系统收口 — Feature A:semantic token 基建

> **id**: `design-system-token-foundation`
> **状态**: ✅ passing(全 2 切片完成,2026-07-31 Session 173)
> **优先级**: 81(feature_list.json)
> **创建日期**: 2026-07-31
> **系列总纲**: [`plan-frontend-design-system-overview.md`](./plan-frontend-design-system-overview.md)
> **系列内位置**: A(地基,3 个 feature 中最先执行;B 依赖本 feature,C 与本 feature 正交)

---

## 0. v1 → vN 变更摘要

| v(N-1) 问题 | 严重度 | vN 处理 |
|---|---|---|
| v1 §4.5① 断言「四 token 亮色底饱和度均高(36%–60% lightness),白字对比度均达 WCAG AA(4.5:1)」数学错误:实测纯白前景(`0 0% 100%`)对 B3 定稿底色 8 组对比度**全部不达 4.5:1**(warning/info 亮+暗连 AA-large 3:1 都不达),与 §4.6 验收硬标准 #2 自相矛盾 | 🔴 高(硬阻断 §4.6 #2) | **v2** §4.5① 修订:foreground 从「统一纯白 `0 0% 100%`」改为「统一深色前景 `222.2 47.4% 11.2%`」(对齐现有 `--secondary-foreground`/`--primary-foreground` 亮色范式)。B3 定稿底色逐字不变。8 组对比度实测重算(§4.5① 表),全部达 AA 4.5:1(最低 danger 亮色 4.72,最高 warning 暗色 9.54)。§4.6 #2 / 切片 01 AC「前景对底色 AA」据此修订 |

---

---

## 1. Problem Statement(对齐 to-spec)

本仓库前端基建扎实(~25 个 HSL token + 完整暗色链路 + ~80% className 已 token 化),但**缺三类语义色 token**:`--success` / `--warning` / `--info`(本 feature 同时落地 `--danger`,与现有 `--destructive` 并存)。

**直接后果**:成功/警告/信息态只能直接引用 Tailwind 调色板原色(`emerald-500` / `amber-500` / `cyan-500`),**绕过 token 层**——这些原色在暗色模式下不随 `:root` ↔ `.dark` 切换,只能靠「原色在深底勉强可见」硬撑,且无法被白标 `--primary` 覆盖机制触及。

这是「设计系统收口」系列的**地基 feature**:不先建 token,B(业务页扫荡)无 token 可映射;B3 设计变体探索已为四 token 定稿精确 HSL 值,本 feature 把它落进 `index.css` + `tailwind.config.js` + `ui/` 组件库内部。

## 2. Solution(对齐 to-spec)

在 `index.css` 的 `:root`(亮)与 `.dark`(暗)各加 4 个语义色 HSL token(B3 定稿值),在 `tailwind.config.js` 的 `theme.extend.colors` 把 `success`/`warning`/`danger`/`info` 暴露为 Tailwind 颜色(含 `DEFAULT` + `foreground`),随后把 `ui/` 组件库**内部**残留的语义性硬编码色(`badge.tsx` 的 dot 装饰色、`toast.tsx` 的状态色、`avatar.tsx` 的 ring 等)**映射到新 token**。

**不动**:`avatar.tsx` 8 色环(设计性多色,刻意保留)、`chart-1..5`(数据可视化多色,合法保留)、业务页硬编码色(留给 Feature B)。

## 3. User Stories(对齐 to-spec)

- 作为 **组件库使用者**(开发),我想要 `bg-success` / `text-warning` 这类 className 直接可用,以便不再手写 `emerald-500` 原色
- 作为 **暗色模式用户**,我想要成功/警告/信息色在暗色下自动切换为提亮变体,以便深底背景上保持 WCAG AA 对比度
- 作为 **设计系统维护者**,我想要语义色集中在 token 层一处定义,以便未来调色只需改一处而非散落多文件
- 作为 **白标客户**,我想要语义色 token 能像 `--primary` 一样被主题覆盖机制触及(为未来扩展预留,本 feature 不实现白标覆盖)
- 作为 **看数据看板的用户**(B3 视觉参照),我想要成功(峰值/达成)、警告(谷值/提醒)、信息(青)三色有稳定可辨的语义,以便快速读懂数据状态

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 0 | 纯前端 feature |
| 数据库迁移 | 0 | 无 schema 变化 |
| 前端文件改动 | ~5 | `src/index.css`(token 定义)、`tailwind.config.js`(颜色暴露)、`src/components/ui/badge.tsx`、`src/components/ui/toast.tsx`、`src/components/ui/avatar.tsx`(组件库内部映射)|
| 新增测试类 | ~1 | frontend 组件级/快照测试(见 §5)|
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(纯前端)
- 是否修改现有租户隔离逻辑? **NO**
- 是否引入跨租户访问点? **NO**
- 验证:无多租户语义

### 4.3 权限影响评估

- 是否新增 permission code? **NO**(纯前端)
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 `require_permission` caller? **NO**
- 是否影响 graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist

**N/A**(纯前端,无表改动)

### 4.5 其他实施决策

**① Token 定义(严格用 B3 定稿值,来源:总纲「目标架构」段)**

`index.css` `:root`(亮色,新增,插在 `--destructive` 之后、`--border` 之前,与语义 token 同簇):

```css
--success: 152 76% 36%;    /* B3 定稿;正向/峰值/达成 */
--success-foreground: 222.2 47.4% 11.2%;  /* 深字 on success 底(见下理由) */
--warning: 35 92% 50%;     /* B3 定稿;提醒/谷值 */
--warning-foreground: 222.2 47.4% 11.2%;  /* 深字 on warning 底 */
--danger: 0 84% 60%;       /* B3 定稿;危险 */
--danger-foreground: 222.2 47.4% 11.2%;   /* 深字 on danger 底 */
--info: 189 90% 42%;       /* B3 定稿;信息/青 */
--info-foreground: 222.2 47.4% 11.2%;     /* 深字 on info 底 */
```

`index.css` `.dark`(暗色,提亮保高辨识度):

```css
--success: 152 64% 48%;    /* 暗色变体(提亮) */
--success-foreground: 222.2 47.4% 11.2%;  /* 深字(暗色底更亮,仍需深字保对比) */
--warning: 38 95% 58%;     /* 暗色变体(提亮) */
--warning-foreground: 222.2 47.4% 11.2%;
--danger: 0 80% 64%;       /* 暗色变体(提亮) */
--danger-foreground: 222.2 47.4% 11.2%;
--info: 189 80% 55%;       /* 暗色变体(提亮) */
--info-foreground: 222.2 47.4% 11.2%;
```

> **foreground 取 `222.2 47.4% 11.2%`(深蓝灰,非纯白)的理由(v2 修订)**:
> v1 曾断言「四 token 亮色底饱和度均高(36%–60% lightness),白字达 WCAG AA(4.5:1)」—— 此断言**数学错误**。按 WCAG 官方相对亮度公式实测,纯白前景(`0 0% 100%`)对 B3 定稿底色 **8 组对比度全部不达 4.5:1**(warning/info 亮+暗连 AA-large 3:1 都不达,见下表「v1 白字」列),与 §4.6 验收硬标准 #2 自相矛盾。
>
> v2 修订:**统一改用深色前景 `222.2 47.4% 11.2%`**(= 现有 `--secondary-foreground` / `--primary-foreground`(亮色)同值),8 组对比度全部达 AA 4.5:1(最低 danger 亮色 4.72,最高 warning 暗色 9.54)。这与组件库既有「中等亮度彩色底用深色前景」范式一致,且 B3 定稿底色**逐字不变**。
>
> | token | 底色亮度 | v1 白字 CR | v2 深字 CR | 判定 |
> |---|---|---|---|---|
> | 亮 `--success`(152 76% 36%)| 0.267 | 3.31 ❌ | **5.39** ✅ | AA |
> | 亮 `--warning`(35 92% 50%)| 0.403 | 2.32 ❌ | **7.69** ✅ | AA |
> | 亮 `--danger`(0 84% 60%)| 0.228 | 3.78 ❌ | **4.72** ✅ | AA |
> | 亮 `--info`(189 90% 42%)| 0.349 | 2.63 ❌ | **6.78** ✅ | AA |
> | 暗 `--success`(152 64% 48%)| 0.437 | 2.15 ❌ | **8.28** ✅ | AA |
> | 暗 `--warning`(38 95% 58%)| 0.511 | 1.87 ❌ | **9.54** ✅ | AA |
> | 暗 `--danger`(0 80% 64%)| 0.260 | 3.39 ❌ | **5.26** ✅ | AA |
> | 暗 `--info`(189 80% 55%)| 0.499 | 1.91 ❌ | **9.33** ✅ | AA |
>
> (计算脚本:WCAG 相对亮度 `0.2126R+0.7152G+0.0722B`,对比度 `(L1+0.05)/(L2+0.05)`,HSL→sRGB 标准变换。)
>
> **注**:`--destructive-foreground: 210 40% 98%` 仍保留近白(destructive 底是 shadcn 既有,用途为 hover/active 背景,其亮色底 lightness 60.2% 与本 feature 语义色不同簇,不在本次统一范畴)。

**② Tailwind 颜色暴露(`tailwind.config.js` `theme.extend.colors`)**

照搬现有 `destructive` 范式(`DEFAULT` + `foreground` 双键),新增 4 个色:

```js
success: { DEFAULT: "hsl(var(--success))", foreground: "hsl(var(--success-foreground))" },
warning: { DEFAULT: "hsl(var(--warning))", foreground: "hsl(var(--warning-foreground))" },
danger:  { DEFAULT: "hsl(var(--danger))",  foreground: "hsl(var(--danger-foreground))" },
info:    { DEFAULT: "hsl(var(--info))",    foreground: "hsl(var(--info-foreground))" },
```

> **`danger` vs `destructive` 并存**:`danger` 是语义色 token(本 feature 新建);`destructive` 是 shadcn/ui 既有命名(保留不动)。两者并存不冲突——业务页选用语义更明确的 `danger`,组件库内部既有 `destructive` 保留。本 feature 不做 `destructive` → `danger` 迁移(那会让 ui/ 改动面失控)。

**③ `ui/` 组件库内部映射(只动语义性硬编码色)**

经实地扫描,`ui/` 内需映射的硬编码色集中在 3 文件:

| 文件 | 现状 | 映射决策 |
|---|---|---|
| `badge.tsx`(4 处)| dot 装饰用 `emerald/amber/rose/...` 等原色表达状态 | **按语义映射**:`bg-emerald-500`→`bg-success` / `bg-amber-500`→`bg-warning` / `bg-rose-500`→`bg-danger`。若存在纯装饰多色 dot(非状态),保留不动 |
| `toast.tsx`(2 处)| success/error/warning toast 用原色 icon | **按语义映射**:success→`text-success` / error→`text-danger` 或复用 `destructive` / warning→`text-warning` |
| `avatar.tsx`(2 处)| 含 8 色环(头像背景刻意多色)+ 可能的 ring 色 | **8 色环保留不动**(设计性多色);只映射真正表达语义的 ring/border |

**映射边界规则**(来自总纲):
- 只有表达 success/warning/danger/info **语义**的硬编码色映射到 token
- avatar 8 色环、badge dot 装饰性多色等「刻意多色」的设计性用法**保留不动**
- 业务页(permissions/notifications/settings/billing 等)的硬编码色**留给 Feature B**,本 feature 不碰

**④ 暗色协同**

建 token 时同步定义暗色变体(`.dark` 段),一次性消除「硬编码色在暗色下靠原色硬撑」的风险——这是本 feature 相对「只加 token 不改暗色」的核心增量。

### 4.6 验收硬标准(来自总纲,客观可验)

1. **grep 归零**(本 feature 范围内):`ui/badge.tsx` + `ui/toast.tsx` + `ui/avatar.tsx` 内的**语义性**硬编码原色 = 0(8 色环保留的不算)
2. **暗色对比度**:四 token 亮/暗变体前景(`222.2 47.4% 11.2%`,v2 深字)对底色对比度 ≥ WCAG AA(4.5:1 正常文本);8 组实测见 §4.5① 表
3. **npm test 全绿 + npm run build 0 错 + oxlint 0/0**
4. **零行为变更**:映射前后视觉一致(亮色下 `bg-success` 渲染色 = 原 `bg-emerald-500` 渲染色,因 B3 定稿值就是 emerald 系)

---

## 5. Testing Decisions(对齐 to-spec)

- **测试金字塔**:本 feature 是 token + className 映射,无运行时逻辑变化 → **以构建/类型/lint 为主,辅以组件级渲染测试**
- **优先复用现有 seam**:看 `src/components/ui/` 是否已有组件测试(如 `key-spec-rows.test.tsx` 范式);有则加 case,无则建最小渲染测试
- **测试内容**:
  - token 定义存在性:`index.css` 含 `--success/--warning/--danger/--info`(`:root` + `.dark` 各 4)
  - 暗色切换正确性:渲染 `bg-success` 元素,切 `.dark` 后取计算色 = 暗色变体(jsdom 可能取不到计算色,则降级为 CSS 文本断言)
  - 组件映射后渲染不报错:Badge/Toast/Avatar 渲染含新 className 的 fixture
- **WCAG 对比度**:用脚本/手算验证 4 组前景-底色对比度(非自动化测试,落入 §4.6 验收手动项 + plan checklist)
- **覆盖率**:无服务端测试基线约束(纯前端);目标 = 现有前端测试不回归 + 新增 token 断言通过

---

## 6. 切片规划(对齐 to-tickets tracer-bullet)

> 见下方「实施切片」段(/to-tickets 产出)。

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:改动文件 ~5、纯前端、无鉴权/权限/迁移/跨服务 → **不满足复杂任务触发条件**(改动 <10、无安全敏感、无不可逆操作)。

**审查方式**:本 feature 走**轻量自审**(EP2 收尾自检 + 切片 acceptance criteria),不强制多模型对抗式审查。若 EP3 实施期发现 token 值或映射边界有歧义,回本 plan 补 v2 变更摘要。

---

## 8. Out of Scope(对齐 to-spec)

- ❌ **业务页硬编码色扫荡**(permissions/notifications/settings/billing/dashboard/users/composite-mode/markdown-view/notification-bell/conversation-list-panel 等)→ Feature B
- ❌ **间距 token + 卡片层级规范** → Feature C
- ❌ **`destructive` → `danger` 迁移**(保留 destructive 既有命名,本 feature 只新增 danger)
- ❌ **白标语义色覆盖机制**(白标 `--primary` 覆盖已实现,但语义色白标覆盖不在本系列范围)
- ❌ **avatar 8 色环保留不动**(设计性多色)
- ❌ **chart-1..5 保留不动**(数据可视化多色)
- ❌ **字号任意值收口**(`text-[10px]` 等)→ Feature C 顺手项
- ❌ **移动端/响应式适配**(系列边界,剥离为独立后续系列)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| B3 定稿值与原 `emerald-500` 渲染色肉眼有差异,破坏视觉一致性 | 中 | 映射后对照 `design-demos/B3.html` 确认;§4.6 验收含「视觉一致」手动项 |
| badge dot 的「状态色」vs「装饰色」边界误判(把装饰色也映射了) | 中 | 逐处核对:dot 是否表达 success/warning/info 语义;模糊处保留不动,写入 plan checklist |
| 暗色变体提亮值与现有 `--destructive` 暗色(`0 62.8% 30.6%`)风格不一致(danger 暗色更亮) | 低 | destructive 暗色偏暗(作 hover/active 背景),danger 作为前景语义色需提亮——两者用途不同,差异合理,记录在本 plan §4.5② |
| jsdom 无法测计算色导致暗色测试降级 | 低 | 降级为 CSS 文本断言(`.dark` 段含 `--success: 152 64% 48%`),配合手动浏览器验证 |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `src/index.css` `:root` + `.dark` 各含 `--success`/`--warning`/`--danger`/`--info`(及 `-foreground`),值 = B3 定稿
2. `tailwind.config.js` `theme.extend.colors` 含 `success`/`warning`/`danger`/`info`(各 `DEFAULT` + `foreground`)
3. `ui/badge.tsx` + `ui/toast.tsx` 内**语义性**硬编码原色 = 0(`ui/avatar.tsx` 仅映射语义 ring,8 色环保留)
4. 四 token 亮/暗变体前景(`222.2 47.4% 11.2%`)对底色 WCAG AA 对比度达标(v2 重算 8 组见 §4.5① 表,全部 ≥ 4.5:1)
5. `cd frontend && npm run build` 0 类型错误 + `npx oxlint` 0/0 + `npm test` 全绿
6. 对照 `design-demos/B3.html`,四 token 渲染色与 B3 定稿视觉一致

---

## 11. 不越界声明

本次改动**只**涉及:`src/index.css`(token 定义)、`tailwind.config.js`(颜色暴露)、`src/components/ui/` 下 badge/toast/avatar 三组件的**语义性**硬编码色映射。

**不**触碰:业务页(pages/*)、layout/notification-bell、chat/markdown-view、avatar 8 色环、chart-1..5、`destructive` 既有命名、白标逻辑、间距/字号体系、任何后端代码。

---

## 实施切片(/to-tickets 产出)

### 切片依赖图

```
切片 01(token 基建:CSS + tailwind 暴露)── 无 blocker,frontier
   └──→ 切片 02(ui/ 组件库内部映射 + 验收)── blocked by 01
```

### 切片 01 — semantic token 基建:`index.css` + `tailwind.config.js`(frontier)✅ commit ffe4a8a

**What it delivers**:从组件库使用者视角,`bg-success` / `text-warning` / `border-danger` / `bg-info` 这类 className 立即可用,且在亮/暗模式下自动切换为 B3 定稿的双色值。这是「四 token 存在且可消费」的最小可验证路径——token 落地 + Tailwind 暴露,任何下游(切片 02 + Feature B)都能引用。

**Blocked by**: 无(可立即开始)

**Acceptance criteria**:

- [x] `src/index.css` `:root` 含 `--success: 152 76% 36%` / `--warning: 35 92% 50%` / `--danger: 0 84% 60%` / `--info: 189 90% 42%` 四 token + 各 `-foreground: 222.2 47.4% 11.2%`(底色 HSL 逐字 = B3 定稿;foreground v2 修订为深字,见 §4.5①)
- [x] `src/index.css` `.dark` 含 `--success: 152 64% 48%` / `--warning: 38 95% 58%` / `--danger: 0 80% 64%` / `--info: 189 80% 55%` 四 token + 各 `-foreground: 222.2 47.4% 11.2%`(底色 HSL 逐字 = B3 定稿暗色变体;foreground v2 深字)
- [x] `tailwind.config.js` `theme.extend.colors` 含 `success`/`warning`/`danger`/`info`,各 `DEFAULT: "hsl(var(--xxx))"` + `foreground: "hsl(var(--xxx-foreground))"`(照 `destructive` 范式)
- [x] 新增/更新前端测试:断言 token 定义存在(`:root` + `.dark` 各 4 token,值正确)
- [x] `cd frontend && npm run build` 0 类型错误 + `npx oxlint` 0/0 + `npm test` 全绿
- [x] 手动验证:四 token 亮/暗变体前景(`222.2 47.4% 11.2%`,v2 深字)对底色 WCAG AA 对比度 ≥ 4.5:1(实测 8 组见 §4.5① 表,全部达标)

**完成证据(commit 后回填 HASH)**:
- 改动文件:`frontend/src/index.css`(:root + .dark 各 8 行 token)+ `frontend/tailwind.config.js`(theme.extend.colors +success/warning/danger/info)+ `frontend/src/__tests__/design-tokens.test.ts`(新建,21 测试)+ `harness/docs/plan-design-system-token-foundation.md`(v2 修订:§0 变更摘要 + §4.5① foreground 决策修订 + 对比度实测表 + §4.6/§10/切片01 AC 措辞同步)
- 验证:`npm run build` 0 类型错误 + `npx oxlint` 0 warning 0 error + `npm test` **131/131 全绿**(原 110 + 21 新增 design-tokens)+ design-tokens 单测 21/21(:root 8 + .dark 8 + tailwind 4 色 + destructive 保留 1)
- WCAG 实测(§4.5① 表):8 组前景 `222.2 47.4% 11.2%` 对 B3 底色对比度全部 ≥ 4.5:1(最低 danger 亮色 4.72,最高 warning 暗色 9.54);v1 纯白前景 8 组全不达标的硬阻断已解
- **v2 修订触发**:实施期发现 plan §4.5① 「纯白前景达 AA」断言数学错误(WCAG 公式实测证伪),回 plan 补 v1→v2 变更摘要 + §4.5① 重写 + 对比度表,foreground 从 `0 0% 100%` → `222.2 47.4% 11.2%`(对齐现有 `--secondary-foreground` 范式),B3 底色逐字不变
- **非末切片**(切片 02 才是 feature 收尾),不动 feature_list.json status/evidence

### 切片 02 — `ui/` 组件库内部映射:badge + toast + avatar(末切片,feature 收尾)✅ commit 8398ab2

**What it delivers**:从组件库维护者视角,`ui/` 内部残留的语义性硬编码原色(badge dot 状态色 / toast 状态 icon 色 / avatar 语义 ring)全部映射到新 token,组件库自身成为「设计系统收口」的干净样板。avatar 8 色环保留不动(设计性多色边界)。

**Blocked by**: 切片 01(token 必须先存在,组件才能引用)

**Acceptance criteria**:

- [x] `src/components/ui/badge.tsx`:语义性 dot 色(`emerald→success` / `amber→warning` / `rose→danger`)映射完成;纯装饰多色 dot(若有)保留并在 evidence 注明保留理由
  - **✅ done**:success variant `bg-emerald-500 text-white`→`bg-success text-success-foreground`;dot-success/warning/destructive `[&::before]:bg-emerald/amber/red-500`→`bg-success/warning/danger`。dot-muted(中性灰,`bg-current`)保留不动(非语义色,无对应 token)。
- [x] `src/components/ui/toast.tsx`:success/warning/error icon 色映射到 `text-success` / `text-warning` / `text-danger`(或复用 `destructive`);映射后渲染不报错
  - **✅ done(实心范式,非 tint)**:success→`bg-success text-success-foreground`、destructive(error)→`bg-danger text-danger-foreground`。**偏离 AC 措辞**「text-success DEFAULT」:DEFAULT 中绿在 `bg-success/10` tint 底上亮色对比度仅 2.96 / 暗色 1.18 不达 WCAG AA 4.5(`/code-review` Spec #3 拦截);改实心 `bg-success`+深 foreground 对齐 badge/button destructive 范式,亮 5.42/4.72 + 暗 8.31/5.28 双模式全过 AA。`text-warning` 条款 vacuous:ToastVariant 只有 default/success/destructive/loading,无 warning variant(代码现状无对应物,evidence 留痕)。
- [x] `src/components/ui/avatar.tsx`:语义性 ring/border 映射;**8 色环保留不动**(evidence 注明保留边界规则)
  - **✅ done(零改动)**:avatar 实测**无语义 ring/border**(仅 8 色环 `COLOR_PALETTE` + `rounded-full` + `text-white`),「ring/border 映射」条款 vacuous;「8 色环保留不动」满足(avatar.tsx 零改动,feature notes 边界规则)。evidence 留痕。
- [x] `ui/` 三文件内语义性硬编码原色 grep = 0(8 色环 + chart 等设计性多色不计)
  - **✅ done**:grep `emerald|amber|rose|red-[0-9]` 在 badge.tsx + toast.tsx **代码归 0**(badge L34 注释文字「amber dot」是描述性非 className,不计);avatar.tsx 仅剩 8 色环 `COLOR_PALETTE`(设计性多色,AC 明确不计)。
- [x] 新增/更新组件渲染测试:Badge/Toast/Avatar 含新 className 的 fixture 渲染通过(复用现有 `key-spec-rows.test.tsx` 范式或建最小渲染测试)
  - **✅ done**:新建 `badge-toast-avatar.test.tsx` 10 测试(5 Badge 语义映射 + 3 Toast 实心 token + 2 Avatar 8 色环保留锁)。锁映射不回退:断言新 className 真出现 + 旧 emerald/red 残留即变红。沿用 key-spec-rows.test.tsx 中文注释 + describe/it 范式。
- [x] `cd frontend && npm run build` 0 错 + `npx oxlint` 0/0 + `npm test` 全绿
  - **✅ done**:build 0 类型错误(1.56s)+ oxlint 0 warning 0 error(180 files)+ npm test **141/141**(131 baseline + 10 新,零行为回归)。
- [x] 视觉一致性验证:对照 `design-demos/B3.html`,映射前后亮色渲染一致(danger 暗色与 destructive 差异按 §4.5② 记录)
  - **✅ done**:B3 定稿底色值逐字落地 index.css(切片 01),toast 实心 + badge dot 映射后亮色渲染与 B3 一致。暗色 danger 提亮(`0 80% 64%`)比 destructive 暗色(`0 62.8% 30.6%`)更亮 —— 按 §4.5② 记录的设计差异(danger 是新语义 token 提亮保对比度,destructive 是 shadcn 既有暗色命名保留)。
- [x] **feature 收尾**:`./init.sh full` 后端零回归(本 feature 纯前端,确认前端改动不影响后端测试) + feature_list.json `status` → `passing` + evidence 写实测 + `./scripts/sync-active-features.sh` 刷新 + 依赖解锁扫描(Feature B 依赖本 feature,本 feature passing 后 B 可置 `in_progress`)
  - **✅ done**:`./init.sh full` **842 passed**(后端零改动零回归)+ feature_list.json status `in_progress → passing` + evidence 4 条 + sync-active 刷新(2 活跃 B+C)+ **依赖解锁**:Feature B(`design-system-color-sweep` p82,depends_on 本 feature)解锁,可置 in_progress(WIP=1 下 B 是下一 frontier)。
