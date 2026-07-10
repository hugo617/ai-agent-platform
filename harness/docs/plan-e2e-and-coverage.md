# 计划:E2E 测试 + 覆盖率门槛 + lint 修复

> 对应 feature_list.json 的 `id`: `e2e-and-coverage`
> 状态: not_started
> 优先级: 17(最后一个,基建任务)
> 前置: 建议 #1-#6 完成后再做(否则 E2E 无内容可测)

---

## 背景:代码量在涨,缺质量护栏

当前项目有 96 个后端测试 + tsc 类型检查,但缺三个护栏:
1. **无覆盖率门槛**:测试全绿 ≠ 覆盖充分,关键分支可能没测到
2. **无 E2E**:单元/集成测试覆盖 API 层,但"登录 → 建 Agent → 对话"这条主线没人跑
3. **前端 4 个 lint warning**:既有代码(button/badge/auth-context/toast),非阻断但该清

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| 后端 pytest | ✅ 96 tests | CI backend job |
| 后端覆盖率检查 | ❌ 无 | CI 无 `--cov` 门槛 |
| 前端类型检查 | ✅ tsc | CI frontend job |
| 前端 lint | ⚠️ 4 warnings | oxlint,非阻断 |
| E2E | ❌ 无 | 无 Playwright |
| CI jobs | ✅ 3 个 | migrations / backend / frontend |

---

## 目标

加三道质量护栏:
1. 后端 pytest 覆盖率门槛(核心层 ≥80%)
2. Playwright E2E 覆盖主线(登录 → Agent → 对话)
3. 前端 oxlint 0 warning

---

## 前置条件

- 建议 #1-#6 完成(E2E 才有完整流程可测:对话、权限矩阵等)
- 至少 `chat-frontend` 完成(E2E 的对话环节依赖它)

---

## 实施步骤

### 第一阶段:后端覆盖率门槛

#### Step 1:CI 加 pytest-cov + 门槛

- **改什么**(`requirements-dev.txt`):加 `pytest-cov`(若未装)
- **改什么**(`.github/workflows/ci.yml` backend job 的 pytest 命令):
  ```yaml
  - name: Run tests with coverage
    run: |
      pytest -ra --strict-markers \
        --cov=app \
        --cov-report=term-missing \
        --cov-fail-under=80
  ```
- **门槛选择**:
  - 第一版 `--cov-fail-under=80`(整体 80%;核心层 services/repositories 通常 >90%,api 层稍低)
  - 若 80% 太严(现有代码可能刚好不够),先跑一次看实际覆盖率,定到"当前 + 2%"再逐步提到 80%
- **本地验证**:`pytest --cov=app --cov-report=term-missing`(看哪些行没覆盖)
- **检查**:CI backend job 带覆盖率门槛全绿

### 第二阶段:E2E 测试

#### Step 2:引入 Playwright

- **安装**(`frontend/`):
  ```bash
  npm i -D @playwright/test
  npx playwright install chromium
  ```
- **配置**(`frontend/playwright.config.ts`):
  - baseURL: `http://localhost:3000`(前端 dev server)
  - webServer: 自动起 `npm run dev`(前端)+ 提示后端需手动起(或用 docker-compose)
  - 测试文件:`frontend/e2e/*.spec.ts`
- **CI 依赖**:E2E 需要前后端都跑起来。CI 里用 docker-compose 起 Postgres + 后端 + 前端,或只跑"前端 mock 后端"的轻量 E2E

#### Step 3:写主线 E2E

- **新建** `frontend/e2e/main-flow.spec.ts`(覆盖核心主线):
  ```typescript
  test("登录 → 建 Agent → 对话 → 查看历史", async ({ page }) => {
    // 1. 登录(用 dev token 或测试账号)
    await page.goto("/login");
    // 填 token / 账号密码

    // 2. 进 Agent 页 → 创建 Agent
    await page.goto("/agents");
    await page.click("text=新建");
    await page.fill("name", "E2E 测试 Agent");
    // ...

    // 3. 进对话页 → 选 Agent → 发消息
    await page.goto("/chat");
    await page.selectOption("[data-testid=agent-select]", "E2E 测试 Agent");
    await page.fill("[data-testid=message-input]", "你好");
    await page.click("[data-testid=send]");
    // 等待流式回复出现
    await expect(page.locator("text=你好")).toBeVisible();        // user 消息
    await expect(page.locator(".assistant-message")).toBeVisible(); // assistant 回复

    // 4. 查看历史(刷新后会话还在)
    await page.reload();
    await expect(page.locator("text=E2E 对话")).toBeVisible();
  });
  ```
- **注意**:
  - E2E 需要 DeepSeek key(或 mock 后端 LLM)。CI 里可用 mock,本地验证用真实 key
  - data-testid:实施时在前端组件加 `data-testid` 属性(E2E 选择器稳定性)
- **检查**:`npx playwright test` 全过

### 第三阶段:前端 lint 修复

#### Step 4:修 oxlint 4 warnings

- **当前**:4 warnings(button/badge/auth-context/toast,既有代码)
- **方法**:跑 `npx oxlint src/` 看具体 warning,逐个修(多半是 `any` 类型 / 未用变量 / 依赖问题)
- **检查**:`npx oxlint src/` → 0 warnings

### 第四阶段:CI 整合

#### Step 5:CI 加 E2E job + coverage 已在 backend job

- **改什么**(`.github/workflows/ci.yml`):
  - backend job 已加 `--cov-fail-under`(Step 1)
  - 新增 e2e job(依赖前后端能启动):
    ```yaml
    e2e:
      name: E2E (Playwright)
      runs-on: ubuntu-latest
      services:
        postgres: ...  # 同 migrations job
      steps:
        - 起后端(docker-compose 或 uvicorn + alembic upgrade)
        - 起前端(npm run dev 或 preview)
        - npx playwright test
    ```
- **权衡**:E2E job 较重(需全栈启动)。若 CI 时长敏感,可先只加 coverage 门槛,E2E 仅本地跑 + 手动触发

### 第五阶段:总验证

#### Step 6:全栈验证

- **命令**:
  ```bash
  # 后端覆盖率
  pytest --cov=app --cov-report=term-missing --cov-fail-under=80
  # 前端 lint
  cd frontend && npx oxlint src/   # 0 warnings
  # E2E(本地,前后端启动)
  cd frontend && npx playwright test
  ```
- **通过标准**:
  - 后端覆盖率 ≥ 门槛(80% 或实际值+2%)
  - oxlint 0 warning
  - E2E 主线全绿
  - CI 所有 job 全绿
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. CI backend job 带 `--cov-fail-under`(覆盖率门槛,≥80% 或合理值)
2. Playwright E2E 覆盖主线:登录 → 建 Agent → 对话 → 历史
3. 前端 oxlint 0 warning(修当前 4 个)
4. CI 所有 job 全绿(含新增 e2e job)

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 覆盖率门槛太严导致 CI 红 | 先跑一次看实际覆盖率,定到"当前+2%"逐步提;不一步到位 80% |
| E2E 在 CI 启动全栈复杂 | 第一版可只本地跑;CI 里用 docker-compose 统一起;或 mock 后端轻量 E2E |
| E2E 依赖 DeepSeek(外部 API) | E2E 用 mock 后端 LLM(拦截 /chat/stream);或用固定测试 key(有成本/不稳定) |
| Playwright 浏览器安装慢 | CI 用 `npx playwright install --with-deps chromium`(只装 chromium) |
| data-testid 散落各组件 | 统一在 E2E 选择器用 role/label 优先,data-testid 兜底 |

### 不做的事(边界)

- 不做视觉回归测试(screenshot diff)
- 不做性能测试
- 不做 100% 覆盖率(80% 是务实门槛,追 100% 投入产出比低)
- 不改测试框架(pytest + Playwright,不换)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| CI workflow | `.github/workflows/ci.yml` |
| 后端测试 | `tests/`(96 个) |
| 前端 lint | `cd frontend && npx oxlint src/` |
| Playwright 文档 | https://playwright.dev/docs/intro |
| pytest-cov | https://pytest-cov.readthedocs.io/ |
| 主线流程(被测对象) | 登录 → /agents 建Agent → /chat 对话(依赖 #1-#5 完成) |
