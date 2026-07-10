# 计划:对话前端(聊天页面 + SSE 流式对接)

> 对应 feature_list.json 的 `id`: `chat-frontend`
> 状态: not_started
> 优先级: 13
> 前置: `chat-conversation-api` ✅ 已完成(后端 SSE + 会话历史 API 已落地)
> 参照模板: `agents-page.tsx`(数据驱动模式)

---

## 背景:前端零 chat 对接,后端已就绪

前端目前能**配置** Agent(`agents-page.tsx` 已接后端),但**完全不能对话**——没有 chat 页面、没有 SSE 对接、没有会话历史 UI。这是"AI 平台"之所以叫 AI 平台的核心体验缺口。

**后端已全部就绪**(前置任务 `chat-conversation-api` 已合入,见 `feature_list.json` evidence):

| 端点 | 方法 | 作用 | 响应 |
|------|------|------|------|
| `/api/v1/chat/stream` | POST | SSE 流式对话 | `text/event-stream` |
| `/api/v1/conversations/` | GET | 会话列表(按 updated_at desc) | `list[ConversationRead]` |
| `/api/v1/conversations/{id}/messages` | GET | 历史消息(按 created_at 升序) | `list[MessageRead]` |
| `/api/v1/conversations/{id}` | DELETE | 删除会话(硬删除) | 204 |

**SSE 帧格式**(来自 `app/api/v1/chat.py` 的 `event_source()`):
```
data: {"delta": "你"}\n\n        ← 逐字/逐块回复
data: {"delta": "好"}\n\n
...
data: {"error": "消息内容"}\n\n   ← 出错时
data: [DONE]\n\n                  ← 流结束
```

### 当前前端状态速查(2026-07-10 核实)

| 层 | 状态 | 详情 |
|----|------|------|
| 后端 chat/conversation 端点 | ✅ 就绪 | 4 个端点,见上表 |
| 前端 chat 页面 | ❌ 不存在 | `pages/` 下 7 个文件,无 chat |
| 前端 SSE 对接 | ❌ 不存在 | client.ts 全是 axios JSON 请求,无流式基建 |
| 前端 endpoints/hooks(chat) | ❌ 不存在 | endpoints.ts 无 conversation/chat 函数 |
| 前端路由 / 导航 | ❌ 无 `/chat` | NAV_ITEMS 5 项,无对话 |
| 前端类型 | ⚠️ 预留但不全 | `types.ts` 有 Conversation/Message,但 Conversation 缺 `updated_at` |

---

## 目标

用户能在聊天页面:选 Agent → 实时对话(打字机效果)→ 查看历史会话 → 删除会话。

---

## 前置条件

- `chat-conversation-api` ✅ 已完成(后端端点就绪)
- 后端 `.env` 配好 `OPENAI_API_KEY`(DeepSeek key,否则流式对话无真实回复;前端开发可先 build 通过再配 key 实测)

---

## 实施步骤

### 第一阶段:类型 + API 层(含 SSE 从零搭建)

#### Step 1:types.ts 补全 Conversation / Message 类型

- **改什么**(`frontend/src/api/types.ts`,现有 Conversation/Message 已预留,补字段):
  ```typescript
  export interface Conversation {
    id: string;
    agent_id: string;
    tenant_id: string;
    user_id: string;
    title: string | null;
    created_at: string;
    updated_at: string;   // ← 新增,对齐后端 ConversationRead(chatter-conversation-api 加的)
  }

  export interface Message {
    id: string;
    role: "user" | "assistant";   // ← 收紧为联合类型(后端只这两种)
    content: string;
    created_at: string;
  }
  ```
- **检查**:tsc 无错(对照后端 `app/schemas/conversation.py` 的 `ConversationRead` / `MessageRead`)

#### Step 2:endpoints.ts 加 conversation 端点 + SSE stream 函数

这是本任务的技术核心——**SSE 流式是前端全新能力,无现成基建**。

- **改什么**(`frontend/src/api/endpoints.ts`,照现有 `fetchXxx`/`createXxx`/`deleteXxx` 命名风格,用 `// ---------- xxx ----------` 注释分块):
  - 加三个普通端点(走现有 axios `api`):
    ```typescript
    export async function fetchConversations(): Promise<Conversation[]> {
      const { data } = await api.get<Conversation[]>("/conversations/");
      return data;
    }
    export async function fetchMessages(conversationId: string): Promise<Message[]> {
      const { data } = await api.get<Message[]>(`/conversations/${conversationId}/messages`);
      return data;
    }
    export async function deleteConversation(conversationId: string): Promise<void> {
      await api.delete(`/conversations/${conversationId}`);
    }
    ```
  - **加 `sendChatStream` 函数(SSE,不能用 axios)**:
    - **为什么不能用 axios**:`stream_agent` 是 `text/event-stream`,要逐帧读取。axios 会一次性 buffer 整个 body,失去流式效果。
    - **为什么不能用 EventSource**:EventSource 不支持自定义 header(Authorization),只能用原生 `fetch` + `ReadableStream`。
    - **实现**(async generator,用 `for await...of` 消费):
      ```typescript
      import { getStoredToken } from "@/api/client";

      export interface ChatStreamChunk {
        delta?: string;
        error?: string;
      }

      export async function* sendChatStream(payload: {
        agent_id: string;
        conversation_id?: string;
        message: string;
      }, signal?: AbortSignal): AsyncGenerator<ChatStreamChunk> {
        const token = getStoredToken();
        const resp = await fetch("/api/v1/chat/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(payload),
          signal,
        });

        if (!resp.ok) {
          // 401 → 复刻 client.ts 的 auth-expired 逻辑
          if (resp.status === 401) {
            clearStoredToken();
            window.dispatchEvent(new CustomEvent("aap:auth-expired"));
          }
          throw new Error(`对话请求失败: ${resp.status}`);
        }
        if (!resp.body) throw new Error("浏览器不支持流式响应");

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE 帧以 \n\n 分隔,最后一段可能不完整 → 留到下次
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith("data:")) continue;
            const data = line.slice(line.indexOf(":") + 1).trim();
            if (data === "[DONE]") return;  // 流结束
            try {
              yield JSON.parse(data) as ChatStreamChunk;  // { delta } 或 { error }
            } catch {
              // 非 JSON 帧,跳过
            }
          }
        }
      }
      ```
    - **注意**:`clearStoredToken` 需从 client.ts 导入(确认是否已导出,若无需在 client.ts 加导出——它内部已用于 401 处理)
- **检查**:tsc 无错;`sendChatStream` 是 async generator。

### 第二阶段:hooks 层

#### Step 3:queries.ts 加 conversation hooks

- **改什么**(`frontend/src/hooks/queries.ts`,照 `qk` 工厂 + `useQuery`/`useMutation` 模式):
  - 在 `qk` 对象加:
    ```typescript
    conversations: ["conversations"] as const,
    messages: (conversationId: string) => ["conversations", conversationId, "messages"] as const,
    ```
  - 加三个 hooks:
    ```typescript
    export function useConversations() {
      return useQuery({ queryKey: qk.conversations, queryFn: fetchConversations });
    }
    export function useMessages(conversationId: string | null) {
      return useQuery({
        queryKey: qk.messages(conversationId ?? ""),
        queryFn: () => fetchMessages(conversationId!),
        enabled: !!conversationId,
      });
    }
    export function useDeleteConversation() {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: deleteConversation,
        onSuccess: () => qc.invalidateQueries({ queryKey: qk.conversations }),
      });
    }
    ```
  - **注意**:`sendChatStream` **不走 TanStack Query**(流式增量回调,不适合 useMutation 的单次成功语义)——在页面组件内直接调用 + 本地 state 管理累积文本。
- **检查**:`npm run build` 通过。

### 第三阶段:聊天页面(核心)

#### Step 4:新建 chat-page.tsx

参照主流聊天 UI(左侧会话列表 + 右侧消息流 + 底部输入框)。**布局**:

```
┌─────────────┬──────────────────────────────┐
│ 会话列表    │ 消息流(overflow-y-auto 滚动)│
│             │  - user 消息(右对齐,主色)  │
│ [新建对话]  │  - assistant 消息(左对齐,灰)│
│ conv1(选中)│  - 流式中的临时消息(打字机) │
│ conv2       │                              │
│ ...         ├──────────────────────────────┤
│             │ 输入框 + 发送按钮             │
│             │ [选择 Agent ▾]                │
└─────────────┴──────────────────────────────┘
```

- **新建文件** `frontend/src/pages/chat-page.tsx`
- **UI 组件**(shadcn 风格自建,在 `src/components/ui/`):用 `Card` / `Button` / `Input` / `Select`;**无 scroll-area 组件**,消息滚动区用原生 `<div className="overflow-y-auto">`(与 agents-page 一致)
- **核心交互逻辑**:
  - **选 Agent**:顶部 `Select` 下拉,数据来自 `useAgents()`(已有 hook)
  - **发消息**:
    1. user 消息立即追加到本地消息数组(乐观更新)
    2. 创建一个空的 assistant 占位消息
    3. 调 `sendChatStream({ agent_id, conversation_id, message })`
    4. `for await (const chunk of sendChatStream(...))`:`chunk.delta` 追加到 assistant 消息(打字机效果);`chunk.error` → `toast.error` 并终止
    5. 流结束后:`qc.invalidateQueries(["conversations"])`(列表更新)+ 若是首条消息需拿到新会话 id(从 conversations 查询结果取)
  - **会话切换**:点左侧会话 → 设置 `selectedConversationId` → `useMessages(id)` 自动加载历史
  - **新建对话**:清空当前消息 + `selectedConversationId = null`(首次发送后端自动建会话)
  - **删除会话**:`confirm()` 确认 → `useDeleteConversation` → 列表刷新;若删的是当前会话,清空消息区
- **状态管理**(组件本地 state,不进 TanStack Query):
  - `selectedConversationId: string | null`
  - `selectedAgentId: string`
  - `messages: Message[]`(历史 + 本地追加,合并)
  - `streaming: boolean`(发送中禁用输入)
  - `streamingText: string`(流式累积的 assistant 文本)
- **自动滚底**:消息更新时 `scrollRef.current?.scrollTo(0, scrollHeight)`
- **loading/error 态**:会话列表/消息 `isLoading` 显示"加载中…";无会话显示空态
- **权限守卫**:chat 页对所有登录用户开放(member 有 `conversations:chat`)。路由在 `<ProtectedRoute>` 内但**不在** `<RequireUserManagement>` 内

#### Step 5:路由 + 导航注册

- **改 `frontend/src/App.tsx`**(在 `ProtectedRoute` 内、`RequireUserManagement` 外,与 `/agents` 同级):
  ```tsx
  <Route path="/" element={<DashboardPage />} />
  <Route path="/agents" element={<AgentsPage />} />
  <Route path="/chat" element={<ChatPage />} />   {/* 新增,不加 RequireUserManagement */}
  <Route element={<RequireUserManagement />}>
    <Route path="/users" ... />
  ```
- **改 `frontend/src/components/layout/dashboard-layout.tsx`**:
  - import 加 `MessageSquare`(从 `lucide-react`)
  - `NAV_ITEMS` 在 `/agents` 后加:
    ```typescript
    { to: "/chat", label: "对话", icon: MessageSquare },   // 不带 needsUserManagement
    ```
- **检查**:登录后侧边栏出现"对话"项(member 也可见),点击进入聊天页。

### 第四阶段:总验证

#### Step 6:前端构建 + 手动验证

- **命令**:
  ```bash
  cd frontend && npm run build   # tsc + vite 通过
  ```
- **手动验证**(前后端都启动 + `.env` 配好 DeepSeek key):
  - 进对话页 → 选 Agent → 发"你好" → 看到打字机效果流式回复
  - 回复完成后 → 左侧会话列表出现新会话
  - 切换到别的会话 → 看到历史消息
  - 删除会话 → 列表消失
  - member 登录 → 也能对话(有 `conversations:chat` 权限)
- **通过标准**:
  - `npm run build` 通过(tsc + vite,0 类型错误)
  - 手动全流程跑通(选 agent → 对话 → 历史 → 删除)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. 前端新增 chat 页面(`/chat` 路由 + 导航"对话"项,member 可见)
2. SSE 流式对接实现打字机效果(用 `fetch + ReadableStream`,非 EventSource/axios)
3. 会话列表 + 历史消息 + 删除会话全功能(对接后端 4 端点)
4. `cd frontend && npm run build` 通过(tsc + vite,0 类型错误)
5. (手动)真实 DeepSeek 下,选 agent → 对话 → 流式回复 → 历史保留 → 删除,全流程通

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| **SSE 是前端全新能力,无现成基建** | Step 2 从零写 `fetch + ReadableStream`;手动带 Authorization header(从 `getStoredToken()`);手动复刻 401 → `AUTH_EXPIRED_EVENT`(参考 client.ts 拦截器逻辑) |
| SSE 解析复杂(帧边界、半帧) | `sendChatStream` 用 buffer split 模式:`buffer.split("\n\n")` 后 `frames.pop()` 留最后一段(可能不完整)到下次;后端每帧 `\n\n` 结尾,`[DONE]` 结束符明确 |
| `fetch` 流式浏览器兼容性 | 所有现代浏览器支持 `ReadableStream`;Vite target 默认 esnext,无问题 |
| 打字机效果高频 setState 性能 | 每 chunk 直接 setState 追加文本即可(LLM token 频率约 10-50/秒,React 可承受);若卡顿再用 `requestAnimationFrame` 批量合并 |
| 流式中途断网/后端错 | 后端在 `data: {"error":"..."}` 中报错 → `sendChatStream` yield `{ error }` → 组件 `toast.error` 提示并保留已收到的部分 |
| 会话标题为空(首次对话) | 列表项 `title` 为空时,fallback 到"新对话"或首条消息前 20 字(前端处理) |
| `clearStoredToken` 是否已导出 | Step 2 前确认 client.ts 的导出;若未导出需加(它内部已用于 401 处理,大概率已 export 或可快速补) |
| 无 scroll-area 组件 | 用原生 `<div className="overflow-y-auto">`(与 agents-page 一致),不引入新组件 |

### 不做的事(边界)

- 不做 Markdown / 代码块渲染(第一版纯文本气泡;Markdown 渲染是后续增强)
- 不做消息编辑/重新生成
- 不做多 Agent 同时对话(一个会话绑一个 agent)
- 不做文件上传/图片(纯文本对话)
- 不做语音输入

---

## 参考文件(实施时对照)

| 参照 | 路径 | 看什么 |
|------|------|--------|
| 数据驱动页面模板 | `frontend/src/pages/agents-page.tsx` | 布局/Dialog/loading 态/toast/confirm 模式 |
| API client(token + 拦截器 + 错误) | `frontend/src/api/client.ts` | `getStoredToken`、401 处理、`apiErrorMessage`、`clearStoredToken` 导出情况 |
| 现有 hooks 模式 | `frontend/src/hooks/queries.ts` | `qk` 工厂、`useQuery`/`useMutation` 写法、`invalidateQueries` |
| 现有 endpoints 模式 | `frontend/src/api/endpoints.ts` | `fetchXxx` 命名、axios 调用、注释分块风格 |
| 路由结构 | `frontend/src/App.tsx` | `ProtectedRoute` / `RequireUserManagement` 布局路由嵌套 |
| 导航项 | `frontend/src/components/layout/dashboard-layout.tsx` | `NAV_ITEMS` / `NavItem` 接口 / `canManageUsers` 过滤 |
| UI 组件库 | `frontend/src/components/ui/*` | button/card/input/select/dialog(无 scroll-area) |
| 后端 SSE 帧格式 | `app/api/v1/chat.py` `event_source()` | `data: {delta}\n\n` + `data: [DONE]\n\n` + `data: {error}\n\n` |
| 后端 conversation schema | `app/schemas/conversation.py` | `ConversationRead`(含 updated_at) / `MessageRead` / `ChatRequest` |
| 前端新增模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` | (如需补充上下文) |
