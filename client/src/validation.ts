import { CANADA_BOUNDS, MAX_LOCATION_QUERY_LENGTH } from "./constants";
import type {
  BoundaryCollection,
  BoundaryRecord,
  Coordinate,
  EcoregionManifestEntry,
  EcoregionPayload,
  Manifest,
  PlantImage,
  PlantImageIndex,
  PlantImageIndexRecord,
  PlantRecord,
  RecommendationCategory
} from "./types";
import { RecommendationCategory as RecommendationCategoryValue } from "./types";

const COLLAPSED_SPACE = /\s+/g;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/g;
const ALLOWED_PLANT_DETAIL_HOST = "www.wildflower.org";
const ALLOWED_PLANT_DETAIL_PATH = "/plants/result.php";
const ALLOWED_IMAGE_SOURCE_HOSTS = new Set(["www.gbif.org", "gbif.org", "commons.wikimedia.org"]);

export interface PlantImageIndexParseResult {
  index: PlantImageIndex;
  inputRecordCount: number;
  parsedRecordCount: number;
  droppedRecordCount: number;
  droppedRecordKeys: string[];
}

export function sanitizeLocationQuery(raw: string): string {
  return raw
    .replace(CONTROL_CHARS, "")
    .replace(COLLAPSED_SPACE, " ")
    .trim()
    .slice(0, MAX_LOCATION_QUERY_LENGTH);
}

export function isValidLocationQuery(query: string): boolean {
  return query.length >= 2 && /[a-zA-Z0-9]/.test(query);
}

export function isValidCoordinate(value: Coordinate): boolean {
  return (
    Number.isFinite(value.lat) &&
    Number.isFinite(value.lon) &&
    value.lat >= CANADA_BOUNDS.minLat &&
    value.lat <= CANADA_BOUNDS.maxLat &&
    value.lon >= CANADA_BOUNDS.minLon &&
    value.lon <= CANADA_BOUNDS.maxLon
  );
}

export function safePlantDetailUrl(rawUrl: string | null): string | null {
  if (!rawUrl) {
    return null;
  }
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:") {
      return null;
    }
    if (url.hostname !== ALLOWED_PLANT_DETAIL_HOST) {
      return null;
    }
    if (url.pathname !== ALLOWED_PLANT_DETAIL_PATH) {
      return null;
    }
    if (!url.searchParams.has("id_plant")) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

function safeHttpsUrl(rawUrl: unknown): string | null {
  if (typeof rawUrl !== "string" || !rawUrl) {
    return null;
  }
  try {
    const url = new URL(rawUrl);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function safePlantImageSourceUrl(rawUrl: string | null): string | null {
  const safeUrl = safeHttpsUrl(rawUrl);
  if (!safeUrl) {
    return null;
  }
  const url = new URL(safeUrl);
  return ALLOWED_IMAGE_SOURCE_HOSTS.has(url.hostname) ? url.toString() : null;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || isNumber(value);
}

function isNullableRecommendationCategory(value: unknown): value is RecommendationCategory | null {
  return (
    value === null ||
    (typeof value === "string" && Object.prototype.hasOwnProperty.call(RecommendationCategoryValue, value))
  );
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function parseManifestEntry(value: unknown): EcoregionManifestEntry {
  assert(isObject(value), "manifest ecoregion entry must be an object");
  assert(isNumber(value.ecoregionId), "manifest ecoregionId must be a number");
  assert(isNullableString(value.ecoregionName), "manifest ecoregionName must be a string or null");
  assert(typeof value.path === "string", "manifest path must be a string");
  assert(isNumber(value.plantCount), "manifest plantCount must be a number");
  return {
    ecoregionId: value.ecoregionId,
    ecoregionName: value.ecoregionName,
    path: value.path,
    plantCount: value.plantCount
  };
}

export function parseManifest(value: unknown): Manifest {
  assert(isObject(value), "manifest must be an object");
  assert(isNumber(value.ecoregionCount), "manifest ecoregionCount must be a number");
  assert(isNumber(value.plantEcoregionCount), "manifest plantEcoregionCount must be a number");
  assert(isNumber(value.missingLbjTraitCount), "manifest missingLbjTraitCount must be a number");
  assert(Array.isArray(value.ecoregions), "manifest ecoregions must be an array");
  return {
    ecoregionCount: value.ecoregionCount,
    plantEcoregionCount: value.plantEcoregionCount,
    missingLbjTraitCount: value.missingLbjTraitCount,
    ecoregions: value.ecoregions.map(parseManifestEntry)
  };
}

function parsePlantRecord(value: unknown): PlantRecord {
  assert(isObject(value), "plant record must be an object");
  assert(isNullableNumber(value.usageKey), "usageKey must be a number or null");
  assert(isNullableString(value.canonicalName), "canonicalName must be a string or null");
  assert(isNullableString(value.vernacularName), "vernacularName must be a string or null");
  assert(isNullableNumber(value.occurrenceCount), "occurrenceCount must be a number or null");
  assert(isNullableNumber(value.humanObservationCount), "humanObservationCount must be a number or null");
  assert(isNullableNumber(value.preservedSpecimenCount), "preservedSpecimenCount must be a number or null");
  assert(isNullableNumber(value.coordinateUncertaintyMedianM), "coordinateUncertaintyMedianM must be a number or null");
  assert(isNullableNumber(value.firstYear), "firstYear must be a number or null");
  assert(isNullableNumber(value.lastYear), "lastYear must be a number or null");
  assert(isStringArray(value.growthHabit), "growthHabit must be an array of strings");
  assert(isNullableString(value.duration), "duration must be a string or null");
  assert(isNullableNumber(value.matureHeightMinFt), "matureHeightMinFt must be a number or null");
  assert(isNullableNumber(value.matureHeightMaxFt), "matureHeightMaxFt must be a number or null");
  assert(isStringArray(value.light), "light must be an array of strings");
  assert(isStringArray(value.moisture), "moisture must be an array of strings");
  assert(isNullableString(value.waterUse), "waterUse must be a string or null");
  assert(isStringArray(value.soilCategories), "soilCategories must be an array of strings");
  assert(isStringArray(value.bloomTime), "bloomTime must be an array of strings");
  assert(isStringArray(value.bloomColor), "bloomColor must be an array of strings");
  assert(isNullableString(value.lbjUrl), "lbjUrl must be a string or null");
  assert(
    value.recommendationCategory === undefined ||
      isNullableRecommendationCategory(value.recommendationCategory),
    "recommendationCategory must be a recognized category or null"
  );
  return {
    ...value,
    recommendationCategory: value.recommendationCategory ?? null
  } as unknown as PlantRecord;
}

function parsePlantImage(value: unknown): PlantImage | null {
  if (!isObject(value)) {
    return null;
  }
  const imageUrl = safeHttpsUrl(value.imageUrl);
  const thumbnailUrl = safeHttpsUrl(value.thumbnailUrl);
  if (!imageUrl || !thumbnailUrl || typeof value.source !== "string" || !isNumber(value.rank)) {
    return null;
  }
  if (!isNullableString(value.gbifId)) {
    return null;
  }
  if (
    !isNullableString(value.license) ||
    !isNullableString(value.creator) ||
    !isNullableString(value.credit) ||
    !isNullableString(value.publisher) ||
    !isNullableNumber(value.width) ||
    !isNullableNumber(value.height)
  ) {
    return null;
  }
  if (value.acceptedAt !== undefined && !isNullableString(value.acceptedAt)) {
    return null;
  }
  return {
    source: value.source,
    gbifId: value.gbifId,
    imageUrl,
    thumbnailUrl,
    sourceUrl: safePlantImageSourceUrl(isNullableString(value.sourceUrl) ? value.sourceUrl : null),
    license: value.license,
    creator: value.creator,
    credit: value.credit,
    publisher: value.publisher,
    width: value.width,
    height: value.height,
    acceptedAt: value.acceptedAt ?? null,
    rank: value.rank
  };
}

function parsePlantImageIndexRecord(usageKey: string, value: unknown): PlantImageIndexRecord | null {
  if (!isObject(value) || !isNumber(value.usageKey) || String(value.usageKey) !== usageKey) {
    return null;
  }
  const primaryImage = parsePlantImage(value.primaryImage);
  if (!primaryImage) {
    return null;
  }
  const secondaryImage = value.secondaryImage === null ? null : parsePlantImage(value.secondaryImage);
  return {
    usageKey: value.usageKey,
    primaryImage,
    secondaryImage
  };
}

export function parsePlantImageIndex(value: unknown): PlantImageIndex {
  assert(isObject(value), "plant image index must be an object");
  return parsePlantImageIndexWithStats(value).index;
}

export function parsePlantImageIndexWithStats(value: unknown): PlantImageIndexParseResult {
  assert(isObject(value), "plant image index must be an object");
  const index: PlantImageIndex = {};
  const droppedRecordKeys: string[] = [];
  for (const [usageKey, record] of Object.entries(value)) {
    if (!/^\d+$/.test(usageKey)) {
      droppedRecordKeys.push(usageKey);
      continue;
    }
    const parsed = parsePlantImageIndexRecord(usageKey, record);
    if (parsed) {
      index[usageKey] = parsed;
    } else {
      droppedRecordKeys.push(usageKey);
    }
  }
  return {
    index,
    inputRecordCount: Object.keys(value).length,
    parsedRecordCount: Object.keys(index).length,
    droppedRecordCount: droppedRecordKeys.length,
    droppedRecordKeys
  };
}

export function parseEcoregionPayload(value: unknown): EcoregionPayload {
  assert(isObject(value), "ecoregion payload must be an object");
  assert(isNumber(value.ecoregionId), "ecoregionId must be a number");
  assert(isNullableString(value.ecoregionName), "ecoregionName must be a string or null");
  assert(isNumber(value.plantCount), "plantCount must be a number");
  assert(Array.isArray(value.plants), "plants must be an array");
  return {
    ecoregionId: value.ecoregionId,
    ecoregionName: value.ecoregionName,
    plantCount: value.plantCount,
    plants: value.plants.map(parsePlantRecord)
  };
}

function parseBoundary(value: unknown): BoundaryRecord {
  assert(isObject(value), "boundary must be an object");
  assert(isNumber(value.ecoregionId), "boundary ecoregionId must be a number");
  assert(isNullableString(value.ecoregionName), "boundary ecoregionName must be a string or null");
  assert(Array.isArray(value.bbox) && value.bbox.length === 4 && value.bbox.every(isNumber), "boundary bbox must contain four numbers");
  assert(isObject(value.geometry), "boundary geometry must be an object");
  assert(value.geometry.type === "Polygon" || value.geometry.type === "MultiPolygon", "boundary geometry type is unsupported");
  assert(Array.isArray(value.geometry.coordinates), "boundary coordinates must be an array");
  return value as unknown as BoundaryRecord;
}

export function parseBoundaryCollection(value: unknown): BoundaryCollection {
  assert(isObject(value), "boundary collection must be an object");
  assert(typeof value.generatedAt === "string", "boundary generatedAt must be a string");
  assert(typeof value.source === "string", "boundary source must be a string");
  assert(isNumber(value.tolerance), "boundary tolerance must be a number");
  assert(Array.isArray(value.ecoregions), "boundary ecoregions must be an array");
  return {
    generatedAt: value.generatedAt,
    source: value.source,
    tolerance: value.tolerance,
    ecoregions: value.ecoregions.map(parseBoundary)
  };
}
