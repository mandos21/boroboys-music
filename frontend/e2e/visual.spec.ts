import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

import { applyVisualPreferences, installApiFixtures } from "./fixtures";

const visualRoutes = [
  { path: "/", name: "dashboard", ready: "Good to have you here" },
  { path: "/series/series-1", name: "series", ready: "BoroCrew After Hours" },
  { path: "/rounds/round-open", name: "round", ready: "September after dark" },
  { path: "/rounds/round-published-demo", name: "published-round", ready: "August favorites" },
  { path: "/rounds/round-open/submit", name: "submission", ready: "Choose a track" },
  { path: "/profile", name: "profile", ready: "Your record, so far" },
  { path: "/settings", name: "settings", ready: "Connected services" },
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

test("distinguishable result colors apply to the dark matrix", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "One browser covers the palette behavior.");
  await page.goto("/settings");
  await page.getByRole("switch", { name: "Distinguishable result colors" }).click();
  await page.goto("/rounds/round-open");
  await expect(page.getByRole("heading", { name: "September after dark" })).toBeVisible();
  const colors = await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
    const cells = ["correct", "incorrect"].map((result) => {
      const cell = document.createElement("button");
      cell.className = `attribution-matrix-cell ${result}`;
      cell.style.setProperty("--heat", "1");
      document.body.append(cell);
      return cell;
    });
    const backgrounds = cells.map((cell) => getComputedStyle(cell).backgroundColor);
    cells.forEach((cell) => cell.remove());
    return backgrounds;
  });
  expect(colors[0]).toContain("96, 165, 250");
  expect(colors[1]).toContain("251, 146, 60");
});

test("the Settings connection action keeps its button contrast", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "One browser covers button styling.");
  await page.goto("/settings");
  const action = page.getByRole("link", { name: "Connect another Last.fm account" });
  await expect(action).toBeVisible();
  expect(await action.evaluate((element) => getComputedStyle(element).color)).toBe(
    "rgb(255, 255, 255)",
  );
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  expect(await action.evaluate((element) => getComputedStyle(element).color)).toBe(
    "rgb(255, 255, 255)",
  );
});

test("published rounds keep the playlist prominent and fold away history and extra tracks", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "One browser covers this interaction.");
  await page.goto("/rounds/round-published-demo");
  await expect(page.getByRole("heading", { name: "August favorites", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Spotify playlist" })).toBeVisible();
  await expect(page.getByText("Submissions are currently closed.")).toBeHidden();
  await page.getByRole("button", { name: "Round details" }).click();
  await expect(page.getByText("Submissions are currently closed.")).toBeVisible();
  await expect(page.getByText("Night Drive", { exact: true }).first()).toBeVisible();
  await expect(page.locator("#round-submission-list > li")).toHaveCount(5);
  await page.getByRole("button", { name: "Show all 7 tracks" }).click();
  await expect(page.locator("#round-submission-list > li")).toHaveCount(7);
  const results = await new AxeBuilder({ page }).include("main").analyze();
  expect(results.violations).toEqual([]);
});

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
