# 计划:对话管理增强(搜索/重命名/标签/收藏/置顶/批量删除)

> 对应 feature_list.json 的 `id`: `conversation-management`
> 状态: not_started
> 优先级: 50
> 前置: 无
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:对话只能列表/读/删,体验不完整

### 现状(2026-07-12 取证)

- **后端** `app/api/v1/conversations.py`:只有 3 操作——`GET /`(列表)、`GET /{id}/messages`(读消息)、`DELETE /{id}`(硬删)
- **Conversation 模型**(`app/models/agent.py` L47-69):只有 id/tenant_id/agent_id/user_id/title/created_at/updated_at,**无 tags/pinned/starred**
- **前端** `chat-page.tsx`:startNewConversation + 列表选择 + handleCopyMessage(复制单条消息)。无搜索/重命名/标签/收藏/置顶/批量删除

### 目标

补全对话管理:
1. 搜索(按标题/内容)
2. 重命名对话
3. 标签/收藏分类
4. 置顶常用
5. 批量删除

---

## 前置条件

- 无。

---

## 实施步骤

### 第一阶段:模型 + 迁移

#### Step 1:Conversation 加字段

- **改什么**(`app/models/agent.py` Conversation,加列):
  ```python
  tags: Mapped[list] = mapped_column(JSONB().with_variant(JSON, "sqlite"), default=list, server_default=text("'{}'"))
  is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
  is_starred: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
  ```
  - tags 用 JSONB(双库兼容,参照 CustomerProfile.tags 模式)
- **迁移**:`alembic revision --autogenerate`
- **检查**:`alembic upgrade head && alembic check`;旧对话 tags=[]/is_pinned=false(默认值)

### 第二阶段:后端 API

#### Step 2:搜索端点

- **改什么**(`app/api/v1/conversations.py` 的 GET / 加参数):
  ```python
  @router.get("/", response_model=list[ConversationRead])
  async def list_conversations(user, db, *, search: str | None = None, tag: str | None = None):
      # search: title ILIKE %q% OR id IN (SELECT conversation_id FROM messages WHERE content ILIKE %q%)
      # tag: tags @> [tag]  (JSONB contains)
  ```
- **检查**:按标题搜;按消息内容搜;按标签过滤

#### Step 3:重命名 / 标签 / 置顶 / 收藏

- **改什么**(`app/api/v1/conversations.py` 加端点):
  ```python
  @router.patch("/{conv_id}/title")        # 重命名
  @router.post("/{conv_id}/tags")           # 加标签(body: tag)
  @router.delete("/{conv_id}/tags/{tag}")   # 删标签
  @router.patch("/{conv_id}/pin")           # 置顶/取消(body: pinned: bool)
  @router.patch("/{conv_id}/star")          # 收藏/取消
  ```
- **权限**:本人会话(user_id == current)或 owner/admin(租户内)
- **检查**:各端点生效;跨用户隔离

#### Step 4:批量删除

- **改什么**(`app/api/v1/conversations.py` 加端点):
  ```python
  @router.post("/batch-delete")
  async def batch_delete(payload: BatchDelete, user, db):
      # body: conversation_ids: list[str]; 校验全部属于当前用户/租户
  ```
- **检查**:批量删;权限校验(不能删别人的)

#### Step 5:列表排序

- **改什么**(GET / 排序逻辑):置顶优先(`ORDER BY is_pinned DESC, updated_at DESC`)
- **检查**:置顶的排前面

### 第三阶段:前端

#### Step 6:types + endpoints + hooks

- **改** types:Conversation 加 tags/is_pinned/is_starred
- **改** endpoints:renameConversation/addTag/removeTag/togglePin/toggleStar/batchDeleteConversations
- **改** hooks:对应 mutation hooks(成功后 invalidate `["conversations"]`)
- **检查**:tsc 无错

#### Step 7:chat-page.tsx 增强

- **改什么**(`frontend/src/pages/chat-page.tsx`):
  - **搜索框**:顶部,实时搜(防抖)→ 调 list?search=
  - **会话列表项**:
    - 置顶的显示 📌 图标 + 排前面
    - 收藏的显示 ⭐
    - 标签显示为小 chip
  - **右键菜单/更多按钮**(每个会话项):
    - 重命名(inline 编辑或 Dialog)
    - 加标签(Dialog 输入)
    - 置顶/取消
    - 收藏/取消
    - 删除(确认)
  - **批量操作**:多选 checkbox + 批量删除按钮
- **检查**:所有交互生效;mutation 后列表刷新

### 第四阶段:验证

#### Step 8:测试 + 总验证

- **后端**(`tests/test_conversation_management.py`):
  - 搜索(标题/内容/标签)
  - 重命名/标签/置顶/收藏生效
  - 批量删除 + 权限(不能删别人)
  - 排序(置顶优先)
  - 租户隔离
- **命令**:`./init.sh` + `npm run build` + `alembic check`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. Conversation 加 tags(JSONB)/is_pinned/is_starred 列 + 迁移无 drift
2. GET / 支持 search(标题+内容)和 tag 过滤;置顶优先排序
3. 重命名/标签/置顶/收藏/批量删除端点 + 权限
4. chat-page.tsx:搜索框 + 右键菜单(重命名/标签/置顶/收藏/删除)+ 批量操作
5. `./init.sh` + `npm run build` + `alembic check` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 消息内容搜索(ILIKE)性能 | 会话量级内可接受;超大量加 GIN 索引或全文检索 |
| tags JSONB 双库兼容 | 用 `JSONB().with_variant(JSON, "sqlite")`,参照 CustomerProfile |
| 批量删除误删 | 前端确认弹窗;后端校验全部属于当前用户 |

### 不做的事(边界)

- 不做对话导出(那是 data-export 55,但对话导文本可在此加「复制全文」)
- 不做对话分享(生成公开链接,后续)
- 不做文件夹/分类(用标签替代,更灵活)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| conversations API(待改) | `app/api/v1/conversations.py` |
| Conversation 模型(待加列) | `app/models/agent.py` L47-69 |
| JSONB 双库模式(参照) | `app/models/customer.py` CustomerProfile.tags |
| 聊天页(待增强) | `frontend/src/pages/chat-page.tsx` |
