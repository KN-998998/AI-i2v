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

// 认两种编号：draft_ 是本机自己建的草稿，weekly_ 是批量生产每天自动建的那一份
// （weekly_<32 位 hex>，后端 _DRAFT_ID_RE 一直接受）。「进入片段审核」是整页跳转，
// 跳过去之后要把 weekly_ 编号原样读回来；原来只认 draft_，会把它当成无效编号换成
// 一份新的空草稿，审片页就是空的，还顺手把浏览器里原来的编号也冲掉了。
// 字符集和总长度与后端的 ^[A-Za-z0-9_-]{1,64}$ 对齐：前缀 6/7 位 + 58/57 位刚好 64。
const DRAFT_ID_PATTERN = /^(?:draft_[A-Za-z0-9_-]{1,58}|weekly_[A-Za-z0-9_-]{1,57})$/;

export function browserDraftId(storage: DraftStorage | null = browserStorage()): string {
  try {
    const stored = storage?.getItem(DRAFT_ID_STORAGE_KEY)?.trim();
    if (stored && DRAFT_ID_PATTERN.test(stored)) return stored;
    const draftId = createDraftId();
    storage?.setItem(DRAFT_ID_STORAGE_KEY, draftId);
    return draftId;
  } catch {
    return createDraftId();
  }
}
