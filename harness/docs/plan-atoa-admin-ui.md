# 计划:AtoA 管理前端 —— API Token 管理 UI

> 对应 feature_list.json 的 `id`: `atoa-admin-ui`
> 状态: not_started
> 优先级: 23
> 前置: `atoa-api-token-auth` ✅（后端 Token 端点就绪，前端才能对接）

---

## 背景:为什么需要这个任务

API Token 的后端鉴权 + 端点（atoa-api-token-auth）就绪后，用户只能用 curl 颁发/管理 Token——不友好。本任务补前端管理 UI，让用户在浏览器里完成「颁发 → 复制 → 查看 → 吊销」全流程。

这是 Apifox 打法四件套里「授权机制」的管理面——Apifox 在管理后台颁发「访问令牌」，本项目对齐这个体验。

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| 后端 Token 端点 | ✅ 前置任务交付 | `app/api/v1/api_tokens.py`（POST/GET/DELETE/verify） |
| 前端管理后台骨架 | ✅ 已完成 | `frontend/src/`（11 页，settings-page 等模式可复用） |
| 前端 Token 管理 UI | ❌ 缺失 | 无 |

---

## 目标

1. **Token 管理界面**：颁发/列表/吊销全流程，明文 Token 仅显示一次
2. **复用现有模式**：对齐 settings-page / members-page 表格 + Dialog 模式
3. **权限守卫**：仅 owner/admin/super_admin 可见可操作

### 已确认的决策（与用户对齐）

| 决策点 | 选择 |
|--------|------|
| 页面位置 | **整合进 settings-page.tsx**（新增「API Token」Card），与 LLM 配置并列——都是「平台设置」 |
| 明文 Token 显示 | **仅颁发时显示一次**（弹窗 + 复制按钮 + 「关闭后不可再见」警告） |
| 列表展示 | 表格（名称 / 掩码前缀 / 创建时间 / 最后使用 / 过期 / 吊销按钮） |

---

## 前置条件

- `atoa-api-token-auth` ✅（后端 `/api-tokens` 端点就绪）
- 前端管理后台骨架完整（已 passing）

---

## 实施步骤

### 第一阶段:前端 API 层

#### Step 1:types.ts + endpoints.ts + queries.ts

- **types.ts**：
  ```typescript
  export interface ApiToken {
    id: string;
    name: string;
    token_prefix: string;       // "ahp_***wxyz"
    scopes: string[];
    last_used_at: string | null;
    expires_at: string | null;
    is_active: boolean;
    created_at: string;
  }
  export interface ApiTokenCreate {
    name: string;
    expires_at?: string | null;
    scopes?: string[];
  }
  export interface ApiTokenCreated extends ApiToken {
    token: string;  // 明文，仅颁发时返回
  }
  ```
- **endpoints.ts**：
  - `fetchApiTokens()` → GET /api-tokens
  - `createApiToken(payload)` → POST /api-tokens
  - `revokeApiToken(id)` → DELETE /api-tokens/{id}
- **queries.ts**：
  - `qk.apiTokens(['api-tokens'])`
  - `useApiTokens`（useQuery）
  - `useCreateApiToken`（useMutation，onSuccess invalidate apiTokens）
  - `useRevokeApiToken`（useMutation，onSuccess invalidate apiTokens）

---

### 第二阶段:页面

#### Step 2:settings-page.tsx 加「API Token」Card

- **位置**：在现有 LLM 配置两个 Card 之后，新增第三个 Card「API Token 管理」
- **权限**：`canManageUsers(me)`（owner/admin/super_admin 可见可操作）
- **内容**：
  - Token 列表表格（名称 / 掩码前缀 / 创建时间 / 最后使用 / 过期 / 状态 / 吊销按钮）
  - 「颁发新 Token」按钮 → 弹 Dialog

#### Step 3:颁发 Dialog

- **表单**（RHF + zod）：
  - `name`（必填，如 "my-cursor-agent"）
  - `expires_at`（可选，日期选择器；留空=永不过期）
  - `scopes`（可选，本版预留不实现细粒度，显示「继承你的全部权限」提示）
- **提交**：`useCreateApiToken`
- **成功后**：**切换到「明文展示」视图**（关键 UX）：
  - 大字号显示明文 token
  - 「复制」按钮（`navigator.clipboard`）
  - 警告横幅：「⚠️ 这是唯一一次显示，关闭后无法再看到，请立即复制保存」
  - 「我已保存，关闭」按钮 → 关闭 Dialog

#### Step 4:吊销确认

- 吊销按钮 → 确认 Dialog（「确定吊销此 Token？吊销后用此 Token 的 Agent 将立即无法访问」）
- `useRevokeApiToken` → toast 反馈 → 列表刷新

---

### 第三阶段:验证

#### Step 5:前端总验证

- `cd frontend && npm run build` 通过（tsc + vite，0 类型错误）
- `npx oxlint` 改动文件 0 warning
- 手动浏览器验证（需前后端启动）：
  - 颁发 → 明文显示 → 复制 → 关闭
  - 列表含新 token（掩码）
  - 吊销 → 列表状态变更
  - 权限：member 看不到此 Card（settings 页在 RequireUserManagement 内）

#### Step 6:回归

- `./init.sh` 全绿（后端不回归，纯前端任务）

---

## 验收标准

1. settings-page 新增「API Token」Card，权限守卫正确
2. 颁发流程：表单 → 明文仅显示一次 → 复制 → 警告
3. 列表 + 吊销工作正常
4. `cd frontend && npm run build` 通过 + oxlint 0 warning
5. `./init.sh` 全绿（后端不回归）
6. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 明文 Token 关闭后丢失 | 颁发成功后**不立即关闭 Dialog**，强制用户看到警告 + 复制；关闭后后端不再返回明文 |
| 复制功能兼容性 | `navigator.clipboard` + fallback（旧浏览器选中文本） |
| 与 LLM 配置 Card 混杂 | 视觉分隔（独立 Card + 标题「API Token 管理」） |
| 权限边界 | settings 页在 RequireUserManagement 路由守卫内；Card 内 canManageUsers 双层守卫 |

### 不做的事（边界）

- 不实现 scope 细粒度编辑（预留字段，UI 显示「继承全部权限」）
- 不实现 Token 编辑（只颁发/吊销，不支持改名——改名语义混乱）
- 不做独立 Token 管理页（整合进 settings-page）
- 不做调用日志展示（system_logs 后续按需）
- 不改后端任何端点（纯前端对接）

---

## 参考文件（实施时对照）

| 参照 | 路径 |
|------|------|
| settings-page.tsx（整合目标） | `frontend/src/pages/settings-page.tsx`（LLM 配置两 Card 模式） |
| members-page.tsx（表格+Dialog 范本） | `frontend/src/pages/members-page.tsx` |
| 前端 API 层 | `frontend/src/api/client.ts` + `endpoints.ts` + `types.ts` |
| 前端 hooks | `frontend/src/hooks/queries.ts`（TanStack Query 模式） |
| 权限 helper | `frontend/src/lib/permission.ts`（canManageUsers） |
| 路由守卫 | `frontend/src/components/auth/require-permission.tsx` |
| 后端 Token 端点（对接源） | `app/api/v1/api_tokens.py`（前置任务交付） |
| 掩码模式参照 | `frontend/src/pages/settings-page.tsx`（API key Eye 切换） |
