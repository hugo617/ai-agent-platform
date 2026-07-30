# 计划:前端 chat-page 拆 ConversationListPanel + buildWorkingList 纯函数

> **id**: `chat-page-split`
> **状态**: draft v2(经 opus 对抗式审查修订)
> **优先级**: 76(当前最高 passing = union-cast-split 75,本任务接其位;第 7 次巡检候选 ① Top)
> **创建日期**: 2026-07-30
> **最后修订**: 2026-07-30(v2)
> **来源**: 第 7 次代码健康度巡检候选 ①(Top recommendation)+ grill 9 决策共识

---

## 0. v1 → v2 变更摘要(对抗式审查修订)

opus 双轴审查(真相核查 + 设计质量)发现 v1 多处事实错误与设计漏洞,本轮修订:

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| **D2「Panel 不 import hooks、父传 data+handler」与声称对齐的 `bookings/store-view` 范式 180° 相反** —— store-view 实测是「Panel 自调 hooks、零 props」 | 🔴 RED | 修正 §2/§4.0 D2/§4.5:**Panel 自调 hooks**(对齐 store-view 真实范式),跨组件 state 全部下沉 Panel,父层零 props |
| **buildWorkingList 签名 `(base, userText) => Message[]` 声称「纯函数」但内含 `Date.now()`/`new Date()`**(非确定) | 🔴 RED | 修订签名加 `now?: () => number = Date.now` 参数;§5 测试 case 改用 `vi.useFakeTimers()` |
| **selectedIds 下沉与 conversations 留父层冲突** —— L135 effect 依赖父层 conversations 却要清空子层 selectedIds,跨层反向命令 | 🔴 RED | §4.5 明确:Panel 自调 useConversations 后,conversations + selectedIds + effect **全部下沉 Panel**,无跨层 |
| **barrel 范式不一致** —— v1 chat 单 entry,同批 devices 双 entry,两者都号称「镜像 bookings」 | 🔴 RED | 统一为双 entry(`chat/chat-page.tsx` barrel + `chat/index.tsx` 路由),对齐 bookings + devices |
| **Ticket 1 git mv 时机悬置** —— 「实施时定」是阻塞性未决 | 🔴 RED | 明确:Ticket 1 **不 git mv**(在旧位置改纯函数),git mv + App.tsx 在 Ticket 3 |
| **handleRegenerate 未声明边界** —— §5 case 2 措辞误导(以为纯函数覆盖了 regenerate) | 🟡 YELLOW | §4.5 显式声明:handleRegenerate 不抽、不测、行为不变 |
| **AC「grep useMemo=0」与 store-view 用了 useMemo 冲突** —— store-view 有 3 处 useMemo | 🟡 YELLOW | §4.5 明确:本次 Panel 不引 memo(与 store-view 的 memo 习惯不同),AC 保持 |
| **全文用行号违反铁律 #5**(行号会变) | 🟡 YELLOW | 改为符号名锚定(`handleSend` 内 working-list 段、`customerNameOf` 函数等) |

---

## 1. Problem Statement(对齐 to-spec)

**问题**:`frontend/src/pages/chat-page.tsx` 是一个 **1038 行的单函数组件**(`ChatPage`,L92-1036,~945 行函数体),内联了三层关注点:

1. **~25 个 state hooks**(L107-191)+ 全部 conversation 管理处理器 inline(`handleDeleteConversation` / `toggleSelect` / `handleBatchDelete` / `openRename` / `submitRename` / `openAddTag` / `submitAddTag` / `handleRemoveTag` / `handleTogglePin` / `handleToggleStar`,L266-368)
2. **整个 SSE streaming 状态机** inline(`handleSend` L369-442,含 working-list 计算 / AbortController / AbortError 区分 / `customer_id` 仅新会话规则)
3. **整个会话列表 panel JSX** inline(L493-669,~175 行:checkbox 多选 / pin·star 徽章 / composite 徽章 / tag chips / customer 归因 / 右键菜单 DropdownMenu)
4. **rename + add-tag 两个 Dialog** inline(L948-1036,由 panel 右键菜单触发,4 个 dialog state `renameTarget`/`renameValue`/`tagTarget`/`tagValue` 驱动)

**关键证据**:`grep -c 'useMemo\|useCallback' chat-page.tsx` = **0**。每个派生值、每个 handler 每次渲染都重建,没有任何 factor-out。

**friction**(对照 `/codebase-design` 词汇):

1. **无 locality**:改一行列表交互(如给 tag chip 加确认弹窗)要在这 945 行里定位上下文,列表逻辑与 streaming 半边纠缠。`bookings/shared.tsx` 已拆成独立模块可独立阅读,chat-page 没有这层 locality。
2. **不可测是结构性问题**(巡检新发现 A2):`handleSend` 的 working-list 计算(L387-400,分支 `localMessages ?? history`)是 bug-prone 逻辑 —— 它决定 regenerate 时旧 assistant 回复是否被重发为 context、user turn 是否重复。但它闘在组件内、无纯函数出口,**无法单测**。bookings 测试套件(`store-view.test.tsx` 在 module 边界 `vi.mock("@/hooks/queries")`)证明单测模式可行,chat-page 的结构主动击败了这个模式 —— `ChatPage` 是唯一 export,逻辑无出口。
3. **范式不一致**:`bookings/` 已拆成 `store-view.tsx` / `hq-view.tsx` / `my-bookings-view.tsx` 独立文件 + `__tests__/`,chat-page 是同款「列表 + 交互」page 里唯一未拆的。

**deletion test**:抽出 `ConversationListPanel`(列表 + 菜单 + 2 Dialog + 4 state)+ `buildWorkingList` 纯函数后,`ChatPage` 瘦到 ~600 行只管 streaming + 编排,**complexity 浓缩**进 Panel(列表交互生命周期自含)和纯函数(working-list 计算独立可测),不是平移。删除这个拆分会把 complexity 重新打散回 945 行单函数。

**为什么现在做**:第 7 次巡检(2026-07-30)Top recommendation。union-cast-split(priority 75)刚收官,前端类型卫生已紧一格;chat-page 的单函数膨胀 + 不可测是当前 leverage 最高、风险最低的候选(纯结构重构零行为变更,bookings/ 已有同款范式可照抄)。composite-chat feature 的 fan-out 已正确抽到 `composite-mode.tsx`(独立 460 行),证明这个 codebase 的 panel 拆分范式是可行的、被验证过的。

---

## 2. Solution(对齐 to-spec)

仿 `bookings/` 已验证的拆分模板,把 chat-page 拆成 **chat/ 文件夹**:

- `ConversationListPanel` 组件 —— **自含完整列表交互生命周期**(对齐 `bookings/store-view` 真实范式):**Panel 自己 import 并调用 `@/hooks/queries`**(useConversations / useDeleteConversation / useRenameConversation / useAddConversationTag / useRemoveConversationTag / useSetConversationPinned / useSetConversationStarred / useBatchDeleteConversations / useCustomerProfiles 等),**零 props**(父层 index.tsx 只做角色分支或直接渲染)。列表渲染 + 右键菜单 + rename/add-tag 两个 Dialog + 4 个 dialog state + selectedIds + searchInput + searchCommitted + 清空 effect **全部下沉 Panel 内部**,无跨层通信。
- `buildWorkingList` **近纯函数**(注入时钟)—— 从 `handleSend` 抽出 working-list 计算(`base + userMsg + assistantMsg`),签名 `buildWorkingList(base, userText, now?) => Message[]`,`now` 参数默认 `Date.now`(注入便于单测),独立单测。
- `customerNameOf` 共享 helper —— 放 `chat/customer-helpers.ts`,签名参数化 `(cid, profiles) => name`(真纯函数,把 customerProfiles 作为参数传入),两边(panel 列表 + chat panel header)都调。
- ChatPage 瘦到 ~600 行,只剩 streaming 半边(agent picker / message stream / input / CompositeMode 渲染)+ streaming 相关 state 编排。

**核心洞察**:chat-page 的「不可测」和「单函数膨胀」是**同一根因**(列表逻辑 + streaming 逻辑 + working-list 计算全闘在一个 export 里)。拆 Panel + 纯函数同时提升可维护性 + 解锁 working-list 这一个纯逻辑点的可测性(注:handleSend 的 SSE/AbortError/customer_id 规则仍不可测,本次不解决,见 §8 Out of Scope)。

---

## 3. User Stories(对齐 to-spec)

- 作为 **store 门店角色**(owner/admin/member),我在对话页看到的列表交互行为**零变化**(纯结构重构,无用户可见行为差异)
- 作为 **平台角色**(super_admin/hq_staff),我的 panorama 视图 + customer 归因显示**零变化**
- 作为 **开发者**,我改列表交互(如调 tag chip 样式)只读 `conversation-list-panel.tsx` 一个文件(~175 行),不必在 945 行里定位
- 作为 **开发者**,我改 streaming 逻辑只读 `chat-page.tsx` 的 streaming 半边,列表半边不干扰
- 作为 **开发者**,我能给 `buildWorkingList` 写纯函数单测,验证「regenerate 不重发旧 assistant 回复」「user turn 不重复」「空 base 兼容」三个边界,回归有保护
- 作为 **未来巡检 agent**,我看到 chat-page 的结构对称于 bookings/,认知负担降低,不再标「单函数膨胀」候选
- 作为 **未来加功能的开发者**,给列表加新交互(如归档按钮)只需在 Panel 内加 handler + state,不碰 streaming 半边

---

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.0 grill 9 决策汇总(一次一问共识,v2 修订)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| **D1** | 拆分粒度 | **Panel + 近纯函数** | 消膨胀 + 解 working-list 可测 + 抽 buildWorkingList。比「只抽 Panel」多解可测点,比「+ useStreamChat hook」避免 over-engineering |
| **D2** | Panel 接口范式 | **Panel 自调 hooks、零 props**(v2 修正) | **对齐 `bookings/store-view` 真实范式**(store-view 实测自调 useBookings 等十余 hook,零 props)。Panel 自己 import 并调用 `@/hooks/queries` 的 conversation 管理 hooks,父层 index.tsx 零 props 传参。v1 误以为 store-view 是「父传 handler」,审查纠正 |
| **D3** | buildWorkingList 落点 | **独立 .ts + 单测(近纯,注入时钟)** | 近纯函数(签名加 `now?: () => number = Date.now` 参数),独立单测文件配套;与 Panel 同在 chat/ 下,locality 好 |
| **D4** | 文件组织 | **建 chat/ 文件夹(双 entry)** | 对齐 `bookings/` 范式:`chat/chat-page.tsx`(barrel re-export)+ `chat/index.tsx`(路由入口);候选② devices-page 同款双 entry,三 plan 范式一致 |
| **D5** | rename/add-tag Dialog 归属 | **Dialog 随 Panel**(panel 自含) | Panel 管完整列表交互生命周期;dialog state(`renameTarget`/`renameValue`/`tagTarget`/`tagValue`)进 Panel 内部,ChatPage 不再关心 |
| **D6** | chat panel(右半边 streaming) | **不动** | 只抽左边;streaming 半边紧耦合 streaming state,抽 panel 收益递减,超出巡检建议 |
| **D7** | customerNameOf helper | **共享 helper(参数化纯函数)** | 两边(panel 列表 + chat panel header)都用;放 `chat/customer-helpers.ts`,签名 `(cid, profiles) => name`(把 customerProfiles 作参数传入,真纯函数,可单测) |
| **D8** | 测试范围 | **两测试文件** | `build-working-list.test.ts`(近纯函数,用 fake timers)+ `conversation-list-panel.test.tsx`(组件 smoke,对齐 store-view.test,Panel 自调 hooks 故 mock 面同 store-view ~10 hook) |
| **D9** | router import 路径 | **chat/chat-page.tsx barrel(v2 修正为双 entry)** | 对齐 `bookings/bookings-page.tsx` + devices 双 entry;App.tsx 改 `@/pages/chat-page` → `@/pages/chat/chat-page`。**v1 单 entry 与 devices 不一致,审查纠正为双 entry** |

### 4.1 影响面清单(项目特化)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | **0** | 纯前端重构,零后端零 schema 零 API |
| 数据库迁移 | **0** | 无 |
| 前端文件改动 | **6 新建 + 2 改** | 新建:`chat/chat-page.tsx`(git mv)+ `chat/conversation-list-panel.tsx` + `chat/build-working-list.ts` + `chat/customer-helpers.ts` + `chat/__tests__/build-working-list.test.ts` + `chat/__tests__/conversation-list-panel.test.tsx`;改:`App.tsx`(import 路径)+ 删旧 `pages/chat-page.tsx` |
| 新增测试类 | **2** | 见上 |
| Skill / Hook / 配置 | **0** | 无 |

> **git mv 保留历史**:`chat-page.tsx` → `chat/chat-page.tsx` 用 `git mv` 保留 blame 历史(bookings-page-split 已验证此范式)。

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(纯前端)
- 是否修改现有租户隔离逻辑? **NO**(前端只是展示层,租户隔离在后端 API + Principal)
- 是否引入跨租户访问点? **NO**(`useCustomerProfiles(!isSuperAdmin(me))` 的 role 守卫原样保留,只是 helper 位置移动)
- 验证:无多租户测试用例(纯结构重构,行为零变化由现有 65 前端测试 + build 保护)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(纯前端)
- 是否影响 graph.py 工具内 check? **NO**
- scope 闸门:不涉及(前端重构)

### 4.4 数据库表设计 checklist

**N/A** —— 纯前端重构,无表改动。

### 4.5 其他实施决策

- **conversationLabel helper**(`conversationLabel` 函数):本地 helper,只被 panel 列表用(渲染 `title` + 列表项 label),随 Panel 一起移到 `conversation-list-panel.tsx` 内部(只它用)。
- **selectedIds / searchInput / searchCommitted / 清空 effect 全部下沉 Panel**(v2 修正):审查发现 v1「selectedIds 下沉 + conversations 留父层」会导致清空 effect(`keying on conversationIdSet`)跨层反向命令流。**修正**:Panel 自调 `useConversations` 后(D2),conversations 数据 + selectedIds + searchInput + searchCommitted + debounce effect + 清空 effect **全部下沉 Panel 内部**,无任何跨层通信。这是 D2「Panel 自调 hooks、零 props」的自然结果 —— Panel 自己拿 conversations,自己管理依赖它的 selectedIds 和 effect。
- **startNewConversation / selectConversation**:这两个 handler 涉及跨半边状态(`selectedConversationId` / `selectedCustomerId` / `localMessages` / `input`)。**关键设计点**:Panel 需要通知 ChatPage「用户选了哪个会话」(驱动 streaming 半边的 history / mode 切换)。方案:Panel 通过 `onSelectConversation(id)` / `onStartNew()` 回调通知父层(这是 Panel 仅有的两个「向上通知」props,非 data/handler 下传)。父层 ChatPage 接收后设置 `selectedConversationId` 等 streaming 半边 state。**这是「零 props」的例外**:Panel 有 ~2 个回调 props(向上通知),但所有 data/mutation 都自调,不传 handler 下。
- **handleRegenerate 不抽、不测、行为不变**(v2 声明边界):`handleRegenerate` 读 `messages = localMessages ?? history ?? []` 后切掉尾部 assistant、回填 input。它是 working-list `base` 的**预备者**(不是消费者)。buildWorkingList 抽出后 handleRegenerate **不改** —— 它的 `setLocalMessages(trimmed)` 行为不变,只是后续 handleSend 调 buildWorkingList 时会读到这个 trimmed 的 localMessages。§5 case 2「regenerate 场景」测的是「给定一个已 trim 的 base」这一**前置条件**,不是 handleRegenerate 本身的测试。
- **buildWorkingList 的 now 参数注入**(v2 修正):原 `handleSend` 内联逻辑用 `Date.now()`(生成 userMsg/assistantMsg 的 id)+ `new Date().toISOString()`(created_at)。抽出后签名 `buildWorkingList(base, userText, now: () => number = Date.now)`,函数内用 `now()` 生成时间戳(id 前缀 `local-user-`/`local-assistant-` + created_at)。测试用 `vi.useFakeTimers()` 固定时间或只断言 id 前缀(非全值)。
- **零行为变更约束**:所有 handler 逻辑原样搬迁,只改位置不改实现。`useMemo`/`useCallback` **不引入**(v2 注:store-view 有 3 处 useMemo,但本次 Panel 不引 memo —— 与 store-view 的 memo 习惯不同,AC「grep useMemo=0」保持)。
- **符号名锚定**(v2 修正,呼应铁律 #5):本 plan 引用代码用符号名(`handleSend` 内 working-list 段 / `customerNameOf` 函数 / `conversationLabel` / rename Dialog 的 `<Dialog open={renameTarget !== null}>` 等),不用行号(行号会随编辑漂移)。grill 阶段记录的行号仅作定位辅助,实施时以符号名 + 代码搜索为准。

---

## 5. Testing Decisions(对齐 to-spec)

### 测试 seam(已在 to-spec 阶段与用户确认,v2 修正)

| Seam | 层级 | 测什么 | 先例 |
|---|---|---|---|
| **seam A: `buildWorkingList` 近纯函数** | 函数级(最高) | 直接 import 调用,`vi.useFakeTimers()` 固定时钟,断言输入→输出(结构 + id 前缀) | 项目首个近纯函数单测 |
| **seam B: `ConversationListPanel` 组件** | 组件级 | `renderWithProviders` + `vi.mock("@/hooks/queries")`(Panel 自调 hooks,mock 面同 store-view ~10 hook)+ `vi.mock("@/components/auth/auth-context")`,断言 render + 交互 | `bookings/store-view.test.tsx`(完全同款) |

**seam 总数 = 2**,都是局部最高点,不新增跨 seam。`ChatPage` 整体不单测(streaming 半边涉及 SSE/AbortController,mock 面大,巡检明确排除)。

### 测试金字塔

- **unit 2 文件**:`build-working-list.test.ts`(近纯函数)+ `conversation-list-panel.test.tsx`(组件)
- **integration 0**:不新增(ChatPage 集成由现有 e2e Playwright 覆盖)
- **E2E 0**:不新增(现有 Playwright chat 流程自动覆盖回归)

### build-working-list.test.ts 边界 case 清单(v2 修正近纯函数)

1. **首次发送**:`base = []`(无 history 无 localMessages)→ working = [userMsg, assistantMsg]。用 `vi.useFakeTimers()` 固定时间,断言结构 + id 前缀(`local-user-`/`local-assistant-`)+ created_at 等于 fake now
2. **regenerate 场景的 base 输入**:`base` 少尾部 assistant(模拟 handleRegenerate 设的 trimmed localMessages)→ working 不含旧 assistant 回复(仅测「给定 trimmed base」这一前置条件,**不测 handleRegenerate 本身**,见 §4.5)
3. **正常 follow-up**:`base = [已有对话]` → working = [...已有, userMsg, assistantMsg]
4. **空 base 兼容**:`base` 为空数组(调用方 handleSend 传 `(localMessages ?? history ?? [])` 已做 fallback)→ working = [userMsg, assistantMsg]
5. **浅拷贝不可变性**:`base.map(m => ({...m}))` 浅拷贝,断言原 base 数组元素不被修改(注:返回的 userMsg/assistantMsg 后续会被 handleSend 的 SSE 循环 mutate content,但那是调用方行为,buildWorkingList 本身只构造)

### conversation-list-panel.test.tsx 覆盖(对齐 store-view.test 范式,Panel 自调 hooks)

- `renderWithProviders` + `vi.mock("@/hooks/queries")` stub ~10 个 hook(useConversations / useDeleteConversation / useRenameConversation / useAddConversationTag / useRemoveConversationTag / useSetConversationPinned / useSetConversationStarred / useBatchDeleteConversations / useCustomerProfiles / useToast)+ `vi.mock("@/components/auth/auth-context")`
- 列表渲染:stub useConversations 返 conversations 数组 → 渲染对应行(pinned/starred/composite 徽章显示正确)
- 空状态:stub 返 [] → 显示「还没有会话」;searchCommitted → 「没有匹配的会话」
- 点击删除 → stub 的 `useDeleteConversation().mutateAsync` 被调
- 右键菜单 → 点「重命名」→ rename Dialog 弹出(DropdownMenu portal 异步,`await findByText`)
- 右键菜单 → 点「添加标签」→ add-tag Dialog 弹出

### 覆盖率目标

- 本任务新增 2 测试文件,目标覆盖抽出的近纯函数 + Panel 的核心交互路径
- 项目前端基线:65 tests / 8 files;本任务后预期 ~73+ tests / 10 files
- 后端覆盖率不受影响(零后端改动)

---

## 6. 切片规划(对齐 to-tickets tracer-bullet,v2 修正 git mv 时机)

> **切片策略**:本任务是**纯前端结构重构**,非功能开发,不切垂直全栈切片。按「依赖顺序 + 风险隔离」分 3 片:先抽无依赖的近纯函数(可立即单测)→ 再抽 Panel(依赖纯函数无,但依赖 ChatPage state 边界厘清)→ 最后收尾(git mv + router + 清理 + 全量验证)。

### Ticket 1: 抽 buildWorkingList 近纯函数 + 单测(expand,**不 git mv**) ✅

- **What to build**:从 `handleSend` 内的 working-list 计算段(`const base = (localMessages ?? history ?? []).map(...)` → userMsg → assistantMsg → working)抽出 `buildWorkingList(base, userText, now?)` 近纯函数到 `chat/build-working-list.ts`(暂建 chat/ 文件夹),`handleSend` 改调它。配套 `build-working-list.test.ts` 覆盖 5 边界 case(用 `vi.useFakeTimers()`)。此切片**不改任何调用方行为**(handleSend 内部改调近纯函数,输入输出等价)。**v2 关键:不 git mv chat-page.tsx**(仍在旧位置 `pages/chat-page.tsx`,handleSend 改调新纯函数,跨目录 import 路径 `./chat/build-working-list` 成立);git mv + App.tsx 改在 Ticket 3。
- **Blocked by**: 无(可立即开始)
- **文件清单**(3):
  - 新建 `frontend/src/pages/chat/build-working-list.ts`
  - 新建 `frontend/src/pages/chat/__tests__/build-working-list.test.ts`
  - 改 `frontend/src/pages/chat-page.tsx`(handleSend 改调近纯函数;文件**不移动**)
- **验证命令**:
  - `cd frontend && npx vitest run src/pages/chat/__tests__/build-working-list.test.ts`(新测试绿)
  - `cd frontend && npm run build`(0 类型错误)
  - `cd frontend && npm test`(65+ 现有全绿,零行为回归)
- **AC**:
  - [x] `buildWorkingList` 近纯函数抽出,签名 `(base: Message[], userText: string, now?: () => number) => Message[]`,`now` 默认 `Date.now`
  - [x] handleSend 改调近纯函数,逻辑等价(working-list 计算不变)
  - [x] 5 边界 case 单测全绿(用 fake timers)
  - [x] build 0 类型错误 + 现有 65 测试零回归
  - [x] **chat-page.tsx 仍在旧位置**(未 git mv,App.tsx 未改)

  **完成证据(Ticket 1,2026-07-30 Session 165 非末切片)**:`build-working-list.ts` 抽出 `(base, userText, now?=Date.now) => Message[]`,base 浅拷贝 `.map((m)=>({...m}))` + user/assistant 两条占位(`local-user-`/`local-assistant-` 前缀 + `created_at` 走 `now()`)。handleSend 改调 `buildWorkingList(localMessages ?? history ?? [], text)` + `const assistantMsg = working[working.length - 1]` 保留流式就地 mutate 引用。`build-working-list.test.ts` 5 边界用例(空 base / 非空 base 追加 / now 注入钉死时间 / 浅拷贝非别名 / 默认 Date.now 回退),`vi.useFakeTimers()`+`vi.setSystemTime`。**验证**:`vitest run` 5/5 绿 + `tsc -b` 0 错 + `npm run build` 绿(1.96s)+ `npm test` **70/70 全绿**(65 基线 + 5 新,零行为回归)+ `oxlint` 0/0。chat-page.tsx 仍 `pages/`(未 git mv),App.tsx 未改。**/code-review 双轴**(general-purpose ×2 并行):Standards 0 硬违规 / 1 已修(`build-working-list.ts` header 注释「读两次」不准 → 改为描述各读两次+默认跨 tick语义);2 判断项留痕(① `now` 参数 test-only Speculative Generality —— 明确由 plan「近纯函数注入时钟」决策正当化保留;② `working[len-1]` positional 耦合 —— 已注释,Ticket 2/3 若追加 trailer 可评估改双返回值)/ Spec 5 AC 全满足 0 缺失 0 误 0 偏差。**非末切片**(Ticket 2/3 待做),不动 feature_list.json status。

### Ticket 2: 抽 ConversationListPanel 组件 + 单测(migrate,**不 git mv**) ✅

- **What to build**:把列表 JSX + 右键菜单 + rename/add-tag 两个 Dialog + 相关处理器(handleDeleteConversation/toggleSelect/handleBatchDelete/openRename/submitRename/openAddTag/submitAddTag/handleRemoveTag/handleTogglePin/handleToggleStar)+ 4 个 dialog state + selectedIds + searchInput + searchCommitted + debounce effect + 清空 effect + `conversationLabel` helper 全部移到 `chat/conversation-list-panel.tsx`。**Panel 自调 `@/hooks/queries` 的 conversation 管理 hooks(D2 范式)**,父层只通过 `onSelectConversation(id)` / `onStartNew()` 两个回调接收用户选择。配套 `conversation-list-panel.test.tsx` 对齐 store-view.test 范式。此切片**行为零变化**(纯搬迁 + Panel 自调 hooks 接线)。
- **Blocked by**: Ticket 1(共享 chat/ 文件夹已建)
- **文件清单**(3):
  - 新建 `frontend/src/pages/chat/conversation-list-panel.tsx`
  - 新建 `frontend/src/pages/chat/__tests__/conversation-list-panel.test.tsx`
  - 改 `frontend/src/pages/chat-page.tsx`(ChatPage 瘦身,渲染 `<ConversationListPanel onSelectConversation={...} onStartNew={...} />`)
- **验证命令**:
  - `cd frontend && npx vitest run src/pages/chat/__tests__/`(两测试绿)
  - `cd frontend && npm run build`(0 类型错误)
  - `cd frontend && npm test`(65+ 全绿,零行为回归)
  - `cd frontend && npx oxlint .`(0 warning)
- **AC**:
  - [x] ConversationListPanel 组件抽出,**自调 hooks、零 data/handler props**(仅 2 个向上回调)
  - [x] selectedIds + searchInput + searchCommitted + 相关 effect 全部下沉 Panel 内部
  - [x] ChatPage 瘦到 ~600 行(只剩 streaming 半边 + 编排)
  - [x] conversation-list-panel.test.tsx 覆盖渲染 + 删除 mutateAsync 被调 + Dialog 弹出
  - [x] build 0 类型错误 + 全测试零回归 + oxlint 0 warning
  - [x] **chat-page.tsx 仍在旧位置**(未 git mv,App.tsx 未改)

  **完成证据(Ticket 2,2026-07-30 Session 165 非末切片)**:从 chat-page.tsx 抽出列表半边(列表 JSX + 右键菜单 + rename/add-tag 2 Dialog + 10 handler + selectedIds/searchInput/searchCommitted/2 effect + conversationLabel helper + customerNameOf 本地副本)到 `chat/conversation-list-panel.tsx`。Panel 自调 9 个会话管理 hook(useConversations/useDeleteConversation/useRenameConversation/useAddConversationTag/useRemoveConversationTag/useSetConversationPinned/useSetConversationStarred/useBatchDeleteConversations/useCustomerProfiles),零 data/mutation 下传。**双栏特化偏离(经 Spec 轴判可接受)**:chat-page 是「列表+详情」双栏、streaming 半边在父层,故 Panel 接收 2 向下只读 UI 状态(`streaming`+`activeConversationId`)+ 2 向上回调(`onSelectConversation`/`onStartNew`)+ `initialSearch`(?search= 深链播种,保「零行为变更」)。AC「仅 2 向上回调」字面被这 3 向下 prop 突破,但 Panel 仍自取 conversations、自调所有 mutation,D2「列表生命周期自含」精神未破。**code-review 双轴(Standards+Spec 并行 sub-agent)共识发现 1 处行为回归并修正**:原 `selectConversation` 的 `if(streaming) return` JS 守卫下移 Panel 后,行 `<button>` 漏 `disabled={streaming}`(原靠 JS 守卫非 disabled)→ streaming 中点会话行会中途切换(违 §4.5「零行为变更」)。修正:行 button 补 `disabled={streaming}`(与 DropdownMenuTrigger/新建按钮守卫一致)+ 补 1 回归用例锁住 + 修掉 chat-page 错误注释。测试 `conversation-list-panel.test.tsx` 11 用例(vi.hoisted mock 9 hook + renderWithProviders + user-event@14):列表渲染 + 徽章 + 空状态(无词/有词)+ 点击选择 + 删除 mutateAsync + 删除当前会话触发 onStartNew + rename/add-tag Dialog 弹出 + streaming 时 trigger/行 button disabled。**验证**:`vitest run` 11/11 绿 + `tsc -b` 0 错 + `npm run build` 绿(1.48s)+ `npm test` **81/81 全绿**(70 基线 + 11 新,零回归)+ `oxlint` 0/0。chat-page.tsx 1032→582 行(<650 AC),仍 `pages/`(未 git mv),App.tsx 未改。**非末切片**(Ticket 3 待做),不动 feature_list.json status。

### Ticket 3: 收尾验证(git mv + router barrel + customer-helpers + 全量验证)

- **What to build**:**git mv `pages/chat-page.tsx` → `pages/chat/chat-page.tsx`**;新建 `chat/index.tsx`(路由入口,export ChatPage)+ 把 `chat-page.tsx` 改成 barrel re-export(对齐 bookings/devices 双 entry);改 `App.tsx` import 路径 `@/pages/chat-page` → `@/pages/chat/chat-page`;抽 `customerNameOf` 到 `chat/customer-helpers.ts`(参数化 `(cid, profiles) => name`),两边改调;feature 收尾。
- **Blocked by**: Ticket 1 + Ticket 2
- **文件清单**(4-5):
  - git mv `frontend/src/pages/chat-page.tsx` → `frontend/src/pages/chat/chat-page.tsx`(整体移动保留 blame)
  - 新建 `frontend/src/pages/chat/index.tsx`(路由入口 export ChatPage)+ 改 `chat/chat-page.tsx` 为 barrel
  - 改 `frontend/src/App.tsx`(import 路径)
  - 新建 `frontend/src/pages/chat/customer-helpers.ts`
  - 改 `chat/chat-page.tsx` + `chat/conversation-list-panel.tsx`(改调共享 helper)
- **验证命令**:
  - `cd frontend && npm run build && npm test && npx oxlint .`(全绿)
  - `grep -rn "from.*chat-page" frontend/src/ | grep -v "pages/chat/"`(确认无残留旧路径 import)
  - `./init.sh full`(全量后端 + 前端,确认零回归)
- **AC**:
  - [ ] git mv 完成,chat-page.tsx 在 chat/ 下
  - [ ] 双 entry 就位(chat-page.tsx barrel + index.tsx 路由)
  - [ ] App.tsx import 指向 chat/chat-page
  - [ ] customerNameOf 共享 helper 抽出(参数化),两边改调
  - [ ] 无残留旧路径 import(grep 归 0)
  - [ ] npm run build + npm test + oxlint 全绿
  - [ ] ./init.sh full 全量绿(840 passed + 前端全绿)
  - [ ] feature 收尾:feature_list.json status → passing + evidence + sync-active + progress.md 更新
  - [ ] 文档影响评估执行

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:
- 改动文件 6 新建 + 2 改 = 8(< 10)✓ 不触发
- 涉及鉴权/权限/数据迁移/跨服务? **NO** ✓ 不触发
- 涉及安全敏感操作(token/密钥/支付)? **NO** ✓ 不触发
- 涉及不可逆操作(删表/删列/改列类型)? **NO** ✓ 不触发

**结论**:**不触发对抗式审查**(纯前端结构重构,改动 < 10 文件,零鉴权零数据迁移)。走单模型 `/code-review` 双轴(Standards + Spec)即可。

---

## 8. Out of Scope(对齐 to-spec)

- ❌ **不抽 chat panel(右半边 streaming)**:agent picker / message stream / input / CompositeMode 渲染原样留 ChatPage(D6 决策,streaming 紧耦合,抽 panel 收益递减)
- ❌ **不抽 useStreamChat hook**:streaming 状态机不抽成 hook(D1 排除的过度方案,引入 SSE/AbortController mock 面复杂)
- ❌ **不引入 useMemo/useCallback**:本次只做结构拆分,不做性能优化(巡检的「grep=0」是诊断不是要求)
- ❌ **不改 conversation/agent/customer 的任何后端逻辑或 API**:纯前端
- ❌ **不改 bookings/ 范式**:只对齐,不动 bookings 现有结构
- ❌ **不碰候选② devices-page 拆分**:那是独立 feature,本轮 Phase 1 只规划 chat-page
- ❌ **不碰候选④ composite_chat billing seam**:已决定暂缓,留后续候选

---

## 9. 风险与缓解(v2 补遗漏高危项)

| 风险 | 严重度 | 缓解 |
|---|---|---|
| ~~selectedIds 下沉与 conversations 留父层冲突~~(v2 已解决) | ~~高~~ → 已消除 | §4.5 修正:Panel 自调 useConversations(D2),conversations + selectedIds + effect 全部下沉 Panel,无跨层(v1 的「留父层」已废弃) |
| **buildWorkingList 非纯(Date.now/new Date)**(v2 新增) | 中 | 签名加 `now?: () => number = Date.now` 参数;测试用 `vi.useFakeTimers()` 固定时钟 |
| Dialog portal 在测试里异步挂载,断言时序错 | 中 | 对齐 store-view.test 范式:`await findByText` + user-event@14(已验证的 DropdownMenu 测试模式) |
| git mv 后 blame 历史丢失 | 低 | Ticket 3 整体 git mv(非拆分移动),保留 blame(bookings-page-split 已验证) |
| handleSend 改调近纯函数引入行为偏差(working-list 计算等价性) | 中 | Ticket 1 单测覆盖 5 边界 case(含 fake timers)+ 现有 65 测试零回归保护 |
| Panel 自调 hooks 后,mock 面变大(~10 hook)| 中 | 对齐 store-view.test 范式(它 mock 10 hook 已验证可行);测试用 `vi.hoisted` + 工厂 stub |
| **范式描述错误导致实施方向偏**(v1 已修正) | ~~高~~ → 已消除 | v2 §2/§4.0 D2 已纠正为「Panel 自调 hooks、零 props」(对齐 store-view 真实范式) |
| composite 消息字段(fragments/status/error)在 working-list 的处理 | 低 | userMsg/assistantMsg 不带这些可选字段是当前行为(对象字面量只填 id/role/content/created_at),保持不变;测试不做严格 deep-equal |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `cd frontend && npm run build` —— 0 类型错误
2. `cd frontend && npm test` —— 全绿(65 现有 + ~8 新增 = ~73+),零行为回归
3. `cd frontend && npx oxlint .` —— 0 warning 0 error
4. `grep -rn "from.*pages/chat-page['\"]" frontend/src/ | grep -v "pages/chat/"` —— 归 0(无残留旧路径 import)
5. `wc -l frontend/src/pages/chat/chat-page.tsx` —— < 650 行(streaming 半边)
6. `grep -c 'useMemo\|useCallback' frontend/src/pages/chat/chat-page.tsx` —— 仍为 0(不引入,确认未顺手加)
7. `./init.sh full` —— 后端 840 passed + 前端全绿,零回归
8. chat/ 文件夹结构对称于 bookings/(chat-page + conversation-list-panel + build-working-list + customer-helpers + __tests__)

---

## 11. 不越界声明

本次改动**只**涉及 `frontend/src/pages/chat-page.tsx` 的结构拆分(拆成 chat/ 文件夹下的 Panel + 纯函数 + helper + 测试)+ `App.tsx` 一行 import 路径;

**不**触碰:
- 后端任何文件(app/ 零改动)
- 数据库 / schema / migration
- bookings/ 现有结构(只对齐范式,不改)
- chat panel 右半边 streaming 逻辑(原样留 ChatPage)
- 任何 API 端点 / 类型定义(`api/types.ts` / `api/endpoints.ts` / `hooks/queries.ts` 零改动)
- 候选② devices-page / 候选④ composite_chat(独立 feature,本轮不碰)
