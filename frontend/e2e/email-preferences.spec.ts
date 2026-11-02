import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { applyVisualPreferences, installApiFixtures } from "./fixtures";

test.beforeEach(async ({ page }, testInfo) => {
  await applyVisualPreferences(page, testInfo.project.name.endsWith("dark"));
  await installApiFixtures(page);
});

test("personal preferences persist between settings and the series dialog", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let global = { notifyReminderEmails: true, notifyRoundPublishedEmails: true };
  let own = { ...global };
  const record = () => ({
    seriesId: "series-1",
    seriesName: "BoroCrew After Hours",
    isArchived: false,
    ...own,
    effectiveReminderEmails: global.notifyReminderEmails && own.notifyReminderEmails,
    effectiveRoundPublishedEmails:
      global.notifyRoundPublishedEmails && own.notifyRoundPublishedEmails,
  });
  const changes = (data: Record<string, boolean>) => ({
    ...(data.notify_reminder_emails !== undefined
      ? { notifyReminderEmails: data.notify_reminder_emails }
      : {}),
    ...(data.notify_round_published_emails !== undefined
      ? { notifyRoundPublishedEmails: data.notify_round_published_emails }
      : {}),
  });
  await page.route("**/api/v1/profiles/me/notification-settings**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() === "PATCH") {
      const change = changes(route.request().postDataJSON());
      if (path.endsWith("series-1")) own = { ...own, ...change };
      else global = { ...global, ...change };
    }
    return route.fulfill({
      json: path.endsWith("/series") ? [record()] : path.endsWith("series-1") ? record() : global,
    });
  });
  // An email link expands the matching series automatically.
  await page.goto("/settings?series=series-1#notifications-title");
  const all = page.getByRole("region", { name: "Across all series", exact: true });
  const series = page.getByRole("region", { name: "Your series", exact: true });
  const personalReminders = series.getByRole("switch", { name: "Round reminders", exact: true });
  await expect(personalReminders).toBeVisible();
  await personalReminders.focus();
  await page.keyboard.press("Space");
  await expect(personalReminders).not.toBeChecked();
  await expect(series.getByRole("button", { name: /BoroCrew After Hours/ })).toContainText(
    "Reminders off",
  );
  await all.getByRole("switch", { name: "Round published", exact: true }).click();
  const personalPublished = series.getByRole("switch", { name: "Round published", exact: true });
  await expect(personalPublished).toBeDisabled();
  await expect(personalPublished).not.toBeChecked();
  await expect(series.getByText(/Publication emails are turned off for all series/)).toBeVisible();
  await page
    .locator(".email-preferences")
    .screenshot({ path: testInfo.outputPath("settings-preferences.png") });
  expect((await new AxeBuilder({ page }).include("main").analyze()).violations).toEqual([]);
  await all.getByRole("switch", { name: "Round published", exact: true }).click();
  await expect(personalPublished).toBeEnabled();
  await expect(personalPublished).toBeChecked();
  await expect(personalReminders).not.toBeChecked();
  await page.goto("/series/series-1");
  const trigger = page.getByRole("button", { name: "My email notifications", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "My email notifications" });
  await expect(
    dialog.getByRole("switch", { name: "Round reminders", exact: true }),
  ).not.toBeChecked();
  await dialog.getByRole("switch", { name: "Round reminders", exact: true }).click();
  await expect(dialog.getByRole("switch", { name: "Round reminders", exact: true })).toBeChecked();
  await dialog.screenshot({ path: testInfo.outputPath("series-preferences.png") });
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    [],
  );
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  expect(errors).toEqual([]);
});

test("failed saves keep the previous value and allow a retry", async ({ page }) => {
  await page.goto("/settings?series=series-1");
  const series = page.getByRole("region", { name: "Your series", exact: true });
  const reminders = series.getByRole("switch", { name: "Round reminders", exact: true });
  await expect(reminders).toBeChecked();
  await page.route("**/api/v1/profiles/me/notification-settings/series/series-1", (route) =>
    route.fulfill({ status: 503, json: { detail: "Unavailable" } }),
  );
  await reminders.click();
  await expect(page.getByText("Couldn’t save notification setting")).toBeVisible();
  await expect(reminders).toBeEnabled();
  await expect(reminders).toBeChecked();
  await page.route("**/api/v1/profiles/me/notification-settings/series/series-1", (route) =>
    route.fulfill({
      json: {
        seriesId: "series-1",
        seriesName: "BoroCrew After Hours",
        isArchived: false,
        notifyReminderEmails: false,
        notifyRoundPublishedEmails: true,
        effectiveReminderEmails: false,
        effectiveRoundPublishedEmails: false,
      },
    }),
  );
  await reminders.click();
  await expect(reminders).not.toBeChecked();
});

test("signed-out preference links preserve the series through sign-in", async ({ page }) => {
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({ status: 401, json: {} }));
  await page.route("**/api/v1/profiles/me/notification-settings", (route) =>
    route.fulfill({ status: 401, json: {} }),
  );
  const destination = "/settings?series=series-1#notifications-title";
  await page.goto(destination);
  await expect(
    page.getByRole("heading", { name: "Sign in to manage your email preferences" }),
  ).toBeVisible();
  const links = page.getByRole("link", { name: "Sign in", exact: true });
  await expect(links).toHaveCount(2);
  for (const link of await links.all()) {
    await expect(link).toHaveAttribute(
      "href",
      `/api/v1/auth/login?return=${encodeURIComponent(destination)}`,
    );
  }
});

for (const scenario of [
  { reminders: false, published: false, message: "Email notifications are off globally" },
  { reminders: false, published: true, message: "Round reminders are off globally" },
  { reminders: true, published: false, message: "Publication emails are off globally" },
]) {
  test(`dialog explains ${scenario.message.toLowerCase()} and dismisses cleanly`, async ({
    page,
  }, testInfo) => {
    await page.route("**/api/v1/profiles/me/notification-settings", (route) =>
      route.fulfill({
        json: {
          notifyReminderEmails: scenario.reminders,
          notifyRoundPublishedEmails: scenario.published,
        },
      }),
    );
    await page.goto("/series/series-1");
    const trigger = page.getByRole("button", { name: "My email notifications", exact: true });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "My email notifications" });
    await expect(dialog.getByText(scenario.message, { exact: true })).toBeVisible();
    await expect(dialog.getByText(/Mattermost/)).toHaveCount(0);
    const reminders = dialog.getByRole("switch", { name: "Round reminders", exact: true });
    const published = dialog.getByRole("switch", { name: "Round published", exact: true });
    if (scenario.reminders) await expect(reminders).toBeEnabled();
    else await expect(reminders).toBeDisabled();
    if (scenario.published) await expect(published).toBeEnabled();
    else await expect(published).toBeDisabled();
    await expect(
      dialog.getByRole("link", { name: "Manage email preferences across all series" }),
    ).toHaveAttribute("href", "/settings#notifications-title");
    const viewport = page.viewportSize()!;
    const box = (await dialog.boundingBox())!;
    if (viewport.width <= 704) {
      expect(box.x).toBeCloseTo(0, 0);
      expect(box.y).toBeCloseTo(0, 0);
      expect(box.width).toBeCloseTo(viewport.width, 0);
      expect(box.height).toBeCloseTo(viewport.height, 0);
    } else {
      expect(box.x + box.width / 2).toBeCloseTo(viewport.width / 2, 0);
      expect(box.y + box.height / 2).toBeCloseTo(viewport.height / 2, 0);
      expect(box.width).toBeLessThan(600);
      await page.mouse.click(8, 8);
      await expect(dialog).not.toBeVisible();
      // Pointer dismissal may leave focus on the clicked surface; Escape and
      // the explicit close button restore focus to the trigger below.
      await trigger.click();
    }
    if (!scenario.reminders && !scenario.published) {
      await dialog.screenshot({ path: testInfo.outputPath("global-emails-off.png") });
      expect(
        (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations,
      ).toEqual([]);
    }
    await dialog.getByRole("button", { name: "Close", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });
}
