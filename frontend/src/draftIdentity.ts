export const DRAFT_ID_STORAGE_KEY = "short-video.canvas.draft-id";

type DraftStorage = Pick<Storage, "getItem" | "setItem">;

function createDraftId(): string {
  const random = globalThis.crypto?.randomUUID?.().replaceAll("-", "")
    ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  return `draft_${random.slice(0, 56)}`;
}

function browserStorage(): DraftStorage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function browserDraftId(storage: DraftStorage | null = browserStorage()): string {
  try {
    const stored = storage?.getItem(DRAFT_ID_STORAGE_KEY)?.trim();
    if (stored && /^draft_[A-Za-z0-9_-]{1,58}$/.test(stored)) return stored;
    const draftId = createDraftId();
    storage?.setItem(DRAFT_ID_STORAGE_KEY, draftId);
    return draftId;
  } catch {
    return createDraftId();
  }
}
