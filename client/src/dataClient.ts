import { BOUNDARY_PATH, DATA_ROOT } from "./constants";
import type { BoundaryCollection, EcoregionManifestEntry, EcoregionPayload, Manifest } from "./types";
import { parseBoundaryCollection, parseEcoregionPayload, parseManifest } from "./validation";

const manifestUrl = `${DATA_ROOT}/manifest.json`;

let manifestPromise: Promise<Manifest> | null = null;
let boundariesPromise: Promise<BoundaryCollection> | null = null;
const ecoregionPayloadCache = new Map<number, Promise<EcoregionPayload>>();

async function fetchJson<T>(path: string, parser: (value: unknown) => T): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "force-cache"
  });
  if (!response.ok) {
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }
  return parser(await response.json());
}

export function loadManifest(): Promise<Manifest> {
  if (!manifestPromise) {
    manifestPromise = fetchJson(manifestUrl, parseManifest).catch((error: unknown) => {
      manifestPromise = null;
      throw error;
    });
  }
  return manifestPromise;
}

export function loadBoundaries(): Promise<BoundaryCollection> {
  if (!boundariesPromise) {
    boundariesPromise = fetchJson(BOUNDARY_PATH, parseBoundaryCollection).catch((error: unknown) => {
      boundariesPromise = null;
      throw error;
    });
  }
  return boundariesPromise;
}

export async function loadInitialData(): Promise<{ manifest: Manifest; boundaries: BoundaryCollection }> {
  const [manifest, boundaries] = await Promise.all([loadManifest(), loadBoundaries()]);
  return { manifest, boundaries };
}

export function findManifestEntry(manifest: Manifest, ecoregionId: number): EcoregionManifestEntry | null {
  return manifest.ecoregions.find((entry) => entry.ecoregionId === ecoregionId) ?? null;
}

export function loadEcoregionPayload(entry: EcoregionManifestEntry): Promise<EcoregionPayload> {
  const existing = ecoregionPayloadCache.get(entry.ecoregionId);
  if (existing) {
    return existing;
  }
  const request = fetchJson(`${DATA_ROOT}/${entry.path}`, parseEcoregionPayload).catch((error: unknown) => {
    ecoregionPayloadCache.delete(entry.ecoregionId);
    throw error;
  });
  ecoregionPayloadCache.set(entry.ecoregionId, request);
  return request;
}

export function resetDataCachesForTests(): void {
  manifestPromise = null;
  boundariesPromise = null;
  ecoregionPayloadCache.clear();
}
