export const APP_TITLE = "Native Plant Finder";
export const PAGE_SIZE = 10;
export const DATA_ROOT = "data/app_data";
export const BOUNDARY_PATH = "data/ecoregion-boundaries.json";
export const NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search";
export const ZIPPOPOTAM_ENDPOINT = "https://api.zippopotam.us/ca";
export const GEOCODER_MIN_INTERVAL_MS = 1000;
export const MAX_LOCATION_QUERY_LENGTH = 120;
export const CANADA_BOUNDS = {
  minLat: 41,
  maxLat: 84,
  minLon: -142,
  maxLon: -52
} as const;

export const MONTH_LABELS: Record<string, string> = {
  jan: "Jan",
  feb: "Feb",
  mar: "Mar",
  apr: "Apr",
  may: "May",
  jun: "Jun",
  jul: "Jul",
  aug: "Aug",
  sep: "Sep",
  oct: "Oct",
  nov: "Nov",
  dec: "Dec"
};

export enum LoadState {
  Idle = "idle",
  Priming = "priming",
  Geocoding = "geocoding",
  ChoosingCandidate = "choosingCandidate",
  MatchingRegion = "matchingRegion",
  LoadingPlants = "loadingPlants",
  Ready = "ready",
  Error = "error"
}
