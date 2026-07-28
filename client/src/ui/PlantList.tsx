import type { ReactNode } from "react";
import { displayName, formatHeight, formatList, formatMonthList, scientificName } from "../formatters";
import { recommendationLabel } from "../recommendations";
import type { PlantRecord } from "../types";
import { safePlantDetailUrl } from "../validation";

export function PlantList({
  plants,
  action
}: {
  plants: PlantRecord[];
  action?: (plant: PlantRecord) => ReactNode;
}) {
  return <div className="plant-list">{plants.map((plant) => <PlantCard key={plant.usageKey ?? `${plant.canonicalName}-${plant.vernacularName}`} plant={plant} action={action?.(plant)} />)}</div>;
}

export function PlantCard({ plant, action }: { plant: PlantRecord; action?: ReactNode }) {
  const detailUrl = safePlantDetailUrl(plant.lbjUrl);
  const categoryLabel = recommendationLabel(plant.recommendationCategory);
  const traits = [
    ["Growth", formatList(plant.growthHabit)],
    ["Duration", plant.duration ?? "Unknown"],
    ["Height", formatHeight(plant)],
    ["Light", formatList(plant.light)],
    ["Moisture", formatList(plant.moisture)],
    ["Soil", formatList(plant.soilCategories)],
    ["Bloom", formatMonthList(plant.bloomTime)],
    ["Color", formatList(plant.bloomColor)]
  ] as const;
  return (
    <article className="plantcard">
      <div className="plantcard-head">
        <div>
          <div className="plant-name-line">
            <h3>{displayName(plant)}</h3>
            {categoryLabel ? <span className="recommendation-badge">{categoryLabel}</span> : null}
          </div>
          <p>{scientificName(plant)}</p>
        </div>
        <div className="plantcard-actions">
          {action}
          {detailUrl ? <a className="details-btn" href={detailUrl} rel="noreferrer" target="_blank">Details</a> : null}
        </div>
      </div>
      <dl className="attrgrid">{traits.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    </article>
  );
}
