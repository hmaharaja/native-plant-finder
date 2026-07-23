import { describe, expect, it } from "vitest";
import {
  activeFilterCount,
  DurationFilter,
  EMPTY_FILTERS,
  FILTER_CATEGORY_CONFIG,
  filterPlants,
  GrowthHabitFilter,
  heightRangesOverlap,
  LightFilter,
  normalizeDelimitedValues,
  plantMatchesFilters,
  validateMatureHeight
} from "../src/filters";
import type { PlantRecord } from "../src/types";

function plant(overrides: Partial<PlantRecord> = {}): PlantRecord {
  return {
    usageKey: 1,
    canonicalName: "Testus plantus",
    vernacularName: "Test plant",
    occurrenceCount: null,
    humanObservationCount: null,
    preservedSpecimenCount: null,
    coordinateUncertaintyMedianM: null,
    firstYear: null,
    lastYear: null,
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
    lbjUrl: null,
    ...overrides
  };
}

describe("filter domain", () => {
  it("normalizes reusable pipe-delimited values", () => {
    expect(normalizeDelimitedValues(" Annual |PERENNIAL||")).toEqual(["annual", "perennial"]);
    expect(normalizeDelimitedValues(null)).toEqual([]);
  });

  it("derives every category option from enums", () => {
    expect(FILTER_CATEGORY_CONFIG.find((item) => item.category === "growthHabit")?.values).toContain("subshrub");
    expect(FILTER_CATEGORY_CONFIG.find((item) => item.category === "duration")?.values).toEqual(
      Object.values(DurationFilter)
    );
  });

  it("validates height boundaries", () => {
    expect(validateMatureHeight({ minimumFt: -1, maximumFt: null })).toMatch(/non-negative/);
    expect(validateMatureHeight({ minimumFt: 4, maximumFt: 3 })).toMatch(/Minimum/);
    expect(validateMatureHeight({ minimumFt: 2, maximumFt: 3 })).toBeNull();
  });

  it("uses OR within categories and AND across categories case-insensitively", () => {
    const record = plant({ growthHabit: ["Subshrub"], light: ["SUN"] });
    const filters = {
      ...EMPTY_FILTERS,
      growthHabit: [GrowthHabitFilter.Herb, GrowthHabitFilter.Subshrub],
      light: [LightFilter.Sun]
    };
    expect(plantMatchesFilters(record, filters)).toBe(true);
    expect(plantMatchesFilters({ ...record, light: ["shade"] }, filters)).toBe(false);
  });

  it("matches compound duration values", () => {
    expect(
      plantMatchesFilters(plant({ duration: "annual|perennial" }), {
        ...EMPTY_FILTERS,
        duration: [DurationFilter.Perennial]
      })
    ).toBe(true);
  });

  it("matches overlapping and one-sided height ranges", () => {
    expect(
      heightRangesOverlap(
        { minimumFt: 5, maximumFt: null },
        { minimumFt: null, maximumFt: 6 }
      )
    ).toBe(true);
    expect(
      heightRangesOverlap(
        { minimumFt: null, maximumFt: 2 },
        { minimumFt: 3, maximumFt: null }
      )
    ).toBe(false);
  });

  it("excludes missing traits only when their category is active", () => {
    const unknown = plant();
    expect(filterPlants([unknown], EMPTY_FILTERS)).toEqual([unknown]);
    expect(filterPlants([unknown], { ...EMPTY_FILTERS, duration: [DurationFilter.Annual] })).toEqual([]);
    expect(
      filterPlants([unknown], { ...EMPTY_FILTERS, matureHeight: { minimumFt: 1, maximumFt: null } })
    ).toEqual([]);
  });

  it("counts each selected value and height boundary", () => {
    expect(
      activeFilterCount({
        ...EMPTY_FILTERS,
        duration: [DurationFilter.Annual, DurationFilter.Perennial],
        matureHeight: { minimumFt: 1, maximumFt: 4 }
      })
    ).toBe(4);
  });
});
