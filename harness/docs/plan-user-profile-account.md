# 计划:用户个人中心(改密码/改资料/我的会话)

> 对应 feature_list.json 的 `id`: `user-profile-account`
> 状态: not_started
> 优先级: 49
> 前置: 无(头像上传弱依赖 file-upload 56,可先做文字字段)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:用户改不了自己信息,只能找管理员

### 现状(2026-07-12 取证)

- **无个人中心页**:`frontend/src/pages/` 无 profile/account 页;`App.tsx` 无 `/profile` 路由
- **`GET /auth/me`**(`app/api/v1/auth.py` L30-49)只读,返回 user_id/tenant_id/email/platform_role/roles
- **改密码**:只有管理员重置他人密码(`PasswordReset` schema 在 `users.py`,admin-gated);**用户自己改不了**
- **settings 页**:是 LLM 配置 + API Token,**不是**个人账号页

### 目标

用户自助管理账号:
1. 改密码(验证旧密码 → 设新密码)
2. 改资料(姓名/头像——头像依赖 file-upload 56,先做姓名)
3. 查看我的会话 / 我的用量
4. `PUT /auth/me` 端点

---

## 前置条件

- 无。头像上传依赖 file-upload(56),可先做密码 + 姓名文字字段。

---

## 实施步骤

### 第一阶段:后端

#### Step 1:User 模型确认可编辑字段

- **核实**(`app/models/tenant.py` User 模型):确认有哪些可编辑字段(姓名/手机/头像)。若缺 `full_name`/`avatar_url` 需补
- **检查**:字段类型 + 是否可空

#### Step 2:PUT /auth/me 端点

- **改什么**(`app/api/v1/auth.py` 加端点):
  ```python
  @router.put("/me", response_model=MeResponse)
  async def update_me(payload: ProfileUpdate, user: CurrentUser, db):
      # 只能改自己(user.user_id);不能改 platform_role/roles(防越权)
      ...
  ```
- **改什么**(`app/schemas/auth.py` 加 `ProfileUpdate`):
  ```python
  class ProfileUpdate(BaseModel):
      full_name: str | None = None
      avatar_url: str | None = None  # 依赖 file-upload,先留字段
  ```
- **检查**:改自己成功;不能改 platform_role/roles(忽略这些字段)

#### Step 3:改密码端点

- **改什么**(`app/api/v1/auth.py` 加端点):
  ```python
  @router.put("/me/password")
  async def change_password(payload: PasswordChange, user, db):
      # 验证旧密码(bcrypt.verify)→ 设新密码(bcrypt.hash)
      # 失败:旧密码错 → 400
  ```
- **改什么**(`app/schemas/auth.py` 加 `PasswordChange`):
  ```python
  class PasswordChange(BaseModel):
      old_password: str
      new_password: str  # 校验长度/复杂度
  ```
- **复用**:密码哈希逻辑在 `app/core/security.py`(已有 bcrypt)
- **检查**:旧密码错 → 400;新密码正确哈希;改后能用新密码登录

#### Step 4:我的会话端点

- **复用**:`GET /conversations?user_id=me` 已有(列表按 user_id 过滤)。前端直接调即可,无需新端点
- **检查**:返回当前用户的会话列表

### 第二阶段:前端

#### Step 5:types + endpoints + hooks

- **改**(`frontend/src/api/types.ts`):`ProfileUpdate` / `PasswordChange` 类型
- **改**(`frontend/src/api/endpoints.ts`):`updateMe(payload)` / `changePassword(payload)`
- **改**(`frontend/src/hooks/queries.ts`):`useUpdateMe`(成功后 invalidate `["me"]`)/ `useChangePassword`
- **检查**:tsc 无错

#### Step 6:profile-page.tsx 个人中心页

- **新建**(`frontend/src/pages/profile-page.tsx`):
  - **资料编辑卡片**:姓名输入框 + 头像(占位,依赖 file-upload)+ 保存按钮
  - **改密码卡片**:旧密码 + 新密码 + 确认新密码 + 提交(前端校验两次一致)
  - **我的会话卡片**:最近会话列表(复用 useConversations)+ 跳转聊天
  - **(可选)我的用量卡片**:我的对话 token 消耗(依赖 43)
- **检查**:表单提交生效;改密码成功后 toast

#### Step 7:入口 + 路由

- **改**(`frontend/src/components/layout/dashboard-layout.tsx`):顶栏头像下拉加「个人中心」入口
- **改**(`frontend/src/App.tsx`):`/profile` → ProfilePage(ProtectedRoute 即可,人人可访问自己的)
- **检查**:头像下拉见「个人中心」;点击进页面

### 第三阶段:验证

#### Step 8:测试 + 总验证

- **后端**(`tests/test_profile.py`):
  - PUT /auth/me 改姓名成功;不能改 platform_role/roles
  - PUT /me/password 旧密码错 → 400;正确 → 新密码可登录
  - 越权:用户 A 改不了用户 B(token 里 user_id 锁定)
- **命令**:`./init.sh` + `npm run build`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. `PUT /auth/me`(改姓名/资料,不能改 platform_role/roles 防越权)
2. `PUT /auth/me/password`(验证旧密码 → 设新密码)
3. profile-page.tsx:资料编辑 + 改密码 + 我的会话
4. 顶栏头像下拉「个人中心」入口 + `/profile` 路由
5. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 改密码后旧 token 仍有效 | MVP 可接受(token 有时效);严格做法是改密码后吊销所有 session |
| 越权改他人资料 | PUT /auth/me 强制用 token 里的 user_id,忽略 body 里的 user_id |
| 头像字段但无上传 | 先留 avatar_url 字段(字符串),file-upload(56)完成后接上传组件 |

### 不做的事(边界)

- 不做头像上传(file-upload 56)
- 不做两步验证/2FA(后续)
- 不做第三方账号绑定管理(Logto 已管)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| GET /auth/me(只读,待加 PUT) | `app/api/v1/auth.py` L30-49 |
| MeResponse schema | `app/schemas/auth.py` |
| 密码哈希(复用) | `app/core/security.py` bcrypt |
| 管理员重置密码(参照) | `app/api/v1/users.py` PasswordReset |
| 布局(加头像下拉) | `frontend/src/components/layout/dashboard-layout.tsx` |
