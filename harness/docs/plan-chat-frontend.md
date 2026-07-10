# 计划:对话前端(聊天页面 + SSE 流式对接)

> 对应 feature_list.json 的 `id`: `chat-frontend`
> 状态: not_started
> 优先级: 13
> 前置: `chat-conversation-api`(会话历史端点就绪)
> 参照模板: `agents-page.tsx`(数据驱动模式)

---

## 背景:当前前端零 chat 对接

前端目前能**配置** Agent(`agents-page.tsx` 已接后端),但**完全不能对话**——没有 chat 页面、没有 SSE 对接、没有会话历史 UI。这是"AI 平台"之所以叫 AI 平台的核心体验缺口。

后端已就绪(前置任务 `chat-conversation-api` 完成后):
- `POST /api/v1/chat/stream` —— SSE 流式对话
- `GET /api/v1/conversations/` —— 会话列表
- `GET /api/v1/conversations/{id}/messages` —— 历史消息
- `DELETE /api/v1/conversations/{id}` —— 删除会话

### 当前状态速查

| 层 | 状态 |
|----|------|
| 后端 chat/conversation 端点 | ✅ 前置任务完成后就绪 |
| 前端 chat 页面 | ❌ 不存在 |
| 前端 SSE 对接 | ❌ 不存在 |
| 前端 endpoints/hooks(chat) | ❌ 不存在 |
| 前端路由 / 导航 | ❌ 无 `/chat` 路由,NAV_ITEMS 无聊天项 |
| 前端 conversation/agent 类型 | ⚠️ Agent 类型有,Conversation/Message 无 |

---

## 目标

用户能在聊天页面:选 Agent → 实时对话(打字机效果)→ 查看历史会话 → 删除会话。

---

## 前置条件

- `chat-conversation-api` 完成(后端端点就绪)
- 后端 `.env` 配好 DeepSeek key(否则流式对话无真实回复;前端开发可用 mock)

---

## 实施步骤

### 第一阶段:类型 + API 层

#### Step 1:types.ts 加 Conversation / Message 类型

- **改什么**(`frontend/src/api/types.ts`):
  ```typescript
  export interface Conversation {
    id: string;
    agent_id: string;
    tenant_id: string;
    user_id: string;
    title: string | null;
    created_at: string;
    updated_at?: string;
  }
  export interface Message {
    id: string;
    role: "user" | "assistant";
    content: string;
    created_at: string;
  }
  ```
- **检查**:tsc 无错(对照后端 `app/schemas/conversation.py` 字段)

#### Step 2:endpoints.ts 加 conversation 端点 + SSE stream 函数

- **改什么**(`frontend/src/api/endpoints.ts`):
  - 加 `fetchConversations(): Promise<Conversation[]>` → GET /conversations/
  - 加 `fetchMessages(convId): Promise<Message[]>` → GET /conversations/{id}/messages
  - 加 `deleteConversation(convId): Promise<void>` → DELETE /conversations/{id}
  - **加 `streamChat` 函数(SSE,不能用 axios)**:
    ```typescript
    // SSE 流式:用原生 fetch + ReadableStream(因为要带 Authorization header,
    // EventSource 不支持自定义 header)
    export async function* streamChat(payload: {
      agent_id: string;
      conversation_id?: string;
      message: string;
    }): AsyncGenerator<{ delta?: string; error?: string; done?: boolean }> {
      const token = getStoredToken();
      const resp = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });
      if (!resp.ok || !resp.body) throw new Error(`chat failed: ${resp.status}`);
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // SSE 帧以 \n\n 分隔,每帧形如 "data: {...}\n\n"
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? ""; // 最后一段可能不完整,留到下次
        for (const frame of frames) {
          const line = frame.trim();
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") { yield { done: true }; return; }
          yield JSON.parse(data); // { delta: "..." } 或 { error: "..." }
        }
      }
    }
    ```
- **检查**:tsc 无错。注意 `streamChat` 是 async generator(用 `for await...of` 消费)。

### 第二阶段:hooks 层

#### Step 3:queries.ts 加 conversation hooks

- **改什么**(`frontend/src/hooks/queries.ts`):
  - `useConversations()` —— TanStack Query,GET 会话列表(key: `["conversations"]`)
  - `useMessages(convId)` —— GET 历史消息(enabled: !!convId,key: `["messages", convId]`)
  - `useDeleteConversation()` —— mutation,成功后 invalidate `["conversations"]`
  - **注意**:`streamChat` 不走 TanStack Query(它是流式的,不是一次性请求),在页面组件里直接调用 + 本地 state 管理
- **检查**:`npm run build` 通过

### 第三阶段:聊天页面

#### Step 4:新建 chat-page.tsx

这是本任务核心。参照主流聊天 UI(左侧会话列表 + 右侧消息流 + 底部输入框)。

- **新建文件** `frontend/src/pages/chat-page.tsx`,结构:
  ```
  ┌─────────────┬──────────────────────────────┐
  │ 会话列表    │ 消息流(滚动区域)            │
  │             │  - user 消息(右对齐,蓝底)   │
  │ [新建对话]  │  - assistant 消息(左对齐,灰) │
  │ conv1(选中)│  - 流式中的临时消息(打字机)  │
  │ conv2       │                              │
  │ ...         ├──────────────────────────────┤
  │             │ 输入框 + 发送按钮             │
  │             │ [选择 Agent ▾]                │
  └─────────────┴──────────────────────────────┘
  ```
- **核心交互逻辑**:
  - **选 Agent**:顶部下拉选 Agent(数据来自 `useAgents`,已有)
  - **发消息**:
    1. 把 user 消息立即追加到本地消息列表(乐观更新)
    2. 调 `streamChat({ agent_id, conversation_id, message })`
    3. `for await (const chunk of streamChat(...))` 逐字追加到 assistant 消息(打字机效果)
    4. 流结束后 `invalidate ["conversations"]`(会话列表更新)+ `["messages", convId]`
    5. 处理 `{ error }` chunk → toast 报错;`{ done }` → 结束
  - **会话切换**:点左侧会话 → `useMessages(convId)` 加载历史
  - **新建对话**:清空当前消息 + conversation_id 置 null(首次发送时后端自动建会话)
  - **删除会话**:点删除 → 确认 → `useDeleteConversation` → 列表刷新
- **UI 组件**(复用现有 ui 库):
  - 用 `Card` / `ScrollArea`(若有)/ 原生 div + overflow-auto
  - 消息气泡:user 右对齐 `bg-primary text-primary-foreground`,assistant 左对齐 `bg-muted`
  - 输入框:`Input` + `Button`,Enter 发送 / Shift+Enter 换行
  - loading 态:发送中禁用输入框 + 按钮,assistant 气泡显示光标动画
- **权限守卫**:chat 页对所有登录用户开放(member 有 `conversations:chat`)。路由放在 `<ProtectedRoute>` 内但不在 `<RequireUserManagement>` 内。

#### Step 5:路由 + 导航注册

- **改什么**(`frontend/src/App.tsx` L43-44 区域):
  ```tsx
  <Route path="/" element={<DashboardPage />} />
  <Route path="/agents" element={<AgentsPage />} />
  <Route path="/chat" element={<ChatPage />} />   {/* 新增 */}
  ```
- **改什么**(`frontend/src/components/layout/dashboard-layout.tsx` NAV_ITEMS L30 后):
  ```typescript
  { to: "/agents", label: "智能体", icon: Bot },
  { to: "/chat", label: "对话", icon: MessageSquare },  // 新增,从 lucide-react 导入
  { to: "/users", ... },
  ```
- **检查**:登录后侧边栏出现"对话"项,点击进入聊天页。

### 第四阶段:总验证

#### Step 6:前端构建 + 手动验证

- **命令**:
  ```bash
  cd frontend && npm run build   # tsc + vite 通过
  ```
- **手动验证**(前后端都启动,DeepSeek key 配好):
  - 进对话页 → 选 Agent → 发"你好" → 看到打字机效果流式回复
  - 回复完成后 → 左侧会话列表出现新会话
  - 切换到别的会话 → 看到历史消息
  - 删除会话 → 列表消失
  - member 登录 → 也能对话(有 `conversations:chat` 权限)
- **通过标准**:
  - `npm run build` 通过
  - 手动全流程跑通(选 agent → 对话 → 历史 → 删除)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. 前端新增 chat 页面(`/chat` 路由 + 导航"对话"项)
2. SSE 流式对接实现打字机效果(用 `fetch + ReadableStream`,非 EventSource)
3. 会话列表 + 历史消息 + 删除会话全功能
4. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)
5. (手动)真实 DeepSeek 下,选 agent → 对话 → 流式回复 → 历史保留 → 删除,全流程通

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| SSE 解析复杂(帧边界、断连) | Step 2 的 `streamChat` 用 buffer split 模式处理半帧;后端每帧 `\n\n` 结尾,`[DONE]` 结束符明确 |
| `fetch` 流式在浏览器兼容性 | 所有现代浏览器支持 `ReadableStream`;Vite target 默认 esnext,无问题 |
| 打字机效果性能(高频 setState) | 用 `requestAnimationFrame` 节流,或批量追加(每 50ms 合并一次 delta) |
| 流式中途断网/后端错 | `streamChat` yield `{ error }` 时 toast 提示并保留已收到的部分;`for await` 正常结束 |
| 会话标题为空(首次对话) | 列表项 title 为空时,fallback 到"新对话"或首条消息前 20 字(前端处理) |
| token 在 localStorage | `streamChat` 用 `getStoredToken()` 读 token,与 axios 拦截器一致 |

### 不做的事(边界)

- 不做 Markdown / 代码块渲染(第一版纯文本气泡;Markdown 渲染是后续增强)
- 不做消息编辑/重新生成
- 不做多 Agent 同时对话(一个会话绑一个 agent)
- 不做文件上传/图片(纯文本对话)
- 不做语音输入

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| 数据驱动页面模板 | `frontend/src/pages/agents-page.tsx` |
| API client(token + 拦截器) | `frontend/src/api/client.ts` |
| 现有 hooks 模式 | `frontend/src/hooks/queries.ts`(`useAgents` 等) |
| 路由结构 | `frontend/src/App.tsx` |
| 导航项 | `frontend/src/components/layout/dashboard-layout.tsx` `NAV_ITEMS` |
| UI 组件库 | `frontend/src/components/ui/*`(button/card/input/dialog/table) |
| 后端 SSE 帧格式 | `app/api/v1/chat.py` `event_source()`(`data: {delta}\n\n` + `data: [DONE]\n\n`) |
| 后端 conversation schema | `app/schemas/conversation.py` |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
