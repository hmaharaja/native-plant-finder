import { useEffect, useState, type ReactNode } from "react";
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
  const thumbnailUrl = image?.thumbnailUrl ?? null;

  useEffect(() => {
    setFailed(false);
  }, [thumbnailUrl]);

  const attribution = image ? plantImageAttribution(image) : null;
  const context = image ? plantImageContext(image, attribution) : "Plant image unavailable";
  const hasImage = Boolean(image && !failed);

  const img = image ? (
    <img
      alt={alt}
      className="plantcard-image"
      decoding="async"
      height="90"
      loading="lazy"
      onError={() => setFailed(true)}
      title={context}
      src={image.thumbnailUrl}
      width="120"
    />
  ) : null;

  const imageContent = hasImage && img
    ? image.sourceUrl
      ? (
          <a
            className="plantcard-image-link"
            href={image.sourceUrl}
            rel="noreferrer"
            target="_blank"
            aria-label={`Open image source for ${alt}. ${context}`}
            title={context}
          >
            {img}
          </a>
        )
      : img
    : (
        <div
          className="plantcard-image-placeholder"
          aria-label={image ? `Plant image unavailable. ${context}` : "Plant image unavailable"}
          role="img"
          title={context}
        />
      );

  return (
    <figure className="plantcard-media">
      <div className="plantcard-image-frame">
        {imageContent}
      </div>
      <figcaption className={`plantcard-attribution ${attribution ? "" : "plantcard-attribution-muted"}`}>
        {image?.sourceUrl && attribution ? (
          <a
            href={image.sourceUrl}
            rel="noreferrer"
            target="_blank"
            aria-label={`${attribution} source for ${alt}. ${context}`}
            title={context}
          >
            {attribution}
          </a>
        ) : attribution ?? "No image"
        }
      </figcaption>
    </figure>
  );
}

function plantImageAttribution(image: PlantImage): string {
  return (
    image.credit?.trim() ||
    image.creator?.trim() ||
    image.publisher?.trim() ||
    image.source.trim().replace(/[-_]+/g, " ").toUpperCase()
  );
}

function plantImageContext(image: PlantImage, attribution: string | null): string {
  const source = image.source.trim().replace(/[-_]+/g, " ").toUpperCase();
  return [
    attribution ? `Attribution: ${attribution}` : null,
    source ? `Source: ${source}` : null,
    image.license ? `License: ${image.license}` : null
  ].filter(Boolean).join(". ");
}
