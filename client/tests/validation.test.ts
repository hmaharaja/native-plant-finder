import { describe, expect, it } from "vitest";
import { isValidCoordinate, isValidLocationQuery, parseEcoregionPayload, parseManifest, parsePlantImageIndex, safePlantDetailUrl, safePlantImageSourceUrl, sanitizeLocationQuery } from "../src/validation";

describe("validation", () => {
  it("sanitizes location input without preserving control characters", () => {
    expect(sanitizeLocationQuery("  V6B\u00001A1   Vancouver  ")).toBe("V6B1A1 Vancouver");
  });

  it("rejects empty and punctuation-only queries", () => {
    expect(isValidLocationQuery("")).toBe(false);
    expect(isValidLocationQuery("??")).toBe(false);
    expect(isValidLocationQuery("BC")).toBe(true);
  });

  it("validates Canadian coordinate bounds", () => {
    expect(isValidCoordinate({ lat: 49.2827, lon: -123.1207 })).toBe(true);
    expect(isValidCoordinate({ lat: 30, lon: -123.1207 })).toBe(false);
  });

  it("parses a manifest and rejects malformed data", () => {
    expect(
      parseManifest({
        ecoregionCount: 1,
        plantEcoregionCount: 2,
        missingLbjTraitCount: 0,
        ecoregions: [{ ecoregionId: 7, ecoregionName: "Fixture", path: "ecoregions/7.json", plantCount: 2 }]
      }).ecoregions[0].path
    ).toBe("ecoregions/7.json");

    expect(() => parseManifest({ ecoregions: [] })).toThrow();
  });

  it("accepts recognized nullable recommendation categories and rejects unknown ones", () => {
    const plant = {
      usageKey: 1, canonicalName: "Example", vernacularName: null,
      occurrenceCount: 1, humanObservationCount: 1, preservedSpecimenCount: 0,
      coordinateUncertaintyMedianM: 5, firstYear: 2020, lastYear: 2021,
      growthHabit: [], duration: null, matureHeightMinFt: null, matureHeightMaxFt: null,
      light: [], moisture: [], waterUse: null, soilCategories: [], bloomTime: [],
      bloomColor: [], lbjUrl: null, recommendationCategory: "conditional"
    };
    const payload = { ecoregionId: 1, ecoregionName: "One", plantCount: 1, plants: [plant] };
    expect(parseEcoregionPayload(payload).plants[0].recommendationCategory).toBe("conditional");
    const legacyPlant = { ...plant };
    delete (legacyPlant as Partial<typeof plant>).recommendationCategory;
    expect(
      parseEcoregionPayload({ ...payload, plants: [legacyPlant] }).plants[0]
        .recommendationCategory
    ).toBeNull();
    expect(() => parseEcoregionPayload({
      ...payload,
      plants: [{ ...plant, recommendationCategory: "unknown" }]
    })).toThrow(/recommendationCategory/);
  });

  it("allows expected HTTPS Lady Bird Johnson plant detail URLs", () => {
    expect(safePlantDetailUrl("https://www.wildflower.org/plants/result.php?id_plant=CALE10")).toBe(
      "https://www.wildflower.org/plants/result.php?id_plant=CALE10"
    );
  });

  it("rejects missing plant detail URLs", () => {
    expect(safePlantDetailUrl(null)).toBeNull();
    expect(safePlantDetailUrl("")).toBeNull();
  });

  it("rejects malformed plant detail URLs", () => {
    expect(safePlantDetailUrl("not a url")).toBeNull();
  });

  it("rejects unsafe plant detail URL schemes", () => {
    expect(safePlantDetailUrl("javascript:alert(1)")).toBeNull();
    expect(safePlantDetailUrl("data:text/html,boom")).toBeNull();
    expect(safePlantDetailUrl("http://www.wildflower.org/plants/result.php?id_plant=CALE10")).toBeNull();
  });

  it("rejects plant detail URLs from unexpected hosts", () => {
    expect(safePlantDetailUrl("https://evil.test/plants/result.php?id_plant=CALE10")).toBeNull();
  });

  it("rejects plant detail URLs with unexpected paths", () => {
    expect(safePlantDetailUrl("https://www.wildflower.org/other?id_plant=CALE10")).toBeNull();
  });

  it("rejects plant detail URLs without a plant id", () => {
    expect(safePlantDetailUrl("https://www.wildflower.org/plants/result.php")).toBeNull();
  });

  it("allows known HTTPS image source links", () => {
    expect(safePlantImageSourceUrl("https://www.gbif.org/occurrence/123")).toBe("https://www.gbif.org/occurrence/123");
    expect(safePlantImageSourceUrl("https://commons.wikimedia.org/wiki/File:Example.jpg")).toBe(
      "https://commons.wikimedia.org/wiki/File:Example.jpg"
    );
  });

  it("rejects unsafe or unexpected image source links", () => {
    expect(safePlantImageSourceUrl("javascript:alert(1)")).toBeNull();
    expect(safePlantImageSourceUrl("http://www.gbif.org/occurrence/123")).toBeNull();
    expect(safePlantImageSourceUrl("https://example.test/source")).toBeNull();
  });

  it("parses valid image records and drops invalid records without failing the index", () => {
    const index = parsePlantImageIndex({
      "123": {
        usageKey: 123,
        primaryImage: {
          source: "gbif",
          gbifId: "456",
          imageUrl: "https://images.example.test/plant.jpg",
          thumbnailUrl: "https://images.example.test/thumb.jpg",
          sourceUrl: "https://www.gbif.org/occurrence/456",
          license: "CC BY",
          creator: "A Person",
          credit: "A Person / Publisher",
          publisher: "Publisher",
          width: 320,
          height: 240,
          acceptedAt: "2026-08-06T00:00:00Z",
          rank: 1
        },
        secondaryImage: null
      },
      "124": {
        usageKey: 124,
        primaryImage: {
          source: "gbif",
          gbifId: null,
          imageUrl: "javascript:alert(1)",
          thumbnailUrl: "https://images.example.test/thumb.jpg",
          sourceUrl: "https://www.gbif.org/occurrence/456",
          license: "CC BY",
          creator: null,
          credit: null,
          publisher: null,
          width: null,
          height: null,
          acceptedAt: null,
          rank: 1
        },
        secondaryImage: null
      },
      "125": "not a record",
      "126": {
        usageKey: 127,
        primaryImage: {
          source: "gbif",
          gbifId: "456",
          imageUrl: "https://images.example.test/plant.jpg",
          thumbnailUrl: "https://images.example.test/thumb.jpg",
          sourceUrl: "https://www.gbif.org/occurrence/456",
          license: "CC BY",
          creator: null,
          credit: null,
          publisher: null,
          width: null,
          height: null,
          acceptedAt: null,
          rank: 1
        },
        secondaryImage: null
      },
      badKey: {
        usageKey: 125
      }
    });

    expect(Object.keys(index)).toEqual(["123"]);
    expect(index["123"].primaryImage.sourceUrl).toBe("https://www.gbif.org/occurrence/456");
  });

  it("requires an object image index", () => {
    expect(() => parsePlantImageIndex([])).toThrow(/plant image index/);
  });
});
