# 计划:门店设备实例 CRUD + 绑定客户(租户隔离)

> **状态**:草案 v2(经对抗式审查修复 3 个 🔴 + 9 个 🟡,已拆 7 个实施切片,待 `/implement` 推进)
> **feature_list.json ID**:`devices-crud-ui`(priority 62,设备功能系列 2/4)
> **前置**:`device-models-crud`(priority 61,已 passing)—— `DeviceModel` 表 / 后端 API 已落地
> **同类先例**:`plan-customers-api.md`(租户级表 + CustomerProfile)/ `plan-groups-api.md`(attach-detach 端点)/ `plan-device-models-crud`(刚合并的范式)
> **依赖链**:device-models-crud ✅ → **devices-crud-ui(本文档)** → device-booking → device-poweron

> **v2 修订记录**(2026-07-22 对抗式审查):
> - 🔴#1 重写 §8 H 项测试 + §3 关键边界 #1:`DeviceModelService.delete` 是软删(`device_model_service.py:148-156`),`ondelete=RESTRICT` 永不触发,真实守卫是 service 层 `_assert_model_live`。补"软删型号下拉隐藏 / 编辑时只读" UX 设计 + 新增 H1-H5 测试
> - 🔴#2 §7 backfill 方案落地:仓库**没有** backfill 范式可参照(原"参照 permission-unified-model"是空头支票),本 feature 新增 `backfill_devices_perms_for_existing_tenants` 函数 + 触发开关 + K1-K6 幂等性测试
> - 🔴#3 决策摘要表重写:纠正"与 group attach/detach 范式一致"的自相矛盾(group 用 `require_super_admin`,devices 用 `require_permission("devices","update")`);bind 返码 201→**200** + `already_bound` 标志;unbind 无绑定 → **204**(幂等);retired serial 复用规则;HQ 全景 selectin 策略
> - 🟡 9 条小修:hq_staff 读放行底层(在 `permission_service.check:103` 特判)、`GET /` HQ 端点不能用 router-level `require_permission`(会 403 hq_staff)、`isHQStaff` helper 当前不存在必须新增、`app/models/__init__.py` 是空文件按文件路径导入、`DeviceModelPublic` 命名空间归属、Customer SET NULL 跨租户副作用风险记录、verification 清单补 model_id 完整性条目、customers-page HqView 对 hq_staff 不可见既存 bug 记录
> - 📋 **拆切片**(2026-07-22 `/to-tickets`):按 tracer-bullet 垂直切片原则拆成 7 个实施切片,写进文末「实施切片」章节,含依赖图。切片 02 的 backfill 触发方式定为**独立一次性脚本** `scripts/backfill_devices_perms.py`

---

## 决策摘要(已与用户确认)

| 议题 | 决策 | 理由 |
|---|---|---|
| **绑定端点 URL 形态** | `POST /devices/{id}/bind {customer_id}`;`DELETE /devices/{id}/bind` | 借鉴 group `POST/DELETE /{group_id}/tenants/{tenant_id}` 的 URL 形态(子资源动作端点),**但守卫不同**:devices 是租户级资源,用 `require_permission("devices","update")`,**不是** group 的 `require_super_admin()`(group 是平台级资源)。详见下方"绑定端点守卫"行 |
| **绑定端点守卫** | `Depends(require_permission("devices","update"))`(owner/admin 写,member 403) | devices 是租户级资源,绑客户是本租户业务动作,不该走平台级 super_admin 守卫。与 customers 写端点范式一致(`require_permission("customers","update")`)|
| **bind 幂等性** | 重复 bind 同一 customer → **200**(非 201),body 含 `already_bound: true` 标志;bind 不同 customer → **200**(覆盖,语义同 PUT);bind 不存在/非本租户 customer → **400** | POST 在子资源动作端点语义上等同"赋值",重复赋值幂等返 200;201 仅在资源实际创建时返,本端点不创建资源(device 已存在)。**决策表上方原写 201 是错误,已纠正为 200** |
| **unbind 无绑定时** | 始终 **204**(DELETE 语义幂等,无绑定时 no-op 返 204,不返 404) | DELETE 幂等是 REST 惯例,避免客户端需要先 GET 判空再 DELETE |
| **HQ 全景视图** | 后端 + 前端都做,双视图分叉 | 与 customers-api/ui 对齐(super_admin 跨租户只读 + 全景字段)。**注意:customers-page 当前 HqView 只对 super_admin 可见**(`isSuperAdmin(me) ? <HqView/> : <StoreView/>`),**hq_staff 当前看不到 HqView** —— 这是 customers-page 既存遗漏,本 feature 的 devices-page 要修正:hq_staff 也要能看到 HqView |
| **前端双视图分叉 helper** | 新增 `isHQStaff(me)` helper(放 `frontend/src/lib/permission.ts`,参照 `isSuperAdmin` L27-29 范式),devices-page 用 `isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : <StoreView/>` | 当前 `permission.ts` 只有 `isSuperAdmin`,**没有 `isHQStaff`**(已核 `frontend/src/lib/permission.ts:27`)。本 feature 必须新增 |
| **状态切换** | `status` 作为 `PUT /devices/{id}` 的可选字段,无独立动作端点 | YAGNI —— 当前只是改字段,不是状态机;状态机动作端点归 device-poweron(`/bookings/{id}/start` 那种) |
| **retired 状态下 serial 复用** | retired **不是软删**,`is_deleted=False`,**仍占唯一索引**。retired 设备的 serial 在同租户内**不能被新 device 复用** → 复用必须先 DELETE(retired 设备)再 create | retired 是业务态(设备还在册,只是停用),不是删除。计划原 G 项"active↔maintenance↔retired 全部合法"对,但隐含约束:retired→create 同 serial 会撞唯一索引 → 400,这是**预期行为**(同一序列号同一时刻只能在一台 device 上) |
| **device-models 前端** | 只补下拉 hook(`useDeviceModels` + `fetchDeviceModels` + `DeviceModelPublic` 类型),不做型号管理页 | 设备入库 Dialog 需要拉型号;型号 CRUD 管理页留给独立 feature,守住 WIP=1 不越界。**`DeviceModelPublic` 类型命名空间归属**:放 `frontend/src/api/types.ts`,字段 `{id, name, specs}`,**与未来 device-models 前端管理页共用**(那时再加 `DeviceModelRead`/`DeviceModelCreate` 等完整类型,`DeviceModelPublic` 是其只读子集,不冲突) |
| **HQ 全景视图 N+1 策略** | `DeviceRepository.list_all_with_meta()` 用 **`selectin load`**(`selectinload(Device.tenant)` / `selectinload(Device.model)` / `selectinload(Device.customer)`),**不复用** `batch_tenant_info`(那是 customer 专用,且只返 tenant_name);后端一次性 SQL 加载关联,async session 不会触发 `MissingGreenlet` | selectin 是 SQLAlchemy 防 N+1 的标准策略(2 条 IN 查询 vs N+1);batch helper 是 customer_service 内部耦合,不该跨域复用 |
| **Customer SET NULL 跨租户副作用** | Customer 当前**仅软删**(无硬删端点),FK `ondelete=SET NULL` 是**死保险绳**,实际不会触发;若未来加 Customer 硬删端点,**必须** service 层先校验"该 customer 是否被任意租户的 device 引用",有则拒绝(避免跨租户级联 NULL 掉别人的 device) | 跨租户副作用风险已被"Customer 仅软删"现状规避,但计划显式记录此约束供未来 feature 参考 |

---

## 关键边界(调研里抠出来的硬约束)

1. **`model_id` FK→device_models `ondelete="RESTRICT"`**:型号被 device 引用时禁**硬删**(device-models-crud 当时的约定)。⚠️ **当前 `DeviceModelService.delete` 是软删**(`app/services/device_model_service.py:148-156`,只翻 `is_deleted=True`),**没有硬删端点**,所以 RESTRICT 在现行代码路径下**永不触发**,仅作为"未来若加硬删端点时的死保险绳"。DeviceModel 表本身**无外键**,devices 这条 FK 是单向引用,在 alembic check 下不会冲突。
   - **本 feature 的真实约束(由 service 层主动校验,不靠 FK)**:
     (a) **入库 / 编辑改 model_id 时**:`DeviceService._assert_model_live(model_id)` 必须查 `DeviceModelRepository.get` (L32-37 已带 `is_deleted=False`) 活态型号,BizError 拒软删型号
     (b) **入库下拉只拉活型号**:前端 `useDeviceModels()` 直接调 `/api/v1/device-models/`,该 list 端点已带 `is_deleted=False` 过滤
     (c) **编辑时若 device 已绑定软删型号**:型号 Select 灰显当前型号名 + 禁止改(只读展示),避免误改成另一型号;若用户强行改必须选活型号
2. **`customer_id` 归属校验的特殊性**:Customer 是**平台级**表(无 `tenant_id`,`identity_key` 全局唯一),一个 customer 可在多租户都有 CustomerProfile。所以 bind 校验语义是「**该 customer 在本租户有 live CustomerProfile**」才允许绑定 —— 通过 `CustomerProfileRepository.get_for_tenant` join 校验,**不是**「customer 属于本租户」。
3. **`tenant_id` FK→tenants `ondelete="CASCADE"`**:参照 CustomerProfile。
4. **部分唯一索引 PG/SQLite 双写**:`postgresql_where=is_deleted=false` + `sqlite_where=is_deleted=0`,upgrade **和** downgrade 都要带,否则 autogenerate drift。
5. **CHECK 约束**:`status IN ('active','maintenance','retired')` 用 `CheckConstraint`(SQLite + PG 都兼容,不用 PG ENUM —— PG ENUM 加值要单独迁移,过重)。
6. **conftest model import**:`tests/conftest.py` 的 `from app.models import (...)` 块要加 `Device`,否则测试 schema 不建表(参照 `device_model` 已在块内)。
7. **menu:devices 权限 seed**:要在 `DEFAULT_OWNER_PERMS` / `DEFAULT_ADMIN_PERMS` / `DEFAULT_MEMBER_PERMS` 里加 `menu:devices`,否则侧边栏 member 看不到入口(参照 customers 系列的 `menu:customers` 范式)。

---

## 后端实施

### 1. ORM Model — `app/models/device.py`(新增)

```
Device:
  id            String(32) PK default=_uuid
  tenant_id     String(32) FK→tenants.id ondelete=CASCADE  NOT NULL
  model_id      String(32) FK→device_models.id ondelete=RESTRICT  NOT NULL
  serial_number String(200) NOT NULL
  status        String(20) NOT NULL default='active' server_default='active'
                CheckConstraint("status IN ('active','maintenance','retired')")
  customer_id   String(32) FK→customers.id ondelete=SET NULL  nullable=True
  created_by    String(128) FK→users.id  nullable=True
  is_deleted    Boolean default=False server_default=false  index=True
  deleted_at    DateTime(timezone=True) nullable
  created_at    DateTime(timezone=True) server_default=now()
  updated_at    DateTime(timezone=True) server_default=now() onupdate=now()

  __table_args__:
    uq_devices_tenant_serial_active (tenant_id, serial_number) UNIQUE
       WHERE is_deleted=false (PG) / =0 (SQLite)
    idx_devices_tenant_id (普通索引)
    ck_devices_status_valid CHECK (status IN ('active','maintenance','retired'))
```

### 2. Migration — `alembic/versions/2026_07_22_<HHMM>_<hash>_add_devices_table.py`(新增)

- `down_revision = 'e649e80a4169'`(device_models 是当前 head,Explore 用 `alembic heads` 已确认)
- `create_table` + `CheckConstraint` + 2 个 `create_index`
- `uq_devices_tenant_serial_active` 带 `postgresql_where=sa.text('is_deleted = false')` + `sqlite_where=sa.text('is_deleted = 0')`
- `downgrade` 镜像,`drop_index` 也要带 where(否则 drift)

### 3. Schema — `app/schemas/device.py`(新增)

- `DeviceStatus = Literal["active", "maintenance", "retired"]`
- `DeviceBase` / `DeviceCreate`(model_id + serial_number 必填,customer_id 可选,初始 status 可选默认 active)/ `DeviceUpdate`(全部可选,含 status)/ `DeviceBindRequest`(customer_id: str | None)
- `DeviceRead`(from_attributes,字段:id/tenant_id(本租户读可返)/model_id/serial_number/status/customer_id/created_at/updated_at)
- `DeviceHqRead`(HQ 全景,带 tenant_id/tenant_name/model_name/customer_name,用于跨租户 viewer)

### 4. Repository — `app/repositories/device.py`(新增)

- `DeviceRepository(TenantScopedRepository[Device])`
- 重写 `get_for_tenant` / `list_for_tenant`(加 `is_deleted.is_(False)`,照抄 CustomerProfileRepository 范式)
- `get_by_tenant_serial(tenant_id, serial_number, exclude_id=None)` 唯一性校验
- `list_all_with_meta()` HQ 全景(selectin load tenant/model/customer 名称,或 join)

### 5. Service — `app/services/device_service.py`(新增)

- `OBJECT = "devices"`
- `_get_live_device(device_id, tenant_id)` → NotFoundError if 跨租户/不存在/软删(防 enumeration,跨租户也是 404)
- `_assert_serial_unique(tenant_id, serial, exclude_id=None)` → BizError if 重复
- `_assert_model_live(model_id)` → 通过 `DeviceModelRepository.get`(已带 `is_deleted=False`)校验型号存在且未软删,BizError if 软删/不存在。**这是 model_id 完整性的真实守卫**(FK RESTRICT 因 device_model_service 是软删而永不触发,见 §3 关键边界 #1)
- `_assert_customer_in_tenant(tenant_id, customer_id)` → 通过 `CustomerProfileRepository.get_for_tenant` 查 customer 在本租户是否有 live profile,BizError/NotFoundError if 没有
- `list(actor_id, tenant_id, platform_role)`:`is_cross_tenant_viewer(platform_role)` 分叉(跨租户返回 `DeviceHqRead`,否则 `DeviceRead` + 本租户)
- `get(device_id, tenant_id, platform_role)` 同上
- `create(actor_id, tenant_id, payload, platform_role=None)`:校验 model 存在 + serial 唯一 + customer 归属(可选填)+ `permission_service.require(actor_id, tenant_id, "devices", "create", platform_role=...)`
- `update(device_id, tenant_id, payload, actor_id, platform_role=None)`:校验 serial 唯一(若改)+ customer 归属(若改)+ status 在三态内(由 schema Literal 保证)+ require("devices","update")
- `delete(device_id, tenant_id, actor_id, platform_role=None)`:软删 + require("devices","delete")
- `bind(device_id, tenant_id, customer_id, actor_id, platform_role=None)` → 返回 `(device, already_bound: bool)`:
  - `_assert_customer_in_tenant`(customer 在本租户有 live profile,否则 BizError 400)
  - 若 `device.customer_id == customer_id`:`already_bound=True`,**不写库**(幂等),返 200
  - 否则:`already_bound=False`,set `device.customer_id = customer_id` → flush,返 200
  - `require("devices","update")`
- `unbind(device_id, tenant_id, actor_id, platform_role=None)`:set `customer_id=None`(**无绑定时 no-op 不抛错**,幂等)→ require("devices","update")

### 6. API — `app/api/v1/devices.py`(新增)

- `router = APIRouter(prefix="/devices", tags=["devices"])`
- `GET /` → 200(内联权限分流:`is_cross_tenant_viewer(platform_role)` → 调 `DeviceService.list(actor_id, tenant_id, platform_role)` 拿 `DeviceHqRead`;否则 `require_permission("devices","read")` + 本租户 `DeviceRead`)
  - ⚠️ **hq_staff 跨租户 read 的底层支撑**:`require_permission` 本身会拒 hq_staff(无 tenant role),真正的放行在 `permission_service.check` 的特判 `app/services/permission_service.py:103` `if platform_role == "hq_staff" and act == "read": return True`。所以 `GET /` **不能用 `Depends(require_permission("devices","read"))` 当 router 依赖**(那会直接 403 hq_staff),**必须在端点函数体内分流**:先 `if is_cross_tenant_viewer(user.platform_role): ...` 否则 `await permission_service.require(user.user_id, user.tenant_id, "devices", "read", platform_role=user.platform_role)`。这是 customers-api / device-models-api 当前的写法,本 feature 照抄
- `GET /{id}` → 200(同上)
- `POST /` → 201(`Depends(require_permission("devices","create"))`)
- `PUT /{id}` → 200(`Depends(require_permission("devices","update"))`)
- `DELETE /{id}` → 204(`Depends(require_permission("devices","delete"))`)
- `POST /{id}/bind` → **200**(body: `{device_id, customer_id, already_bound: bool}`,见决策表"bind 幂等性"行;**不是 201**,因 device 资源已存在,bind 是赋值动作不创建新资源)(`Depends(require_permission("devices","update"))`)
- `DELETE /{id}/bind` → 204(同上;**无绑定时也返 204**,DELETE 幂等语义)
- 在 `app/main.py` 注册 `app.include_router(devices.router, prefix=prefix)`

### 7. 权限 seed — `app/services/permission_service.py`

- `DEFAULT_OWNER_PERMS` / `DEFAULT_ADMIN_PERMS` 加 `devices:create/read/update/delete`
- `DEFAULT_MEMBER_PERMS` 加 `devices:read`
- `DEFAULT_MENU_PERMS["owner"]` / `["admin"]` / `["member"]` 各加 `"devices"`(菜单 code,会生成 `menu:devices` 策略)
- **backfill(必须做,否则现存租户权限缺失,功能上线即坏)**:
  - **现状盘点**:`permission_service.py` **没有** backfill 范式可参照 —— `_seed_default_permissions_for_tenant` 只在新建租户时跑(L231-265 流程),`add_policy` / `_upsert_permission` / `RolePermissionRepository.grant` 都幂等可复用,但没有"给老租户补缺失 perm"的函数。原计划"参照 permission-unified-model feature 的 backfill 范式"是**空头支票,该范式不存在**。
  - **本 feature 新增 `backfill_devices_perms_for_existing_tenants(db)` 函数**(放 `permission_service.py` 末尾,或新建 `app/services/permission_backfill.py` 若你想隔离):
    ```
    对每个 tenant in SELECT id FROM tenants WHERE is_deleted=false:
      role_repo = RoleRepository(db); rp_repo = RolePermissionRepository(db)
      role_ids = {role.code: role.id for role in role_repo.list_for_tenant(tenant_id)}
      for role_code, perms in [("owner", DEFAULT_OWNER_PERMS), ("admin", DEFAULT_ADMIN_PERMS), ("member", DEFAULT_MEMBER_PERMS)]:
          for obj, act in perms:
              if obj != "devices": continue   # 只 backfill 本次新增的,不动其他
              pid = await self._upsert_permission(db, tenant_id, obj, act)  # 幂等
              rid = role_ids.get(role_code)
              if rid: await rp_repo.grant(rid, pid, tenant_id)  # 幂等:no-op on dupe
      for role_code, menu_codes in DEFAULT_MENU_PERMS.items():
          for code in menu_codes:
              if code != "devices": continue
              await self.add_policy(role_code, tenant_id, "menu", code)
              pid = await self._upsert_permission(db, tenant_id, "menu", code, perm_type="menu")
              rid = role_ids.get(role_code)
              if rid: await rp_repo.grant(rid, pid, tenant_id)
      await sync_role_permissions_to_casbin(tenant_id)  # 同步到 casbin enforcer
    ```
  - **触发方式二选一**(实施时定):
    (a) **独立一次性脚本** `scripts/backfill_devices_perms.py`,CI 不跑,手动执行一次
    (b) **挂在 `app/main.py` lifespan startup** 里跑一次幂等 backfill,加 `if SETTINGS.run_permission_backfill:` 开关(只在环境变量显式打开时跑)
  - **测试**:`tests/test_devices_api.py` 加测试 K 章节:造一个 backfill 前(无 devices 策略)的租户 fixture → 跑 backfill → 断言 owner 拿到 `devices:create`、member 拿到 `devices:read`、`menu:devices` 在 owner/admin/member 三角色都生效
  - **CI 影响**:幂等,重复跑 no-op,不会破坏其他租户的策略

### 8. 测试 — `tests/test_devices_api.py`(新增,~35 用例)

章节布局参照 `test_device_models_api.py` + `test_customers_api.py` + `test_groups_api.py`:

- **A. owner/admin CRUD**:create + list + get + update + delete,断言全字段
- **B. 跨租户隔离**:造 `tnt-iso-2` 的 device → list 看不到 + GET/PUT/DELETE → 404(防 enumeration)
- **C. (tenant_id, serial_number) 唯一约束**:同租户同 serial 重复 → 400;软删后可复用 → 201
- **D. 权限矩阵**:member 只读(写 → 403)、hq_staff 跨租户只读(写 → 403,读拿到 HQ 全景字段)、unauth → 401
- **E. super_admin 全景**:读全租户 + 写
- **F. bind/unbind**:bind 成功 **200 + `already_bound:false`**、重复 bind(同 customer)→ **200 + `already_bound:true`**(不写库)、bind 不同 customer(覆盖)→ **200**、unbind 成功 204、**unbind 未绑定的 device → 204**(幂等 no-op,非 404)、跨租户 customer 绑定 → 400(BizError)、bind 不存在的 customer → 400(BizError)
- **G. 状态切换**:PUT 改 status active→maintenance→retired→active 全部合法;非法值(如 'online')→ schema 422 拒
- **H. model_id 完整性(service 层守卫,不靠 FK RESTRICT)**:
  - H1 入库时传已软删的 model_id → 400 BizError(由 `_assert_model_live` 拦)
  - H2 入库时传不存在的 model_id → 400 BizError
  - H3 编辑改 model_id 指向软删型号 → 400 BizError
  - H4 软删型号已存在的 device 引用,该 device GET 仍能返回(型号只读展示,不崩)
  - H5 软删型号不出现在入库下拉(依赖 `/api/v1/device-models/` 已带 `is_deleted=False` 过滤,本 feature 不再重复实现)
  - **说明**:`ondelete=RESTRICT` 仅是死保险绳(当前无硬删端点触发它),不写"RESTRICT 拦截"测试 —— 那是虚构测试

### 9. conftest model import

`tests/conftest.py` 的 `from app.models import (...)` 块加 `Device`(`# isort:skip` 那个块,参照 device_model 已在列)。
- **注意**:`app/models/__init__.py` 是空文件(项目惯例:不 re-export,按 module 路径 `from app.models.device import Device` 导入)。conftest 那个块是 `from app.models.device_model import DeviceModel` 这种**按文件路径**导入,所以加 `from app.models.device import Device` 一行即可,不涉及 `__init__.py` 改动。**核 `tests/conftest.py:126` 当前 `device_model` 写法是 module 名还是 re-export**,实施时按相同模式加。

### 10. backfill 测试 — 新增 K 章节

`tests/test_devices_api.py` 加 K 章节(参照 §7 backfill 方案):
- K1 造一个**没有 devices 策略**的租户 fixture(直接调 `_seed_default_permissions_for_tenant` 前的状态,或临时 revoke 掉 owner/admin/member 的 devices:*)
- K2 跑 `backfill_devices_perms_for_existing_tenants(db)`
- K3 断言:该租户 owner 拿到 `devices:create/read/update/delete` + `menu:devices`(调 `permission_service.check` 验证)
- K4 断言:member 拿到 `devices:read` + `menu:devices`,**没有** `devices:create`(防过度授权)
- K5 断言:幂等性 —— 再跑一次 backfill,断言不报错、不重复 grant、行为不变
- K6 断言:其他既有权限(如 `customers:read`)不受 backfill 影响(只动 devices/menu:devices 相关)

---

## 前端实施

### 1. `frontend/src/api/types.ts`

加 `Device`、`DeviceCreate`、`DeviceUpdate`、`DeviceBindRequest`、`DeviceModelPublic`(只有 id/name/specs)。

### 2. `frontend/src/api/endpoints.ts`

加 `fetchDevices()`、`fetchDevice(id)`、`createDevice(payload)`、`updateDevice(id, payload)`、`deleteDevice(id)`、`bindDeviceCustomer(id, customerId)`、`unbindDeviceCustomer(id)`、`fetchDeviceModels()`(对 `/api/v1/device-models/`,普通用户返回 `DeviceModelPublicRead`)。

### 3. `frontend/src/hooks/queries.ts`

- `qk.devices`、`qk.deviceModels`
- `useDevices()`、`useCreateDevice()`、`useUpdateDevice()`、`useDeleteDevice()`、`useBindDeviceCustomer()`、`useUnbindDeviceCustomer()`
- `useDeviceModels()`(下拉用,enabled 守卫参照 `useAllTenants`)

### 4. `frontend/src/pages/devices-page.tsx`(新增,参照 customers-page.tsx 骨架)

- 顶层 `isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : <StoreView/>`
  - ⚠️ **`isHQStaff` 当前不存在**(`frontend/src/lib/permission.ts:27` 只有 `isSuperAdmin`),本 feature 必须**新增 `isHQStaff(me)` helper**(参照 `isSuperAdmin` 范式:`return me?.platform_role === "hq_staff";`)
  - ⚠️ **customers-page.tsx:127 当前是 `isSuperAdmin(me) ? <HqView/> : <StoreView/>`**(不含 hq_staff)—— 这是 customers-page 的既存遗漏。**本 feature 不修 customers-page**(WIP=1 越界),但 devices-page 必须用 `isSuperAdmin(me) || isHQStaff(me)`。同时在文档影响评估里记一条:"customers-page 的 HqView 对 hq_staff 不可见,是既存 bug,建议下个 customer feature 修"
- **StoreView**:
  - 列表 Table:序列号 / 型号名 / 状态 Badge / 绑定客户 / 创建时间 / 操作 DropdownMenu
  - 状态用 `<Badge variant="dot-success|dot-warning|dot-destructive">` 映射 active→运行中 / maintenance→维护中 / retired→已退役
  - 入库 Dialog:`useDeviceModels()` 填型号 Select + serial_number Input + 初始 status Select(active 默认)
  - 编辑 Dialog:serial_number + status(Select 三态)+ customer Select(可选,用 `useCustomerProfiles()`)
  - 绑定客户 Dialog:复用 chat-page.tsx:685-707 那个内联 Select 范式(从 `useCustomerProfiles()` 拉)+ 「不绑定」选项
  - 删除确认 Dialog(destructive)
  - `canCreate`/`canUpdate`/`canDelete` 通过 `hasPermission(me,"devices",act)` 隐藏按钮
- **HqView**(参照 customers-page HqView 范式):
  - 跨租户表格,每行展示 tenant_name,只读,无写按钮
  - 同样用 Badge 显示状态

### 5. `frontend/src/App.tsx`

- `const DevicesPage = lazy(() => import("@/pages/devices-page").then(...))`
- `<Route path="/devices" element={<DevicesPage />} />`(裸 ProtectedRoute,member 可读)

### 6. `frontend/src/components/layout/nav-items.ts`

- 在「管理 / 业务管理」subgroup 加 `{ to: "/devices", label: "设备", icon: <Monitor/>, menuCode: "menu:devices" }`(用 lucide-react Monitor 或 Smartphone icon)

---

## 验证清单(对照 feature_list.json 的 verification 字段 5 条逐项)

- [ ] 后端:POST/GET/PUT/DELETE /api/v1/devices + POST/DELETE /devices/{id}/bind 全实现
- [ ] TenantScopedRepository 强制 tenant_id 过滤(`get_for_tenant` / `list_for_tenant` 重写)
- [ ] 部分唯一索引 `(tenant_id, serial_number WHERE is_deleted=False)` PG + SQLite 双写
- [ ] 权限矩阵:owner/admin 写、member 只读、super_admin 跨租户只读、hq_staff 跨租户只读(底层由 `permission_service.check` 的 `platform_role == "hq_staff" and act == "read"` 特判 + `is_cross_tenant_viewer` 分叉实现,非仅靠三守卫)
- [ ] `device.customer_id` FK→customers SET NULL
- [ ] `device.model_id` FK→device_models RESTRICT(死保险绳)+ service 层 `_assert_model_live` 是真实守卫
- [ ] pytest 覆盖:CRUD + 租户隔离 404 + 权限矩阵 + 唯一约束 + 软删 + bind/unbind + model_id 完整性(软删/不存在型号 → 400)
- [ ] `alembic upgrade head && alembic check` 无 drift(本地若 docker 起不来,依赖 CI)
- [ ] `cd frontend && npm run build` 通过
- [ ] `cd frontend && npx oxlint` 0 error
- [ ] `./init.sh` 全绿
- [ ] feature_list.json:`devices-crud-ui` status=passing + evidence
- [ ] `./scripts/sync-active-features.sh` 刷新 active 视图
- [ ] progress.md 加 Session 记录 + 更新「当前最高优先级未完成功能」
- [ ] 文档影响评估(4 行格式)

---

## 不做清单(边界声明,避免越界)

- ❌ 真实硬件下发链路(MQTT/WS/寻址)—— device-poweron feature 也不做
- ❌ IoT 上报 / device_metrics 表 —— 未来 backlog
- ❌ 「设备是否正被占用」语义 —— 由 bookings 派生(`WHERE device_id=? AND status='in_service'`),不是 devices.status 的职责
- ❌ device-models 的前端管理页 —— 单独 feature
- ❌ 预约排期 / bookings 表 —— device-booking feature
- ❌ `kind` 字段(物理形态由 model.specs 表达)
- ❌ StorePilot 的 online/offline/low_battery/maintenance 混合状态(在无 IoT 上报链路的当下,在线状态会变成永远 stale 的脏数据)

---

## 实施切片(7 个 tracer-bullet 垂直切片,每个切片一个 context window 完成)

> 切片原则:每切片是窄而全的垂直切片(Model→Migration→Repo→Service→API→测试/前端闭环),不是按层水平切。每切片可独立 demo/verify。阻塞边明确,frontier 上无 blocker 的切片可立即开工。
>
> 实施节奏:一次一个切片,用 `/implement` 推进,切片间清 context。WIP=1 仍然适用 —— 同一时刻只在一个切片上 in_progress,该切片全绿(测试 + verification 清单对应项)才进下一个。

### 切片 01 — 后端地基:Device 表 + 软删租户隔离 CRUD + model_id 完整性

**Blocked by:** 无 —— 可立即开工

**What it delivers:** 一个 tenant 内的 owner 能创建/读/改/删本店设备实例(选活型号 + 填序列号 + 填初始状态),member 只读,跨租户 GET/PUT/DELETE 返 404 防 enumeration。本切片**不含**客户绑定、不含 HQ 全景、不含前端、不含权限 backfill。

**Acceptance criteria:**
- [ ] `app/models/device.py`:`Device` ORM model(audit 列 / 软删 / FK 写法对齐 `CustomerProfile`)
- [ ] alembic 迁移:down_revision=`e649e80a4169`,`create_table` + `CheckConstraint(status IN (...))` + 2 个 `create_index`(普通索引 + 部分唯一索引 `uq_devices_tenant_serial_active`,**upgrade 和 downgrade 都带 `postgresql_where=is_deleted=false` + `sqlite_where=is_deleted=0`**,防 drift)
- [ ] `app/schemas/device.py`:`DeviceStatus = Literal[...]`、`DeviceBase`/`DeviceCreate`/`DeviceUpdate`/`DeviceRead`
- [ ] `app/repositories/device.py`:`DeviceRepository(TenantScopedRepository[Device])`,重写 `get_for_tenant`/`list_for_tenant` 加 `is_deleted.is_(False)`,新增 `get_by_tenant_serial(tenant_id, serial, exclude_id=None)`
- [ ] `app/services/device_service.py`:`_get_live_device`(跨租户/不存在/软删 → NotFoundError)、`_assert_serial_unique`(→ BizError)、`_assert_model_live`(软删/不存在型号 → BizError,**真实守卫**,FK RESTRICT 因软删永不触发)、`create`/`update`/`delete`
- [ ] `app/api/v1/devices.py`:`GET/POST/PUT/DELETE /api/v1/devices`(本切片用 router-level `require_permission("devices","read/create/update/delete")`,HQ 分流留给切片 03 替换)+ `app/main.py` 注册 router
- [ ] `tests/conftest.py` 的 `from app.models import (...)` 块加 `Device`(按 module 路径,参照 `device_model` 写法)
- [ ] `tests/test_devices_api.py` 章节:A(CRUD 全字段断言)+ B(跨租户 404 防 enumeration)+ C(同租户同 serial 重复 → 400,软删后可复用 → 201)+ D(member 写 → 403,unauth → 401)+ G(状态切换 active↔maintenance↔retired 全合法,非法值 → 422)+ H(model_id 完整性 H1-H5:软删/不存在型号 → 400、软删型号已引用 device GET 不崩)
- [ ] 本地 `alembic upgrade head` 通过(SQLite 内存库)

---

### 切片 02 — 权限 seed + 老租户 backfill(不破坏现存租户)

**Blocked by:** 01(devices obj/act 已在 Service 里被 require,backfill 才有目标)

**What it delivers:** 新建租户的 owner/admin/member 自动拿到 devices 权限和 `menu:devices`;**现存所有租户**也能拿到(backfill 幂等),功能上线即用,不破坏其他 perm。

**Acceptance criteria:**
- [ ] `app/services/permission_service.py`:`DEFAULT_OWNER_PERMS`/`DEFAULT_ADMIN_PERMS` 加 `devices:create/read/update/delete`;`DEFAULT_MEMBER_PERMS` 加 `devices:read`
- [ ] `DEFAULT_MENU_PERMS["owner"|"admin"|"member"]` 各加 `"devices"` code(对应 `menu:devices`)
- [ ] 新增 `backfill_devices_perms_for_existing_tenants(db)` 函数:扫 `tenants` 表未软删租户,对每个租户的 owner/admin/member role 幂等补 devices 相关 perm(调 `_upsert_permission` + `RolePermissionRepository.grant` + `sync_role_permissions_to_casbin`),**只动 devices/menu:devices 相关,不碰其他 perm**
- [ ] `scripts/backfill_devices_perms.py` 独立一次性脚本(async main + DB session 初始化 + 调上述函数 + 打印每租户补了几条),CI 不跑,手动执行一次
- [ ] `tests/test_devices_api.py` K 章节:K1 造无 devices 策略租户 fixture → K2 跑 backfill → K3 owner 拿全 + `menu:devices` → K4 member 只 `devices:read` + `menu:devices`(防过度授权)→ K5 幂等(再跑 no-op 不报错)→ K6 其他 perm(如 `customers:read`)不受影响

---

### 切片 03 — HQ 全景视图(后端,跨租户只读)

**Blocked by:** 01(共用 DeviceService 骨架)

**What it delivers:** super_admin 和 hq_staff 能看到跨所有租户的设备全景(带 tenant_name / model_name / customer_name),hq_staff 写端点返 403。

**Acceptance criteria:**
- [ ] `app/schemas/device.py` 加 `DeviceHqRead`(全景字段:tenant_id/tenant_name/model_name/customer_name)
- [ ] `app/repositories/device.py` 加 `list_all_with_meta()` / `get_all_with_meta(device_id)`:用 `selectinload(Device.tenant)` / `selectinload(Device.model)` / `selectinload(Device.customer)`(防 N+1,防 async session `MissingGreenlet`),**不复用** `customer.batch_tenant_info`(那是 customer 域耦合)
- [ ] `app/services/device_service.py`:`list(actor_id, tenant_id, platform_role)` / `get(...)` 接 `platform_role` 参数,用 `is_cross_tenant_viewer(platform_role)` 分叉返 `DeviceHqRead` vs `DeviceRead` + 本租户
- [ ] `app/api/v1/devices.py`:`GET /` 和 `GET /{id}` **改为端点函数体内分流**(`if is_cross_tenant_viewer(user.platform_role): → 全景`;否则 `await permission_service.require(user.user_id, user.tenant_id, "devices", "read", platform_role=user.platform_role)`),**移除切片 01 临时用的 router-level `require_permission("devices","read")` 依赖**(否则 hq_staff 被直接 403,放行路径在 `permission_service.check:103` 特判)
- [ ] `tests/test_devices_api.py` HQ 章节:super_admin 拿全景字段且能读跨租户 device、hq_staff 拿全景字段 + 写端点(create/update/delete/bind)返 403
- [ ] 决策记录:本切片暴露 customers-page 当前 HqView 对 hq_staff 不可见的**既存 bug**,不在本切片修(WIP=1),写入文档影响评估

---

### 切片 04 — 客户绑定端点(bind/unbind,幂等语义)

**Blocked by:** 01(共用 `_get_live_device` + DeviceService 骨架)

**What it delivers:** owner/admin 能给设备绑定/解绑客户。bind 同 customer 幂等返 `already_bound:true`,bind 跨租户/不存在 customer → 400,unbind 无绑定时幂等返 204。

**Acceptance criteria:**
- [ ] `app/schemas/device.py` 加 `DeviceBindRequest(customer_id: str | None)` + `DeviceBindResponse(device_id, customer_id, already_bound: bool)`
- [ ] `app/services/device_service.py`:
  - `bind(device_id, tenant_id, customer_id, actor_id, platform_role)` → 返 `(device, already_bound: bool)`:`_assert_customer_in_tenant`(走 `CustomerProfileRepository.get_for_tenant`,失败 BizError 400);`device.customer_id == customer_id` 则 `already_bound=True` 不写库,否则覆盖 `already_bound=False`;`require("devices","update")`
  - `unbind(device_id, tenant_id, actor_id, platform_role)`:set `customer_id=None`,**无绑定时 no-op 不抛错**,`require("devices","update")`
- [ ] `app/api/v1/devices.py`:
  - `POST /{id}/bind` → **200**(body: `DeviceBindResponse`,**不是 201**,device 资源已存在,bind 是赋值动作),`Depends(require_permission("devices","update"))`
  - `DELETE /{id}/bind` → **204**(无绑定也 204,DELETE 幂等),同上守卫
- [ ] `tests/test_devices_api.py` F 项全 8 条:bind 成功 200 + `already_bound:false`、重复 bind 同 customer → 200 + `already_bound:true`、bind 不同 customer 覆盖 → 200、unbind 成功 204、unbind 未绑定 device → 204(非 404)、跨租户 customer bind → 400、不存在 customer bind → 400、member bind → 403

---

### 切片 05 — 前端地基:types/endpoints/queries + isHQStaff + 路由

**Blocked by:** 03(`DeviceHqRead` schema 定型),04(`DeviceBindResponse` schema 定型)

**What it delivers:** 前端拿到 devices/device-models 的完整类型和 API client,hq_staff 在前端可被识别,`/devices` 路由可达(空页即可,UI 实现留给切片 06/07)。

**Acceptance criteria:**
- [ ] `frontend/src/api/types.ts`:`Device`、`DeviceCreate`、`DeviceUpdate`、`DeviceBindRequest`、`DeviceBindResponse`、`DeviceHqRead`、`DeviceModelPublic`(`{id, name, specs}`,未来 device-models 管理页共用此类型)
- [ ] `frontend/src/api/endpoints.ts`:`fetchDevices()`、`fetchDevice(id)`、`createDevice(payload)`、`updateDevice(id, payload)`、`deleteDevice(id)`、`bindDeviceCustomer(id, customerId)`、`unbindDeviceCustomer(id)`、`fetchDeviceModels()`(打 `/api/v1/device-models/`,返 `DeviceModelPublicRead`)
- [ ] `frontend/src/hooks/queries.ts`:`qk.devices` / `qk.deviceModels` + `useDevices()`、`useCreateDevice()`、`useUpdateDevice()`、`useDeleteDevice()`、`useBindDeviceCustomer()`、`useUnbindDeviceCustomer()`、`useDeviceModels()`(下拉用,enabled 守卫参照 `useAllTenants`)
- [ ] `frontend/src/lib/permission.ts`:新增 `isHQStaff(me)` helper(参照 `isSuperAdmin` L27-29 范式)
- [ ] `frontend/src/App.tsx`:`const DevicesPage = lazy(...)` + `<Route path="/devices" element={<DevicesPage/>}/>`(裸 ProtectedRoute,member 可读)
- [ ] `frontend/src/components/layout/nav-items.ts`:业务管理 subgroup 加 `{ to: "/devices", label: "设备", icon: <Monitor/>, menuCode: "menu:devices" }`
- [ ] `cd frontend && npm run build` + `npx oxlint` 通过

---

### 切片 06 — 前端 StoreView(门店设备管理页)

**Blocked by:** 05

**What it delivers:** 门店 owner/admin 在 `/devices` 看到本店设备表格,能入库/改状态/绑定客户/解绑/软删;member 只读,写按钮按 `hasPermission` 隐藏。

**Acceptance criteria:**
- [ ] `frontend/src/pages/devices-page.tsx` StoreView:列表 Table(序列号 / 型号名 / 状态 Badge / 绑定客户 / 创建时间 / 操作 DropdownMenu)
- [ ] 状态 Badge 映射:active→运行中(dot-success)/ maintenance→维护中(dot-warning)/ retired→已退役(dot-destructive)
- [ ] 入库 Dialog:`useDeviceModels()` 填型号 Select(只活型号,API 已过滤)+ serial_number Input + 初始 status Select(active 默认)
- [ ] 编辑 Dialog:serial_number + status 三态 Select + customer Select(可选,`useCustomerProfiles()`)+ 「不绑定」选项
- [ ] **软删型号 UX**(plan §3 关键边界 #1-c):device 已绑定软删型号时,编辑 Dialog 型号字段只读灰显当前型号名,不允许改成软删型号
- [ ] 绑定客户 Dialog:内联 Select 范式参照 `chat-page.tsx:685-707`,从 `useCustomerProfiles()` 拉
- [ ] 删除确认 Dialog(destructive variant)
- [ ] `canCreate`/`canUpdate`/`canDelete` 用 `hasPermission(me,"devices",act)` 隐藏写按钮
- [ ] `cd frontend && npm run build` + `npx oxlint` 通过

---

### 切片 07 — 前端 HqView + 整体验证收尾

**Blocked by:** 06

**What it delivers:** super_admin 和 hq_staff 在 `/devices` 看到跨租户只读全景表格;整 feature 走完 `./init.sh` 全绿 + feature_list.json/progress.md 更新 + 文档影响评估。

**Acceptance criteria:**
- [ ] `devices-page.tsx` 顶层 `isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : <StoreView/>`
- [ ] HqView:跨租户表格(列:tenant_name / 序列号 / 型号名 / 状态 Badge / 绑定客户),只读,无写按钮
- [ ] **不修 customers-page.tsx**(WIP=1,既存 hq_staff 不可见 bug 留给后续 customer feature)
- [ ] `./init.sh` 全绿(ruff + pytest 全章节 A-K + frontend build + oxlint)
- [ ] `alembic upgrade head && alembic check` 本地通过(若本地 docker 起不来,依赖 CI 通过)
- [ ] `feature_list.json`:`devices-crud-ui` status=`passing` + evidence 字段写实测结果
- [ ] `./scripts/sync-active-features.sh` 刷新 active 视图
- [ ] `progress.md` 加 Session 记录 + 更新「当前最高优先级未完成功能」指向 device-booking
- [ ] 文档影响评估(4 行格式):含"customers-page HqView 对 hq_staff 不可见"既存 bug 记录(供下个 customer feature 修)

---

### 切片依赖图

```
01 (后端地基) ──┬─→ 02 (权限 seed + backfill)
               ├─→ 03 (HQ 全景后端) ──┐
               └─→ 04 (bind/unbind) ──┤
                                       ↓
                               05 (前端地基) ──→ 06 (StoreView) ──→ 07 (HqView + 收尾)
```

**Frontier 推进策略**:
- 切片 01 完成后,02/03/04 三者可并行(三个不同 in_progress 上下文),但 WIP=1 要求**串行** —— 推荐 02 → 03 → 04 顺序(02 是上线即用必备,03 改动 01 的 API 守卫最好早做避免后续返工,04 相对独立)
- 切片 05 等 03+04 都完成(HQ + bind schema 都定型)
- 切片 06 → 07 严格串行

---

## 调研证据(Explore 三路并行,2026-07-22)

| 关键论点 | 出处 |
|---|---|
| `TenantScopedRepository.get_for_tenant` 强制 tenant_id 过滤 | `app/repositories/base.py` |
| `CustomerProfileRepository` 是 TenantScopedRepository + 软删重写范式 | `app/repositories/customer.py` L136-165 |
| 迁移链当前 head = `e649e80a4169`(device_models) | `alembic heads` 实测 |
| 多列部分唯一索引写法 | `alembic/versions/2026_07_12_0710_6f197cf8f964_add_customers_and_customer_profiles_.py` |
| attach/detach 端点范式(POST + DELETE `{parent}/{id}/{child}/{cid}`) | `app/api/v1/groups.py` L104-127 |
| 404 防 enumeration(Service 用 get_for_tenant 统一抛 NotFoundError) | `app/services/customer_service.py` L104-110 |
| 全局异常 handler(NOT_FOUND→404 / BIZ→400 / PERMISSION→403) | `app/main.py` L287-312 |
| `require_permission` / `require_super_admin` / `require_cross_tenant_viewer` 三守卫 | `app/api/deps.py` L241-299 |
| 前端门店 CRUD 页骨架 + 双视图 | `frontend/src/pages/customers-page.tsx` |
| 前端 API client 三件套(client/endpoints/types/queries) | `frontend/src/api/*` + `frontend/src/hooks/queries.ts` |
| 前端下拉数据源范式 | `frontend/src/pages/logs-page.tsx:89-94`(`useAllTenants` + enabled) |
| 客户选择器内联范式 | `frontend/src/pages/chat-page.tsx:685-707` |
| oxlint 配置(只 2 条规则,0 error 判据) | `frontend/.oxlintrc.json` |
| conftest fixtures 清单 + super_admin_client 副作用警告 | `tests/conftest.py` |
| 部分唯一索引测试范式 | `tests/test_device_models_api.py:153` `test_super_admin_delete_soft_then_name_reusable` |
