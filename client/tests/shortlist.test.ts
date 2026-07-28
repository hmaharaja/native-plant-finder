import { describe, expect, it } from "vitest";
import {
  getAddResult,
  hydrateShortlist,
  parseShortlist,
  ShortlistStore,
  shortlistReducer,
  type ShortlistSelection,
  type StorageLike
} from "../src/shortlist";
import type { EcoregionPayload, PlantRecord } from "../src/types";

const empty: ShortlistSelection = { kind: "empty" };
const plant = (usageKey: number | null, recommendationCategory: PlantRecord["recommendationCategory"] = null): PlantRecord => ({
  usageKey, canonicalName: `Plant ${usageKey}`, vernacularName: null, occurrenceCount: null,
  humanObservationCount: null, preservedSpecimenCount: null, coordinateUncertaintyMedianM: null,
  firstYear: null, lastYear: null, growthHabit: [], duration: null, matureHeightMinFt: null,
  matureHeightMaxFt: null, light: [], moisture: [], waterUse: null, soilCategories: [],
  bloomTime: [], bloomColor: [], lbjUrl: null, recommendationCategory
});
const payload = (plants: PlantRecord[], ecoregionId = 7): EcoregionPayload => ({
  ecoregionId, ecoregionName: "Prairie", plantCount: plants.length, plants
});

describe("shortlistReducer", () => {
  it("preserves insertion order, ignores duplicates, and resets after the last removal", () => {
    let state = shortlistReducer(empty, { type: "add", ecoregionId: 7, usageKey: 2 });
    state = shortlistReducer(state, { type: "add", ecoregionId: 7, usageKey: 1 });
    expect(shortlistReducer(state, { type: "add", ecoregionId: 7, usageKey: 2 })).toBe(state);
    expect(state).toEqual({ kind: "scoped", ecoregionId: 7, usageKeys: [2, 1] });
    state = shortlistReducer(state, { type: "remove", usageKey: 2 });
    state = shortlistReducer(state, { type: "remove", usageKey: 1 });
    expect(state).toEqual(empty);
  });

  it("enforces region and capacity", () => {
    let state: ShortlistSelection = { kind: "scoped", ecoregionId: 7, usageKeys: [1] };
    expect(getAddResult(state, 8, 2)).toBe("region-mismatch");
    for (let key = 2; key <= 10; key++) state = shortlistReducer(state, { type: "add", ecoregionId: 7, usageKey: key });
    expect(getAddResult(state, 7, 11)).toBe("capacity");
    expect(shortlistReducer(state, { type: "add", ecoregionId: 7, usageKey: 11 })).toBe(state);
  });
});

describe("shortlist persistence", () => {
  it("accepts only the exact bounded schema", () => {
    expect(parseShortlist('{"version":1,"ecoregionId":7,"usageKeys":[2,1]}')).toEqual({
      kind: "scoped", ecoregionId: 7, usageKeys: [2, 1]
    });
    for (const raw of [
      '{"version":2,"ecoregionId":7,"usageKeys":[1]}',
      '{"version":1,"ecoregionId":7,"usageKeys":[]}',
      '{"version":1,"ecoregionId":7,"usageKeys":[1,1]}',
      '{"version":1,"ecoregionId":7,"usageKeys":[0]}',
      '{"version":1,"ecoregionId":7,"usageKeys":[1],"extra":true}',
      "x".repeat(2049)
    ]) expect(() => parseShortlist(raw)).toThrow();
  });

  it("falls back without losing later in-memory transitions", () => {
    const storage: StorageLike = {
      getItem: () => null,
      setItem: () => { throw new Error("blocked"); },
      removeItem: () => { throw new Error("blocked"); }
    };
    const store = new ShortlistStore(storage);
    expect(store.save({ kind: "scoped", ecoregionId: 7, usageKeys: [1] })).toBe(false);
    expect(store.save({ kind: "scoped", ecoregionId: 7, usageKeys: [1, 2] })).toBe(false);
  });
});

describe("shortlist hydration", () => {
  it("restores order and retains missing, duplicate, and excluded keys as unresolved", () => {
    const selection: ShortlistSelection = { kind: "scoped", ecoregionId: 7, usageKeys: [3, 1, 2, 4] };
    expect(hydrateShortlist(selection, payload([
      plant(1), plant(3), plant(2), plant(2), plant(null), plant(4, "poor_avoid")
    ]))).toEqual({ records: [plant(3), plant(1)], unresolvedKeys: [2, 4] });
    expect(() => hydrateShortlist(selection, payload([], 8))).toThrow();
  });
});
