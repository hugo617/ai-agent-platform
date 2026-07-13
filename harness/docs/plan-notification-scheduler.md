# 计划:通知系统 + 定时任务框架(in-app 通知 + APScheduler)

> 对应 feature_list.json 的 `id`: `notification-scheduler`
> 状态: not_started
> 优先级: 54
> 前置: 无(余额预警触发场景依赖 token-wallet-billing 44)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:无通知系统、无定时任务框架

### 现状

- **通知**:全项目搜 `notification|notify|message.?center` **零真实命中**。无通知模型、无端点、无铃铛组件。`SystemLog` 是写Only 审计,不是用户通知。
- **定时任务**:搜 `celery|apscheduler|cron|periodic|background` **零命中**。无任务队列。一切同步处理。

### 商业价值

**Token 计费的配套**:余额预警(余额 < 阈值)、充值到账通知、月度用量报告,都需要通知 + 定时扫描。不做的话用户得自己刷页面。

### 目标

1. **in-app 通知**:站内消息中心(Notification 模型 + API + 铃铛组件)
2. **APScheduler 定时任务**:余额预警扫描、用量日报、过期清理

---

## 前置条件

- 无。余额预警触发场景依赖 token-wallet-billing(44),但通知框架本身独立。

---

## 实施步骤

### 第一阶段:通知模型 + API

#### Step 1:Notification 模型 + 迁移

- **新建**(`app/models/notification.py`):
  ```python
  class Notification(Base):
      __tablename__ = "notifications"
      id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
      tenant_id: Mapped[str] = mapped_column(String(32), index=True)  # 可空(platform 级通知)
      user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # NULL=全员
      type: Mapped[str] = mapped_column(String(32))  # balance_warning/recharge/role_change/usage_report/system
      title: Mapped[str] = mapped_column(String(200))
      content: Mapped[str] = mapped_column(Text)
      link: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 点击跳转
      is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
      created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
  ```
- **注册** + **迁移**
- **检查**:`alembic upgrade head && alembic check`

#### Step 2:NotificationService + API

- **新建**(`app/services/notification_service.py`):
  ```python
  class NotificationService:
      async def create(self, tenant_id, user_id, type, title, content, link=None) -> Notification
      async def list_for_user(self, user_id, tenant_id, unread_only=False) -> list[Notification]
      async def mark_read(self, notification_id, user_id)
      async def mark_all_read(self, user_id, tenant_id)
      async def unread_count(self, user_id, tenant_id) -> int
  ```
- **新建**(`app/api/v1/notifications.py`):
  ```python
  GET /notifications          # 列表(?unread_only=true)
  GET /notifications/unread-count  # 未读数
  PUT /notifications/{id}/read     # 标记已读
  PUT /notifications/read-all      # 全部已读
  ```
- **权限**:人人可查自己的通知(按 user_id 过滤)
- **路由注册**

#### Step 3:通知触发点接入

- **余额预警**(依赖 44):wallet balance < threshold → create(balance_warning)
- **充值到账**(依赖 44):recharge 后 → create(recharge)
- **角色变更**:UserService 改角色后 → create(role_change)
- **检查**:各触发点产生通知

### 第二阶段:APScheduler 定时任务

#### Step 4:集成 APScheduler

- **加依赖**(`requirements.txt`):`apscheduler`
- **新建**(`app/core/scheduler.py`):
  ```python
  from apscheduler.schedulers.asyncio import AsyncIOScheduler
  scheduler = AsyncIOScheduler()

  def init_scheduler(app):
      # 注册定时任务
      scheduler.add_job(scan_balance_warnings, "cron", hour=9, minute=0)  # 每天 9 点
      scheduler.add_job(cleanup_expired_tokens, "cron", hour=2)  # 凌晨清理
      scheduler.start()
  ```
- **启动**(`app/main.py` lifespan):`init_scheduler(app)`

#### Step 5:定时任务实现

- **余额预警扫描**(`scan_balance_warnings`):
  ```python
  async def scan_balance_warnings():
      # 查所有 wallet where balance < low_balance_threshold AND 未发过今日预警
      # → create(balance_warning) + (可选)记录已发避免重复
  ```
- **用量日报**(可选,依赖 43):每日汇总各门店 token 消耗 → create(usage_report)
- **过期清理**:清理过期的 VerificationCode / 过期 session(软删或硬删)
- **检查**:任务按 schedule 触发;产生通知

### 第三阶段:前端

#### Step 6:铃铛组件 + 通知中心

- **新建**(`frontend/src/components/layout/notification-bell.tsx`):
  - 顶栏铃铛图标 + 未读数 badge
  - 点击下拉显示最近通知(未读高亮)
  - 标记已读 / 全部已读
  - 点击通知跳转 link
  - 轮询或 refetch 间隔(30s)拉 unread_count
- **新建**(`frontend/src/pages/notifications-page.tsx`):
  - 全部通知列表(分页 + 未读过滤)
- **改**(`dashboard-layout.tsx`):顶栏加 `<NotificationBell />`
- **改**(`App.tsx`):`/notifications` → NotificationsPage
- **检查**:铃铛显示未读数;下拉看通知;标记已读生效

### 第四阶段:验证

#### Step 7:测试 + 总验证

- **后端**(`tests/test_notifications.py`):
  - create/list/mark_read/unread_count
  - 权限:用户只看自己的通知
  - 定时任务触发(mock schedule)
- **命令**:`./init.sh` + `npm run build` + `alembic check`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. Notification 模型 + 迁移;NotificationService(create/list/mark_read/unread_count)
2. API:GET/PUT notifications + unread-count
3. 通知触发点:余额预警(依赖44)/充值到账/角色变更
4. APScheduler 集成 + 定时任务(余额扫描/用量日报/清理)
5. 前端:铃铛组件(未读 badge + 下拉)+ 通知中心页
6. `./init.sh` + `npm run build` + `alembic check` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 定时任务多实例重复执行 | 生产单实例跑 scheduler;或多实例用 APScheduler + DB 锁 |
| 通知量大刷屏 | 按类型聚合/去重(同类型同日只发一次);用户可配接收偏好 |
| 铃铛轮询性能 | 30s 间隔 + 轻量 unread-count 端点;或 SSE 推送(后续) |
| APScheduler 进程崩溃 | 加异常捕获 + 日志;重启自动恢复 |

### 不做的事(边界)

- 不做邮件/短信推送(只 in-app)
- 不做实时推送(SSE/WebSocket,后续)
- 不做通知偏好设置(后续)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| app 启动(lifespan) | `app/main.py` |
| 布局(加铃铛) | `frontend/src/components/layout/dashboard-layout.tsx` |
| wallet(余额预警触发) | `app/models/wallet.py`(任务44建) |
| 角色变更(通知触发) | `app/services/permission_service.py` `set_role_for_user_in_domain` |
