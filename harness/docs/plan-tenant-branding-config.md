# 计划:租户品牌配置(logo/名称/主题色/登录文案,白标 SaaS)

> 对应 feature_list.json 的 `id`: `tenant-branding-config`
> 状态: not_started
> 优先级: 52
> 前置: 无(logo 上传弱依赖 file-upload 56,可先做名称/主题色/文案)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:settings 只有 LLM 配置,无品牌(白标缺失)

### 现状

- `frontend/src/pages/settings-page.tsx`:只有 3 个 Card(平台 LLM / 租户 LLM / API Token)
- 无 logo 上传、无主题色、无登录页文案
- 多租户白标 SaaS 的基本能力缺失

### 目标

租户级品牌配置:
1. logo(依赖 file-upload 56,可后补)
2. 显示名称(覆盖默认)
3. 主题色(应用到全站 CSS 变量)
4. 登录页文案
5. 用户登录看到的是该门店品牌

---

## 前置条件

- 无。logo 上传依赖 file-upload(56),可先做名称/主题色/文案。

---

## 实施步骤

### 第一阶段:后端

#### Step 1:TenantConfig 模型 + 迁移

- **新建**(`app/models/tenant_config.py`)或在 Tenant 加字段(推荐独立表,避免 Tenant 臃肿):
  ```python
  class TenantConfig(Base):
      __tablename__ = "tenant_configs"
      __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_config_tenant"),)
      id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
      tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id", ondelete="CASCADE"))
      display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
      logo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
      theme_color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # #RRGGBB
      login_text: Mapped[str | None] = mapped_column(Text, nullable=True)
      created_at / updated_at
  ```
- **注册**(`alembic/env.py`)+ **迁移**
- **检查**:`alembic upgrade head && alembic check`

#### Step 2:API 端点

- **新建**(`app/api/v1/tenant_config.py`):
  ```python
  @router.get("/{tenant_id}/config", response_model=TenantConfigRead)
  @router.put("/{tenant_id}/config", response_model=TenantConfigRead)
  ```
- **权限**:GET 公开(登录页要用,无需登录)或按 tenant_id 查;PUT 需 `require_permission("settings", "update")`(owner/admin)
- **路由注册**

#### Step 3:GET /auth/me 返回品牌(或前端单独查)

- **选择**:前端登录后单独调 `GET /tenant-config`(当前租户)获取品牌;或 MeResponse 带品牌字段
- **推荐**:独立端点,登录页也能用(未登录时按 tenant slug 查)

### 第二阶段:前端

#### Step 4:types + endpoints + hooks

- **改** types:`TenantConfig`
- **改** endpoints:`fetchTenantConfig(tenantId)` / `updateTenantConfig(tenantId, payload)`
- **改** hooks:`useTenantConfig` / `useUpdateTenantConfig`
- **检查**:tsc 无错

#### Step 5:settings-page 加品牌 Card

- **改什么**(`frontend/src/pages/settings-page.tsx`):
  - 加第 4 个 Card「品牌配置」(owner/admin 可见)
  - 字段:显示名称 + logo(上传占位,依赖 56)+ 主题色(color picker)+ 登录页文案
  - 保存 → updateTenantConfig
- **检查**:配置保存生效

#### Step 6:主题色全局应用

- **改什么**(`frontend/src/App.tsx` 或 layout):
  - 应用启动时查当前租户品牌 → 设 CSS 变量 `--primary: <theme_color>`
  - Tailwind/shadcn 组件用 `var(--primary)`(主题色随租户变)
- **检查**:改主题色后全站按钮/链接变色

#### Step 7:登录页 + 顶栏品牌注入

- **改**(`frontend/src/pages/login-page.tsx`):显示 login_text + logo(若有)
- **改**(`dashboard-layout.tsx` 顶栏):显示 display_name(覆盖默认) + logo
- **检查**:登录页和顶栏显示该租户品牌

### 第三阶段:验证

#### Step 8:测试 + 总验证

- **后端**(`tests/test_tenant_config.py`):
  - GET/PUT config
  - 权限:owner/admin 可改;member 只读
  - 租户隔离:门店 A 改不了门店 B
- **命令**:`./init.sh` + `npm run build` + `alembic check`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. TenantConfig 表(display_name/logo_url/theme_color/login_text)+ 迁移无 drift
2. GET/PUT /tenant-config 端点 + 权限(owner/admin 改)
3. settings 加品牌配置 Card
4. 主题色 CSS 变量全局应用(改色全站生效)
5. 登录页 + 顶栏显示品牌(logo + display_name + login_text)
6. `./init.sh` + `npm run build` + `alembic check` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 主题色对比度差(用户选浅色) | 提供预设色板 + 校验对比度;或固定几个主题选项 |
| 未登录时查品牌(登录页) | 需要按 tenant slug 查;或用默认品牌,登录后替换 |
| CSS 变量兼容性 | shadcn/Tailwind 已用 CSS 变量;确认变量名覆盖 |

### 不做的事(边界)

- 不做自定义域名(需要 DNS/SSL,远期)
- 不做自定义 CSS/布局(只主题色 + logo + 文案)
- 不做多主题切换(一租户一主题)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| settings 页(待加 Card) | `frontend/src/pages/settings-page.tsx` |
| 登录页(待加品牌) | `frontend/src/pages/login-page.tsx` |
| 布局(顶栏品牌) | `frontend/src/components/layout/dashboard-layout.tsx` |
| Tenant 模型 | `app/models/tenant.py` |
