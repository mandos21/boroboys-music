import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:4173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    browserName: "chromium",
    colorScheme: "light",
    locale: "en-US",
    timezoneId: "America/New_York",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: "visual-desktop-light",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "visual-desktop-dark",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: "visual-tablet-light",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "visual-tablet-dark",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "visual-mobile-light",
      use: {
        ...devices["Desktop Chrome"],
        isMobile: true,
        hasTouch: true,
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: "visual-mobile-dark",
      use: {
        ...devices["Desktop Chrome"],
        isMobile: true,
        hasTouch: true,
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: "accessibility",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
  ],
  snapshotPathTemplate: "{testDir}/{testFilePath}-snapshots/{arg}-{projectName}{ext}",
});
