import { describe, expect, it } from "vitest";
import { boundaryContainsPoint, findEcoregionForCoordinate } from "../src/geometry";
import type { BoundaryCollection, BoundaryRecord } from "../src/types";

const square: BoundaryRecord = {
  ecoregionId: 7,
  ecoregionName: "Fixture",
  bbox: [-1, -1, 1, 1],
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
        [-1, -1]
      ]
    ]
  }
};

describe("geometry", () => {
  it("matches points inside a polygon", () => {
    expect(boundaryContainsPoint(square, { lat: 0, lon: 0 })).toBe(true);
    expect(boundaryContainsPoint(square, { lat: 2, lon: 0 })).toBe(false);
  });

  it("finds the first containing ecoregion", () => {
    const collection: BoundaryCollection = {
      generatedAt: "2026-07-19T00:00:00Z",
      source: "fixture",
      tolerance: 0,
      ecoregions: [square]
    };
    expect(findEcoregionForCoordinate(collection, { lat: 0, lon: 0 })?.ecoregionId).toBe(7);
  });
});
