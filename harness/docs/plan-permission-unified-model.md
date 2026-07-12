# 计划:权限目录统一 + 操作权限细化(权限重构系列 1/4)

> 对应 feature_list.json 的 `id`: `permission-unified-model`
> 状态: not_started
> 优先级: 39
> 前置: 无(本任务是整个权限重构系列的地基)
> 系列总纲: [`plan-permission-redesign-overview.md`](plan-permission-redesign-overview.md)

---

## 背景:权限目录三处漂移 + 操作粒度粗

### 现状(代码层,2026-07-12 核实)

权限目录 `(obj, act)` 真相源散在三处,且已经 drift:

| 真相源 | 位置 | 问题 |
|---|---|---|
| 默认权限常量 | `permission_service.py` `DEFAULT_OWNER_PERMS` / `DEFAULT_ADMIN_PERMS` / `DEFAULT_MEMBER_PERMS` | `conversations:delete` 缺席(owner 没种子) |
| 路由守卫 | `app/api/v1/*.py` 各文件的 `require_permission(obj, act)` | `conversations:delete` 在 `conversations.py:65` 有校验,但无角色持有 → 形同虚设 |
| 前端显示 | `permissions-page.tsx` `OBJ_LABELS` / `ACT_ORDER` | 只标了 4 个 obj、漏 `manage` 动作;`customers`/`settings`/`api_tokens` 前端无中文标签 |

### 操作粒度粗

- `settings:manage` 一勾全勾(没法配「只读设置」)
- `api_tokens:manage` 同样无法拆分(读/颁发/吊销混在一起)
- 缺 `export`(导出)、`approve`(审批)等常见业务动作预留

### 目标

1. **消除三处漂移**:让后端 `Permission` 表 + catalogue 端点成为**唯一真相源**,前端从它读,不再硬编码。
2. **细化操作粒度**:把 `manage` 拆细,补全缺失项,让权限矩阵能精确表达「只读设置」「只能颁发不能吊销 token」。
3. **不动 menu/data_scope**——那是任务 2/3 的事。本任务只整理 `type="api"` 的操作权限。

---

## 前置条件

- 无。本系列第一棒,所有改动在现有 `type="api"` 范围内,不引入新 type。

---

## 实施步骤

### 第一阶段:确定新的操作权限目录(真相源重写)

#### Step 1:重写 `DEFAULT_*_PERMS`,统一为完整目录

- **改什么**(`app/services/permission_service.py`,重写 `DEFAULT_OWNER_PERMS` / `DEFAULT_ADMIN_PERMS` / `DEFAULT_MEMBER_PERMS` 三常量,约 L379-402):
  - 把 `settings:manage` 拆为 `settings:read` + `settings:update`
  - 把 `api_tokens:manage` 拆为 `api_tokens:read` + `api_tokens:create` + `api_tokens:delete`(delete 含吊销语义)
  - 补 `conversations:delete` 到 owner(对齐路由守卫)
  - 补 `agents:export` / `customers:export`(预留导出动作,owner/admin 持有)
  - 确保每个路由守卫用到的 `(obj, act)` 都在至少一个默认角色里(否则该权限形同虚设)
- **完整目录(目标态)**:

  | obj | actions | 说明 |
  |---|---|---|
  | agents | read/create/update/delete/export | +export 预留 |
  | conversations | read/create/update/delete/chat | 补 delete/update |
  | users | read/create/update/delete | 不变 |
  | roles | read/create/update/delete | 不变 |
  | settings | read/update | **拆 manage** |
  | api_tokens | read/create/delete | **拆 manage** |
  | customers | read/create/update/delete/export | +export 预留 |

- **检查**:对照 `app/api/v1/*.py` 所有 `require_permission` 调用,确认每个 `(obj, act)` 都在默认目录里;反过来确认目录每一项都有对应路由(export 可暂无路由,标注「预留」)

#### Step 2:Permission 表加 `obj`/`act` 实列(可选优化)

- **当前问题**:`Permission.code = "<obj>:<act>"` 编码成字符串,靠 `split(":", 1)` 解析,查询/过滤不便
- **改什么**(`app/models/rbac.py` Permission 模型):
  - 加 `obj: Mapped[str]` 和 `act: Mapped[str]` 两个实列(从 code 解析回填)
  - 保留 `code` 字段(向后兼容 + 唯一约束仍用 `(tenant_id, code)`)
  - seed 时同步填这三个字段
- **迁移**(`alembic` autogenerate):加两列 + data migration 回填现有行(从 code split)
- **检查**:`alembic upgrade head && alembic check` 无 drift;现有按 code 的查询不受影响
- **边界判断**:如果评估发现拆列改动面太大(影响 SCD2/casbin 同步逻辑),可**降级为不改表结构**,仅让 catalogue 端点返回解析后的 obj/act(现状已这么做)。**建议:第一版降级,保持 code 编码,降低风险。** 实施时先评估,确实需要再拆列。

### 第二阶段:消除前端漂移

#### Step 3:前端从 catalogue 端点读目录,删硬编码常量

- **改什么**(`frontend/src/pages/permissions-page.tsx`):
  - 删除 `OBJ_LABELS`(L35-40)和 `ACT_ORDER`(L43)硬编码常量
  - 改为从 `usePermissionCatalogue()`(已有 hook)读取真实目录
  - 中文标签映射挪到后端:catalogue 端点的 `PermissionItem.name` 直接返回中文友好名(如「智能体-查看」),前端只显示
- **改什么**(`app/api/v1/permissions.py` catalogue 端点 + `app/services/permission_service.py` seed):
  - seed 时给每个 Permission 填中文 `name`(如 obj=agents/act=read → name="智能体-查看")
  - 建一张 `OBJ_CN` / `ACT_CN` 映射表(在 permission_service 里),seed 和 catalogue 共用
- **检查**:`npm run build` 通过;矩阵页显示 7 个 obj 的中文标签(含 settings/api_tokens/customers)

### 第三阶段:seed 幂等性 + 现有租户补齐

#### Step 4:seed 升级 + 现有租户权限补齐

- **改什么**(`app/services/permission_service.py` `seed_tenant_defaults`):
  - 确认 `_upsert_permission` 幂等(已有,确认对新增的 export/delete 项也生效)
  - 确认 SCD2 `role_permissions` 当前态与 casbin 策略同步(已有 `sync_role_permissions_to_casbin`,确认对新拆的 settings/api_tokens 项生效)
- **现有租户补齐**:写一次性脚本或迁移,给已存在的租户补上新拆的权限项(`settings:read`/`settings:update`/`api_tokens:read` 等)到对应角色的 casbin 策略 + SCD2 当前态
  - 路径:在 `scripts/` 加 `backfill_permissions.py`,逻辑:遍历租户 → 对每个角色,按新 `DEFAULT_*_PERMS` 比对缺失项 → grant
  - 或:写成 alembic data migration(更规范,但 casbin 表被 `_EXCLUDED_TABLES` 排除,需在迁移里手动调 casbin enforcer)
- **检查**:跑 backfill 后,GET `/permissions/matrix` 对老租户也显示完整新目录

### 第四阶段:测试 + 总验证

#### Step 5:补测试

- **改/加**(`tests/test_permissions_api.py`):
  - 矩阵正确性:新建租户后 owner 持有全部新目录项(含 settings:read/update、api_tokens:read/create/delete、agents:export)
  - catalogue 返回中文 name
  - 跨租户隔离不变
  - backfill 脚本:对模拟的老租户(只旧目录)跑 backfill → 矩阵补齐
- **检查**:`pytest tests/test_permissions_api.py -v` 全过

#### Step 6:总验证

- **命令**:
  ```bash
  ./init.sh   # ruff + pytest 全绿
  cd frontend && npm run build   # 前端无类型错
  ```
- **通过标准**:
  - `./init.sh` 全绿(含新目录项测试)
  - `npm run build` 通过
  - GET `/permissions/matrix` 返回完整新目录,前端显示中文标签,无硬编码残留
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `DEFAULT_*_PERMS` 重写:settings/api_tokens 的 manage 拆细,补 conversations:delete + export 预留
2. 前端 `OBJ_LABELS`/`ACT_ORDER` 硬编码删除,改从 catalogue 端点读真实目录
3. catalogue 端点 PermissionItem.name 返回中文友好名
4. 现有租户通过 backfill 补齐新目录项
5. `./init.sh` + `npm run build` 全绿
6. 权限目录三处漂移消除(后端 Permission 表 = 路由守卫 = 前端显示,单一真相源)

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 拆 manage 导致老租户角色「丢失」原 manage 能力 | backfill 脚本必须给老租户补上拆细后的权限;先在测试租户验证 |
| casbin 表被 Alembic 排除,backfill 写 casbin 要绕过迁移 | backfill 走 `permission_service.add_policy`(走 enforcer),不直接写表 |
| Permission 表拆 obj/act 实列改动面大 | **第一版降级:不拆列,保持 code 编码**,catalogue 端点解析返回。评估后再定 |
| 前端删 OBJ_LABELS 后矩阵列顺序乱 | catalogue 端点按 obj 分组 + sort_order 排序,前端按返回顺序渲染 |
| 路由守卫用到了拆掉前的 manage | 全局搜 `require_permission("settings"` / `"api_tokens"`,逐个改为 read/update 或 read/create/delete |

### 不做的事(边界,留给后续任务)

- 不新增 `type="menu"` 权限(任务 2 `permission-menu-view`)
- 不加 `data_scope`(任务 3 `permission-data-scope`)
- 不重写矩阵 UI 的超管锁定行(任务 4 `permission-matrix-redesign`)
- 不改 casbin 模型 `casbin_model.conf`(matcher 不变)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-permission-redesign-overview.md` |
| 默认权限常量(待重写) | `app/services/permission_service.py` `DEFAULT_*_PERMS` ~L379 |
| Permission 模型 | `app/models/rbac.py` ~L77 |
| catalogue 端点 | `app/api/v1/permissions.py` |
| 前端矩阵页(待删硬编码) | `frontend/src/pages/permissions-page.tsx` ~L35 |
| RBAC 文档 | `项目指南/02-后端架构/06-权限模型RBAC.md` |
