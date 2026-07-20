const { expect, test } = require("@playwright/test");

test("loads the search experience", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Native Plant Finder" })).toBeVisible();
  await expect(page.getByLabel("City or postal code")).toBeVisible();
  await expect(page.getByRole("button", { name: "Find plants" })).toBeVisible();
});
