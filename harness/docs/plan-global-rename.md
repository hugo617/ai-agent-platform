# 计划:全局改名为新产品

> 对应 feature_list.json 的 `id`: `global-rename`
> 状态: not_started
> 参考: 项目指南/04-二开脚手架/01-改造清单与命名.md 第 1 步

---

## 目标

把脚手架里所有 "ai-agent-platform" / "权限控制台" 标识,替换成你自己的新产品名。
改完后对外可见的所有地方(后端 API 标题、前端页头、文档)都展示新产品身份,代码功能不变。

## 前置条件

- **先定好新产品名**(本文用 `<新产品名>` 代指)。建议同时定好:
  - 产品名(英文标识,如 `my-saas`,用于配置和包名)
  - 显示名(中文,如 `我的工作台`,用于页头和标题)
- 定名前不要开始执行,否则中途返工。

---

## 实施步骤

### Step 1:改后端 APP_NAME 配置(核心)

这是最关键的一步——`settings.app_name` 是名字的唯一来源,改了它,FastAPI 标题和 `/health` 自动生效。

- **改什么**:
  - `.env:3` → `APP_NAME=ai-agent-platform` 改为 `APP_NAME=<新产品名>`
  - `.env.example:6` → `APP_NAME=ai-agent-platform` 改为 `APP_NAME=<新产品名>`
  - `app/core/config.py:23` → `app_name: str = "ai-agent-platform"` 改为默认值 `<新产品名>`
- **检查**:
  - `main.py` 不硬编码名字(它读 `settings.app_name`),无需改动。
  - 改完后启动后端,访问 `/health` 应返回新名字;`/docs` 页面标题应是新名字。

### Step 2:改后端产品描述(建议)

产品定位的描述也该跟着改,影响 API 文档显示。

- **改什么**:
  - `app/main.py:32` → `description="Multi-tenant AI Agent SaaS platform"` 改为你的产品定位一句话
  - `pyproject.toml:2` → `name = "ai-agent-platform"` 改为 `<新产品名>`
  - `pyproject.toml:4` → `description = "..."` 改为你的产品定位
- **检查**:非功能必需,但影响 API 文档 / pip 元信息的展示。

### Step 3:改前端用户可见标题

前端有 **3 处硬编码**(二开文档只列了 2 处,漏了登录页):

- **改什么**:
  - `frontend/index.html:7` → `<title>权限控制台 · ai-agent-platform</title>` 改为 `<title><显示名> · <新产品名></title>`
  - `frontend/src/components/layout/dashboard-layout.tsx:64` → `权限控制台` 改为 `<显示名>`
  - `frontend/src/pages/login-page.tsx:99` → `登录权限控制台` 改为 `登录<显示名>` ⚠️(二开清单遗漏,务必一起改)
- **检查**:
  - 全仓库前端源码中 "权限控制台" 应 0 残留:`grep -rn '权限控制台' frontend/src/ frontend/index.html`
  - `NAV_ITEMS` 导航项不含产品名,无需动。
  - `frontend/package.json` 的 `name` 当前是 `"frontend"`(非 ai-agent-platform),可改可不改。

### Step 4:改文档与版权

文档不影响运行,但影响二开交付的完整度。

- **改什么**:
  - `README.md:1` → `# ai-agent-platform` 改为 `# <新产品名>`
  - `frontend/README.md:1` → 含 ai-agent-platform,改为 `<新产品名>`
  - `NOTICE:1` → `ai-agent-platform` 改为 `<新产品名>`
  - `casbin_model.conf:1` → 注释里的 ai-agent-platform(纯注释,可选改)
  - `docs/LOGTO_SETUP.md:78,86` → `--network ai-agent-platform_default`:这是 docker 按文件夹名生成的网络名。**若不改文件夹名则保持**;改了文件夹名要同步改
  - `docs/LOGTO_SETUP.md:105` → 示例文案 `ai-agent-platform-api` 改为你的命名
- **检查**:文档类 grep 检查,允许保留"历史说明"语境里提到旧名(如有意保留)。

### Step 5:重新生成 OpenAPI 导出

- **改什么**:
  - `docs/openapi/openapi.json` 的 `title` 字段是 `settings.app_name` 的导出产物,**不要手改**。
- **怎么做**:改完 Step 1 后,重新跑导出命令自动更新。具体导出方式见 `项目指南` 或 `app/main.py` 的导出逻辑。
- **检查**:openapi.json 里 title 应为新名字。

### Step 6:总验证(全做完后执行)

- **命令**:
  ```bash
  # 1. 后端验证
  ./init.sh

  # 2. 前端构建
  cd frontend && npm run build && cd ..

  # 3. 残留检查(排除依赖/缓存目录)
  grep -rn 'ai-agent-platform\|权限控制台' \
    --include='*.py' --include='*.ts' --include='*.tsx' \
    --include='*.html' --include='*.md' --include='*.toml' \
    . 2>/dev/null | grep -vE '\.venv/|\.git/|node_modules/|\.codegraph/|\.zcode/|\.apifox/'
  ```
- **通过标准**:
  - `./init.sh` 全绿(ruff + pytest)
  - `npm run build` 通过
  - grep 残留检查:除了"有意保留的历史说明"(如有),无其他残留
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

(feature_list.json 的 verification 字段与这里同步)

1. `./init.sh` 全绿(ruff + pytest)
2. `cd frontend && npm run build` 通过
3. grep 检查无 "ai-agent-platform" / "权限控制台" 残留(排除依赖/缓存目录)
4. `docs/openapi/openapi.json` 的 title 已更新(重导出产物)

---

## 风险 / 注意事项

### 可选批次:改 "aap" 缩写

"aap" 是 ai-agent-platform 的缩写,出现在数据库用户名/容器名/CI 环境变量,**不影响功能正确性**。

- **出现位置**:
  - `docker-compose.yml:5,22,42,56,57` → container_name / volumes 用 aap 前缀
  - `.github/workflows/ci.yml:25-27,36` → POSTGRES_USER/DB 用 aap / aap_ci
  - `.env:10-15`, `.env.example:15-21` → POSTGRES_* / DATABASE_URL 用 aap
- **决策**:
  - 只改"对外可见标识" → **不动 aap**(它只在基础设施配置里,用户看不到)
  - 要彻底去标识 → 单独一批改,但 ⚠️ **若改 aap,DATABASE_URL 的用户名必须与 POSTGRES_USER 一致**,否则连不上库
- **建议**:先用上面的 Step 1-6 改完可见标识,aap 缩写单独评估,不要混在一起改。

### 其他注意

- 项目文件夹名 `ai-agent-platform` 本身改不改都不影响运行。若要改,记得检查 git remote 等配置。
- 改名是"二开第 1 步",做完后再考虑删模块 / 加新业务模块(见 项目指南/04-二开脚手架/01)。
- 上述文件行号基于 2026-07-10 的代码核实,执行前建议快速 grep 确认行号没漂移。
