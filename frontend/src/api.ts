import type { AssetLibraryPlan, BackgroundTemplate, ClipLibraryItem, ComposeJob, DraftPayload, GenerationJob, ImageProcessingJob, ManualAssetReviewScan, MediaAnalysis } from "./model";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const raw = await response.text();
    try {
      const payload = JSON.parse(raw) as { detail?: string; error?: string };
      throw new Error(payload.detail || payload.error || `请求失败（${response.status}）`);
    } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
      throw new Error(raw || `请求失败（${response.status}）`);
    }
  }
  return response.json() as Promise<T>;
}

export async function fetchDraft(draftId: string): Promise<DraftPayload | null> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}`, { cache: "no-store" });
  if (response.status === 404) return null;
  return parseResponse<DraftPayload>(response);
}

export async function persistDraft(draftId: string, payload: DraftPayload): Promise<DraftPayload> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<DraftPayload>(response);
}

export async function fetchCanvasClips(): Promise<ClipLibraryItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/clips`, { cache: "no-store" });
  return parseResponse<ClipLibraryItem[]>(response);
}

export type TTSVoiceOption = {
  provider: "qwen";
  model: string;
  voice_id: string;
  label: string;
  gender: "female" | "male" | "custom";
};

export type TTSOptions = {
  configured: boolean;
  provider: "qwen" | null;
  default_model: string | null;
  voices: TTSVoiceOption[];
};

export async function fetchTTSOptions(): Promise<TTSOptions> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/tts/options`, { cache: "no-store" });
  return parseResponse<TTSOptions>(response);
}

export type CaptionSplitResponse = {
  source: string;
  /** Screen copy: commas and sentence stops used as split markers are omitted. */
  segments: string[];
  /** Original copy for matching TTS narration and natural pauses. */
  voice_segments: string[];
  mode: "local" | "local_fallback" | "qwen";
  used_llm: boolean;
  warning: string | null;
};

export async function splitCaptionText(text: string, useLlm = false): Promise<CaptionSplitResponse> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/captions/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, use_llm: useLlm }),
  });
  return parseResponse<CaptionSplitResponse>(response);
}

export async function uploadDraftFile(draftId: string, file: File, kind: "image" | "audio", metadata?: { dish?: string; category?: string }) {
  const body = new FormData();
  body.append("kind", kind);
  if (metadata?.dish) body.append("dish", metadata.dish);
  if (metadata?.category) body.append("category", metadata.category);
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/files`, { method: "POST", body });
  return parseResponse<{ url: string; original_name: string; stored_name: string; size: number; analysis?: MediaAnalysis }>(response);
}

export async function fetchBackgroundTemplates(): Promise<BackgroundTemplate[]> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/backgrounds`, { cache: "no-store" });
  return parseResponse<BackgroundTemplate[]>(response);
}

export async function uploadBackgroundTemplate(file: File): Promise<BackgroundTemplate> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/canvas/backgrounds`, { method: "POST", body });
  return parseResponse<BackgroundTemplate>(response);
}

export async function createAssetLibraryPlan(draftId: string, assetRoot: string, backgroundRoot: string, categoryCounts: Record<string, number>): Promise<AssetLibraryPlan> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/plan?draft_id=${encodeURIComponent(draftId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asset_root: assetRoot, background_root: backgroundRoot, category_counts: categoryCounts }),
  });
  return parseResponse<AssetLibraryPlan>(response);
}

export async function pickAssetLibraryFolder(title: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/pick-folder`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
    signal,
  });
  const payload = await parseResponse<{ path: string }>(response);
  return payload.path;
}

export async function scanManualAssetLibraryUpload(files: File[]): Promise<ManualAssetReviewScan> {
  const form = new FormData();
  files.forEach(file => form.append("files", file, (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name));
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/manual-review/scans/uploads`, { method: "POST", body: form });
  return parseResponse<ManualAssetReviewScan>(response);
}

export async function saveAssetLibraryRule(dishName: string, category: string, foodType?: "冷食" | "热食" | "混合/多温", visualSubjectType?: "菜品主体" | "手部" | "厨师上半身" | "手部+厨师上半身"): Promise<{ dishName: string; category: string; foodType?: "冷食" | "热食" | "混合/多温" | null; visualSubjectType?: "菜品主体" | "手部" | "厨师上半身" | "手部+厨师上半身" }> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dish_name: dishName, category, food_type: foodType ?? null, visual_subject_type: visualSubjectType ?? "菜品主体" }),
  });
  return parseResponse<{ dishName: string; category: string }>(response);
}

export type AssetLibraryRule = { dishName: string; category: string; foodType?: "冷食" | "热食" | "混合/多温" | null; visualSubjectType?: "菜品主体" | "手部" | "厨师上半身" | "手部+厨师上半身" };

export async function fetchAssetLibraryRules(): Promise<AssetLibraryRule[]> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/rules`, { cache: "no-store" });
  return parseResponse<AssetLibraryRule[]>(response);
}

export async function fetchAssetLibraryClassifications(assetRoot: string): Promise<Pick<AssetLibraryPlan, "assetRoot" | "classificationResults" | "classificationMode" | "classificationWarning">> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/classifications?asset_root=${encodeURIComponent(assetRoot)}`, { cache: "no-store" });
  return parseResponse<Pick<AssetLibraryPlan, "assetRoot" | "classificationResults" | "classificationMode" | "classificationWarning">>(response);
}

export async function scanManualAssetLibrary(assetRoot: string): Promise<ManualAssetReviewScan> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/manual-review/scans?asset_root=${encodeURIComponent(assetRoot)}`, { method: "POST" });
  return parseResponse<ManualAssetReviewScan>(response);
}

export async function fetchManualAssetReviewScan(scanId: string): Promise<ManualAssetReviewScan> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/manual-review/scans/${encodeURIComponent(scanId)}`, { cache: "no-store" });
  return parseResponse<ManualAssetReviewScan>(response);
}

export async function saveManualAssetReviewState(scanId: string, selections: Record<string, { category: string; foodType: "冷食" | "热食" | "混合/多温" | ""; visualSubjectType: "菜品主体" | "手部" | "厨师上半身" | "手部+厨师上半身" }>, excludedDishKeys: string[]): Promise<ManualAssetReviewScan> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/manual-review/scans/${encodeURIComponent(scanId)}/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections, excluded_dish_keys: excludedDishKeys }),
  });
  return parseResponse<ManualAssetReviewScan>(response);
}

export async function organizeManualAssetLibrary(scanId: string, targetRoot: string, classifications: Array<{ dishKey: string; category: string; foodType: "冷食" | "热食" | "混合/多温"; visualSubjectType: "菜品主体" | "手部" | "厨师上半身" | "手部+厨师上半身" }>, excludedDishKeys: string[] = []): Promise<{ scanId: string; targetRoot: string; dishCount: number; imageCount: number }> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/asset-library/manual-review/organize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scan_id: scanId, target_root: targetRoot, classifications, excluded_dish_keys: excludedDishKeys }),
  });
  return parseResponse<{ scanId: string; targetRoot: string; dishCount: number; imageCount: number }>(response);
}

export async function startCanvasImageProcessing(draftId: string, nodeId: string): Promise<ImageProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/image-processing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId }),
  });
  return parseResponse<ImageProcessingJob>(response);
}

export async function getCanvasImageProcessingStatus(draftId: string, jobId: string): Promise<ImageProcessingJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/image-processing/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  return parseResponse<ImageProcessingJob>(response);
}

export async function waitForCanvasImageProcessing(draftId: string, job: ImageProcessingJob): Promise<ImageProcessingJob> {
  let current = job;
  for (let attempt = 0; attempt < 120 && (current.status === "queued" || current.status === "running"); attempt += 1) {
    await new Promise(resolve => window.setTimeout(resolve, 1000));
    current = await getCanvasImageProcessingStatus(draftId, job.job_id);
  }
  return current;
}

export type PreflightIssue = { code: string; message: string };
export type PreflightReport = {
  ok: boolean;
  errors: PreflightIssue[];
  warnings: PreflightIssue[];
  summary: { clipCount: number; totalDurationSeconds: number; overlayCount: number; voiceCount: number };
};

export async function startCanvasGeneration(draftId: string, nodeId: string, force = false): Promise<GenerationJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/generations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, force }),
  });
  return parseResponse<GenerationJob>(response);
}

export async function getCanvasGenerationStatus(draftId: string, jobId: string): Promise<GenerationJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/generations/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  return parseResponse<GenerationJob>(response);
}

export async function waitForCanvasGeneration(draftId: string, job: GenerationJob): Promise<GenerationJob> {
  let current = job;
  for (let attempt = 0; attempt < 180 && (current.status === "queued" || current.status === "running"); attempt += 1) {
    await new Promise(resolve => window.setTimeout(resolve, 2000));
    current = await getCanvasGenerationStatus(draftId, job.job_id);
  }
  return current;
}

export async function runCanvasPreflight(draftId: string, workspaceId?: string, includeSound = true): Promise<PreflightReport> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/preflight`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...(workspaceId ? { workspace_id: workspaceId } : {}), include_sound: includeSound }),
  });
  return parseResponse<PreflightReport>(response);
}

export async function startCanvasCompose(draftId: string, workspaceId?: string, includeSound = false): Promise<ComposeJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...(workspaceId ? { workspace_id: workspaceId } : {}), include_sound: includeSound }),
  });
  return parseResponse<ComposeJob>(response);
}

export async function getCanvasComposeStatus(draftId: string, jobId: string): Promise<ComposeJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/compose/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  return parseResponse<ComposeJob>(response);
}
