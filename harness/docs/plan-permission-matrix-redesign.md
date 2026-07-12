# 计划:权限矩阵 UI 重写(超管锁定行 + 菜单/操作分区 + data_scope 选择器)(权限重构系列 4/4)

> 对应 feature_list.json 的 `id`: `permission-matrix-redesign`
> 状态: not_started
> 优先级: 42
> 前置: `permission-unified-model` + `permission-menu-view` + `permission-data-scope`(前三者完成后,本任务做 UI 收官)
> 系列总纲: [`plan-permission-redesign-overview.md`](plan-permission-redesign-overview.md)

---

## 背景:矩阵 UI 需整合三类权限

### 现状(前置三任务完成后)

到本任务开始时,后端已具备:
- `type="api"` 操作权限(已细化,任务 1)
- `type="menu"` 菜单权限(任务 2)
- `Role.data_scope` 数据范围字段(任务 3)

但权限矩阵 UI 还是旧版(任务 1 只做了「能显示 menu」,没做完整重写)。需要重写为**统一管理三类权限**的体验。

### 用户的明确诉求(2026-07-12)

1. **「超管直接拥有全部」要可见** —— 矩阵显示超管行,全选且锁定
2. **菜单权限 + 操作权限并列** —— 一个矩阵看全两类
3. **数据范围可配** —— 每个角色能选 data_scope

### 目标

重写 `permissions-page.tsx` 为统一的权限管理中心:
1. 超管行:固定全选 + 锁定图标(不可编辑,语义清晰)
2. 角色行:可编辑,菜单权限区 + 操作权限区并列(或 tab)
3. 每个角色:data_scope 选择器(all/tenant/group/self)
4. 友好的分组、图例、保存反馈

---

## 前置条件

- `permission-unified-model` 完成(操作权限细化 + 目录统一)
- `permission-menu-view` 完成(menu 权限 + 前端导航已改造)
- `permission-data-scope` 完成(data_scope 字段 + Repository 过滤)
- 三者均 passing

---

## 实施步骤

### 第一阶段:数据层准备

#### Step 1:矩阵端点返回 data_scope + type 分区

- **改什么**(`app/api/v1/permissions.py` matrix 端点 + `app/schemas/rbac.py` `PermissionMatrix`):
  - `PermissionMatrix.roles` 每个角色含 `data_scope` 字段
  - `PermissionMatrix.permissions` 每项含 `type` 字段(menu/api),前端可按 type 分组
  - 超管信息:矩阵返回一个特殊标记或前端按 `platform_role` 处理(超管不在 roles 里,是平台级)
- **检查**:GET /permissions/matrix 返回 roles[].data_scope + permissions[].type

### 第二阶段:UI 重写

#### Step 2:矩阵布局设计

- **目标布局**(`permissions-page.tsx` 重写):

  ```
  ┌─────────────────────────────────────────────────────────────┐
  │ 权限管理                                       [刷新]        │
  ├─────────────────────────────────────────────────────────────┤
  │ 🛡️ 超级管理员  🔒 全部权限(平台级,不可配置)              │  ← 超管锁定行
  ├─────────────────────────────────────────────────────────────┤
  │ 角色        | 数据范围 | 菜单权限              | 操作权限    │
  │             |         | 仪表盘 智能体 对话 ... | 读 建 删 ...│
  ├─────────────────────────────────────────────────────────────┤
  │ owner       | [租户▼] |  ✅    ✅    ✅      | ✅ ✅ ✅     │
  │ admin       | [租户▼] |  ✅    ✅    ✅      | ✅ ✅ ❌     │
  │ member      | [自身▼] |  ✅    ✅    ❌      | ✅ ❌ ❌     │
  │ 自定义角色  | [组▼]   |  ...                  | ...         │
  └─────────────────────────────────────────────────────────────┘
  图例:✅ 已授权  ❌ 未授权  🔒 锁定  [编辑中…]
  ```
- **三大区域**:
  - **超管锁定行**(顶部):独立卡片,「🔒 全部权限(平台级)」,不可点
  - **菜单权限区**:列 = menu 权限项,按业务分组(智能体域/对话域/管理域)
  - **操作权限区**:列 = api 权限项,按 obj 分组(智能体/对话/用户/角色/客户/设置/API Token)
- **data_scope 列**:每个角色一个下拉(all/tenant/group/self),改完调 role update 端点

#### Step 3:超管锁定行实现

- **改什么**(`permissions-page.tsx`):
  - 顶部独立区块:`platform_role === "super_admin"` 时显示
  - 文案:「🛡️ 超级管理员 — 拥有全部权限(平台级,不可配置)」
  - 不渲染超管的权限格子(无意义,全选)
  - 非 super_admin 登录不显示此行(超管是平台概念)
- **检查**:super_admin 登录矩阵页看到锁定行;owner 登录看不到(超管行是平台信息)

#### Step 4:菜单权限区 + 操作权限区并列

- **改什么**(`permissions-page.tsx`):
  - 矩阵分两个横向区块(或用 tab「菜单权限 / 操作权限」切换)
  - 列从 `usePermissionCatalogue()` 按 type 过滤(menu 区只显示 type=menu 的列;操作区只 type=api)
  - 列按 obj 分组,组间加分隔线或小标题
  - 格子点击 → grant/revoke(已有 hooks)+ loading 态 + 成功刷新
- **检查**:两区都能正常编辑;member 只读(无 roles:update)

#### Step 5:data_scope 选择器

- **改什么**(`permissions-page.tsx`):
  - 每个角色行加 `<Select>` 下拉:选项 all/tenant/group/self(中文:全部/本租户/本组织/仅自己)
  - 改值 → 调 `useUpdateRole({data_scope})`(已有 role update hook,加 data_scope 字段)
  - 系统角色(owner/admin/member)默认 tenant,允许改;超管不显示(data_scope 概念不适用平台角色)
  - group 选项提示:「需要本门店属于某个组织」
- **检查**:改 member 的 data_scope 为 self → 该 member 查客户只看自己(依赖任务 3 的 Repository 过滤)

#### Step 6:增强友好性

- **分组与图例**:
  - 列按 obj 分组(智能体 / 对话 / 用户 / 角色 / 客户 / 设置 / API Token)
  - 保留图例(✅/❌/🔒)
  - 角色名旁标「系统」徽章(owner/admin/member,提示是 seed 默认)
- **快捷操作**:
  - 「全选本组」按钮(某 obj 的全部动作一次性 grant)
  - 「授权查看」联动(menu:xxx + xxx:read 一起 grant)
- **保存反馈**:编辑中 spinner + 成功 toast + 失败回滚

### 第三阶段:总验证

#### Step 7:总验证

- **命令**:
  ```bash
  cd frontend && npm run build   # tsc + vite + oxlint
  ./init.sh   # 后端无改动也要确认不回归
  ```
- **手动验证**(前后端都启动):
  - super_admin 登录 → 矩阵页顶部见超管锁定行;下方角色矩阵可编辑
  - owner 登录 → 无超管行;菜单/操作两区可编辑;改 data_scope 生效
  - member 登录 → 矩阵只读;data_scope 不可改
  - 改某角色的菜单权限 → 该角色用户登录菜单变化(验证任务 2 联动)
  - 改某角色 data_scope=self → 该角色用户查客户只看自己(验证任务 3 联动)
- **通过标准**:
  - `npm run build` + oxlint 0 warning
  - 超管锁定行可见;菜单/操作两区可编辑;data_scope 选择器生效
  - 三类权限(菜单/操作/数据)统一在一个矩阵管理
- **全过 → 填 evidence + status 改 passing + 更新 progress.md + 更新系列总纲状态**

---

## 验收标准

1. 矩阵页顶部显示超管锁定行(全选 + 锁定图标,不可编辑)
2. 菜单权限区 + 操作权限区并列(或 tab 切换),均可编辑
3. 每个角色行有 data_scope 选择器,改值生效
4. 系统角色标「系统」徽章;member 矩阵只读
5. 列按 obj 分组,有图例和快捷操作
6. `npm run build` + oxlint 0 warning
7. 三类权限(菜单/操作/数据)统一管理,验证联动生效

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 矩阵列过多(7 obj × 5 act + 12 menu ≈ 47 列) | 按 obj 分组 + 横向滚动;或 tab 切换菜单/操作;优先级分组(常用在前) |
| data_scope 改动影响已有用户查询 | 改 data_scope 是角色级,立即生效;给个确认弹窗「将影响 N 个成员的查询范围」 |
| 超管行语义混淆(超管不在 roles 里) | 明确:超管行是「信息展示」非「可编辑角色」;用独立卡片视觉区分 |
| 系统角色 data_scope 被误改导致 owner 看不到数据 | 系统角色改 data_scope 加确认弹窗;owner 默认 tenant,提示「改为 self 将导致所有者只看自己数据」 |

### 不做的事(边界)

- 不做按钮级权限配置(只菜单/页面级 + 操作级)
- 不做权限模板(预设角色模板一键应用)——后续增强
- 不做权限变更审批流
- 不做 data_scope 的自定义范围(只四档预设)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-permission-redesign-overview.md` |
| 当前矩阵页(待重写) | `frontend/src/pages/permissions-page.tsx` |
| 矩阵 hook(已有) | `frontend/src/hooks/queries.ts` `usePermissionMatrix` |
| grant/revoke hooks(已有) | `frontend/src/hooks/queries.ts` |
| 角色 update(加 data_scope) | `frontend/src/hooks/queries.ts` `useUpdateRole` |
| 矩阵端点(待扩 data_scope/type) | `app/api/v1/permissions.py` |
| 新增前端模块教程 | `项目指南/04-二开脚手架/03-新增前端模块.md` |
