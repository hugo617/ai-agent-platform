# 计划:权限体系重构总览(菜单 + 操作 + 数据三类权限)

> 这是 **权限重构系列任务的总纲文档**(非可执行任务本身)。
> 具体实施拆成 4 个 WIP=1 子任务,见下方「子任务清单」。
> 对应 feature_list.json 的 `id`: `permission-unified-model` / `permission-menu-view` / `permission-data-scope` / `permission-matrix-redesign`

---

## 背景:为什么要重构权限体系

### 用户痛点(2026-07-12 Session 045 提出)

1. **「只有增删改查,没有视图权限」** —— 当前 `Permission.type` 字段预留了分类(`api`/`menu`/`view`),但全项目只写过 `"api"`。菜单/页面可见性在另一套前端硬编码常量里(`needsSuperAdmin`/`needsUserManagement`),两套从不相交。用户无法在权限矩阵里配置「某个角色能不能看到某个菜单/页面」。
2. **「超管直接拥有全部」不可见** —— `super_admin` 是硬编码 bypass(`permission_service.check` 第一行直接 return True),不在矩阵里 → 权限不可见、不可理解。
3. **操作权限粒度粗** —— `settings`/`api_tokens` 只有粗的 `manage`(一勾全勾),无法配「只能看设置不能改」。缺 `export`/`approve` 等业务动作。
4. **权限目录三处漂移** —— `DEFAULT_*_PERMS` 常量、路由 `require_permission`、前端 `OBJ_LABELS`/`ACT_ORDER` 各维护一份,已经 drift(如 `conversations:delete` 有校验无 seed;`customers`/`settings`/`api_tokens` 前端无中文标签)。

### 行业实践共识(调研结论)

成熟 SaaS/后台权限系统都把权限拆成**三个正交维度**(参考 JavaGuide《权限系统设计详解》、WorkOS《RBAC Best Practices》、AltexSoft《Access Control Matrix》、Oso《RBAC》)：

| 维度 | 回答的问题 | 本项目现状 |
|---|---|---|
| **① 菜单/视图权限** | 这个用户**能看到**哪些菜单/页面/按钮? | ❌ 缺失(前端硬编码) |
| **② 操作/功能权限** | 这个用户**能调用**哪些 API? | ✅ 有,但只有 `api` 类型、粒度粗 |
| **③ 数据权限** | 这个用户能看到**哪些数据行**? | ⚠️ 部分覆盖(super_admin/hq_staff + 租户过滤),无显式建模 |

---

## 总体方案(用户 2026-07-12 拍板)

### 决策记录

| 决策点 | 用户选择 |
|---|---|
| 权限维度范围 | **菜单 + 操作 + 数据三类全做** |
| 超管建模 | **矩阵显示超管行,全选且锁定**(后端保持 bypass,UI 可见可理解) |
| 操作粒度 | **适度细化 + 统一目录**(拆 manage、补缺失项、目录变唯一真相源) |
| 数据权限深度 | **B. 角色级数据范围 `data_scope` 四档**(all/tenant/group/self) |
| 任务拆分 | **拆成 4 个 WIP=1 任务** |

### 目标架构

```
Permission.type:
  ├── "menu"   ← 新增:菜单/页面可见性(驱动前端导航 + 路由守卫)
  └── "api"    ← 已有:操作权限(驱动后端 require_permission + AI 工具双重校验)

Role.data_scope:                       ← 新增(数据权限)
  all      = 看全部(平台级,仅超管/hq_staff 用)
  tenant   = 看本租户(默认,owner/admin/member)
  group    = 看本组织/门店组(Group 内)
  self     = 只看自己的数据(业务员典型场景)

权限目录(唯一真相源):
  后端 Permission 表 + catalogue 端点 → 前端从它读取,不再硬编码

权限矩阵 UI:
  ├── 超管行:固定全选 + 锁定图标(语义:平台级全权,不可删减)
  ├── owner/admin/member:可编辑(菜单 + 操作两类权限并列)
  └── 自定义角色:可编辑
```

### 三类权限的职责边界(重要,避免混淆)

| 权限类型 | 驱动什么 | 安全边界? |
|---|---|---|
| **menu** | 前端菜单可见性、路由守卫、按钮显隐 | ❌ UX 层(可绕过,真正拦的是 api 权限) |
| **api** | 后端 `require_permission` + AI 工具双重校验 | ✅ 硬安全边界 |
| **data_scope** | Repository 层查询自动注入数据范围过滤 | ✅ 硬安全边界 |

> 关键约定:**menu 权限是 api 权限的 UX 影子**。一个角色没有 `customers:read`(api)就没有 `customers:menu`(menu)——menu 只是让界面干净,真正能否访问由 api 权限在后端兜底。两者通常一起 grant/revoke,但允许独立配置(例如:给某角色看「客户」菜单但不给「删除客户」操作)。

---

## 子任务清单(WIP=1 顺序执行)

| 顺序 | id | 范围 | 前置 | plan 文档 |
|------|----|------|------|----------|
| 1 | `permission-unified-model` | 统一权限目录 + 操作权限细化(拆 manage、补缺失、消除三处漂移) | 无 | `harness/docs/plan-permission-unified-model.md` |
| 2 | `permission-menu-view` | 新增菜单/视图权限类型(type=menu)+ 前端导航/路由由权限驱动 | 1 | `harness/docs/plan-permission-menu-view.md` |
| 3 | `permission-data-scope` | 角色加 data_scope 字段 + Repository 层数据范围过滤 | 1 | `harness/docs/plan-permission-data-scope.md` |
| 4 | `permission-matrix-redesign` | 权限矩阵 UI 重写:超管锁定行 + 菜单/操作两类并列 + data_scope 选择器 | 1,2,3 | `harness/docs/plan-permission-matrix-redesign.md` |

> 依赖关系:任务 1 是地基(目录统一 + 操作细化),任务 2/3 可并行但 WIP=1 仍顺序执行,任务 4 依赖前三者。

---

## 不做的事(系列边界)

- **不上 ABAC**(行级条件表达式)——过度工程,data_scope 四档已覆盖典型需求
- **不动 super_admin 的后端 bypass 语义**——平台级全权不变,只在前端让它「可见可理解」
- **不做权限变更审批流**(提交-审核-生效)——超出当前 MVP 范围
- **不做 SCD2 历史回溯**——保持现状(按需项),本系列只改当前态

---

## 参考文件(系列实施时对照)

| 参照 | 路径 |
|------|------|
| 权限模型文档 | `项目指南/02-后端架构/06-权限模型RBAC.md` |
| 默认权限常量(真相源之一) | `app/services/permission_service.py` `DEFAULT_*_PERMS` |
| casbin 唯一封装 | `app/services/permission_service.py` |
| Permission/Role 模型 | `app/models/rbac.py` |
| 声明式校验工厂 | `app/api/deps.py` `require_permission` |
| 前端权限判断 | `frontend/src/lib/permission.ts` |
| 前端导航(硬编码) | `frontend/src/components/layout/dashboard-layout.tsx` `NAV_ITEMS` |
| 权限矩阵页(待重写) | `frontend/src/pages/permissions-page.tsx` |

## 行业实践参考链接

- [权限系统设计详解 — JavaGuide](https://javaguide.cn/system-design/security/design-of-authority-system.html)
- [RBAC Best Practices — WorkOS](https://workos.com/blog/rbac-best-practices)
- [Access Control Matrix: A Practical Guide — AltexSoft](https://www.altexsoft.com/blog/access-control-matrix-acm/)
- [How to Build a RBAC Layer — Oso Security](https://www.osohq.com/learn/rbac-role-based-access-control)
- [全网最全权限系统设计方案 — 腾讯云](https://cloud.tencent.com/developer/article/2314166)
- [终于把后管权限系统设计讲清楚了 — 阿里云开发者社区](https://developer.aliyun.com/article/1445175)
