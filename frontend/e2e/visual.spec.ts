import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { applyVisualPreferences, installApiFixtures } from "./fixtures";

const visualRoutes = [
  { path: "/", name: "dashboard", ready: "Good to have you here" },
  { path: "/series/series-1", name: "series", ready: "BoroCrew After Hours" },
  { path: "/rounds/round-open", name: "round", ready: "September after dark" },
  { path: "/rounds/round-open/submit", name: "submission", ready: "Choose a track" },
  { path: "/profile", name: "profile", ready: "Your record, so far" },
  { path: "/admin/series/series-1", name: "series-administration", ready: "Automation" },
];

test.beforeEach(async ({ page }, testInfo) => {
  await applyVisualPreferences(page, testInfo.project.name.endsWith("dark"));
  await installApiFixtures(page);
});

for (const route of visualRoutes) {
  test(`${route.name} remains visually stable`, async ({ page }, testInfo) => {
    test.skip(!testInfo.project.name.startsWith("visual-"), "Visual projects only.");
    await page.goto(route.path);
    await expect(page.getByText(route.ready, { exact: false }).first()).toBeVisible();
    await expect(page).toHaveScreenshot(`${route.name}.png`, {
      fullPage: true,
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.002,
    });
  });
}

test("representative screens have no automatically detectable accessibility violations", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "Accessibility project only.");
  for (const route of visualRoutes) {
    await page.goto(route.path);
    await expect(page.locator("main")).toBeVisible();
    const results = await new AxeBuilder({ page })
      .include("main")
      .disableRules(["landmark-one-main"])
      .analyze();
    expect(results.violations, route.name).toEqual([]);
  }
});

test("keyboard users can skip the shell and reach page content", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "Accessibility project only.");
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skipLink = page.getByText("Skip to main content");
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("help hints stay in the viewport and dismiss after focus leaves", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "Accessibility project only.");
  await page.goto("/series/series-1");

  const hint = page.getByRole("button", { name: "How the group genre mix works" });
  await hint.focus();
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toBeVisible();

  const bounds = await tooltip.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds?.x).toBeGreaterThanOrEqual(0);
  expect(bounds?.y).toBeGreaterThanOrEqual(0);
  expect(bounds?.x + bounds?.width).toBeLessThanOrEqual(1440);
  expect(bounds?.y + bounds?.height).toBeLessThanOrEqual(1000);

  await page.getByRole("link", { name: "BoroCrew Music home" }).focus();
  await expect(tooltip).toBeHidden();
});

test("the mobile account menu uses a dismissible sheet", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "Accessibility project only.");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByRole("button", { name: "Open account menu" }).click();
  const menu = page.getByRole("dialog", { name: "Account menu" });
  await expect(menu).toBeVisible();
  await menu.getByRole("button", { name: "Close account menu" }).click();
  await expect(menu).toBeHidden();
});

test("a profile visit does not change the series genre grid", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "Accessibility project only.");
  await page.goto("/profile");
  await page.locator('a[href="/series/series-1"]').first().click();

  const grid = page.locator(".series-insights-grid");
  await expect(grid).toBeVisible();
  await expect
    .poll(() =>
      grid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length),
    )
    .toBe(2);

  const panels = grid.locator(":scope > .series-insight-panel");
  const [fingerprint, mix] = await Promise.all([
    panels.nth(0).boundingBox(),
    panels.nth(1).boundingBox(),
  ]);
  expect(fingerprint).not.toBeNull();
  expect(mix).not.toBeNull();
  expect(Math.abs((fingerprint?.y ?? 0) - (mix?.y ?? 0))).toBeLessThan(1);
  expect(Math.abs((fingerprint?.width ?? 0) - (mix?.width ?? 0))).toBeLessThan(1);
});

test("mobile account sheet remains visually stable", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("visual-"), "Visual projects only.");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByRole("button", { name: "Open account menu" }).click();
  await expect(page.getByRole("dialog", { name: "Account menu" })).toBeVisible();
  await expect(page).toHaveScreenshot("account-menu.png");
});
