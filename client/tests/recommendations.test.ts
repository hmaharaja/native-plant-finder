import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, filterPlants, GrowthHabitFilter } from "../src/filters";
import { paginate } from "../src/pagination";
import {
  permittedRecommendations,
  recommendationVisibility,
  recommendationLabel
} from "../src/recommendations";
import { RecommendationCategory, type PlantRecord } from "../src/types";

function plant(name: string, category: RecommendationCategory | null, growthHabit: string[] = []): PlantRecord {
  return {
    usageKey: name.length,
    canonicalName: name,
    vernacularName: name,
    occurrenceCount: null,
    humanObservationCount: null,
    preservedSpecimenCount: null,
    coordinateUncertaintyMedianM: null,
    firstYear: null,
    lastYear: null,
    growthHabit,
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
    recommendationCategory: category
  };
}

describe("recommendation categories", () => {
  it.each([
    [RecommendationCategory.good_default, "default-visible", "Garden-friendly"],
    [RecommendationCategory.conditional, "default-visible", "Site-dependent"],
    [RecommendationCategory.specialist_restoration, "specialist-opt-in", "Restoration use"],
    [RecommendationCategory.poor_avoid, "always-excluded", null],
    [RecommendationCategory.invalid_ambiguous, "always-excluded", null],
    [null, "default-visible", null]
  ] as const)("handles %s", (category, visibility, label) => {
    expect(recommendationVisibility(category)).toBe(visibility);
    expect(recommendationLabel(category)).toBe(label);
  });

  it("preserves order and removes excluded records before filtering and pagination", () => {
    const plants = [
      plant("first", RecommendationCategory.good_default, ["Herb"]),
      plant("hidden", RecommendationCategory.poor_avoid, ["Herb"]),
      plant("second", null, ["Tree"]),
      plant("ambiguous", RecommendationCategory.invalid_ambiguous, ["Herb"]),
      plant("third", RecommendationCategory.conditional, ["Herb"])
    ];

    const eligible = permittedRecommendations(plants, false);
    const filtered = filterPlants(eligible, { ...EMPTY_FILTERS, growthHabit: [GrowthHabitFilter.Herb] });
    const page = paginate(filtered, 1, 1);

    expect(eligible.map((record) => record.canonicalName)).toEqual(["first", "second", "third"]);
    expect(filtered.map((record) => record.canonicalName)).toEqual(["first", "third"]);
    expect(page.totalItems).toBe(2);
    expect(page.items[0].canonicalName).toBe("first");
  });

  it("places opted-in specialists first while preserving group order", () => {
    const plants = [
      plant("ordinary one", null),
      plant("specialist one", RecommendationCategory.specialist_restoration),
      plant("ordinary two", RecommendationCategory.good_default),
      plant("specialist two", RecommendationCategory.specialist_restoration)
    ];
    expect(permittedRecommendations(plants, false).map((item) => item.canonicalName)).toEqual([
      "ordinary one", "ordinary two"
    ]);
    expect(permittedRecommendations(plants, true).map((item) => item.canonicalName)).toEqual([
      "specialist one", "specialist two", "ordinary one", "ordinary two"
    ]);
  });
});
