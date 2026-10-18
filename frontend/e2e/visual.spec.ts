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

test("round settings and checks have breathing room", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "One browser covers the spacing.");
  await page.route("**/api/v1/admin/rounds/round-open", (route) =>
    route.fulfill({
      json: {
        id: "round-open",
        seriesId: "series-1",
        title: "October 2026",
        status: "open",
        timezone: "America/New_York",
        opensAt: "2026-10-01T00:00:00-04:00",
        closesAt: "2026-10-31T23:59:00-04:00",
        publishAt: "2026-11-01T23:59:00-05:00",
        submissionLimit: 3,
        prompt: null,
        publisherAccountId: null,
        attributionRevealDelaySeconds: null,
        policySnapshot: [],
        members: [],
      },
    }),
  );
  await page.route("**/api/v1/admin/rounds/round-open/publication", (route) =>
    route.fulfill({ json: null }),
  );
  await page.goto("/admin/rounds/round-open");
  const sections = page.locator(".admin-shell > .round-settings");
  await expect(sections).toHaveCount(2);
  const gap = await sections.evaluateAll(([first, second]) => {
    const firstBox = first.getBoundingClientRect();
    const secondBox = second.getBoundingClientRect();
    return secondBox.top - firstBox.bottom;
  });
  expect(gap).toBeGreaterThanOrEqual(12);
});

test("submission review keeps refresh status steady and explains shared listens", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "One browser covers the review behavior.");
  await page.route("**/api/v1/connections", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/rounds/round-open/track-search?*", (route) =>
    route.fulfill({
      json: [
        {
          name: "Night Drive",
          artist: "The Lanterns",
          album: "Slow Gold",
          artworkUrl: null,
          spotifyTrackId: "track-1",
          spotifyUri: "spotify:track:1",
        },
      ],
    }),
  );
  await page.route("**/api/v1/rounds/round-open/evaluate-track", (route) =>
    route.fulfill({
      json: {
        trackId: "track-1",
        canSubmit: true,
        limitRemaining: 2,
        requiresWarningConfirmation: true,
        policyResults: [
          {
            kind: "duplicate_in_series",
            decision: "warn",
            message: "This track has already appeared in this series.",
            result: {},
            version: "1",
          },
        ],
      },
    }),
  );
  let evidenceRequests = 0;
  await page.route("**/api/v1/rounds/round-open/tracks/track-1/evidence", (route) => {
    evidenceRequests += 1;
    return route.fulfill({
      json: {
        roundId: "round-open",
        trackId: "track-1",
        evidence: [
          {
            accountId: "listener-1",
            displayName: "Riley",
            isMine: false,
            playcount: 2,
            artistPlaycount: 207,
            albumPlaycount: 2,
            fetchedAt: "2026-09-08T12:00:00-04:00",
            refreshAfter:
              evidenceRequests === 1 ? "2026-09-08T12:00:00-04:00" : "2026-09-10T12:00:00-04:00",
            status: "available",
          },
        ],
      },
    });
  });
  await page.goto("/rounds/round-open/submit");
  await page.getByRole("button", { name: "Maybe later" }).click();
  await page.getByLabel("Search Spotify").fill("Night Drive");
  await page.getByRole("button", { name: /Night Drive.*The Lanterns/ }).click();
  await expect(
    page.getByText("This may be familiar to 1 other person in the round."),
  ).toBeVisible();
  await expect(page.getByText("Checking for recent Last.fm listens…")).toBeVisible();
  await expect(page.getByText("Checking for recent Last.fm listens…")).toBeHidden({
    timeout: 6000,
  });
  expect(evidenceRequests).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("This track has already appeared in this series.")).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /I understand and still want to submit/ }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Link it in settings" })).toBeVisible();
  await expect(page.getByText(/observed Sep/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Submit track" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /I understand and still want to submit/ }).check();
  await expect(page.getByRole("button", { name: "Submit track" })).toBeEnabled();
  const accessibility = await new AxeBuilder({ page }).include(".review-panel").analyze();
  expect(accessibility.violations).toEqual([]);
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  const darkAccessibility = await new AxeBuilder({ page }).include(".review-panel").analyze();
  expect(darkAccessibility.violations).toEqual([]);
});

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

test("matrix cells reveal their explanation on a phone tap", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "visual-mobile-light", "Touch viewport only.");
  const alice = { id: "alice", displayName: "Alice", profileImageUrl: null };
  const bob = { id: "bob", displayName: "Bob", profileImageUrl: null };
  await page.route("**/api/v1/rounds/round-published-demo/attribution", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        published: true,
        revealed: true,
        revealAt: null,
        roster: [],
        game: null,
        leaderboard: [],
      },
    }),
  );
  await page.route("**/api/v1/rounds/round-published-demo/attribution/breakdown", (route) =>
    route.fulfill({
      json: [
        {
          contributor: alice,
          songs: [
            {
              submissionId: "song-a",
              guesses: [{ guesser: bob, guessedContributor: bob, isCorrect: false }],
            },
          ],
        },
        { contributor: bob, songs: [] },
      ],
    }),
  );
  await page.goto("/rounds/round-published-demo");
  const cell = page.getByRole("button", { name: "Bob guessed Alice's songs were Bob's" });
  await expect(cell).toBeVisible();
  await cell.tap();
  await expect(page.getByRole("tooltip")).toContainText("Bob guessed Alice's songs were Bob's");
  expect(await cell.evaluate((element) => getComputedStyle(element).userSelect)).toBe("none");
});

test("Guess Who awards keep their layout across screen sizes", async ({ page }, testInfo) => {
  test.skip(
    ![
      "visual-desktop-light",
      "visual-desktop-dark",
      "visual-mobile-light",
      "visual-mobile-dark",
    ].includes(testInfo.project.name),
  );
  const kevin = { id: "kevin", displayName: "Kevin Reynolds", profileImageUrl: null };
  const kay = { id: "kay", displayName: "Kay Michelet", profileImageUrl: null };
  const matt = { id: "matt", displayName: "Matt DeGenaro", profileImageUrl: null };
  type PreviewGuess = {
    guesser: typeof kevin;
    guessedContributor: typeof kevin;
    isCorrect: boolean;
  };
  const song = (name: string, guesses: PreviewGuess[]) => ({
    submissionId: name,
    track: { name, artist: "A favorite artist", artworkUrl: null },
    groupCorrectCount: guesses.filter((guess) => guess.isCorrect).length,
    groupTotalCount: guesses.length,
    guesses,
  });
  await page.route("**/api/v1/rounds/round-published-demo/attribution", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        published: true,
        revealed: true,
        revealAt: null,
        roster: [],
        game: null,
        leaderboard: [
          { contributor: kay, correctCount: 12, totalCount: 20 },
          { contributor: matt, correctCount: 12, totalCount: 20 },
          { contributor: kevin, correctCount: 7, totalCount: 20 },
        ],
      },
    }),
  );
  await page.route("**/api/v1/rounds/round-published-demo/attribution/breakdown", (route) =>
    route.fulfill({
      json: [
        {
          contributor: kevin,
          groupCorrectCount: 1,
          groupTotalCount: 2,
          yourCorrectCount: null,
          yourTotalCount: null,
          songs: [
            song("Kevin's pick", [
              { guesser: kay, guessedContributor: matt, isCorrect: false },
              { guesser: matt, guessedContributor: kevin, isCorrect: true },
            ]),
          ],
        },
        {
          contributor: kay,
          groupCorrectCount: 0,
          groupTotalCount: 2,
          yourCorrectCount: null,
          yourTotalCount: null,
          songs: [
            song("Kay's pick", [
              { guesser: kevin, guessedContributor: matt, isCorrect: false },
              { guesser: matt, guessedContributor: matt, isCorrect: false },
            ]),
          ],
        },
        {
          contributor: matt,
          groupCorrectCount: 2,
          groupTotalCount: 2,
          yourCorrectCount: null,
          yourTotalCount: null,
          songs: [
            song("Matt's pick", [
              { guesser: kay, guessedContributor: matt, isCorrect: true },
              { guesser: kevin, guessedContributor: matt, isCorrect: true },
            ]),
          ],
        },
      ],
    }),
  );
  await page.route("**/api/v1/rounds/round-published-demo/awards", (route) =>
    route.fulfill({
      json: [
        {
          title: "Underground",
          variant: "underground",
          detail: "Dug deepest into the catalog.",
          explanation: "3 of 3 tracks in this round's least listened-to third",
          contributor: kevin,
        },
        {
          title: "Eclectic",
          variant: "eclectic",
          detail: "Took the long way around the genres.",
          explanation: "3 of 3 tracks covered distinct genre groups",
          contributor: kay,
        },
        {
          title: "Specialized",
          variant: "specialized",
          detail: "Stayed in a familiar lane.",
          explanation: "3 of 3 tracks shared similar genre groups",
          contributor: matt,
        },
        {
          title: "Uncharted",
          variant: "uncharted",
          detail: "Made the genre map draw a blank.",
          explanation: "2 of 3 tracks had no recognized genre tags",
          contributor: kevin,
        },
      ],
    }),
  );
  await page.goto("/rounds/round-published-demo");
  const roundAwards = page.getByLabel("Round awards");
  await expect(roundAwards.locator(".attribution-award")).toHaveCount(4);
  const awards = page.getByLabel("Guess Who awards");
  await expect(awards.locator(".attribution-award")).toHaveCount(4);
  const columns = await awards.evaluate(
    (element) => getComputedStyle(element).gridTemplateColumns.split(" ").length,
  );
  expect(columns).toBe(testInfo.project.name.includes("desktop") ? 4 : 1);
  await page.addStyleTag({ content: ".app-header { position: static !important; }" });
  await expect(awards).toHaveScreenshot("guess-who-awards.png", { animations: "disabled" });
  await expect(roundAwards).toHaveScreenshot("round-awards.png", { animations: "disabled" });
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

test("the series management action stays readable in dark mode", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "One browser covers button styling.");
  await page.goto("/series/series-1");
  const action = page.getByRole("link", { name: "Manage series" });
  await expect(action).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.dataset.theme = "dark";
  });
  await expect
    .poll(() => action.evaluate((element) => getComputedStyle(element).color))
    .toBe("rgb(220, 232, 224)");
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

test("help hints stay in the viewport and dismiss with Escape", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "accessibility", "Accessibility project only.");
  await page.goto("/series/series-1");

  const hint = page.getByRole("button", { name: "How the group genre mix works" });
  await hint.click();
  const hintPanel = page.locator(".info-hint-popup").filter({ hasText: "Each bar is built" });
  await expect(hintPanel).toBeVisible();

  const bounds = await hintPanel.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds?.x).toBeGreaterThanOrEqual(0);
  expect(bounds?.y).toBeGreaterThanOrEqual(0);
  expect(bounds?.x + bounds?.width).toBeLessThanOrEqual(1440);
  expect(bounds?.y + bounds?.height).toBeLessThanOrEqual(1000);

  await page.keyboard.press("Escape");
  await expect(hintPanel).toBeHidden();
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
