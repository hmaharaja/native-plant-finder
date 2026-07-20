import { MONTH_LABELS } from "./constants";
import type { PlantRecord } from "./types";

const TWO_DECIMAL_FORMATTER = new Intl.NumberFormat("en-CA", {
  maximumFractionDigits: 2
});

export function titleCase(value: string): string {
  return value.replace(/\w\S*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
}

export function formatNumber(value: number): string {
  return TWO_DECIMAL_FORMATTER.format(value);
}

export function formatList(values: string[], fallback = "Unknown"): string {
  return values.length ? values.map(titleCase).join(", ") : fallback;
}

export function formatMonthList(values: string[]): string {
  return values.length ? values.map((value) => MONTH_LABELS[value.toLowerCase()] ?? titleCase(value)).join(", ") : "Unknown";
}

export function formatHeight(plant: PlantRecord): string {
  if (plant.matureHeightMinFt === null && plant.matureHeightMaxFt === null) {
    return "Unknown";
  }
  if (plant.matureHeightMinFt !== null && plant.matureHeightMaxFt !== null) {
    return `${formatNumber(plant.matureHeightMinFt)}-${formatNumber(plant.matureHeightMaxFt)} ft`;
  }
  if (plant.matureHeightMaxFt !== null) {
    return `Up to ${formatNumber(plant.matureHeightMaxFt)} ft`;
  }
  return plant.matureHeightMinFt === null ? "Unknown" : `From ${formatNumber(plant.matureHeightMinFt)} ft`;
}

export function displayName(plant: PlantRecord): string {
  return plant.vernacularName ? titleCase(plant.vernacularName) : plant.canonicalName ?? "Unnamed plant";
}

export function scientificName(plant: PlantRecord): string {
  return plant.canonicalName ?? "Scientific name unavailable";
}
