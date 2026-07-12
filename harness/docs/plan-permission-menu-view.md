# 计划:菜单/视图权限(权限重构系列 2/4)

> 对应 feature_list.json 的 `id`: `permission-menu-view`
> 状态: not_started
> 优先级: 40
> 前置: `permission-unified-model`(目录统一后,菜单权限作为目录的一类纳入)
> 系列总纲: [`plan-permission-redesign-overview.md`](plan-permission-redesign-overview.md)

---

## 背景:前端菜单可见性与权限矩阵脱钩

### 现状(2026-07-12 核实)

前端菜单/页面可见性由**两套硬编码布尔**驱动,完全和权限矩阵无关:

| 位置 | 机制 | 问题 |
|---|---|---|
| `dashboard-layout.tsx` `NAV_ITEMS` | 每个菜单项打 `needsSuperAdmin` / `needsUserManagement` 标签 | 可见性写死在代码里,管理员无法通过权限矩阵配置 |
| `lib/permission.ts` `canManageUsers` | 硬编码 `{owner, admin}` 集合 + super_admin | 只能表达「用户管理」这一类,无法细到「能不能看客户页」 |
| `require-permission.tsx` / `require-super-admin.tsx` | 路由守卫同样硬编码 | 普通成员手输 URL 会被拦,但拦截逻辑不可配 |

**后果**:用户说的「没有视图权限」——管理员在权限矩阵里勾什么,都影响不了菜单显示。菜单可见性是另一套独立、硬编码的系统。

### 目标

引入 `type="menu"` 权限类型,让**菜单/页面可见性可配置**:
1. 每个菜单/页面注册一个 menu 权限项(如 `menu:agents`、`menu:customers`)
2. 角色通过 grant/revoke 配置可见哪些菜单
3. 前端导航 + 路由守卫从权限判断,不再硬编码
4. 超管自动拥有全部 menu 权限(bypass 不变)

### 关键设计:menu 是 api 的 UX 影子

> **重要约定**:menu 权限是 **UX 层**,不是安全边界。真正能否访问由 api 权限在后端兜底。
> - 一个角色有 `menu:customers` 但无 `customers:read` → 看得到菜单,点进去 403(后端拦)
> - 一个角色无 `menu:customers` 但有 `customers:read` → 看不到菜单,但手输 URL 后端放行(这种配置不推荐,但允许)
> - 通常 menu + 对应 api 的 read 一起 grant,UI 上提供「一键授权查看」联动

---

## 前置条件

- `permission-unified-model` 完成(权限目录已统一,`Permission.type` 字段就绪,seed 机制幂等)

---

## 实施步骤

### 第一阶段:定义菜单权限目录

#### Step 1:盘点前端所有菜单/页面,生成 menu 权限清单

- **做什么**:遍历 `frontend/src/components/layout/dashboard-layout.tsx` 的 `NAV_ITEMS` + 所有路由,列出需要 menu 权限的页面:
  | menu code | 对应页面 | 当前控制 |
  |---|---|---|
  | `menu:dashboard` | / | 全员 |
  | `menu:agents` | /agents | 全员 |
  | `menu:chat` | /chat | 全员 |
  | `menu:customers` | /customers | 全员 |
  | `menu:groups` | /groups | 全员 |
  | `menu:members` | /members | needsUserManagement |
  | `menu:users` | /users | needsUserManagement |
  | `menu:roles` | /roles | needsUserManagement |
  | `menu:permissions` | /permissions | needsUserManagement |
  | `menu:settings` | /settings | needsUserManagement |
  | `menu:tenants` | /tenants | needsSuperAdmin(平台级) |
- **检查**:清单覆盖所有顶层路由,无遗漏

#### Step 2:Permission.type 启用 "menu" + seed 菜单权限项

- **改什么**(`app/services/permission_service.py`):
  - 新增 `DEFAULT_MENU_PERMS` 常量:每个角色默认可见哪些菜单
    - owner: 全部 menu
    - admin: 除 menu:tenants(平台级)外全部
    - member: menu:dashboard/agents/chat/customers(业务菜单)
  - `seed_tenant_defaults` 里:`_upsert_permission` 创建 `type="menu"` 的权限项(code 如 `menu:agents`,name 如「菜单-智能体」)
  - grant 给对应角色(casbin 策略 + SCD2 同步)
- **注意**:`menu:tenants` 是平台级菜单,**不进租户 seed**(租户内配不了平台菜单);它由 `super_admin` bypass 覆盖
- **检查**:新建租户后 GET `/permissions/catalogue?type=menu` 返回全部菜单项

#### Step 3:catalogue 端点支持 type 过滤

- **改什么**(`app/api/v1/permissions.py`):
  - `GET /permissions/catalogue` 加可选 query `?type=menu|api`,默认返回全部
  - 矩阵端点的 `permissions` 数组含 type 字段,前端可按 type 分组渲染
- **改什么**(`app/schemas/rbac.py` `PermissionItem`):加 `type: str` 字段
- **检查**:GET `/permissions/catalogue?type=menu` 只返回菜单项

### 第二阶段:后端校验适配

#### Step 4:menu 权限的校验策略(关键决策)

- **决策**:menu 权限**是否要后端校验**?
  - **选项 A(推荐):menu 权限不进 `require_permission`,纯前端 UX**。理由:menu 是 UX 影子,后端真正拦的是 api 权限(如 `customers:read`)。如果 menu 也后端校验,会出现「有 menu:customers 但手输 URL 被拦」的怪异行为——但后端拦它的是 `customers:read` 的 api 权限,不是 menu 权限。
  - 选项 B:menu 也进后端校验(每页加 `require_permission("menu", "xxx")`)——冗余,且和 api 权限重复
- **采用 A**:menu 权限只驱动前端,**后端路由守卫保持现有 `require_permission(obj, act)` 的 api 校验不变**
- **检查**:确认不改 `app/api/deps.py`;menu 权限只在前端消费

### 第三阶段:前端改造(核心)

#### Step 5:MeResponse 暴露 menu 权限清单

- **改什么**(`app/schemas/auth.py` `MeResponse`):
  - 加 `permissions: list[str]` 字段(当前生效的全部权限 code,含 menu 和 api 两类)
  - 或更省带宽:加 `menus: list[str]`(只 menu code)+ 保留现有 `roles`
- **改什么**(`app/api/v1/auth.py` `/me` 端点):
  - 查当前用户在当前租户的全部生效权限(casbin 或 SCD2 当前态),填入 MeResponse
  - super_admin → permissions/menus 返回全部(或前端 bypass 判断)
- **检查**:登录后 GET `/me` 返回 `menus: ["menu:dashboard", "menu:agents", ...]`

#### Step 6:前端导航 + 路由守卫改用 menu 权限

- **改什么**(`frontend/src/lib/permission.ts`):
  - 加 `canViewMenu(me, menuCode): boolean` —— `super_admin` 直接 true,否则查 `me.menus.includes(menuCode)`
  - 保留 `canManageUsers` 向后兼容(或标记 deprecated,逐步迁移)
- **改什么**(`frontend/src/components/layout/dashboard-layout.tsx`):
  - `NAV_ITEMS` 每项加 `menuCode: "menu:agents"` 字段
  - 过滤逻辑改为 `canViewMenu(me, item.menuCode)`
  - 删除 `needsSuperAdmin` / `needsUserManagement` 标签(由 menu 权限替代)
  - `menu:tenants` 单独处理:super_admin 专属,不进租户 menu 权限,前端按 `platform_role === "super_admin"` 显示
- **改什么**(`frontend/src/components/auth/require-permission.tsx` / `require-super-admin.tsx`):
  - 路由守卫改用 `canViewMenu`(或保留 super_admin 守卫给平台路由)
- **检查**:`npm run build` 通过;member 登录只看到 dashboard/agents/chat/customers;owner 看到全部(除 tenants);super_admin 看到全部含 tenants

#### Step 7:权限矩阵页显示 menu 权限分区

- **改什么**(`frontend/src/pages/permissions-page.tsx`):
  - 矩阵按 `type` 分两大区:上区「菜单权限」(menu 项)、下区「操作权限」(api 项)
  - 或加 tab 切换(菜单/操作)
  - 注意:完整重写(含超管锁定行)是任务 4,本任务只让 menu 权限**能显示能编辑**,UI 美化留给任务 4
- **检查**:矩阵页能看到并勾选 menu 权限项

### 第四阶段:测试 + 总验证

#### Step 8:补测试

- **后端**(`tests/test_permissions_api.py`):
  - catalogue?type=menu 返回全部菜单项
  - 新建租户 owner 持有全部 menu,member 只持有业务 menu
  - grant/revoke menu 权限 → MeResponse 反映
  - 跨租户隔离:menu 权限租户级隔离
- **前端**:`npm run build` + 手动验证菜单可见性随角色变化

#### Step 9:总验证

- **命令**:
  ```bash
  ./init.sh
  cd frontend && npm run build
  ```
- **通过标准**:
  - 后端测试全绿
  - 前端 build 通过
  - member 登录菜单变少(只业务菜单);改 member 的 menu 权限 → 菜单实时变
  - 超管看到全部菜单
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. `Permission.type="menu"` 启用,seed 生成全部菜单权限项(`menu:dashboard`/`menu:agents`/...)
2. `GET /permissions/catalogue?type=menu` 返回菜单项
3. `MeResponse` 暴露当前用户 menu 权限清单
4. 前端导航 + 路由守卫从 `canViewMenu` 判断,删除 `needsSuperAdmin`/`needsUserManagement` 硬编码(tenants 例外,仍按 platform_role)
5. 权限矩阵页可配置 menu 权限(完整 UI 美化留给任务 4)
6. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| MeResponse 变重(带全部权限码) | 只带 menu code(≤12 项),api 权限不进 MeResponse(前端按需查矩阵);或用位图压缩 |
| 老用户 menu 权限缺失(种子没跑) | backfill:现有租户的 owner/admin/member 按 DEFAULT_MENU_PERMS 补 grant(可并入任务 1 的 backfill 脚本) |
| menu:tenants 是平台级,租户配不了 | 前端按 `platform_role === "super_admin"` 硬显示该菜单;不进租户 seed |
| 删 needsUserManagement 后行为回归 | 逐页验证:members/users/roles/permissions/settings 五页对 member 隐藏;owner 全见 |
| menu 和 api read 联动 | UI 提供「授权查看」快捷按钮(同时 grant menu:xxx + xxx:read);不强制联动,允许独立配 |

### 不做的事(边界)

- 不加 data_scope(任务 3)
- 不做矩阵 UI 完整重写(超管锁定行等,任务 4)
- 不改后端 `require_permission` 机制(menu 不进后端校验)
- 不做按钮级权限(本任务只做页面/菜单级;按钮级后续按需)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-permission-redesign-overview.md` |
| 前端导航(待改) | `frontend/src/components/layout/dashboard-layout.tsx` `NAV_ITEMS` |
| 前端权限判断(待改) | `frontend/src/lib/permission.ts` |
| 路由守卫(待改) | `frontend/src/components/auth/require-permission.tsx` |
| MeResponse(待改) | `app/schemas/auth.py` |
| catalogue 端点(待改) | `app/api/v1/permissions.py` |
| seed 逻辑(待改) | `app/services/permission_service.py` `seed_tenant_defaults` |
