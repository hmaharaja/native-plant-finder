import type { PlantRecord } from "./types";

export enum FilterCategory {
  GrowthHabit = "growthHabit",
  Light = "light",
  Moisture = "moisture",
  Duration = "duration"
}

export enum GrowthHabitFilter {
  Herb = "herb",
  Shrub = "shrub",
  Subshrub = "subshrub",
  Tree = "tree",
  Vine = "vine",
  GrassGrasslike = "grass/grass-like",
  CactusSucculent = "cactus/succulent",
  Fern = "fern"
}

export enum LightFilter {
  Sun = "sun",
  PartShade = "part shade",
  Shade = "shade"
}

export enum MoistureFilter {
  Dry = "dry",
  Moist = "moist",
  Wet = "wet"
}

export enum DurationFilter {
  Annual = "annual",
  Biennial = "biennial",
  Perennial = "perennial"
}

export interface MatureHeightRange {
  readonly minimumFt: number | null;
  readonly maximumFt: number | null;
}

export interface FilterState {
  readonly growthHabit: readonly GrowthHabitFilter[];
  readonly light: readonly LightFilter[];
  readonly moisture: readonly MoistureFilter[];
  readonly duration: readonly DurationFilter[];
  readonly matureHeight: MatureHeightRange;
}

export interface FilterCategoryConfig {
  readonly category: FilterCategory;
  readonly label: string;
  readonly values: readonly string[];
}

export const HEIGHT_TOLERANCE_FT = 0.5;

export const FILTER_CATEGORY_CONFIG: readonly FilterCategoryConfig[] = [
  { category: FilterCategory.GrowthHabit, label: "Growth habit", values: Object.values(GrowthHabitFilter) },
  { category: FilterCategory.Light, label: "Light", values: Object.values(LightFilter) },
  { category: FilterCategory.Moisture, label: "Moisture", values: Object.values(MoistureFilter) },
  { category: FilterCategory.Duration, label: "Duration", values: Object.values(DurationFilter) }
];

export const EMPTY_FILTERS: FilterState = {
  growthHabit: [],
  light: [],
  moisture: [],
  duration: [],
  matureHeight: { minimumFt: null, maximumFt: null }
};

export function normalizeDelimitedValues(value: string | null, delimiter = "|"): string[] {
  if (!value) return [];
  return value
    .split(delimiter)
    .map((part) => part.trim().toLocaleLowerCase())
    .filter(Boolean);
}

export function validateMatureHeight(range: MatureHeightRange): string | null {
  const { minimumFt, maximumFt } = range;
  if (
    (minimumFt !== null && (!Number.isFinite(minimumFt) || minimumFt < 0)) ||
    (maximumFt !== null && (!Number.isFinite(maximumFt) || maximumFt < 0))
  ) {
    return "Heights must be finite, non-negative numbers.";
  }
  if (minimumFt !== null && maximumFt !== null && minimumFt > maximumFt) {
    return "Minimum height cannot exceed maximum height.";
  }
  return null;
}

export function parseOptionalHeight(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(trimmed)) return Number.NaN;
  return Number(trimmed);
}

function matchesCategory(recorded: readonly string[], requested: readonly string[]): boolean {
  if (!requested.length) return true;
  const normalized = new Set(recorded.map((value) => value.trim().toLocaleLowerCase()));
  return requested.some((value) => normalized.has(value.toLocaleLowerCase()));
}

export function heightRangeFitsWithin(
  recorded: MatureHeightRange,
  requested: MatureHeightRange,
  toleranceFt = HEIGHT_TOLERANCE_FT
): boolean {
  if (
    validateMatureHeight(recorded) ||
    validateMatureHeight(requested) ||
    !Number.isFinite(toleranceFt) ||
    toleranceFt < 0
  ) {
    return false;
  }

  const recordedMinimum = recorded.minimumFt ?? 0;
  const recordedMaximum = recorded.maximumFt ?? Number.POSITIVE_INFINITY;
  const allowedMinimum =
    requested.minimumFt === null ? Number.NEGATIVE_INFINITY : Math.max(0, requested.minimumFt - toleranceFt);
  const allowedMaximum =
    requested.maximumFt === null ? Number.POSITIVE_INFINITY : requested.maximumFt + toleranceFt;

  return recordedMinimum >= allowedMinimum && recordedMaximum <= allowedMaximum;
}

export function plantMatchesFilters(plant: PlantRecord, filters: FilterState): boolean {
  const heightActive = filters.matureHeight.minimumFt !== null || filters.matureHeight.maximumFt !== null;
  const hasRecordedHeight = plant.matureHeightMinFt !== null || plant.matureHeightMaxFt !== null;
  return (
    matchesCategory(plant.growthHabit, filters.growthHabit) &&
    matchesCategory(plant.light, filters.light) &&
    matchesCategory(plant.moisture, filters.moisture) &&
    matchesCategory(normalizeDelimitedValues(plant.duration), filters.duration) &&
    (!heightActive ||
      (hasRecordedHeight &&
        heightRangeFitsWithin(
          { minimumFt: plant.matureHeightMinFt, maximumFt: plant.matureHeightMaxFt },
          filters.matureHeight
        )))
  );
}

export function filterPlants(plants: readonly PlantRecord[], filters: FilterState): PlantRecord[] {
  if (validateMatureHeight(filters.matureHeight)) return [];
  return plants.filter((plant) => plantMatchesFilters(plant, filters));
}

export function activeFilterCount(filters: FilterState): number {
  return (
    filters.growthHabit.length +
    filters.light.length +
    filters.moisture.length +
    filters.duration.length +
    Number(filters.matureHeight.minimumFt !== null) +
    Number(filters.matureHeight.maximumFt !== null)
  );
}
