import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { applyVisualPreferences, installApiFixtures } from "./fixtures";

test.beforeEach(async ({ page }, info) => {
  await applyVisualPreferences(page, info.project.name.endsWith("dark"));
  await installApiFixtures(page);
});

test("home and series creation dialog remain usable and accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Add another track" })).toHaveAttribute(
    "href",
    "/rounds/round-open/submit",
  );
  await expect(page.getByRole("progressbar", { name: "Your submitted tracks" })).toHaveAttribute(
    "value",
    "1",
  );
  expect((await new AxeBuilder({ page }).include("main").analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole("button", { name: "Create a series" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("textbox", { name: "Name", exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual(
    [],
  );
  await dialog.getByRole("textbox", { name: "Name", exact: true }).fill("My new series");
  await dialog.getByRole("button", { name: "Advanced options" }).click();
  await expect(dialog.getByRole("textbox", { name: /^URL name/ })).toHaveValue("my-new-series");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Create a series" })).toBeFocused();
});

test("completed and opted-out rounds do not ask for more picks", async ({ page }) => {
  await page.route("**/api/v1/series", async (route) => {
    await route.fulfill({
      json: [
        {
          id: "series-1",
          name: "Monthly Music",
          latestPublishedRound: null,
          featuredRound: {
            id: "round-open",
            title: "September",
            status: "open",
            opensAt: "2026-09-01T00:00:00Z",
            closesAt: "2026-10-01T00:00:00Z",
            publishAt: "2026-10-02T00:00:00Z",
            isMember: true,
            yourSubmissionCount: 1,
            submissionLimit: 3,
            declinedFurtherSubmissions: true,
            artworkUrls: [],
            spotifyPlaylistUrl: null,
            publishedAt: null,
          },
        },
      ],
    });
  });
  await page.goto("/");
  await expect(page.getByText("Your pick is in. You’re all set.")).toBeVisible();
  await expect(page.getByRole("link", { name: "View your picks" })).toHaveAttribute(
    "href",
    "/rounds/round-open#round-submissions",
  );
  await expect(page.getByRole("link", { name: /Choose a track|Add another track/ })).toHaveCount(0);
});
