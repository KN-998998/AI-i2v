import type { ClipLibraryItem, ComposeJob, DraftPayload } from "./model";

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

export async function uploadDraftFile(draftId: string, file: File, kind: "image" | "audio") {
  const body = new FormData();
  body.append("kind", kind);
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/files`, { method: "POST", body });
  return parseResponse<{ url: string; original_name: string; stored_name: string; size: number }>(response);
}

export async function startCanvasCompose(draftId: string, workspaceId?: string): Promise<ComposeJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(workspaceId ? { workspace_id: workspaceId } : {}),
  });
  return parseResponse<ComposeJob>(response);
}

export async function getCanvasComposeStatus(draftId: string, jobId: string): Promise<ComposeJob> {
  const response = await fetch(`${API_BASE_URL}/api/canvas/drafts/${encodeURIComponent(draftId)}/compose/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  return parseResponse<ComposeJob>(response);
}
