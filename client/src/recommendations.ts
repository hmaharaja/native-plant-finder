import recommendationCategoryContract from "../../recommendation_categories.json";
import type { PlantRecord, RecommendationCategory } from "./types";

const recommendationCategoryDefinitions = recommendationCategoryContract.categories;

export type RecommendationVisibility = "default-visible" | "specialist-opt-in" | "always-excluded";

export function recommendationVisibility(category: RecommendationCategory | null): RecommendationVisibility {
  return category === null ? "default-visible" : recommendationCategoryDefinitions[category].visibility as RecommendationVisibility;
}

export function recommendationLabel(category: RecommendationCategory | null): string | null {
  return category === null ? null : recommendationCategoryDefinitions[category].label;
}

export function isSpecialistRecommendation(plant: PlantRecord): boolean {
  return recommendationVisibility(plant.recommendationCategory) === "specialist-opt-in";
}

export function permittedRecommendations(plants: readonly PlantRecord[], showSpecialists: boolean): PlantRecord[] {
  const permitted = plants.filter((plant) => {
    const visibility = recommendationVisibility(plant.recommendationCategory);
    return visibility === "default-visible" || (showSpecialists && visibility === "specialist-opt-in");
  });
  if (!showSpecialists) return permitted;
  return [
    ...permitted.filter(isSpecialistRecommendation),
    ...permitted.filter((plant) => !isSpecialistRecommendation(plant))
  ];
}

export function hasSpecialistRecommendations(plants: readonly PlantRecord[]): boolean {
  return plants.some(isSpecialistRecommendation);
}
