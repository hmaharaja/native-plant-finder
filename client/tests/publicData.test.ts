import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parsePlantImageIndexWithStats } from "../src/validation";

const plantImageIndexPath = resolve(
  __dirname,
  "../public/data/app_data/plant_images/index.json"
);

describe("public data", () => {
  it("ships a plant image index with no records dropped by the runtime parser", () => {
    const payload = JSON.parse(readFileSync(plantImageIndexPath, "utf-8"));
    const result = parsePlantImageIndexWithStats(payload);

    expect(
      result.droppedRecordCount,
      `Dropped plant image records: ${result.droppedRecordKeys.slice(0, 20).join(", ")}`
    ).toBe(0);
    expect(result.parsedRecordCount).toBe(result.inputRecordCount);
  });
});
