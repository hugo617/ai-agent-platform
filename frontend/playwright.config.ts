import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration.
 *
 * Prerequisites for running E2E (local or CI):
 *   1. A running Postgres (docker-compose up -d postgres)
 *   2. The backend on :8000 with APP_ENV=development so the /dev/* token
 *      endpoints are enabled, and OPENAI_BASE_URL pointing at the mock server.
 *   3. The mock OpenAI server on :8088 (see e2e/mock-openai-server.py).
 *   4. `alembic upgrade head` + `python scripts/init_admin.py` to seed the
 *      super-admin.
 *
 * Playwright only auto-starts the frontend dev server (below). The backend,
 * Postgres, and mock server must be started by the caller (locally) or by the
 * CI workflow (see .github/workflows/ci.yml e2e job).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // shared backend DB — run serially to avoid data races
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? "line" : "list",
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },

  // Auto-start the frontend dev server. The backend (:8000) + mock OpenAI
  // server (:8088) + Postgres are started externally (locally by the operator,
  // in CI by the e2e workflow steps).
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
