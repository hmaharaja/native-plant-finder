import recommendationCategoryContract from "../../recommendation_categories.json";

const recommendationCategoryDefinitions = recommendationCategoryContract.categories;

export type RecommendationCategory = keyof typeof recommendationCategoryDefinitions;

export const RecommendationCategory = Object.freeze(
  Object.fromEntries(
    Object.keys(recommendationCategoryDefinitions).map((category) => [category, category])
  )
) as { readonly [Category in RecommendationCategory]: Category };

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface EcoregionManifestEntry {
  ecoregionId: number;
  ecoregionName: string | null;
  path: string;
  plantCount: number;
}

export interface Manifest {
  ecoregionCount: number;
  plantEcoregionCount: number;
  missingLbjTraitCount: number;
  ecoregions: EcoregionManifestEntry[];
}

export interface PlantRecord {
  usageKey: number | null;
  canonicalName: string | null;
  vernacularName: string | null;
  occurrenceCount: number | null;
  humanObservationCount: number | null;
  preservedSpecimenCount: number | null;
  coordinateUncertaintyMedianM: number | null;
  firstYear: number | null;
  lastYear: number | null;
  growthHabit: string[];
  duration: string | null;
  matureHeightMinFt: number | null;
  matureHeightMaxFt: number | null;
  light: string[];
  moisture: string[];
  waterUse: string | null;
  soilCategories: string[];
  bloomTime: string[];
  bloomColor: string[];
  lbjUrl: string | null;
  recommendationCategory: RecommendationCategory | null;
}

export interface EcoregionPayload {
  ecoregionId: number;
  ecoregionName: string | null;
  plantCount: number;
  plants: PlantRecord[];
}

export interface Coordinate {
  lat: number;
  lon: number;
}

export interface GeocoderCandidate {
  id: string;
  label: string;
  coordinate: Coordinate;
}

export type LinearRing = Coordinate[];
export type Polygon = LinearRing[];
export type MultiPolygon = Polygon[];

export interface BoundaryRecord {
  ecoregionId: number;
  ecoregionName: string | null;
  bbox: [number, number, number, number];
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
}

export interface BoundaryCollection {
  generatedAt: string;
  source: string;
  tolerance: number;
  ecoregions: BoundaryRecord[];
}
