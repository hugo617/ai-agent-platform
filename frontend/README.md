# agenthub · 前端

智能体云平台的前端控制台 —— Vite + React + TypeScript + shadcn/ui。

## 技术栈

| 层 | 选型 |
|----|------|
| 构建 | Vite |
| 框架 | React 18 + TypeScript |
| UI | shadcn/ui + Tailwind CSS（含 Radix UI 原语）|
| 路由 | React Router v6 |
| 数据请求 | TanStack Query v5 |
| 表单 | React Hook Form + Zod |
| HTTP | axios |
| 图标 | lucide-react |

## 目录结构

```
src/
├── api/                  API 层：类型 + axios 客户端 + endpoints
│   ├── types.ts          与后端 Pydantic 对齐的 TypeScript 类型
│   ├── client.ts         axios 实例 + token 拦截器
│   └── endpoints.ts      各资源 API 调用
├── hooks/
│   └── queries.ts        TanStack Query hooks（useAgents/useCreateAgent…）
├── components/
│   ├── ui/               shadcn/ui 基础组件（button/card/input/table/dialog…）
│   ├── layout/           DashboardLayout（侧边栏 + 顶栏）
│   └── auth/             AuthProvider + ProtectedRoute（路由守卫）
├── pages/
│   ├── login-page.tsx    登录页（dev token 注入 / Logto TODO）
│   ├── dashboard-page.tsx 概览
│   ├── agents-page.tsx   智能体 CRUD
│   ├── roles-page.tsx    角色定义
│   └── permissions-page.tsx 权限矩阵可视化
├── lib/utils.ts          cn() 工具
├── App.tsx               路由 + Providers
└── main.tsx              入口
```

## 启动

### 前置：后端先跑起来

后端在仓库根目录，按根 README 启动 FastAPI（默认 `http://localhost:8000`）。

### 启动前端

```bash
cd frontend
npm install
npm run dev      # 访问 http://localhost:3000
```

Vite dev server 会把 `/api/*` 和 `/health` 代理到 `http://localhost:8000`（见 `vite.config.ts`）。

## 认证说明（MVP 阶段）

当前采用 **dev token 注入**策略：
- 登录页输入后端签发的 JWT access token，存到 localStorage
- 每个 API 请求自动带 `Authorization: Bearer <token>`

Logto 真实 OIDC 跳转登录的接入位置已标记在 `login-page.tsx` 中（TODO 注释），后续替换即可。

## 核心页面

| 路径 | 页面 | 说明 |
|------|------|------|
| `/login` | 登录 | dev token 输入 |
| `/` | 概览 | 角色 / 智能体数 / 租户 / API 状态卡片 |
| `/agents` | 智能体 | 列表 + 新建/编辑/删除（带对话框表单）|
| `/roles` | 角色 | owner / member 角色定义 + 权限来源说明 |
| `/permissions` | 权限矩阵 | 角色 × 资源 × 动作可视化表格 |

## 构建

```bash
npm run build    # tsc 类型检查 + Vite 生产构建，产物在 dist/
npm run preview  # 本地预览生产构建
```

## 与后端 API 的对接

所有 API 调用集中在 `src/api/endpoints.ts`，TanStack Query hooks 在 `src/hooks/queries.ts`。
类型定义在 `src/api/types.ts`，和后端 `app/schemas/*` 一一对应。
将来后端 schema 变化，可用 `openapi-typescript` 自动生成类型替换手动维护。
