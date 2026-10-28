import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { applyVisualPreferences, installApiFixtures, seriesNotifications } from "./fixtures";

test.beforeEach(async ({ page }, testInfo) => {
  await applyVisualPreferences(page, testInfo.project.name.endsWith("dark"));
  await installApiFixtures(page);
});

test("series tabs and notification editor work across viewports", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/admin/series/series-1?tab=notifications");
  await expect(page.getByRole("heading", { name: "Notification rules" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Series management" });
  await expect(nav.getByRole("link", { name: "Notifications" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: testInfo.outputPath("notifications.png"), fullPage: true });
  await page.getByRole("button", { name: "Add notification" }).click();
  const editor = page.locator("section.notification-rule");
  await editor.getByLabel("Rule name").fill("Last call");
  await editor.getByLabel("How long").fill("6");
  await editor.getByRole("combobox", { name: "Unit", exact: true }).selectOption("60");
  await nav.getByRole("link", { name: "Members" }).click();
  await expect(page.getByRole("heading", { name: "Series members" })).toBeVisible();
  await nav.getByRole("link", { name: "Notifications" }).click();
  await expect(editor.getByLabel("Rule name")).toHaveValue("Last call");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Series members" })).toBeVisible();
  await page.goForward();
  await expect(editor.getByLabel("How long")).toHaveValue("6");
  await editor.getByLabel("Milestone").selectOption("published");
  await expect(editor.getByLabel("Timing")).toHaveValue("1");
  await expect(editor.getByLabel("Timing").locator('option[value="-1"]')).toHaveJSProperty(
    "disabled",
    true,
  );
  await page.route("**/api/v1/admin/series/series-1/notifications/preview", (route) =>
    route.fulfill({
      json: { ...seriesNotifications.upcoming[0], message: "Your preview message" },
    }),
  );
  await editor.getByRole("button", { name: "Preview message" }).click();
  await expect(editor.getByText("Your preview message")).toBeVisible();
  await expect(editor.getByText("Preview only. No message has been sent.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  const accessibility = await new AxeBuilder({ page }).include("main").analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("notification-editor.png"), fullPage: true });
  await editor.getByRole("button", { name: "Cancel", exact: true }).click();
  for (const [tab, heading] of [
    ["History", "Past rounds"],
    ["Rounds", "Current and upcoming rounds"],
  ]) {
    await nav.getByRole("link", { name: tab, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
  await expect(nav.getByRole("link", { name: "Automation", exact: true })).toHaveCount(0);
  const settings = page.getByRole("region", { name: "Round settings" });
  const rounds = page.getByRole("region", { name: "Current and upcoming rounds" });
  await page.screenshot({ path: testInfo.outputPath("rounds.png"), fullPage: true });
  await settings.getByRole("button", { name: /Default round checks/ }).click();
  await settings.getByLabel("Add a check").selectOption("no_recent_series_repeat");
  await settings.getByRole("button", { name: /Guess Who defaults/ }).click();
  await settings.getByRole("switch", { name: "Enable Guess Who for new rounds" }).check();
  await settings.getByLabel("Minutes to keep names hidden after publishing").fill("90");
  await rounds.getByRole("button", { name: /Round automation/ }).click();
  await rounds.getByLabel(/Tracks each contributor/).fill("4");
  await rounds.getByRole("button", { name: /Round automation/ }).click();
  await nav.getByRole("link", { name: "Members", exact: true }).click();
  await expect(page.getByRole("button", { name: "Edit series details" })).toHaveCount(0);
  await nav.getByRole("link", { name: "Rounds", exact: true }).click();
  await expect(settings.getByLabel("Minutes to keep names hidden after publishing")).toHaveValue(
    "90",
  );
  await rounds.getByRole("button", { name: /Round automation/ }).click();
  await expect(rounds.getByLabel(/Tracks each contributor/)).toHaveValue("4");
  const savedPlan = page.waitForRequest(
    (request) => request.method() === "PATCH" && request.url().endsWith("/admin/series/series-1"),
  );
  await rounds.getByRole("button", { name: "Save plan" }).click();
  expect((await savedPlan).postDataJSON().round_plan).toMatchObject({
    kind: "calendar",
    submission_limit: 4,
    title_template: "{month} favorites",
    publish_delay_minutes: 0,
  });
  await rounds.getByRole("button", { name: /Schedule a round/ }).click();
  await expect(rounds.getByLabel("Title", { exact: true })).toBeVisible();
  const roundAccessibility = await new AxeBuilder({ page }).include("main").analyze();
  expect(roundAccessibility.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("rounds-expanded.png"), fullPage: true });
  await settings.getByRole("button", { name: "Edit series details" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByLabel("Description")).toBeVisible();
  await page.keyboard.press("Escape");
  expect(errors).toEqual([]);
});
