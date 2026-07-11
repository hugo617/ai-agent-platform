# 计划:聊天页 Markdown 渲染 + 核心交互(复制/停止/重新生成)

> 对应 feature_list.json 的 `id`: `chat-markdown-rendering`
> 状态: not_started
> 优先级: 26
> 前置: `chat-frontend` ✅(聊天页已就绪,本任务把"纯文本原型"升级为"可用的 AI 对话体验")

---

## 背景:为什么需要这个任务

聊天页是 AI 产品的核心使用界面,但当前实现是"纯文本原型级"——助手回复的标题、列表、表格、代码块全部原样显示为纯文本,无法解析 Markdown。这是 AI 产品最直观的体验短板:用户问"写一段 Python 代码",收到的回复里 ` ```python ` 标记原样显示,代码没有高亮、没有复制按钮。

同时,几个"任何 ChatGPT-like 产品都有的基础交互"缺失:`abortRef` 声明了却没有停止按钮、没有复制、没有重新生成。

### 问题根因(代码佐证)

- **纯文本渲染**:`frontend/src/pages/chat-page.tsx:318` 用 `whitespace-pre-wrap` + `{msg.content}` 直接输出文本,**无 Markdown 解析**。助手回复的 `**加粗**`、`- 列表`、` ```code``` ` 全部原样显示。
- **无 Markdown 依赖**:`frontend/package.json` 无 `react-markdown` / `remark-gfm` / `rehype-highlight` / `shiki`,grep 全仓零引用。
- **停止按钮缺失**:`chat-page.tsx:72` 声明了 `abortRef = useRef<AbortController>()`,`chat-page.tsx:155` 创建了 controller,但**界面上没有任何按钮调用 `controller.abort()`**。用户无法中途停止生成。发送按钮在 streaming 时只是 `disabled`(L348)。
- **无复制按钮**:grep `clipboard|navigator.clipboard` 全仓零命中。
- **无重新生成**:删除最后一条 assistant 消息重新发送的逻辑不存在。

### 后果

1. **AI 回复可读性极差**:代码/表格/列表原样显示,产品看起来不专业
2. **无法中途停止**:LLM 长输出时用户只能等完,无法 abort
3. **无基础交互**:复制代码、重新生成是 ChatGPT-like 产品的标配,缺失显得半成品

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| Markdown 渲染 | ❌ 纯文本 `whitespace-pre-wrap` | `chat-page.tsx:318` |
| 代码高亮 | ❌ 无 | — |
| 停止生成按钮 | ❌ abortRef 存在但未接 UI | `chat-page.tsx:72,155` |
| 复制消息/代码块 | ❌ 无 | grep clipboard 零命中 |
| 重新生成 | ❌ 无 | — |
| Markdown 依赖 | ❌ 无 | `package.json` 无 react-markdown |

---

## 目标

1. **Markdown 渲染**:助手回复支持解析 GFM Markdown(标题/列表/表格/链接/代码块/行内代码),用户消息保持纯文本
2. **代码高亮**:代码块语法高亮(常见语言)
3. **停止生成按钮**:streaming 时发送按钮变为"停止"按钮,点击调用 `controller.abort()`
4. **复制按钮**:每条 assistant 消息 + 每个代码块支持一键复制
5. **重新生成**:删除最后一条 assistant 回复,基于其对应的 user 消息重新发起对话

### 已确认的决策(与用户对齐)

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Markdown 库 | **react-markdown + remark-gfm + rehype-highlight** | 生态最成熟;remark-gfm 支持表格/任务列表;rehype-highlight 用 highlight.js(轻量,无需 shiki 的 WASM) |
| 代码高亮 | **rehype-highlight**(highlight.js) | 比 shiki 轻(highlight.js ~30KB vs shiki 需按语言加载 WASM);样式用现成 `highlight.js` CSS theme |
| 用户消息渲染 | **保持纯文本**(`whitespace-pre-wrap`) | 用户输入不解析 Markdown(避免注入风险 + 用户消息通常是自然语言) |
| 流式渲染 | **边流边渲染 Markdown** | 不等流结束才解析;react-markdown 支持增量更新(每个 delta 拼接后重新渲染,性能可接受) |
| 重新生成 | **本地重发**(删本地 assistant + 用原 user 消息重发) | 不改后端;后端会存新的 assistant 回复(老的留在库里有冗余,可接受,见边界) |

---

## 前置条件

- `chat-frontend` ✅(聊天页 SSE 流式已就绪)
- `real-chat-llm-config` ✅(真实对话已跑通)

---

## 实施步骤

### 第一阶段:依赖 + Markdown 渲染组件

#### Step 1:安装前端依赖

```bash
cd frontend
npm install react-markdown remark-gfm rehype-highlight highlight.js
```

- `react-markdown`:Markdown → React 渲染
- `remark-gfm`:GFM 扩展(表格/任务列表/删除线/自动链接)
- `rehype-highlight`:代码块语法高亮(基于 highlight.js)
- `highlight.js`:highlight.js 核心(含 CSS theme)

#### Step 2:新建 `frontend/src/components/chat/markdown-view.tsx`

- **props**:`{ content: string }`
- **实现**:
  ```tsx
  import ReactMarkdown from "react-markdown";
  import remarkGfm from "remark-gfm";
  import rehypeHighlight from "rehype-highlight";
  // 导入 highlight.js 的 CSS theme(dark 主题适配 .dark class)
  import "highlight.js/styles/github.css";
  
  export function MarkdownView({ content }: { content: string }) {
    return (
      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
          {content}
        </ReactMarkdown>
      </div>
    );
  }
  ```
- **自定义 components(可选增强)**:覆盖 `code` 组件,给代码块加"复制"按钮(见 Step 4)

#### Step 3:chat-page.tsx 集成 MarkdownView

- **改什么**(`chat-page.tsx:309-329` 的消息渲染段):
  - **user 消息**:保持 `{msg.content}` + `whitespace-pre-wrap`(纯文本)
  - **assistant 消息**:替换为 `<MarkdownView content={msg.content} />`
  - 流式中(content 还在增长):同样用 MarkdownView,react-markdown 会增量渲染
- **样式调整**:assistant 消息气泡去掉 `whitespace-pre-wrap`(Markdown 接管排版),保留圆角/背景;加 `overflow-x-auto` 防代码块溢出

---

### 第二阶段:核心交互

#### Step 4:停止生成按钮

- **改什么**(`chat-page.tsx` 发送按钮区,L346-354):
  - streaming 时,发送按钮 `<Send>` 替换为"停止"按钮(`<Square icon>`,lucide-react 的 `Square`)
  - 点击停止按钮:`abortRef.current?.abort()` → `finally` 块已处理 `setStreaming(false)` + invalidate
  - **abort 后的 assistant 消息处理**:保留已生成的部分内容(本地 `assistantMsg.content` 已有部分 delta),但**不落库**(后端 event_source 的 generator 被 abort 后,append_message 不会执行)——可接受,或在 Step 中加"abort 时把部分内容落库"(可选,见边界)
- **效果**:用户可中途停止 LLM 生成

#### Step 5:复制消息按钮

- **改什么**(assistant 消息气泡,加 hover 显示的操作栏):
  - assistant 消息悬停时显示 `Copy` 图标按钮(lucide-react `Copy` / `Check`)
  - 点击:`navigator.clipboard.writeText(msg.content)` → 图标变 `Check` 2 秒后恢复
  - **代码块复制**(可选增强):在 MarkdownView 的 `components.code` 覆盖里,给 `<pre>` 加复制按钮(复制该代码块内容)

#### Step 6:重新生成

- **改什么**(assistant 消息操作栏,仅最后一条 assistant 可见):
  - 在最后一条 assistant 消息的操作栏加 `RotateCcw` 按钮
  - 点击逻辑:
    1. 找到该 assistant 消息对应的上一条 user 消息(`messages[messages.length - 2]` 若是 user)
    2. 从 `localMessages` 里移除最后一条 assistant(可选:连同 user 一起移除,或保留 user 重发)
    3. 用那条 user 消息的 content 重新调 `sendChatStream`
  - **简化版**(推荐):移除最后的 assistant placeholder,把对应的 user content 填回输入框,让用户手动再发(降低复杂度,避免后端重复存 user 消息)
  - **完整版**:自动重发(需处理后端会多存一条 user 消息的问题,见边界)

---

### 第三阶段:验证

#### Step 7:前端构建 + lint

- `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)
- `npx oxlint src/pages/chat-page.tsx src/components/chat/markdown-view.tsx` 0 warning

#### Step 8:手动浏览器验证(需前后端启动)

- 发一条消息让 assistant 回复含 Markdown(如"用 Python 写一个冒泡排序,并解释时间复杂度")
- 验证:代码块有语法高亮、列表/标题正确渲染、代码块/消息有复制按钮
- 验证:streaming 中途点停止,生成立即停止
- 验证:点重新生成,assistant 重新回复
- 证据截图/描述写入 evidence

---

## 验收标准

1. **Markdown 渲染**:assistant 回复的标题/列表/表格/代码块/行内代码正确渲染(非纯文本)
2. **代码高亮**:代码块按语言语法高亮
3. **停止生成**:streaming 时可点击停止,生成立即中断
4. **复制**:消息级 + 代码块级复制可用
5. **重新生成**:最后一条 assistant 可重新生成
6. `cd frontend && npm run build` 通过 + oxlint 0 warning
7. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| react-markdown 流式渲染性能(每个 delta 全量重解析) | 对话消息通常 < 2KB,delta 高频更新可能有轻微卡顿;可加 `useMemo` 或在 content 增长超过阈值时降频(本任务先不优化,实测后决定) |
| XSS 安全(assistant 回复含恶意 Markdown/HTML) | react-markdown 默认**不渲染原始 HTML**(不用 rehype-raw), `<script>` 标签会被转义为文本;链接加 `target="_blank" rel="noopener"` |
| highlight.js CSS 主题与暗色模式冲突 | 导入 `highlight.js/styles/github.css`(浅色)+ 在 `.dark` 下覆盖为 `github-dark`(或直接用 `github-dark-dimmed`);Tailwind 配 prose-dark |
| 新增依赖体积 | react-markdown ~20KB + remark-gfm ~15KB + rehype-highlight ~5KB + highlight.js ~30KB(仅常见语言);总 ~70KB gzip,可接受 |
| 重新生成导致后端重复存 user 消息 | 简化版(填回输入框手动发)规避此问题;完整版需后端支持"撤销最后一条"——本任务不做(见边界) |
| abort 后 assistant 部分内容未落库 | 可接受(行为与"对话出错"一致);后续 context-engineering 任务会处理"部分回复落库容错" |

### 不做的事(边界)

- **不做消息编辑/删除**:ChatGPT 的"编辑后重发"交互复杂(需后端消息级 CRUD),本任务不做
- **不做完整版重新生成**:不自动重发(避免后端重复存 user);简化版=填回输入框
- **不做文件上传/多模态**:Message.content 是纯文本,不支持图片/附件(需改 schema + 存储)
- **不做 LaTeX/数学公式渲染**(KaTeX):非通用需求,后续按需
- **不做 Mermaid 图表渲染**:同上
- **不改后端**:纯前端任务(后端的 Message/content 结构不变)
- **不做对话搜索/置顶/重命名**:那是会话管理增强,属另一任务

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 纯文本渲染根因 | `frontend/src/pages/chat-page.tsx:318` |
| abortRef 未接 UI | `frontend/src/pages/chat-page.tsx:72,155` |
| 发送按钮区(改停止按钮) | `frontend/src/pages/chat-page.tsx:346-354` |
| 消息渲染循环 | `frontend/src/pages/chat-page.tsx:309-329` |
| SSE 流式接收 | `frontend/src/api/endpoints.ts:404-454` `sendChatStream` |
| 现有 Card/Button 图标范式 | `frontend/src/components/ui/`(lucide-react 图标) |
| Tailwind 配置 | `frontend/tailwind.config.js`(确认 prose 插件 / darkMode) |
| 前端表单/交互范式 | `frontend/src/pages/agents-page.tsx`(Dialog + RHF + zod) |
| react-markdown 文档 | https://github.com/remarkjs/react-markdown |
| highlight.js 主题 | https://highlightjs.org/static/demo/ |
