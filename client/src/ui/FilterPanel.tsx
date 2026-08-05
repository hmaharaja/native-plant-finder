import { useEffect, useState } from "react";
import {
  activeFilterCount,
  EMPTY_FILTERS,
  FILTER_CATEGORY_CONFIG,
  FilterCategory,
  type FilterState,
  parseOptionalHeight,
  validateMatureHeight
} from "../filters";
import { titleCase } from "../formatters";

interface FilterPanelProps {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
}

export function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const [isOpen, setIsOpen] = useState(() => !window.matchMedia("(max-width: 860px)").matches);
  const [minimum, setMinimum] = useState(filters.matureHeight.minimumFt?.toString() ?? "");
  const [maximum, setMaximum] = useState(filters.matureHeight.maximumFt?.toString() ?? "");
  const count = activeFilterCount(filters);
  const draftRange = { minimumFt: parseOptionalHeight(minimum), maximumFt: parseOptionalHeight(maximum) };
  const heightError = validateMatureHeight(draftRange);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 860px)");
    const update = (event: MediaQueryListEvent) => setIsOpen(!event.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    setMinimum(filters.matureHeight.minimumFt?.toString() ?? "");
    setMaximum(filters.matureHeight.maximumFt?.toString() ?? "");
  }, [filters.matureHeight.minimumFt, filters.matureHeight.maximumFt]);

  function toggleValue(category: FilterCategory, value: string, checked: boolean) {
    const current = filters[category] as readonly string[];
    onChange({ ...filters, [category]: checked ? [...current, value] : current.filter((item) => item !== value) });
  }

  function updateHeight(nextMinimum: string, nextMaximum: string) {
    setMinimum(nextMinimum);
    setMaximum(nextMaximum);
    const range = { minimumFt: parseOptionalHeight(nextMinimum), maximumFt: parseOptionalHeight(nextMaximum) };
    if (!validateMatureHeight(range)) onChange({ ...filters, matureHeight: range });
  }

  function clearAll() {
    setMinimum("");
    setMaximum("");
    onChange(EMPTY_FILTERS);
  }

  return (
    <section className="filter-panel" aria-label="Plant filters">
      <button
        className="filter-toggle"
        type="button"
        aria-expanded={isOpen}
        aria-controls="filter-controls"
        onClick={() => setIsOpen((value) => !value)}
      >
        <span>Filters {count ? `(${count})` : ""}</span>
        <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
      </button>
      <div id="filter-controls" hidden={!isOpen}>
        <label className="specialist-toggle">
          <input
            type="checkbox"
            checked={filters.showSpecialists}
            onChange={(event) => onChange({ ...filters, showSpecialists: event.target.checked })}
          />
          <span>Show specialist species</span>
        </label>
        {filters.showSpecialists ? (
          <p className="specialist-note" role="status">
            Showing species usually intended for specialists and not regular gardens.
          </p>
        ) : null}
        {FILTER_CATEGORY_CONFIG.map((config) => (
          <fieldset key={config.category}>
            <legend>{config.label}</legend>
            <div className="filter-options">
              {config.values.map((value) => {
                const selected = (filters[config.category] as readonly string[]).includes(value);
                return (
                  <label key={value}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={(event) => toggleValue(config.category, value, event.target.checked)}
                    />
                    <span>{titleCase(value)}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
        <fieldset>
          <legend>Mature height (ft)</legend>
          <div className="height-inputs">
            <label>
              <span>Minimum</span>
              <input
                aria-describedby={heightError ? "height-error" : undefined}
                type="number"
                min="0"
                step="any"
                value={minimum}
                onChange={(event) => updateHeight(event.target.value, maximum)}
              />
            </label>
            <label>
              <span>Maximum</span>
              <input
                aria-describedby={heightError ? "height-error" : undefined}
                type="number"
                min="0"
                step="any"
                value={maximum}
                onChange={(event) => updateHeight(minimum, event.target.value)}
              />
            </label>
          </div>
          {heightError ? (
            <p id="height-error" className="filter-error" role="alert">
              {heightError}
            </p>
          ) : null}
        </fieldset>
        <div className="filter-footer">
          <span aria-live="polite">{count} active</span>
          <button type="button" onClick={clearAll} disabled={!count && !heightError}>
            Clear all
          </button>
        </div>
      </div>
    </section>
  );
}
