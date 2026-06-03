const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  testMatch: /smoke-test.*\.js|visual-audit.*\.js|final-visual-audit.*\.js/,
  timeout: 600000,
  expect: { timeout: 10000 },
  use: {
    baseURL: 'http://REDACTED-HOST:8002',
    screenshot: 'on',
    headless: true,
    viewport: { width: 1440, height: 900 },
    actionTimeout: 15000,
  },
  reporter: [['list']],
});
