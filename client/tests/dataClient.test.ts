import { afterEach, describe, expect, it, vi } from "vitest";
import { findManifestEntry, loadBoundaries, loadEcoregionPayload, loadManifest, resetDataCachesForTests } from "../src/dataClient";

function mockFetch(responses: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = responses[url];
    if (!body) {
      return {
        ok: false,
        status: 404,
        json: async () => null
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => body
    };
  });
}

describe("dataClient", () => {
  afterEach(() => {
    resetDataCachesForTests();
    vi.restoreAllMocks();
  });

  it("loads and caches static data", async () => {
    const fetchMock = mockFetch({
      "data/app_data/manifest.json": {
        ecoregionCount: 1,
        plantEcoregionCount: 1,
        missingLbjTraitCount: 0,
        ecoregions: [{ ecoregionId: 7, ecoregionName: "Fixture", path: "ecoregions/7.json", plantCount: 1 }]
      },
      "data/ecoregion-boundaries.json": {
        generatedAt: "2026-07-19T00:00:00Z",
        source: "fixture",
        tolerance: 0,
        ecoregions: []
      },
      "data/app_data/ecoregions/7.json": {
        ecoregionId: 7,
        ecoregionName: "Fixture",
        plantCount: 1,
        plants: [
          {
            usageKey: 1,
            canonicalName: "Aster laevis",
            vernacularName: "smooth aster",
            occurrenceCount: 1,
            humanObservationCount: 1,
            preservedSpecimenCount: 0,
            coordinateUncertaintyMedianM: null,
            firstYear: 2020,
            lastYear: 2020,
            growthHabit: ["herb"],
            duration: null,
            matureHeightMinFt: null,
            matureHeightMaxFt: null,
            light: [],
            moisture: [],
            waterUse: null,
            soilCategories: [],
            bloomTime: [],
            bloomColor: [],
            lbjUrl: null
          }
        ]
      }
    });
    vi.stubGlobal("fetch", fetchMock);

    const manifest = await loadManifest();
    await loadManifest();
    const entry = findManifestEntry(manifest, 7);
    expect(entry?.path).toBe("ecoregions/7.json");
    expect((await loadBoundaries()).ecoregions).toEqual([]);
    expect((await loadEcoregionPayload(entry!)).plants[0].canonicalName).toBe("Aster laevis");
    await loadEcoregionPayload(entry!);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does not permanently cache failed manifest loads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => null })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          ecoregionCount: 1,
          plantEcoregionCount: 1,
          missingLbjTraitCount: 0,
          ecoregions: [{ ecoregionId: 7, ecoregionName: "Fixture", path: "ecoregions/7.json", plantCount: 1 }]
        })
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadManifest()).rejects.toThrow("503");
    await expect(loadManifest()).resolves.toMatchObject({ ecoregionCount: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not permanently cache failed ecoregion payload loads", async () => {
    const entry = { ecoregionId: 7, ecoregionName: "Fixture", path: "ecoregions/7.json", plantCount: 1 };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => null })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          ecoregionId: 7,
          ecoregionName: "Fixture",
          plantCount: 0,
          plants: []
        })
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadEcoregionPayload(entry)).rejects.toThrow("500");
    await expect(loadEcoregionPayload(entry)).resolves.toMatchObject({ ecoregionId: 7 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
