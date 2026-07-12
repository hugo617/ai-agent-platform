# 计划:聊天页溢出修复 + 会话标题生成(chat-overflow-title-fix)

> 对应 feature_list.json 的 `id`: `chat-overflow-title-fix`
> 状态: passing ✅
> 优先级: 36(MVP 之后,新发现 bug 修复)
> 前置: `chat-markdown-rendering` ✅ 已完成

---

## 背景:用户反馈的 bug

用户访问 `http://localhost:3001/chat`,反馈两个问题:
1. **会话列表不显示会话标题** —— 新会话栏全是"新对话",看不出哪条是哪条
2. **消息过多时溢出会话框** —— 内容溢出,横向/纵向撑破

## 根因(代码佐证)

### Bug 1:会话标题永远是"新对话"

- **后端从不生成 title**:`conversation_service.create_or_get()`(`app/services/conversation_service.py`)创建会话时 `title=None`,默认参数;chat 端点(`app/api/v1/chat.py`)调用时也从不传 title → 所有会话 title 字段恒为 null
- **前端兜底逻辑失效**:`conversationLabel(conv, firstMessage?)`(`chat-page.tsx`)设计了"用首条 user 消息截前 20 字做摘要"的兜底,但**调用处 `conversationLabel(conv)` 只传了 conv,没传 firstMessage** → 兜底分支永远不触发 → 全部 fallback 到"新对话"

### Bug 2:溢出

- **会话列表 Card 不滚动**:`h-[calc(100vh-12rem)]` 固定高,但内部 `CardContent` 只加了 `overflow-y-auto` 没有受控 flex 高度(作为普通 div,没有 `flex-1 min-h-0`)→ **实际不滚动,会话多了撑破 Card**
- **user 消息长串横向溢出**:`whitespace-pre-wrap` 缺 `break-words`/`overflow-wrap:anywhere` → 长 URL/长 token 横向撑破气泡
- **assistant 气泡无 overflow 兜底**:`max-w-[85%]` 外层 div 无 `overflow-hidden`,宽表格/长行可能撑破

### 其它顺带发现

- 移动端:两个 Card 都 `h-[calc(100vh-12rem)]`,单列堆叠时双倍超高
- 删除按钮点击区偏小(无 `min-h`/`min-w`)
- 会话列表项缺次要信息(只有标题,无时间),可识别性差

## 目标

1. **会话标题**:首条 user 消息前 20 字存入 title(后端生成,前端信任后端 title)
2. **会话列表纵向可滚动**:不撑破 Card
3. **消息气泡宽内容自动断行**:不横向溢出
4. **移动端布局合理 + 交互区达标**

## 改动清单(已实施)

### 后端(2 文件)

**1. `app/services/conversation_service.py`** — `create_or_get` 新增 `first_message` 参数
- 新增可选参数 `first_message: str | None = None`
- 当新建会话(conversation_id 为 None)且 title 为 None 且 first_message 非空时:取首条消息 strip 后前 20 字,<20 字加 `…`,≥20 字原样
- 向后兼容:其它调用点(conversations API)不传 first_message 仍正常

**2. `app/api/v1/chat.py`** — `chat_stream` 调用时传 `first_message=payload.message`
- 1 行改动:新会话在创建瞬间用首条 user 消息生成 title
- 已存在会话(conversation_id 非空)走 get 分支,不受影响

### 前端(1 文件:chat-page.tsx)

**3. 会话列表纵向滚动修复**
- 列表 Card:`h-[calc(100vh-12rem)]` → `flex h-[70vh] flex-col lg:h-[calc(100vh-12rem)]`(加 flex flex-col + 移动端 70vh)
- CardContent:`overflow-y-auto p-2` → `min-h-0 flex-1 overflow-y-auto p-2`(`min-h-0` 是 flex 子项能收缩的关键)

**4. 右侧 chat 面板溢出修复**
- chat 面板 Card 高度同步改 `h-[70vh] lg:h-[calc(100vh-12rem)]`(移动端不双倍超高)
- user 气泡:`whitespace-pre-wrap break-words` → 加 `[overflow-wrap:anywhere]`(长无空格串可断)
- assistant 气泡:外层 `max-w-[85%]` 加 `overflow-hidden` 兜底

**5. 会话列表项增强**
- label button 改 flex-col:标题 + `created_at` 次要信息(11px muted),加 `min-h-[28px]` 保点击区
- 删除按钮加 `min-h-[28px] min-w-[28px]`,点击区达标

## 验证(已通过)

| 验证项 | 命令 | 结果 |
|--------|------|------|
| 后端 ruff | `.venv/bin/ruff check conversation_service.py chat.py` | All checks passed |
| 后端 chat 测试 | `pytest tests/test_chat.py -q` | **16 passed**(原 14 + 新增 2) |
| 新增 title 测试 | `pytest tests/test_chat.py -k title` | 2 passed(长消息截断 + 短消息原样) |
| 前端 build | `npm run build`(含 tsc 类型检查) | ✅ built in 3.90s |
| 前端 lint | `npm run lint`(oxlint) | Found 0 warnings and 0 errors |

新增测试:
- `test_conversation_title_derived_from_first_message`:验证长消息(>20 字)→ title = 前 20 字 + `…`
- `test_conversation_title_short_message_no_ellipsis`:验证短消息(<20 字)→ title 原样,无 `…`

## 决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 标题生成位置 | **后端**(create_or_get 内) | 一次生成、永久存储、零额外开销;前端只需展示 title 字段 |
| 标题来源 | **首条 user 消息截前 20 字** | 用户已确认;无需 LLM、无 token 成本、符合原 conversationLabel 设计意图 |
| 标题方案否决项 | ~~LLM 总结~~ | 额外 token 成本 + 异步复杂度 + 需错误降级,过度设计 |
| 标题方案否决项 | ~~后端列表返回 first_message 字段~~ | 多动 schema/repository/service;title 字段已存在,直接用它更干净 |
| firstMessage 前端兜底 | **保留函数参数,不主动加载** | 列表项信任后端 title;按需 useMessages 每条会话开销大;极少数旧 null title 会话显示"新对话"可接受 |

## 不做(防越界)

- 不动 MarkdownView 组件本身(已用 break-words,无溢出问题)
- 不动会话 CRUD API 结构(只加 first_message 内部参数)
- 不重构 chat-page 整体布局(只做窄范围 CSS 修复)
- 标题不用 LLM 总结
