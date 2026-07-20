import { FormEvent, useEffect, useMemo, useState } from "react";
import { APP_TITLE, LoadState } from "../constants";
import { findManifestEntry, loadBoundaries, loadEcoregionPayload, loadInitialData, loadManifest } from "../dataClient";
import { displayName, formatHeight, formatList, formatMonthList, formatNumber, scientificName } from "../formatters";
import { createDefaultGeocoder, geocoderErrorMessage } from "../geocoder";
import { findEcoregionForCoordinate } from "../geometry";
import { paginate } from "../pagination";
import type { BoundaryCollection, Coordinate, EcoregionPayload, GeocoderCandidate, Manifest, PlantRecord } from "../types";
import { isValidLocationQuery, safePlantDetailUrl, sanitizeLocationQuery } from "../validation";

const geocoder = createDefaultGeocoder();

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

  const pagination = useMemo(() => paginate(payload?.plants ?? [], page), [page, payload]);

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
          <div>
            <p className="eyebrow">Canada native plants</p>
            <h1>{APP_TITLE}</h1>
          </div>
          <div className="header-stat" aria-label="Loaded data summary">
            <span>{manifest?.ecoregionCount ?? "--"}</span>
            <small>ecoregions</small>
          </div>
        </header>

        <main id="main" className="main-layout">
          <section className="search-panel" aria-labelledby="search-title">
            <div className="panel-intro">
              <h2 id="search-title">Find plants for your region</h2>
              <p>
                Enter a city or postal code.
              </p>
            </div>
            <form className="search-form" onSubmit={handleSubmit}>
              <label htmlFor="location">City or postal code</label>
              <div className="search-row">
                <input
                  id="location"
                  name="location"
                  value={query}
                  maxLength={120}
                  autoComplete="postal-code"
                  inputMode="search"
                  placeholder="Vancouver, BC or V6B 1A1"
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
            <p className="attribution">
              Postal lookup by Zippopotam.us. Location search by{" "}
              <a href="https://nominatim.openstreetmap.org/" rel="noreferrer" target="_blank">
                Nominatim
              </a>{" "}
              and OpenStreetMap contributors.
            </p>
          </section>

          <section className="results-panel" aria-labelledby="results-title">
            <ResultsHeader payload={payload} searchContext={searchContext} />
            {candidates.length > 1 ? <CandidateList candidates={candidates} onChoose={chooseCandidate} /> : null}
            {payload ? (
              <>
                <PlantList plants={pagination.items} />
                {pagination.hasPagination ? (
                  <PaginationControls page={pagination.page} pageCount={pagination.pageCount} onPageChange={setPage} />
                ) : null}
              </>
            ) : (
              <EmptyState state={state} />
            )}
          </section>
        </main>
      </div>
    </>
  );
}

function ResultsHeader({ payload, searchContext }: { payload: EcoregionPayload | null; searchContext: SearchContext | null }) {
  return (
    <div className="results-header">
      <div>
        <p className="eyebrow">Native list</p>
        <h2 id="results-title">{payload?.ecoregionName ?? "Results"}</h2>
      </div>
      {payload ? (
        <div className="result-count">
          <span>{payload.plantCount.toLocaleString()}</span>
          <small>plants</small>
        </div>
      ) : null}
      {searchContext ? <p className="matched-location">Matched from {searchContext.candidateLabel}</p> : null}
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

function PlantList({ plants }: { plants: PlantRecord[] }) {
  return (
    <div className="plant-list">
      {plants.map((plant) => {
        const detailUrl = safePlantDetailUrl(plant.lbjUrl);
        return (
          <article className="plant-card" key={plant.usageKey ?? `${plant.canonicalName}-${plant.vernacularName}`}>
            <div className="plant-card-heading">
              <div>
                <h3>{displayName(plant)}</h3>
                <p>{scientificName(plant)}</p>
              </div>
              {detailUrl ? (
                <a href={detailUrl} rel="noreferrer" target="_blank">
                  Details
                </a>
              ) : null}
            </div>
            <dl className="trait-grid">
              <Trait label="Growth" value={formatList(plant.growthHabit)} />
              <Trait label="Duration" value={plant.duration ?? "Unknown"} />
              <Trait label="Height" value={formatHeight(plant)} />
              <Trait label="Light" value={formatList(plant.light)} />
              <Trait label="Moisture" value={formatList(plant.moisture)} />
              <Trait label="Soil" value={formatList(plant.soilCategories)} />
              <Trait label="Bloom" value={formatMonthList(plant.bloomTime)} />
              <Trait label="Color" value={formatList(plant.bloomColor)} />
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function Trait({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
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
