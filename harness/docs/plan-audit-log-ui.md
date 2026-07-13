# 计划:审计日志查询 UI(SystemLog 暴露 API + 前端审计页)

> 对应 feature_list.json 的 `id`: `audit-log-ui`
> 状态: not_started
> 优先级: 48
> 前置: 无
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:SystemLog 在写但无 API 无 UI,数据在黑暗里

### 现状(2026-07-12 取证)

- **模型**:`app/models/log.py` 的 `SystemLog` 在写,由 `app/services/logging_service.py` 的 `record()` 写入
- **查询**:全项目搜 `SystemLog|system_logs|/logs` 在 `app/api/` **零命中**——只有写,没有读端点
- **前端**:`frontend/src/pages/` 无 `logs-page.tsx`/`audit-page.tsx`;`App.tsx` 路由无 `/logs`
- **后果**:审计数据在黑暗里,运维/合规完全看不了

### 目标

让审计日志可查可看:
1. 后端查询端点 `GET /logs`(分页 + 多维过滤)
2. 前端审计日志页(表格 + 过滤器)
3. 权限:super_admin 看全平台,owner/admin 看本租户

---

## 前置条件

- 无。SystemLog 模型和写入逻辑已就绪。

---

## 实施步骤

### 第一阶段:后端

#### Step 1:SystemLog 模型确认 + Repository

- **先核实**(`app/models/log.py`,已查 2026-07-13):SystemLog 字段为
  `id / level / action / module / message / details_json`(DB 列名 `details`)
  `/ resource_type / resource_id / old_values / new_values`
  `/ user_id`(FK users,**操作人**;非 operator_id)`/ session_id / tenant_id`(FK tenants,平台级操作可空)
  `/ user_agent / ip / request_id / duration_ms / created_at`。
  - 注意 before/after 在模型里是 **`old_values`/`new_values`**(JSONB),不是 `before`/`after`
  - 操作人是 **`user_id`**,不是 `operator_id`
  - 已有索引:`idx_system_logs_resource`/`_tenant_id`/`_user_id`(过滤维度已覆盖)
- **新建**(`app/repositories/log.py`):
  ```python
  class SystemLogRepository(BaseRepository[SystemLog]):
      model = SystemLog
      async def list_logs(self, *, tenant_id=None, user_id=None, action=None,
                          resource_type=None, date_from=None, date_to=None,
                          limit=50, offset=0) -> tuple[list[SystemLog], int]:
          # 动态 WHERE 构建;tenant_id=None 表示跨租户(super_admin)
  ```
- **检查**:Repository 支持多维过滤 + 分页

#### Step 2:Schema + 端点

- **改什么**(`app/schemas/log.py` 新建或追加):
  ```python
  class SystemLogRead(BaseModel):
      id: str
      level: str
      action: str
      module: str
      message: str
      resource_type: str | None
      resource_id: str | None
      old_values: dict | None     # before 快照
      new_values: dict | None     # after 快照
      user_id: str | None          # 操作人(关联 users.id)
      tenant_id: str | None
      ip: str | None
      request_id: str | None
      created_at: datetime
      # operator_name 可选:join users 表取(按 user_id)
  ```
- **新建**(`app/api/v1/logs.py`):
  ```python
  @router.get("/", response_model=list[SystemLogRead])
  async def list_logs(user, db, tenant_id=None, user_id=None, action=None,
                      resource_type=None, date_from=None, date_to=None,
                      limit=50, offset=0):
      # super_admin: 可传 tenant_id 过滤或全平台;非 super_admin: 强制 tenant_id=user.tenant_id
  ```
- **权限**:`require_super_admin`(看全平台)或 `require_permission("logs", "read")`(看本租户)
- **路由注册**(`app/main.py`)
- **检查**:端点返回数据;权限分流正确

#### Step 3:DEFAULT_*_PERMS 加 logs:read

- **改什么**(`app/services/permission_service.py`):owner/admin 加 `("logs", "read")`
- **检查**:owner/admin 能查本租户日志;member 不能

### 第二阶段:前端

#### Step 4:types + endpoints + hooks

- **改**(`frontend/src/api/types.ts`):`SystemLog` 类型
- **改**(`frontend/src/api/endpoints.ts`):`fetchLogs(params)`
- **改**(`frontend/src/hooks/queries.ts`):`useLogs(params)`(params 含过滤条件)
- **检查**:tsc 无错

#### Step 5:logs-page.tsx 审计日志页

- **新建**(`frontend/src/pages/logs-page.tsx`):
  - **过滤器栏**:操作人 / 操作类型(下拉:create/update/delete/login 等)/ 资源类型 / 时间范围(date picker)
  - **表格**(TanStack Table):时间 / 操作人 / 操作 / 资源类型 / 资源ID / 详情(展开看 before/after diff)
  - **分页**:limit/offset
  - **权限**:owner/admin 可见(member 无 logs:read 则不显示)
- **检查**:页面对接端点;过滤生效;diff 展示

#### Step 6:侧边栏 + 路由

- **改**(`frontend/src/components/layout/dashboard-layout.tsx` NAV_ITEMS):加「审计日志」(`/logs`,needsUserManagement)
- **改**(`frontend/src/App.tsx`):`/logs` → LogsPage(RequireUserManagement 守卫)
- **检查**:owner/admin 侧边栏见「审计日志」;点击进页面

### 第三阶段:验证

#### Step 7:测试 + 总验证

- **后端**(`tests/test_logs_api.py`):
  - 查询/过滤(按操作人/类型/资源/时间)
  - 租户隔离:门店 A 看不到门店 B 日志
  - super_admin 看全平台
  - member 无 logs:read → 403
- **命令**:`./init.sh` + `npm run build`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. `GET /logs` 端点(分页 + 过滤:operator/action/resource_type/date_range)
2. 权限分流:super_admin 全平台,owner/admin 本租户,member 403
3. DEFAULT_*_PERMS 加 `logs:read`(owner/admin)
4. logs-page.tsx:TanStack Table + 过滤器 + before/after diff 展开
5. 侧边栏「审计日志」菜单 + 路由守卫
6. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 日志量大查询慢 | 分页(limit≤100)+ created_at 索引;时间范围必填或默认近 30 天 |
| before/after JSON 展示 | 用 JSON viewer 组件或 `<pre>` 格式化;diff 高亮可选 |
| 平台级操作无 tenant_id | tenant_id 可空;super_admin 查询不强制 tenant_id 过滤 |

### 不做的事(边界)

- 不做日志导出(那是 data-export 55)
- 不做日志归档/清理策略(后续运维)
- 不做实时日志推送(手动刷新)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| SystemLog 模型 | `app/models/log.py` |
| 写入逻辑 | `app/services/logging_service.py` |
| 列表页模板 | `frontend/src/pages/users-page.tsx`(TanStack Table + 过滤) |
| 路由守卫 | `frontend/src/components/auth/require-permission.tsx` |
