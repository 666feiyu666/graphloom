import { defineConfig } from "@playwright/test";
import path from "node:path";

const e2eDir = path.resolve(process.cwd(), ".e2e");
const dbPath = path.join(e2eDir, "graphloom.db");
const backendDir = path.resolve(process.cwd(), "../backend");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 12_000 },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    channel: "chrome",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `bash -lc 'rm -rf "${e2eDir}" && mkdir -p "${e2eDir}" && cd "${backendDir}" && GRAPPHLOOM_DB_PATH="${dbPath}" GRAPPHLOOM_FRONTEND_DIST="${path.join(e2eDir, "dist")}" GRAPPHLOOM_RATE_LIMIT_PER_MINUTE=100000 uv run uvicorn app.main:app --host 127.0.0.1 --port 8000'`,
      url: "http://127.0.0.1:8000/api/v1/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
