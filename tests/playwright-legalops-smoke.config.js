const os = require("os");
const path = require("path");
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: /smoke-(cadastro-processos|tarefas-kanban-receiver)\.spec\.js/,
  timeout: 600000,
  expect: { timeout: 10000 },
  workers: 1,
  outputDir:
    process.env.CASEHUB_SMOKE_PLAYWRIGHT_OUTPUT_DIR ||
    path.join(os.tmpdir(), `casehub-legalops-playwright-${new Date().toISOString().replace(/[:.]/g, "-")}`),
  use: {
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    actionTimeout: 15000,
  },
  reporter: [["list"]],
});
