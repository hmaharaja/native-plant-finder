import { describe, expect, it } from "vitest";
import {
  activeFilterCount,
  DurationFilter,
  EMPTY_FILTERS,
  FILTER_CATEGORY_CONFIG,
  filterPlants,
  GrowthHabitFilter,
  heightRangeFitsWithin,
  LightFilter,
  normalizeDelimitedValues,
  parseOptionalHeight,
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
    recommendationCategory: null,
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
    expect(validateMatureHeight({ minimumFt: Number.NaN, maximumFt: null })).toMatch(/finite/);
    expect(validateMatureHeight({ minimumFt: null, maximumFt: Number.POSITIVE_INFINITY })).toMatch(/finite/);
    expect(validateMatureHeight({ minimumFt: 4, maximumFt: 3 })).toMatch(/Minimum/);
    expect(validateMatureHeight({ minimumFt: 2.25, maximumFt: 3.75 })).toBeNull();
  });

  it("parses optional decimal heights without interpreting untrusted text", () => {
    expect(parseOptionalHeight("")).toBeNull();
    expect(parseOptionalHeight("  ")).toBeNull();
    expect(parseOptionalHeight("6.87")).toBe(6.87);
    expect(parseOptionalHeight(".5")).toBe(0.5);
    expect(parseOptionalHeight("5.")).toBe(5);
    expect(parseOptionalHeight("-1")).toBeNaN();
    expect(parseOptionalHeight("Infinity")).toBeNaN();
    expect(parseOptionalHeight("1e3")).toBeNaN();
    expect(parseOptionalHeight("<script>alert(1)</script>")).toBeNaN();
    expect(parseOptionalHeight("5; DROP TABLE plants")).toBeNaN();
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

  it("requires a plant range to fit inclusively inside the requested range", () => {
    expect(
      heightRangeFitsWithin(
        { minimumFt: 5, maximumFt: 15 },
        { minimumFt: 5, maximumFt: 15 }
      )
    ).toBe(true);
    expect(
      heightRangeFitsWithin(
        { minimumFt: 4.49, maximumFt: 15 },
        { minimumFt: 5, maximumFt: 15 }
      )
    ).toBe(false);
  });

  it("applies a half-foot tolerance at both boundaries", () => {
    const requested = { minimumFt: 5, maximumFt: 15 };
    expect(heightRangeFitsWithin({ minimumFt: 4.5, maximumFt: 15.5 }, requested)).toBe(true);
    expect(heightRangeFitsWithin({ minimumFt: 4.499, maximumFt: 15 }, requested)).toBe(false);
    expect(heightRangeFitsWithin({ minimumFt: 5, maximumFt: 15.501 }, requested)).toBe(false);
  });

  it("supports maximum-only requested and recorded ranges", () => {
    expect(
      heightRangeFitsWithin(
        { minimumFt: null, maximumFt: 4 },
        { minimumFt: null, maximumFt: 3.5 }
      )
    ).toBe(true);
    expect(
      heightRangeFitsWithin(
        { minimumFt: null, maximumFt: 4.01 },
        { minimumFt: null, maximumFt: 3.5 }
      )
    ).toBe(false);
  });

  it("supports minimum-only filters while rejecting unbounded plants from finite maxima", () => {
    expect(
      heightRangeFitsWithin(
        { minimumFt: 4.5, maximumFt: 20 },
        { minimumFt: 5, maximumFt: null }
      )
    ).toBe(true);
    expect(
      heightRangeFitsWithin(
        { minimumFt: 5, maximumFt: null },
        { minimumFt: null, maximumFt: 20 }
      )
    ).toBe(false);
    expect(
      heightRangeFitsWithin(
        { minimumFt: 5, maximumFt: null },
        { minimumFt: 5, maximumFt: null }
      )
    ).toBe(true);
  });

  it("rejects malformed ranges and invalid tolerance values", () => {
    expect(
      heightRangeFitsWithin(
        { minimumFt: -1, maximumFt: 2 },
        { minimumFt: null, maximumFt: 4 }
      )
    ).toBe(false);
    expect(
      heightRangeFitsWithin(
        { minimumFt: 1, maximumFt: 2 },
        { minimumFt: 4, maximumFt: 3 }
      )
    ).toBe(false);
    expect(
      heightRangeFitsWithin(
        { minimumFt: 1, maximumFt: 2 },
        { minimumFt: 1, maximumFt: 2 },
        Number.NaN
      )
    ).toBe(false);
    expect(
      heightRangeFitsWithin(
        { minimumFt: 1, maximumFt: 2 },
        { minimumFt: 1, maximumFt: 2 },
        -0.5
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
