import { describe, expect, it } from "vitest";
import { formatHeight, formatNumber } from "../src/formatters";
import type { PlantRecord } from "../src/types";

const basePlant: PlantRecord = {
  usageKey: 1,
  canonicalName: "Aster laevis",
  vernacularName: "smooth aster",
  occurrenceCount: 1,
  humanObservationCount: 1,
  preservedSpecimenCount: 0,
  coordinateUncertaintyMedianM: null,
  firstYear: 2020,
  lastYear: 2020,
  growthHabit: [],
  duration: null,
  matureHeightMinFt: null,
  matureHeightMaxFt: null,
  light: [],
  moisture: [],
  waterUse: null,
  soilCategories: [],
  bloomTime: [],
  bloomColor: [],
  lbjUrl: null
};

describe("formatters", () => {
  it("limits displayed numbers to two decimal places", () => {
    expect(formatNumber(2.3333333333)).toBe("2.33");
    expect(formatNumber(10)).toBe("10");
  });

  it("formats height ranges with two decimal places at most", () => {
    expect(
      formatHeight({
        ...basePlant,
        matureHeightMinFt: 0.6666666667,
        matureHeightMaxFt: 2.3333333333
      })
    ).toBe("0.67-2.33 ft");
  });
});
