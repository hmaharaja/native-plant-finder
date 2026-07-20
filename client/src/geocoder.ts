import { GEOCODER_MIN_INTERVAL_MS, NOMINATIM_ENDPOINT, ZIPPOPOTAM_ENDPOINT } from "./constants";
import type { Coordinate, GeocoderCandidate } from "./types";
import { isValidCoordinate, sanitizeLocationQuery } from "./validation";

interface NominatimSearchResult {
  place_id: number;
  display_name: string;
  lat: string;
  lon: string;
}

interface ZippopotamPlace {
  "place name": string;
  longitude: string;
  latitude: string;
  state: string;
  "state abbreviation": string;
}

interface ZippopotamResult {
  "post code": string;
  places: ZippopotamPlace[];
}

export interface GeocoderProvider {
  search(query: string): Promise<GeocoderCandidate[]>;
}

export class GeocoderError extends Error {
  constructor(
    message: string,
    readonly status?: number
  ) {
    super(message);
    this.name = "GeocoderError";
  }
}

const geocodeCache = new Map<string, Promise<GeocoderCandidate[]>>();
let lastRequestStartedAt = 0;
const CANADIAN_POSTAL_CODE = /^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d$/i;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

async function throttleRequest(): Promise<void> {
  const now = Date.now();
  const elapsed = now - lastRequestStartedAt;
  if (elapsed < GEOCODER_MIN_INTERVAL_MS) {
    await wait(GEOCODER_MIN_INTERVAL_MS - elapsed);
  }
  lastRequestStartedAt = Date.now();
}

function parseCoordinate(result: NominatimSearchResult): Coordinate | null {
  const coordinate = {
    lat: Number.parseFloat(result.lat),
    lon: Number.parseFloat(result.lon)
  };
  return isValidCoordinate(coordinate) ? coordinate : null;
}

function postalFsa(query: string): string | null {
  const normalized = query.replace(/\s+/g, "").toUpperCase();
  return CANADIAN_POSTAL_CODE.test(normalized) ? normalized.slice(0, 3) : null;
}

function candidateFromZippopotamPlace(fsa: string, place: ZippopotamPlace): GeocoderCandidate | null {
  const coordinate = {
    lat: Number.parseFloat(place.latitude),
    lon: Number.parseFloat(place.longitude)
  };
  if (!isValidCoordinate(coordinate)) {
    return null;
  }
  return {
    id: `postal-${fsa}-${place["place name"]}`,
    label: `${fsa}, ${place["place name"]}, ${place.state}, Canada`,
    coordinate
  };
}

export class NominatimGeocoder implements GeocoderProvider {
  async search(rawQuery: string): Promise<GeocoderCandidate[]> {
    const query = sanitizeLocationQuery(rawQuery);
    const cacheKey = query.toLowerCase();
    const cached = geocodeCache.get(cacheKey);
    if (cached) {
      return cached;
    }

    const request = this.fetchCandidates(query).catch((error: unknown) => {
      geocodeCache.delete(cacheKey);
      throw error;
    });
    geocodeCache.set(cacheKey, request);
    return request;
  }

  private async fetchCandidates(query: string): Promise<GeocoderCandidate[]> {
    await throttleRequest();
    const params = new URLSearchParams({
      q: query,
      format: "jsonv2",
      addressdetails: "1",
      countrycodes: "ca",
      limit: "5"
    });
    const response = await fetch(`${NOMINATIM_ENDPOINT}?${params.toString()}`, {
      headers: { Accept: "application/json" }
    });

    if (!response.ok) {
      throw new GeocoderError(`Location lookup failed: ${response.status}`, response.status);
    }

    const results = (await response.json()) as NominatimSearchResult[];
    return results
      .map((result) => {
        const coordinate = parseCoordinate(result);
        if (!coordinate) {
          return null;
        }
        return {
          id: String(result.place_id),
          label: result.display_name,
          coordinate
        };
      })
      .filter((candidate): candidate is GeocoderCandidate => candidate !== null);
  }
}

export class CanadianPostalGeocoder implements GeocoderProvider {
  async search(rawQuery: string): Promise<GeocoderCandidate[]> {
    const query = sanitizeLocationQuery(rawQuery);
    const fsa = postalFsa(query);
    if (!fsa) {
      return [];
    }

    const cacheKey = `postal:${fsa}`;
    const cached = geocodeCache.get(cacheKey);
    if (cached) {
      return cached;
    }

    const request = this.fetchFsa(fsa).catch((error: unknown) => {
      geocodeCache.delete(cacheKey);
      throw error;
    });
    geocodeCache.set(cacheKey, request);
    return request;
  }

  private async fetchFsa(fsa: string): Promise<GeocoderCandidate[]> {
    const response = await fetch(`${ZIPPOPOTAM_ENDPOINT}/${encodeURIComponent(fsa)}`, {
      headers: { Accept: "application/json" }
    });
    if (response.status === 404) {
      return [];
    }
    if (!response.ok) {
      throw new GeocoderError(`Postal code lookup failed: ${response.status}`, response.status);
    }

    const result = (await response.json()) as ZippopotamResult;
    return result.places
      .map((place) => candidateFromZippopotamPlace(fsa, place))
      .filter((candidate): candidate is GeocoderCandidate => candidate !== null);
  }
}

export class FallbackGeocoder implements GeocoderProvider {
  constructor(private readonly providers: GeocoderProvider[]) {}

  async search(query: string): Promise<GeocoderCandidate[]> {
    const errors: Error[] = [];
    for (const provider of this.providers) {
      try {
        const candidates = await provider.search(query);
        if (candidates.length > 0) {
          return candidates;
        }
      } catch (error) {
        errors.push(error instanceof Error ? error : new Error(String(error)));
      }
    }
    if (errors.length === this.providers.length && errors.length > 0) {
      throw errors[errors.length - 1];
    }
    return [];
  }
}

export function geocoderErrorMessage(error: unknown): string {
  if (error instanceof GeocoderError && error.status === 429) {
    return "Location lookup is temporarily rate-limited. Wait a moment and try again.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Unable to find native plants for that location.";
}

export function createDefaultGeocoder(): GeocoderProvider {
  return new FallbackGeocoder([new CanadianPostalGeocoder(), new NominatimGeocoder()]);
}

export function resetGeocoderCachesForTests(): void {
  geocodeCache.clear();
  lastRequestStartedAt = 0;
}
