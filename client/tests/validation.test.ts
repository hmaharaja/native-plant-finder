import { describe, expect, it } from "vitest";
import { isValidCoordinate, isValidLocationQuery, parseManifest, safePlantDetailUrl, sanitizeLocationQuery } from "../src/validation";

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
});
