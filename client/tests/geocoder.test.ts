import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CanadianPostalGeocoder,
  FallbackGeocoder,
  FullPostalCodeGeocoder,
  GeocoderError,
  geocoderErrorMessage,
  NominatimGeocoder,
  resetGeocoderCachesForTests
} from "../src/geocoder";
import type { GeocoderProvider } from "../src/geocoder";

function mockJsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  };
}

describe("geocoder", () => {
  afterEach(() => {
    resetGeocoderCachesForTests();
    vi.restoreAllMocks();
  });

  it("uses the Canadian FSA for full postal code lookups", async () => {
    const fetchMock = vi.fn<[RequestInfo | URL], Promise<ReturnType<typeof mockJsonResponse>>>(async () =>
      mockJsonResponse({
        "post code": "X9X",
        places: [
          {
            "place name": "Mock Prairie",
            longitude: "-100.0000",
            latitude: "50.0000",
            state: "Test Province",
            "state abbreviation": "TP"
          }
        ]
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    const candidates = await new CanadianPostalGeocoder().search("X9X 9X9");

    const firstCall = fetchMock.mock.calls[0];
    expect(firstCall).toBeDefined();
    expect(String(firstCall?.[0])).toBe("https://api.zippopotam.us/ca/X9X");
    expect(candidates[0]).toMatchObject({
      label: "X9X, Mock Prairie, Test Province, Canada",
      coordinate: { lat: 50, lon: -100 }
    });
  });

  it("prefers Nominatim coordinates for full Canadian postal codes", async () => {
    const primary: GeocoderProvider = {
      search: vi.fn(async () => [
        {
          id: "full-postal",
          label: "X9X 9X9, Mock Prairie, Test Province, Canada",
          coordinate: { lat: 50.001, lon: -100.001 }
        }
      ])
    };
    const fallback: GeocoderProvider = {
      search: vi.fn(async () => [
        {
          id: "fsa",
          label: "X9X, Mock Prairie, Test Province, Canada",
          coordinate: { lat: 50, lon: -100 }
        }
      ])
    };

    const candidates = await new FullPostalCodeGeocoder(primary, fallback).search("X9X 9X9");

    expect(candidates[0].id).toBe("full-postal");
    expect(primary.search).toHaveBeenCalledWith("X9X 9X9");
    expect(fallback.search).not.toHaveBeenCalled();
  });

  it("falls back to FSA lookup when Nominatim has no full postal code candidates", async () => {
    const logSpy = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const primary: GeocoderProvider = { search: vi.fn(async () => []) };
    const fallback: GeocoderProvider = {
      search: vi.fn(async () => [
        {
          id: "fsa",
          label: "X9X, Mock Prairie, Test Province, Canada",
          coordinate: { lat: 50, lon: -100 }
        }
      ])
    };

    const candidates = await new FullPostalCodeGeocoder(primary, fallback).search("X9X 9X9");

    expect(candidates[0].id).toBe("fsa");
    expect(fallback.search).toHaveBeenCalledWith("X9X 9X9");
    expect(logSpy).toHaveBeenCalledWith("Falling back to FSA postal lookup: Nominatim returned no candidates");
  });

  it("falls back to FSA lookup when Nominatim rate-limits full postal code lookups", async () => {
    const logSpy = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const primary: GeocoderProvider = {
      search: vi.fn(async () => Promise.reject(new GeocoderError("Location lookup failed: 429", 429)))
    };
    const fallback: GeocoderProvider = {
      search: vi.fn(async () => [
        {
          id: "fsa",
          label: "X9X, Mock Prairie, Test Province, Canada",
          coordinate: { lat: 50, lon: -100 }
        }
      ])
    };

    const candidates = await new FullPostalCodeGeocoder(primary, fallback).search("X9X 9X9");

    expect(candidates[0].id).toBe("fsa");
    expect(fallback.search).toHaveBeenCalledWith("X9X 9X9");
    expect(logSpy).toHaveBeenCalledWith("Falling back to FSA postal lookup: Nominatim was rate-limited");
  });

  it("does not hide non-rate-limit Nominatim errors for full postal code lookups", async () => {
    const primary: GeocoderProvider = {
      search: vi.fn(async () => Promise.reject(new GeocoderError("Location lookup failed: 503", 503)))
    };
    const fallback: GeocoderProvider = { search: vi.fn(async () => []) };

    await expect(new FullPostalCodeGeocoder(primary, fallback).search("X9X 9X9")).rejects.toThrow("503");
    expect(fallback.search).not.toHaveBeenCalled();
  });

  it("sends non-postal queries only to the primary geocoder", async () => {
    const primary: GeocoderProvider = {
      search: vi.fn(async () => [{ id: "city", label: "Brampton", coordinate: { lat: 43.68, lon: -79.76 } }])
    };
    const fallback: GeocoderProvider = { search: vi.fn(async () => []) };

    const candidates = await new FullPostalCodeGeocoder(primary, fallback).search("Brampton");

    expect(candidates[0].id).toBe("city");
    expect(primary.search).toHaveBeenCalledWith("Brampton");
    expect(fallback.search).not.toHaveBeenCalled();
  });

  it("does not cache failed Canadian postal lookups", async () => {
    const fetchMock = vi
      .fn<[RequestInfo | URL], Promise<ReturnType<typeof mockJsonResponse>>>()
      .mockResolvedValueOnce(mockJsonResponse({}, 500))
      .mockResolvedValueOnce(
        mockJsonResponse({
          "post code": "X9X",
          places: [
            {
              "place name": "Mock Prairie",
              longitude: "-100.0000",
              latitude: "50.0000",
              state: "Test Province",
              "state abbreviation": "TP"
            }
          ]
        })
      );
    vi.stubGlobal("fetch", fetchMock);
    const geocoder = new CanadianPostalGeocoder();

    await expect(geocoder.search("X9X 9X9")).rejects.toThrow("500");
    await expect(geocoder.search("X9X 9X9")).resolves.toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not cache failed Nominatim lookups", async () => {
    const fetchMock = vi
      .fn<[RequestInfo | URL], Promise<ReturnType<typeof mockJsonResponse>>>()
      .mockResolvedValueOnce(mockJsonResponse({}, 503))
      .mockResolvedValueOnce(
        mockJsonResponse([
          {
            place_id: 1,
            display_name: "Brampton, Ontario, Canada",
            lat: "43.6858320",
            lon: "-79.7599366"
          }
        ])
      );
    vi.stubGlobal("fetch", fetchMock);
    const geocoder = new NominatimGeocoder();

    await expect(geocoder.search("Brampton")).rejects.toThrow("503");
    await expect(geocoder.search("Brampton")).resolves.toHaveLength(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("falls back to later providers when postal lookup has no candidates", async () => {
    const first: GeocoderProvider = { search: vi.fn(async () => []) };
    const second: GeocoderProvider = {
      search: vi.fn(async () => [{ id: "city", label: "Brampton", coordinate: { lat: 43.68, lon: -79.76 } }])
    };

    const candidates = await new FallbackGeocoder([first, second]).search("Brampton");

    expect(candidates[0].id).toBe("city");
    expect(second.search).toHaveBeenCalledWith("Brampton");
  });

  it("falls back to later providers when an earlier provider errors", async () => {
    const first: GeocoderProvider = { search: vi.fn(async () => Promise.reject(new Error("postal unavailable"))) };
    const second: GeocoderProvider = {
      search: vi.fn(async () => [{ id: "city", label: "Brampton", coordinate: { lat: 43.68, lon: -79.76 } }])
    };

    const candidates = await new FallbackGeocoder([first, second]).search("X9X 9X9");

    expect(candidates[0].id).toBe("city");
    expect(second.search).toHaveBeenCalledWith("X9X 9X9");
  });

  it("throws when every fallback provider errors", async () => {
    const first: GeocoderProvider = { search: vi.fn(async () => Promise.reject(new Error("postal unavailable"))) };
    const second: GeocoderProvider = { search: vi.fn(async () => Promise.reject(new Error("city unavailable"))) };

    await expect(new FallbackGeocoder([first, second]).search("X9X 9X9")).rejects.toThrow("city unavailable");
  });

  it("returns specific copy for rate-limited geocoder failures", async () => {
    const fetchMock = vi.fn<[RequestInfo | URL], Promise<ReturnType<typeof mockJsonResponse>>>(async () => mockJsonResponse({}, 429));
    vi.stubGlobal("fetch", fetchMock);

    await expect(new NominatimGeocoder().search("Brampton").catch(geocoderErrorMessage)).resolves.toBe(
      "Location lookup is temporarily rate-limited. Wait a moment and try again."
    );
  });
});
