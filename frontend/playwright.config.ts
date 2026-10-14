import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:5174",
    headless: true,
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
      args: ["--no-sandbox"],
    },
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        "cd ../backend && DATABASE_URL=postgresql+psycopg://rg:rg_local_dev@127.0.0.1:5432/rgstock_e2e RG_DATA_DIR=/tmp/rg-e2e-data .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001",
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: false,
    },
    {
      command: "RG_API_TARGET=http://127.0.0.1:8001 npm run dev -- --port 5174",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
    },
  ],
});
