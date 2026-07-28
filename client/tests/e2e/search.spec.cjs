const { expect, test } = require("@playwright/test");

test("loads the search experience", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Native Plant Finder" })).toBeVisible();
  await expect(page.getByLabel("City or postal code")).toBeVisible();
  await expect(page.getByRole("button", { name: "Find plants" })).toBeVisible();
});

test("real Vancouver data changes when specialist species are enabled", async ({ page }) => {
  await page.route("https://nominatim.openstreetmap.org/**", (route) =>
    route.fulfill({
      json: [{
        place_id: 1,
        display_name: "Vancouver, British Columbia, Canada",
        lat: "49.2827",
        lon: "-123.1207"
      }]
    })
  );
  await page.goto("/");
  await page.getByLabel("City or postal code").fill("Vancouver, BC");
  await page.getByRole("button", { name: "Find plants" }).click();

  const countLine = page.locator(".count-line");
  await expect(countLine).toContainText("species");
  const defaultCount = await countLine.textContent();
  const defaultFirstPlant = await page.locator(".plantcard h3").first().textContent();
  await expect(page.getByText("Xanthium Orientale", { exact: true })).toHaveCount(0);

  await page.getByLabel("Show specialist species").check();
  await expect(countLine).not.toHaveText(defaultCount);
  await expect(page.locator(".plantcard h3").first()).not.toHaveText(defaultFirstPlant);
  await expect(page.getByText("Restoration use", { exact: true }).first()).toBeVisible();
});

function record(name, growthHabit, duration, min, max, recommendationCategory = null) {
  return {
    usageKey: [...name].reduce((total, character) => total + character.charCodeAt(0), 0),
    canonicalName: name,
    vernacularName: name,
    occurrenceCount: null,
    humanObservationCount: null,
    preservedSpecimenCount: null,
    coordinateUncertaintyMedianM: null,
    firstYear: null,
    lastYear: null,
    growthHabit,
    duration,
    matureHeightMinFt: min,
    matureHeightMaxFt: max,
    light: ["sun"],
    moisture: ["moist"],
    waterUse: null,
    soilCategories: [],
    bloomTime: [],
    bloomColor: [],
    lbjUrl: null,
    recommendationCategory
  };
}

async function mockSearch(page, plantOverride = null) {
  let geocodeRequests = 0;
  const plants = plantOverride ?? [
    ...Array.from({ length: 11 }, (_, index) =>
      record(
        `Prairie herb ${index + 1}`,
        ["Herb"],
        "annual|perennial",
        1,
        3,
        ["good_default", "conditional", "specialist_restoration"][index] ?? null
      )
    ),
    record("Tall tree", ["tree"], "perennial", 20, null),
    record("Little shrub", ["Subshrub"], "annual", null, 2),
    record("Unsafe plant", ["Herb"], "perennial", 1, 2, "poor_avoid"),
    record("Ambiguous plant", ["Herb"], "perennial", 1, 2, "invalid_ambiguous")
  ];
  await page.route("**/data/app_data/manifest.json", (route) =>
    route.fulfill({
      json: {
        ecoregionCount: 1,
        plantEcoregionCount: 1,
        missingLbjTraitCount: 0,
        ecoregions: [{ ecoregionId: 7, ecoregionName: "Test Prairie", path: "ecoregions/7.json", plantCount: plants.length }]
      }
    })
  );
  await page.route("**/data/ecoregion-boundaries.json", (route) =>
    route.fulfill({
      json: {
        generatedAt: "2026-01-01",
        source: "test",
        tolerance: 0,
        ecoregions: [
          {
            ecoregionId: 7,
            ecoregionName: "Test Prairie",
            bbox: [-124, 48, -122, 50],
            geometry: {
              type: "Polygon",
              coordinates: [[[-124, 48], [-122, 48], [-122, 50], [-124, 50], [-124, 48]]]
            }
          }
        ]
      }
    })
  );
  await page.route("**/data/app_data/ecoregions/7.json", (route) =>
    route.fulfill({
      json: {
        ecoregionId: 7,
        ecoregionName: "Test Prairie",
        plantCount: plants.length,
        plants
      }
    })
  );
  await page.route("https://nominatim.openstreetmap.org/search**", (route) => {
    geocodeRequests += 1;
    return route.fulfill({ json: [{ place_id: 1, display_name: "Victoria, BC", lat: "49", lon: "-123" }] });
  });
  return () => geocodeRequests;
}

async function submitSearch(page) {
  await page.goto("/");
  await page.getByLabel("City or postal code").fill("Victoria, BC");
  await page.getByRole("button", { name: "Find plants" }).click();
}

test("offers the opt-in when a region has only specialist recommendations", async ({ page }) => {
  await mockSearch(page, [
    record("Specialist first", ["Herb"], "perennial", 1, 2, "specialist_restoration"),
    record("Specialist second", ["Herb"], "perennial", 1, 2, "specialist_restoration")
  ]);
  await submitSearch(page);
  await expect(page.getByRole("heading", { name: "This region’s recommended plants are specialist species" })).toBeVisible();
  await page.getByRole("button", { name: "Show specialist species" }).click();
  await expect(page.getByRole("heading", { name: "Specialist First" })).toBeVisible();
  await expect(page.getByText("2 of 2 species")).toBeVisible();
});

test("shows a terminal empty state when a region has only excluded records", async ({ page }) => {
  await mockSearch(page, [
    record("Unsafe", ["Herb"], "perennial", 1, 2, "poor_avoid"),
    record("Ambiguous", ["Herb"], "perennial", 1, 2, "invalid_ambiguous")
  ]);
  await submitSearch(page);
  const emptyState = page.getByRole("heading", { name: "No recommended plants are available" }).locator("..");
  await expect(emptyState).toBeVisible();
  await expect(emptyState.getByRole("button", { name: /Clear/ })).toHaveCount(0);
});

test("filters before and after search without duplicate geocoding and recovers from zero results", async ({ page }) => {
  const getGeocodeRequests = await mockSearch(page);
  await page.goto("/");

  const filterToggle = page.getByRole("button", { name: /^Filters/ });
  if ((await filterToggle.getAttribute("aria-expanded")) === "false") await filterToggle.click();
  await page.getByLabel("Herb", { exact: true }).check();
  await page.getByLabel("City or postal code").fill("Victoria, BC");
  await page.getByRole("button", { name: "Find plants" }).click();

  await expect(page.getByRole("heading", { name: "Prairie Herb 1", exact: true })).toBeVisible();
  await expect(page.getByText("Garden-friendly", { exact: true })).toBeVisible();
  await expect(page.getByText("Site-dependent", { exact: true })).toBeVisible();
  await expect(page.getByText("Restoration use", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Prairie Herb 4", exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Prairie Herb 4", exact: true }).locator("xpath=ancestor::article").locator(".recommendation-badge")
  ).toHaveCount(0);
  await expect(page.getByText("Unsafe plant", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Ambiguous plant", { exact: true })).toHaveCount(0);
  await expect(page.getByText("10 of 12 species")).toBeVisible();
  await page.getByLabel("Show specialist species").check();
  await expect(page.getByText("Showing species usually intended for specialists and not regular gardens.")).toBeVisible();
  await expect(page.getByText("Restoration use", { exact: true })).toBeVisible();
  await expect(page.getByText("11 of 13 species")).toBeVisible();
  const headings = page.locator(".plantcard h3");
  await expect(headings.first()).toHaveText("Prairie Herb 3");
  expect(getGeocodeRequests()).toBe(1);

  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Page 2 of 2", { exact: true })).toBeVisible();
  await page.getByLabel("Herb", { exact: true }).uncheck();
  await page.getByLabel("Tree", { exact: true }).check();
  await expect(page.getByRole("heading", { name: "Tall Tree" })).toBeVisible();
  await expect(page.getByText("page 1 of 1")).toBeVisible();
  expect(getGeocodeRequests()).toBe(1);

  await page.getByLabel("Minimum").fill("30");
  await expect(page.getByRole("heading", { name: "No plants match these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("Minimum")).toHaveValue("");
  await expect(page.getByLabel("Maximum")).toHaveValue("");
  await expect(page.getByText("12 of 12 species")).toBeVisible();

  await page.getByLabel("Shade", { exact: true }).check();
  await expect(page.getByRole("heading", { name: "No plants match these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("12 of 12 species")).toBeVisible();
  expect(getGeocodeRequests()).toBe(1);
});

test("saves plants independently of filters and restores them after reload", async ({ page }) => {
  await mockSearch(page);
  await submitSearch(page);

  const firstCard = page.locator(".plantcard").first();
  const savedName = await firstCard.getByRole("heading").textContent();
  await firstCard.getByRole("button", { name: "Save plant" }).click();
  await expect(firstCard.getByText("Saved", { exact: true })).toBeVisible();
  await expect(page.getByText("View Saved Plants \u00b7 1/10", { exact: true })).toBeVisible();
  const savedToggle = page.getByRole("button", { name: /^View Saved Plants\s+1\/10$/ });
  const beforeSwitchBox = await savedToggle.boundingBox();
  expect(beforeSwitchBox).not.toBeNull();
  const resultsPanelBox = await page.locator("section.results-panel").first().boundingBox();
  expect(resultsPanelBox).not.toBeNull();

  const filterToggle = page.getByRole("button", { name: /^Filters/ });
  if ((await filterToggle.getAttribute("aria-expanded")) === "false") await filterToggle.click();
  await page.getByLabel("Tree", { exact: true }).check();
  await expect(page.getByRole("heading", { name: savedName })).toHaveCount(0);

  await savedToggle.click();
  const resultsToggle = page.getByRole("button", { name: "View Search Results", exact: true });
  await expect(resultsToggle).toBeVisible();
  const afterSwitchBox = await resultsToggle.boundingBox();
  expect(afterSwitchBox).not.toBeNull();
  const beforeSwitchRight = beforeSwitchBox.x + beforeSwitchBox.width;
  const afterSwitchRight = afterSwitchBox.x + afterSwitchBox.width;
  expect(Math.abs(afterSwitchRight - beforeSwitchRight)).toBeLessThanOrEqual(1);
  if ((page.viewportSize()?.width ?? 0) > 860) {
    expect(Math.abs(afterSwitchBox.y - beforeSwitchBox.y)).toBeLessThanOrEqual(1);
    const shortlistPanelBox = await page.locator(".shortlist-panel").boundingBox();
    expect(shortlistPanelBox).not.toBeNull();
    expect(shortlistPanelBox.width).toBeGreaterThan(resultsPanelBox.width);
    expect(shortlistPanelBox.x).toBeLessThan(resultsPanelBox.x);
  }
  await expect(page.getByRole("heading", { name: savedName })).toBeVisible();
  await resultsToggle.click();
  await expect(page.getByText("View Saved Plants \u00b7 1/10", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  await expect(page.getByText("View Saved Plants \u00b7 1/10", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^View Saved Plants\s+1\/10$/ }).click();
  await expect(page.getByRole("button", { name: "View Search Results", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: savedName })).toBeVisible();
});

test("saved plants empty state returns to and preserves current results", async ({ page }) => {
  await mockSearch(page);
  await submitSearch(page);
  const firstName = await page.locator(".plantcard h3").first().textContent();
  await page.getByRole("button", { name: /^View Saved Plants\s+0\/10$/ }).click();
  await expect(page.getByRole("button", { name: "View Search Results", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No saved plants yet" })).toBeVisible();
  await page.getByRole("button", { name: "Search for plants to save" }).click();
  await expect(page.locator(".plantcard h3").first()).toHaveText(firstName);
});
