import type { BoundaryCollection, BoundaryRecord, Coordinate, LinearRing } from "./types";

function isInsideBbox(point: Coordinate, bbox: [number, number, number, number]): boolean {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return point.lon >= minLon && point.lon <= maxLon && point.lat >= minLat && point.lat <= maxLat;
}

function ringContainsPoint(point: Coordinate, ring: LinearRing): boolean {
  let inside = false;
  for (let currentIndex = 0, previousIndex = ring.length - 1; currentIndex < ring.length; previousIndex = currentIndex++) {
    const current = ring[currentIndex];
    const previous = ring[previousIndex];
    const crosses =
      current.lat > point.lat !== previous.lat > point.lat &&
      point.lon < ((previous.lon - current.lon) * (point.lat - current.lat)) / (previous.lat - current.lat) + current.lon;
    if (crosses) {
      inside = !inside;
    }
  }
  return inside;
}

function rawRingToCoordinates(ring: number[][]): LinearRing {
  return ring.map(([lon, lat]) => ({ lon, lat }));
}

function polygonContainsPoint(point: Coordinate, polygon: number[][][]): boolean {
  if (polygon.length === 0) {
    return false;
  }
  const outerRing = rawRingToCoordinates(polygon[0]);
  if (!ringContainsPoint(point, outerRing)) {
    return false;
  }
  return polygon.slice(1).every((hole) => !ringContainsPoint(point, rawRingToCoordinates(hole)));
}

export function boundaryContainsPoint(boundary: BoundaryRecord, point: Coordinate): boolean {
  if (!isInsideBbox(point, boundary.bbox)) {
    return false;
  }
  if (boundary.geometry.type === "Polygon") {
    return polygonContainsPoint(point, boundary.geometry.coordinates as number[][][]);
  }
  return (boundary.geometry.coordinates as number[][][][]).some((polygon) => polygonContainsPoint(point, polygon));
}

export function findEcoregionForCoordinate(
  boundaries: BoundaryCollection,
  point: Coordinate
): BoundaryRecord | null {
  return boundaries.ecoregions.find((boundary) => boundaryContainsPoint(boundary, point)) ?? null;
}
