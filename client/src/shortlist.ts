import type { EcoregionPayload, PlantRecord } from "./types";
import { recommendationVisibility } from "./recommendations";

export const SHORTLIST_LIMIT = 10;
export const SHORTLIST_STORAGE_KEY = "native-plant-finder:shortlist:v1";

export type ShortlistSelection =
  | { kind: "empty" }
  | { kind: "scoped"; ecoregionId: number; usageKeys: number[] };

export type ShortlistAction =
  | { type: "add"; ecoregionId: number; usageKey: number }
  | { type: "remove"; usageKey: number }
  | { type: "clear" };

export type AddResult = "added" | "already-saved" | "capacity" | "region-mismatch" | "invalid";

export interface HydratedShortlist {
  records: PlantRecord[];
  unresolvedKeys: number[];
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function isUsageKey(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

export function parseShortlist(raw: string | null): ShortlistSelection {
  if (raw === null) return { kind: "empty" };
  if (raw.length > 2048) throw new Error("Invalid saved plants");
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid saved plants");
  const candidate = value as Record<string, unknown>;
  if (
    Object.keys(candidate).length !== 3 ||
    candidate.version !== 1 ||
    !isUsageKey(candidate.ecoregionId) ||
    !Array.isArray(candidate.usageKeys) ||
    candidate.usageKeys.length === 0 ||
    candidate.usageKeys.length > SHORTLIST_LIMIT
  ) throw new Error("Invalid saved plants");
  const keys = candidate.usageKeys;
  if (keys.some((key) => !isUsageKey(key)) || new Set(keys).size !== keys.length) {
    throw new Error("Invalid saved plants");
  }
  return { kind: "scoped", ecoregionId: candidate.ecoregionId, usageKeys: [...keys] as number[] };
}

export function serializeShortlist(selection: ShortlistSelection): string | null {
  return selection.kind === "empty"
    ? null
    : JSON.stringify({ version: 1, ecoregionId: selection.ecoregionId, usageKeys: selection.usageKeys });
}

export function shortlistReducer(selection: ShortlistSelection, action: ShortlistAction): ShortlistSelection {
  if (action.type === "clear") return selection.kind === "empty" ? selection : { kind: "empty" };
  if (action.type === "add") {
    if (!isUsageKey(action.ecoregionId) || !isUsageKey(action.usageKey)) return selection;
    if (selection.kind === "empty") {
      return { kind: "scoped", ecoregionId: action.ecoregionId, usageKeys: [action.usageKey] };
    }
    if (
      selection.ecoregionId !== action.ecoregionId ||
      selection.usageKeys.includes(action.usageKey) ||
      selection.usageKeys.length >= SHORTLIST_LIMIT
    ) return selection;
    return { ...selection, usageKeys: [...selection.usageKeys, action.usageKey] };
  }
  if (selection.kind === "empty" || !selection.usageKeys.includes(action.usageKey)) return selection;
  const usageKeys = selection.usageKeys.filter((key) => key !== action.usageKey);
  return usageKeys.length ? { ...selection, usageKeys } : { kind: "empty" };
}

export function getAddResult(
  selection: ShortlistSelection,
  ecoregionId: number,
  usageKey: number
): AddResult {
  if (!isUsageKey(ecoregionId) || !isUsageKey(usageKey)) return "invalid";
  if (selection.kind === "empty") return "added";
  if (selection.ecoregionId !== ecoregionId) return "region-mismatch";
  if (selection.usageKeys.includes(usageKey)) return "already-saved";
  return selection.usageKeys.length >= SHORTLIST_LIMIT ? "capacity" : "added";
}

export function hydrateShortlist(selection: ShortlistSelection, payload: EcoregionPayload): HydratedShortlist {
  if (selection.kind === "empty") return { records: [], unresolvedKeys: [] };
  if (payload.ecoregionId !== selection.ecoregionId) throw new Error("Saved plant region did not match");
  const index = new Map<number, PlantRecord>();
  const invalid = new Set<number>();
  for (const plant of payload.plants) {
    if (!isUsageKey(plant.usageKey)) continue;
    if (index.has(plant.usageKey)) {
      index.delete(plant.usageKey);
      invalid.add(plant.usageKey);
    } else if (!invalid.has(plant.usageKey)) {
      index.set(plant.usageKey, plant);
    }
  }
  const records: PlantRecord[] = [];
  const unresolvedKeys: number[] = [];
  for (const key of selection.usageKeys) {
    const plant = index.get(key);
    if (plant && recommendationVisibility(plant.recommendationCategory) !== "always-excluded") records.push(plant);
    else unresolvedKeys.push(key);
  }
  return { records, unresolvedKeys };
}

export class ShortlistStore {
  private storage: StorageLike | null;
  private lastSerialized: string | null | undefined;
  readonly failedAtInitialization: boolean;

  constructor(storage: StorageLike | null) {
    this.storage = storage;
    let failed = false;
    try {
      this.lastSerialized = storage?.getItem(SHORTLIST_STORAGE_KEY) ?? null;
    } catch {
      this.storage = null;
      this.lastSerialized = null;
      failed = true;
    }
    this.failedAtInitialization = failed;
  }

  load(): ShortlistSelection {
    try {
      return parseShortlist(this.lastSerialized ?? null);
    } catch {
      try {
        this.storage?.removeItem(SHORTLIST_STORAGE_KEY);
      } catch {
        this.storage = null;
      }
      this.lastSerialized = null;
      return { kind: "empty" };
    }
  }

  save(selection: ShortlistSelection): boolean {
    const serialized = serializeShortlist(selection);
    if (serialized === this.lastSerialized) return this.storage !== null;
    if (!this.storage) return false;
    try {
      if (serialized === null) this.storage.removeItem(SHORTLIST_STORAGE_KEY);
      else this.storage.setItem(SHORTLIST_STORAGE_KEY, serialized);
      this.lastSerialized = serialized;
      return true;
    } catch {
      this.storage = null;
      return false;
    }
  }
}
