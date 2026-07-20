// @ts-check
const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.cjs",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:5173/native-plant-finder/",
    trace: "on-first-retry"
  },
  webServer: {
    command: "npm run dev -- --base=/native-plant-finder/",
    url: "http://127.0.0.1:5173/native-plant-finder/",
    reuseExistingServer: !process.env.CI
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 5"] } }
  ]
});
