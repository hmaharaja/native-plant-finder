import { useState, type ReactNode } from "react";
import { displayName, formatHeight, formatList, formatMonthList, scientificName } from "../formatters";
import { recommendationLabel } from "../recommendations";
import type { PlantImage, PlantImageIndex, PlantRecord } from "../types";
import { safePlantDetailUrl } from "../validation";

export function PlantList({
  plants,
  imageIndex,
  action
}: {
  plants: PlantRecord[];
  imageIndex?: PlantImageIndex | null;
  action?: (plant: PlantRecord) => ReactNode;
}) {
  return <div className="plant-list">{plants.map((plant) => <PlantCard key={plant.usageKey ?? `${plant.canonicalName}-${plant.vernacularName}`} plant={plant} image={plant.usageKey === null ? null : imageIndex?.[String(plant.usageKey)]?.primaryImage ?? null} action={action?.(plant)} />)}</div>;
}

export function PlantCard({ plant, image, action }: { plant: PlantRecord; image?: PlantImage | null; action?: ReactNode }) {
  const detailUrl = safePlantDetailUrl(plant.lbjUrl);
  const categoryLabel = recommendationLabel(plant.recommendationCategory);
  const name = displayName(plant);
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
        <PlantCardImage image={image ?? null} alt={name} />
        <div>
          <div className="plant-name-line">
            <h3>{name}</h3>
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

function PlantCardImage({ image, alt }: { image: PlantImage | null; alt: string }) {
  const [failed, setFailed] = useState(false);
  if (!image || failed) {
    return <div className="plantcard-image-placeholder" aria-label="Plant image unavailable" role="img" />;
  }

  const img = (
    <img
      alt={alt}
      className="plantcard-image"
      decoding="async"
      height="72"
      loading="lazy"
      onError={() => setFailed(true)}
      src={image.thumbnailUrl}
      width="96"
    />
  );

  return image.sourceUrl ? (
    <a className="plantcard-image-link" href={image.sourceUrl} rel="noreferrer" target="_blank">
      {img}
    </a>
  ) : img;
}
