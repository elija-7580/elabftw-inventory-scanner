import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 30000,
  retries: 0,
  webServer: {
    command:
      "cd /repo && SCANNER_WEB_DIR=/repo/web/dist /repo/.venv/bin/uvicorn inventory_scanner.app:app --host 127.0.0.1 --port 8765",
    url: "http://127.0.0.1:8765/health",
    reuseExistingServer: true,
    timeout: 120000,
  },
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "webkit-iphone",
      use: { ...devices["iPhone 13"] },
    },
  ],
});
