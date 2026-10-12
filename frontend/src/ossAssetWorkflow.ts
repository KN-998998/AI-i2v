import { normalizeDishCategory, type AssetLibraryPlanItem, type DishCategory, type FoodType, type VisualSubjectType } from "./model.ts";
import type { OssAsset } from "./api.ts";

const COLD_CATEGORIES = new Set<DishCategory>(["寿司", "刺身", "甜品", "水果"]);

function foodTypeForCategory(category: DishCategory): FoodType {
  if (category === "套餐") return "混合/多温";
  return COLD_CATEGORIES.has(category) ? "冷食" : "热食";
}

/** 将已确认的 OSS 结果转成画布现有的菜品链输入格式。 */
export function ossAssetsToPlanItems(jobId: string, assets: readonly OssAsset[]): AssetLibraryPlanItem[] {
  return assets
    .filter(asset => (asset.status === "ready_for_review" || asset.status === "completed") && Boolean(asset.normalized_url))
    .map(asset => {
      const dishName = asset.dish_name.trim() || "未命名菜品";
      const dishCategory = normalizeDishCategory(asset.category, dishName);
      const imagePreview = asset.normalized_url ?? "";
      const visualSubjectType: VisualSubjectType = "菜品主体";
      return {
        dishName,
        displayName: dishName,
        sourceCategory: asset.category,
        dishCategory,
        foodType: foodTypeForCategory(dishCategory),
        visualSubjectType,
        imageName: asset.filename,
        imagePreview,
        sourcePath: imagePreview,
        storedName: asset.filename,
        background: { id: "oss-default-background", name: "待选择背景", url: "", source: "local" },
        reviewRequired: false,
        classificationReason: `已确认的 OSS 素材任务 ${jobId}`,
        categoryCandidates: [dishCategory],
      };
    });
}
