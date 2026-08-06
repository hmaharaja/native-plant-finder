import { FormEvent, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { APP_TITLE, LoadState } from "../constants";
import { findManifestEntry, loadBoundaries, loadEcoregionPayload, loadInitialData, loadManifest, loadPlantImageIndex } from "../dataClient";
import { formatNumber } from "../formatters";
import { EMPTY_FILTERS, filterPlants, type FilterState } from "../filters";
import { createDefaultGeocoder, geocoderErrorMessage } from "../geocoder";
import { findEcoregionForCoordinate } from "../geometry";
import { paginate } from "../pagination";
import {
  hasSpecialistRecommendations,
  permittedRecommendations
} from "../recommendations";
import {
  getAddResult,
  hydrateShortlist,
  isUsageKey,
  SHORTLIST_LIMIT,
  ShortlistStore,
  shortlistReducer,
  type HydratedShortlist,
  type ShortlistSelection
} from "../shortlist";
import type { BoundaryCollection, Coordinate, EcoregionPayload, GeocoderCandidate, Manifest, PlantImageIndex, PlantRecord } from "../types";
import { isValidLocationQuery, sanitizeLocationQuery } from "../validation";
import { FilterPanel } from "./FilterPanel";
import { PlantList } from "./PlantList";

const geocoder = createDefaultGeocoder();

function createShortlistStore(): ShortlistStore {
  if (typeof window === "undefined") return new ShortlistStore(null);
  try {
    return new ShortlistStore(window.sessionStorage);
  } catch {
    return new ShortlistStore({
      getItem: () => { throw new Error("Storage unavailable"); },
      setItem: () => { throw new Error("Storage unavailable"); },
      removeItem: () => { throw new Error("Storage unavailable"); }
    });
  }
}

interface SearchContext {
  query: string;
  candidateLabel: string;
}

function statusText(state: LoadState): string {
  switch (state) {
    case LoadState.Priming:
      return "Preparing regional plant data";
    case LoadState.Geocoding:
      return "Finding that place";
    case LoadState.ChoosingCandidate:
      return "Choose the matching place";
    case LoadState.MatchingRegion:
      return "Matching the ecoregion";
    case LoadState.LoadingPlants:
      return "Loading native plants";
    case LoadState.Ready:
      return "Results ready";
    case LoadState.Error:
      return "Something needs attention";
    default:
      return "Ready";
  }
}

function useInitialData() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [boundaries, setBoundaries] = useState<BoundaryCollection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    loadInitialData()
      .then((data) => {
        if (!isMounted) {
          return;
        }
        setManifest(data.manifest);
        setBoundaries(data.boundaries);
      })
      .catch((reason: unknown) => {
        if (isMounted) {
          setError(reason instanceof Error ? reason.message : "Unable to load app data.");
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  return { manifest, boundaries, error };
}

async function loadPlantsForCoordinate(
  coordinate: Coordinate,
  manifest: Manifest,
  boundaries: BoundaryCollection
): Promise<EcoregionPayload> {
  const boundary = findEcoregionForCoordinate(boundaries, coordinate);
  if (!boundary) {
    throw new Error("No Canadian ecoregion matched that location.");
  }
  const entry = findManifestEntry(manifest, boundary.ecoregionId);
  if (!entry) {
    throw new Error(`No plant data is available for ${boundary.ecoregionName ?? "that ecoregion"}.`);
  }
  return loadEcoregionPayload(entry);
}

export function App() {
  const { manifest, boundaries, error: initialError } = useInitialData();
  const [query, setQuery] = useState("");
  const [state, setState] = useState<LoadState>(LoadState.Priming);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<GeocoderCandidate[]>([]);
  const [payload, setPayload] = useState<EcoregionPayload | null>(null);
  const [searchContext, setSearchContext] = useState<SearchContext | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const storeRef = useRef<ShortlistStore>();
  if (!storeRef.current) {
    storeRef.current = createShortlistStore();
  }
  const [selection, dispatchSelection] = useReducer(shortlistReducer, undefined, () => storeRef.current!.load());
  const [view, setView] = useState<"results" | "shortlist">("results");
  const [hydrated, setHydrated] = useState<HydratedShortlist | null>(null);
  const [hydrationStatus, setHydrationStatus] = useState<"idle" | "loading" | "ready" | "load-error">("idle");
  const [storageNotice, setStorageNotice] = useState(storeRef.current.failedAtInitialization);
  const [shortlistNotice, setShortlistNotice] = useState<string | null>(null);
  const [hydrationRetry, setHydrationRetry] = useState(0);
  const [plantImageIndex, setPlantImageIndex] = useState<PlantImageIndex | null>(null);
  const appMounted = useRef(true);
  const hydrationRequest = useRef(0);
  const imageIndexLoadInFlight = useRef(false);
  const locationInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    appMounted.current = true;
    return () => {
      appMounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!storeRef.current!.save(selection)) setStorageNotice(true);
  }, [selection]);

  useEffect(() => {
    if (view !== "shortlist" || selection.kind === "empty") {
      setHydrated(null);
      setHydrationStatus("idle");
      return;
    }
    const requestId = ++hydrationRequest.current;
    setHydrationStatus("loading");
    setHydrated(null);
    const load = async () => {
      const source = payload?.ecoregionId === selection.ecoregionId
        ? payload
        : await (async () => {
            const safeManifest = manifest ?? await loadManifest();
            const entry = findManifestEntry(safeManifest, selection.ecoregionId);
            if (!entry) throw new Error("Saved plant region is unavailable");
            return loadEcoregionPayload(entry);
          })();
      if (requestId !== hydrationRequest.current) return;
      setHydrated(hydrateShortlist(selection, source));
      setHydrationStatus("ready");
    };
    load().catch(() => {
      if (requestId === hydrationRequest.current) setHydrationStatus("load-error");
    });
    return () => { hydrationRequest.current += 1; };
  }, [hydrationRetry, manifest, payload, selection, view]);

  const savedCount = selection.kind === "empty" ? 0 : selection.usageKeys.length;
  const savedKeys = selection.kind === "empty" ? new Set<number>() : new Set(selection.usageKeys);
  const savedRegionName = selection.kind === "scoped"
    ? (payload?.ecoregionId === selection.ecoregionId
        ? payload.ecoregionName
        : manifest?.ecoregions.find((entry) => entry.ecoregionId === selection.ecoregionId)?.ecoregionName)
    : null;

  useEffect(() => {
    if (initialError) {
      setError(initialError);
      setState(LoadState.Error);
      return;
    }
    if (manifest && boundaries && state === LoadState.Priming) {
      setState(LoadState.Idle);
    }
  }, [boundaries, initialError, manifest, state]);

  // Keep visibility derivation out of a memo so Vite Fast Refresh cannot retain
  // a list produced by older recommendation logic while hot-loading new controls.
  const permittedPlants = permittedRecommendations(payload?.plants ?? [], filters.showSpecialists);
  const filteredPlants = filterPlants(permittedPlants, filters);
  const pagination = useMemo(() => paginate(filteredPlants, page), [filteredPlants, page]);

  useEffect(() => {
    const hasVisiblePlants =
      (view === "results" && pagination.items.length > 0) ||
      (view === "shortlist" && (hydrated?.records.length ?? 0) > 0);
    if (!hasVisiblePlants || plantImageIndex || imageIndexLoadInFlight.current) {
      return;
    }

    imageIndexLoadInFlight.current = true;
    loadPlantImageIndex()
      .then((index) => {
        if (appMounted.current) {
          setPlantImageIndex(index);
        }
      })
      .catch(() => {
        // Keep cards usable with placeholders; dataClient clears its rejected promise.
      })
      .finally(() => {
        imageIndexLoadInFlight.current = false;
      });
  }, [hydrated?.records.length, pagination.items.length, page, plantImageIndex, payload?.ecoregionId, view]);

  function handleFiltersChange(nextFilters: FilterState) {
    setFilters(nextFilters);
    setPage(1);
  }

  function savePlant(plant: PlantRecord) {
    if (!payload || !isUsageKey(plant.usageKey)) return;
    const result = getAddResult(selection, payload.ecoregionId, plant.usageKey);
    if (result === "region-mismatch") {
      setShortlistNotice(`Your saved plants are for ${savedRegionName ?? "another ecoregion"}; these results are for ${payload.ecoregionName ?? "this ecoregion"}.`);
      return;
    }
    if (result === "capacity") return;
    dispatchSelection({ type: "add", ecoregionId: payload.ecoregionId, usageKey: plant.usageKey });
    setShortlistNotice(`${plant.vernacularName ?? plant.canonicalName ?? "Plant"} saved.`);
  }

  function removePlant(usageKey: number) {
    dispatchSelection({ type: "remove", usageKey });
    setShortlistNotice("Plant removed.");
  }

  function showResultsOrSearch() {
    setView("results");
    if (!payload) requestAnimationFrame(() => locationInput.current?.focus());
  }

  async function handleCoordinate(coordinate: Coordinate, candidateLabel: string, submittedQuery: string) {
    if (!manifest) {
      await loadManifest();
    }
    if (!boundaries) {
      await loadBoundaries();
    }
    const safeManifest = manifest ?? (await loadManifest());
    const safeBoundaries = boundaries ?? (await loadBoundaries());
    setState(LoadState.LoadingPlants);
    const plants = await loadPlantsForCoordinate(coordinate, safeManifest, safeBoundaries);
    setPayload(plants);
    setSearchContext({ query: submittedQuery, candidateLabel });
    setPage(1);
    setCandidates([]);
    setState(LoadState.Ready);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = sanitizeLocationQuery(query);
    setQuery(cleanQuery);
    setError(null);
    setPayload(null);
    setCandidates([]);

    if (!isValidLocationQuery(cleanQuery)) {
      setError("Enter a Canadian city or postal code.");
      setState(LoadState.Error);
      return;
    }

    try {
      setState(LoadState.Geocoding);
      const matches = await geocoder.search(cleanQuery);
      if (matches.length === 0) {
        throw new Error("No Canadian location matched that search.");
      }
      if (matches.length > 1) {
        setCandidates(matches);
        setState(LoadState.ChoosingCandidate);
        return;
      }
      await handleCoordinate(matches[0].coordinate, matches[0].label, cleanQuery);
    } catch (reason) {
      setError(geocoderErrorMessage(reason));
      setState(LoadState.Error);
    }
  }

  async function chooseCandidate(candidate: GeocoderCandidate) {
    try {
      setError(null);
      await handleCoordinate(candidate.coordinate, candidate.label, query);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load plants for that location.");
      setState(LoadState.Error);
    }
  }

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="page-shell">
        <header className="app-header" aria-label="App header">
          <div className="hero-copy">
            <p className="eyebrow">Canada &middot; native plant lookup</p>
            <h1>{APP_TITLE}</h1>
            <p className="hero-subline">
              What grows where <span>you</span> are?
            </p>
          </div>
          <HerbariumIllustration />
        </header>

        <main id="main" className="main-layout">
          <section className={`search-panel ${view === "shortlist" ? "view-hidden" : ""}`} aria-label="Plant search">
            <div className="panel-intro">
              <p>
                Enter a city or postal code.
              </p>
            </div>
            <form className="search-form" onSubmit={handleSubmit}>
              <label className="visually-hidden" htmlFor="location">
                City or postal code
              </label>
              <div className="searchcell">
                <i className="ti ti-map-pin-filled" aria-hidden="true" />
                <input
                  ref={locationInput}
                  id="location"
                  name="location"
                  value={query}
                  maxLength={120}
                  autoComplete="postal-code"
                  inputMode="search"
                  onChange={(event) => setQuery(event.target.value)}
                />
                <button type="submit" disabled={state === LoadState.Geocoding || state === LoadState.LoadingPlants}>
                  Find plants
                </button>
              </div>
            </form>
            <p className="status-line" role="status" aria-live="polite">
              {statusText(state)}
            </p>
            {error ? <p className="error-message">{error}</p> : null}
            {payload && selection.kind === "scoped" && payload.ecoregionId !== selection.ecoregionId ? (
              <p className="error-message">Your saved plants are for {savedRegionName ?? "another ecoregion"}; these results are for {payload.ecoregionName ?? "this ecoregion"}.</p>
            ) : null}
            {storageNotice ? <p className="error-message">Saved plants are available for this page only because browser storage is unavailable.</p> : null}
            <FilterPanel filters={filters} onChange={handleFiltersChange} />
          </section>

          <div className={`results-column ${view === "shortlist" ? "results-column-wide" : ""}`}>
            <div className="results-view-toolbar">
              <button className="saved-plants-nav" type="button" aria-pressed={view === "shortlist"} onClick={() => setView(view === "shortlist" ? "results" : "shortlist")}>
                {view === "shortlist" ? (
                  "View Search Results"
                ) : (
                  <>View Saved Plants <span aria-hidden="true">&middot;</span> {savedCount}/{SHORTLIST_LIMIT}</>
                )}
              </button>
            </div>

            <section className={`results-panel ${view === "shortlist" ? "view-hidden" : ""}`} aria-labelledby="results-title">
              <ResultsHeader
                payload={payload}
                searchContext={searchContext}
                page={pagination.page}
                pageCount={pagination.pageCount}
                filteredCount={filteredPlants.length}
                permittedCount={permittedPlants.length}
              />
              {candidates.length > 1 ? <CandidateList candidates={candidates} onChoose={chooseCandidate} /> : null}
              {payload ? (
                <>
                  {filteredPlants.length ? (
                    <PlantList plants={pagination.items} imageIndex={plantImageIndex} action={(plant) => {
                      const key = plant.usageKey;
                      const saved = isUsageKey(key) && savedKeys.has(key);
                      const mismatch = selection.kind === "scoped" && payload.ecoregionId !== selection.ecoregionId;
                      return saved ? (
                        <>
                          <span className="saved-badge">Saved</span>
                          <button className="card-action" type="button" onClick={() => removePlant(key)}>Remove</button>
                        </>
                      ) : (
                        <button
                          className="card-action"
                          type="button"
                          disabled={!isUsageKey(key) || savedCount >= SHORTLIST_LIMIT || mismatch}
                          title={mismatch ? `Saved plants are scoped to ${savedRegionName ?? "another ecoregion"}` : undefined}
                          onClick={() => savePlant(plant)}
                        >Save plant</button>
                      );
                    }} />
                  ) : permittedPlants.length > 0 ? (
                    <NoMatches onClear={() => handleFiltersChange(EMPTY_FILTERS)} />
                  ) : !filters.showSpecialists && hasSpecialistRecommendations(payload.plants) ? (
                    <SpecialistOnly onShow={() => handleFiltersChange({ ...filters, showSpecialists: true })} />
                  ) : (
                    <NoRecommendations />
                  )}
                  {pagination.hasPagination ? (
                    <PaginationControls page={pagination.page} pageCount={pagination.pageCount} onPageChange={setPage} />
                  ) : null}
                </>
              ) : (
                <EmptyState state={state} />
              )}
            </section>

            <section className={`results-panel shortlist-panel ${view === "results" ? "view-hidden" : ""}`} aria-labelledby="shortlist-title">
              <div className="results-header">
                <div className="results-title-block"><p className="eyebrow">Your field notes</p><h2 id="shortlist-title">Saved plants</h2></div>
                <div className="match-line"><p><span>Saved</span>{savedCount} of {SHORTLIST_LIMIT} plants</p>{savedRegionName ? <p><span>Ecoregion</span>{savedRegionName}</p> : null}</div>
              </div>
              <p className="status-line" role="status" aria-live="polite">{shortlistNotice}</p>
              {selection.kind === "empty" ? (
                <div className="empty-state no-matches"><div><h3>No saved plants yet</h3><p>Save plants from your regional results to compare them here.</p><button type="button" onClick={showResultsOrSearch}>Search for plants to save</button></div></div>
              ) : hydrationStatus === "loading" ? <div className="empty-state">Loading saved plants.</div>
              : hydrationStatus === "load-error" ? <div className="empty-state no-matches"><div><h3>Saved plants could not be loaded</h3><p>Your saved plant IDs are still safe.</p><button type="button" onClick={() => setHydrationRetry((value) => value + 1)}>Retry</button></div></div>
              : hydrated ? <>
                  <div className="shortlist-toolbar"><button type="button" onClick={() => { if (window.confirm("Clear all saved plants?")) dispatchSelection({ type: "clear" }); }}>Clear saved plants</button></div>
                  <PlantList plants={hydrated.records} imageIndex={plantImageIndex} action={(plant) => isUsageKey(plant.usageKey) ? <><span className="saved-badge">Saved</span><button className="card-action" type="button" onClick={() => removePlant(plant.usageKey!)}>Remove</button></> : null} />
                  {hydrated.unresolvedKeys.map((key) => <article className="plantcard unresolved-card" key={key}><div><h3>Plant unavailable</h3><p>This saved plant can no longer be displayed.</p></div><button className="card-action" type="button" onClick={() => removePlant(key)}>Remove</button></article>)}
                </> : null}
            </section>
          </div>
        </main>
      </div>
    </>
  );
}

function HerbariumIllustration() {
  const flowerHeads = [
    { x: 120, y: 34, scale: 1, rotate: -8 },
    { x: 91, y: 54, scale: 0.66, rotate: -22 },
    { x: 151, y: 66, scale: 0.72, rotate: 18 }
  ];

  return (
    <figure className="herbarium" aria-hidden="true">
      <svg viewBox="0 0 240 220" role="img" focusable="false">
        <path className="specimen-stem main" d="M114 202 C116 160, 116 114, 121 42" />
        <path className="specimen-stem branch" d="M117 112 C101 91, 95 72, 92 56" />
        <path className="specimen-stem branch" d="M119 124 C139 104, 148 83, 153 66" />
        <path className="specimen-leaf" d="M111 143 C79 126, 61 103, 59 73 C91 82, 112 108, 111 143 Z" />
        <path className="specimen-vein" d="M106 136 C92 115, 78 96, 63 78" />
        <path className="specimen-leaf" d="M122 151 C154 137, 176 112, 185 78 C149 82, 127 110, 122 151 Z" />
        <path className="specimen-vein" d="M128 142 C145 119, 163 98, 181 82" />
        <path className="specimen-leaf small" d="M107 184 C82 179, 63 162, 54 139 C81 138, 102 155, 107 184 Z" />
        <path className="specimen-vein" d="M101 178 C87 163, 73 151, 57 141" />
        {flowerHeads.map((head) => (
          <g
            key={`${head.x}-${head.y}`}
            className="monarda-head"
            transform={`translate(${head.x} ${head.y}) rotate(${head.rotate}) scale(${head.scale})`}
          >
            <path className="bract" d="M-20 20 C-11 9, 10 9, 22 20 C9 27, -7 28, -20 20 Z" />
            {Array.from({ length: 17 }).map((_, index) => {
              const angle = -86 + index * 10.75;
              const length = index % 3 === 0 ? 37 : 31;
              const endX = Math.round(-length * Math.sin((angle * Math.PI) / 180));
              const endY = Math.round(-length * Math.cos((angle * Math.PI) / 180));
              return (
                <path
                  key={index}
                  className="tube"
                  d={`M0 14 C${-5 + index * 0.62} 1, ${-8 + index * 0.94} -12, ${endX} ${endY}`}
                />
              );
            })}
            {Array.from({ length: 13 }).map((_, index) => (
              <path
                key={`petal-${index}`}
                className="petal"
                d="M0 14 C-5 6, -4 -3, 0 -11 C5 -3, 5 6, 0 14 Z"
                transform={`rotate(${-78 + index * 13})`}
              />
            ))}
            <circle className="seed-head" r="11" cy="13" />
          </g>
        ))}
      </svg>
      <figcaption>Monarda fistulosa</figcaption>
    </figure>
  );
}

function ResultsHeader({
  payload,
  searchContext,
  page,
  pageCount,
  filteredCount,
  permittedCount
}: {
  payload: EcoregionPayload | null;
  searchContext: SearchContext | null;
  page: number;
  pageCount: number;
  filteredCount: number;
  permittedCount: number;
}) {
  return (
    <div className="results-header">
      <div className="results-title-block">
        <p className="eyebrow">Native list</p>
        <h2 id="results-title">Results</h2>
      </div>
      {payload ? (
        <div className="match-line" aria-label="Matched ecoregion">
          <p>
            <span>Matched ecoregion:</span> {payload.ecoregionName}
          </p>
          {searchContext ? (
            <p>
              <span>Matched from</span> {searchContext.candidateLabel}
            </p>
          ) : null}
          <p className="count-line">
            {filteredCount.toLocaleString()} of {permittedCount.toLocaleString()} species &middot; page {page} of{" "}
            {pageCount}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function SpecialistOnly({ onShow }: { onShow: () => void }) {
  return (
    <div className="empty-state no-matches">
      <div>
        <h3>This region’s recommended plants are specialist species</h3>
        <p>These plants are usually intended for restoration or other specialist settings.</p>
        <button type="button" onClick={onShow}>Show specialist species</button>
      </div>
    </div>
  );
}

function NoRecommendations() {
  return (
    <div className="empty-state no-matches">
      <div>
        <h3>No recommended plants are available</h3>
        <p>This region currently contains only records excluded from recommendations.</p>
      </div>
    </div>
  );
}

function NoMatches({ onClear }: { onClear: () => void }) {
  return (
    <div className="empty-state no-matches">
      <div>
        <h3>No plants match these filters</h3>
        <p>Try widening your selections or start fresh.</p>
        <button type="button" onClick={onClear}>
          Clear filters
        </button>
      </div>
    </div>
  );
}

function CandidateList({
  candidates,
  onChoose
}: {
  candidates: GeocoderCandidate[];
  onChoose: (candidate: GeocoderCandidate) => void;
}) {
  return (
    <div className="candidate-list" aria-label="Location matches">
      {candidates.map((candidate) => (
        <button key={candidate.id} type="button" onClick={() => onChoose(candidate)}>
          <span>{candidate.label}</span>
          <small>
            {formatNumber(candidate.coordinate.lat)}, {formatNumber(candidate.coordinate.lon)}
          </small>
        </button>
      ))}
    </div>
  );
}

function EmptyState({ state }: { state: LoadState }) {
  const copy =
    state === LoadState.Priming
      ? "Preparing the regional lookup files."
      : "Search for a Canadian location to load native plants for its ecoregion.";
  return <div className="empty-state">{copy}</div>;
}

function PaginationControls({
  page,
  pageCount,
  onPageChange
}: {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <nav className="pagination" aria-label="Plant result pages">
      <button type="button" disabled={page === 1} onClick={() => onPageChange(page - 1)}>
        Previous
      </button>
      <span>
        Page {page} of {pageCount}
      </span>
      <button type="button" disabled={page === pageCount} onClick={() => onPageChange(page + 1)}>
        Next
      </button>
    </nav>
  );
}
