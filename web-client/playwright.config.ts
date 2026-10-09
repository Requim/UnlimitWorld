import { defineConfig } from "@playwright/test";

const channel = (process.env.M5_BROWSER_CHANNEL ?? "chrome") as "chrome";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel,
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: process.platform === "win32"
        ? "..\\.venv\\Scripts\\python.exe scripts\\run_test_api.py"
        : "../.venv/bin/python scripts/run_test_api.py",
      port: 8787,
      reuseExistingServer: true,
      timeout: 20_000,
    },
    {
      command: "npm run dev -- --port 5173",
      port: 5173,
      reuseExistingServer: true,
      timeout: 20_000,
    },
  ],
});
