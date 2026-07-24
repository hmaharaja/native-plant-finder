const { expect, test } = require("@playwright/test");

test("loads the search experience", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Native Plant Finder" })).toBeVisible();
  await expect(page.getByLabel("City or postal code")).toBeVisible();
  await expect(page.getByRole("button", { name: "Find plants" })).toBeVisible();
});

function record(name, growthHabit, duration, min, max) {
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
    recommendationCategory: null
  };
}

async function mockSearch(page) {
  let geocodeRequests = 0;
  const plants = [
    ...Array.from({ length: 11 }, (_, index) =>
      record(`Prairie herb ${index + 1}`, ["Herb"], "annual|perennial", 1, 3)
    ),
    record("Tall tree", ["tree"], "perennial", 20, null),
    record("Little shrub", ["Subshrub"], "annual", null, 2)
  ];
  await page.route("**/data/app_data/manifest.json", (route) =>
    route.fulfill({
      json: {
        ecoregionCount: 1,
        plantEcoregionCount: 1,
        missingLbjTraitCount: 0,
        ecoregions: [{ ecoregionId: 7, ecoregionName: "Test Prairie", path: "ecoregions/7.json", plantCount: 13 }]
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
        plantCount: 13,
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

test("filters before and after search without duplicate geocoding and recovers from zero results", async ({ page }) => {
  const getGeocodeRequests = await mockSearch(page);
  await page.goto("/");

  const filterToggle = page.getByRole("button", { name: /^Filters/ });
  if ((await filterToggle.getAttribute("aria-expanded")) === "false") await filterToggle.click();
  await page.getByLabel("Herb", { exact: true }).check();
  await page.getByLabel("City or postal code").fill("Victoria, BC");
  await page.getByRole("button", { name: "Find plants" }).click();

  await expect(page.getByRole("heading", { name: "Prairie Herb 1", exact: true })).toBeVisible();
  await expect(page.getByText("11 of 13 species")).toBeVisible();
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
  await expect(page.getByText("13 of 13 species")).toBeVisible();

  await page.getByLabel("Shade", { exact: true }).check();
  await expect(page.getByRole("heading", { name: "No plants match these filters" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByText("13 of 13 species")).toBeVisible();
  expect(getGeocodeRequests()).toBe(1);
});
