import { test, expect } from "@playwright/test";

/**
 * Main-flow E2E test: login → create Agent → chat → view history.
 *
 * Prerequisites (started outside Playwright — see playwright.config.ts):
 *   - Backend on :8000 (APP_ENV=development, OPENAI_BASE_URL=http://localhost:8088)
 *   - Postgres on :5433 with `alembic upgrade head` + `python scripts/init_admin.py`
 *   - Mock OpenAI server on :8088
 *
 * Login uses the seeded super-admin (admin / Admin@123456) via the password
 * form — deterministic and offline, no Logto needed.
 */

const ADMIN = { identifier: "admin", password: "Admin@123456" };

test("login → create agent → chat → view history", async ({ page }) => {
  // ----------------------------------------------------------- 1. login
  await page.goto("/login");
  await page.getByTestId("login-identifier").fill(ADMIN.identifier);
  await page.getByTestId("login-password").fill(ADMIN.password);
  await page.getByTestId("login-submit").click();

  // Wait until we leave the login page (URL no longer contains /login).
  await expect(page).not.toHaveURL(/\/login/);

  // ----------------------------------------------------------- 2. create agent
  await page.goto("/agents");
  // Ensure the agents page loaded (heading + create button).
  await expect(page.getByTestId("create-agent-btn")).toBeVisible({ timeout: 10_000 });

  const agentName = `E2E Agent ${Date.now()}`;
  await page.getByTestId("create-agent-btn").click();
  await page.getByTestId("agent-name-input").fill(agentName);
  await page.getByTestId("agent-submit").click();

  // The new agent appears in the list (also in the success toast).
  await expect(page.getByText(agentName).first()).toBeVisible({ timeout: 10_000 });

  // ----------------------------------------------------------- 3. chat
  await page.goto("/chat");
  // Wait for the chat panel to render.
  await expect(page.getByTestId("message-input")).toBeVisible({ timeout: 10_000 });

  const greeting = `你好 E2E ${Date.now()}`;
  await page.getByTestId("message-input").fill(greeting);
  await page.getByTestId("send-btn").click();

  // The user's message appears immediately (optimistic append).
  await expect(page.getByText(greeting)).toBeVisible();

  // The assistant's reply streams in from the mock LLM. Wait for it to have
  // non-empty content (the mock replies with a fixed string).
  await expect(
    page.getByTestId("assistant-message").filter({ hasText: "模拟回复" })
  ).toBeVisible({ timeout: 20_000 });

  // ----------------------------------------------------------- 4. history persists
  await page.reload();

  // After reload, the conversation list still contains conversations from
  // prior turns (proving the chat + messages were persisted server-side).
  await expect(page.getByTestId("message-input")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("会话").first()).toBeVisible();
  // At least one conversation exists in the sidebar list.
  const convButtons = page.locator('[title="删除会话"]');
  await expect(convButtons.first()).toBeVisible({ timeout: 10_000 });
  const count = await convButtons.count();
  expect(count).toBeGreaterThanOrEqual(1);
});
