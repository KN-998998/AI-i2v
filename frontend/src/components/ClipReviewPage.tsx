import { useEffect, useState } from "react";
import { fetchWeeklyRunByDraft, saveWeeklyClipReview, type WeeklyDailyPlan } from "../api";
import { navigate } from "../router";
import { useWorkflowStore } from "../workflowStore";

export function ClipReviewPage({ onToast }: { onToast: (message: string) => void }) {
  const draftId = useWorkflowStore(state => state.draftId);
  const candidates = useWorkflowStore(state => state.candidateClips);
  const loadDraft = useWorkflowStore(state => state.loadDraft);
  const [run, setRun] = useState<WeeklyDailyPlan | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  useEffect(() => { void fetchWeeklyRunByDraft(draftId).then(setRun).catch(() => setRun(null)); }, [draftId]);
  const visible = candidates.filter(item => item.sourcePath);
  const review = async (clipId: string, decision: "approved" | "rejected", start: number, end: number) => {
    if (!run) return;
    setBusyId(clipId);
    try {
      const next = await saveWeeklyClipReview(run.id, clipId, decision, start, end);
      setRun(next);
      await loadDraft();
    } catch (error) { onToast(error instanceof Error ? error.message : "审核保存失败"); }
    finally { setBusyId(null); }
  };
  const decided = (run?.reviewSummary.approved ?? 0) + (run?.reviewSummary.rejected ?? 0);
  return <main className="step-main clip-review-page"><div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/workflow/weekly-plan")}>周计划生产</button><span>/</span><strong>片段审核</strong></div><div className="step-header"><div><span className="panel-label">MANDATORY CLIP REVIEW</span><h1>候选片段审核</h1><p>每个已生成片段都必须通过或淘汰；通过时可确认裁剪时间。完成后才允许进入无声成片组合。</p></div></div>{!run ? <section className="step-panel empty-panel"><strong>当前草稿不是周计划运行，或运行尚未创建。</strong></section> : <><section className="step-panel clip-review-summary"><strong>{run.runDate} · 已审核 {decided}/{visible.length}</strong><span>通过 {run.reviewSummary.approved ?? 0} · 淘汰 {run.reviewSummary.rejected ?? 0} · 每条成片需要 {run.clipsPerVideo} 个片段</span>{decided === visible.length && visible.length > 0 && <button type="button" className="btn btn-primary" onClick={() => navigate("/workflow/compose")}>审核完成，进入无声成片组合</button>}</section><div className="clip-review-grid">{visible.map(clip => <ClipReviewCard key={clip.id} clip={clip} busy={busyId === clip.id} onReview={review} />)}</div></>}</main>;
}

function ClipReviewCard({ clip, busy, onReview }: { clip: { id: string; dish: string; sourceUrl?: string; previewUrl?: string; sourceStartSeconds?: number; sourceEndSeconds?: number; sourceDurationSeconds?: number; reviewStatus?: "approved" | "rejected" }; busy: boolean; onReview: (id: string, decision: "approved" | "rejected", start: number, end: number) => void }) {
  const [start, setStart] = useState(clip.sourceStartSeconds ?? 0.5);
  const [end, setEnd] = useState(clip.sourceEndSeconds ?? clip.sourceDurationSeconds ?? 3);
  return <article className={`clip-review-card ${clip.reviewStatus ?? "pending"}`}><video controls preload="metadata" src={clip.previewUrl || clip.sourceUrl} /><div><strong>{clip.dish}</strong><span>{clip.reviewStatus === "approved" ? "已通过" : clip.reviewStatus === "rejected" ? "已淘汰" : "待审核"}</span></div><div className="weekly-day-fields"><label className="field"><span>起点(s)</span><input className="input" type="number" min="0" step="0.1" value={start} onChange={event => setStart(Number(event.target.value))} /></label><label className="field"><span>终点(s)</span><input className="input" type="number" min="0.1" step="0.1" value={end} onChange={event => setEnd(Number(event.target.value))} /></label></div><div className="compose-actions"><button type="button" className="btn btn-primary" disabled={busy || end <= start} onClick={() => onReview(clip.id, "approved", start, end)}>通过</button><button type="button" className="btn btn-danger" disabled={busy} onClick={() => onReview(clip.id, "rejected", start, end)}>淘汰</button></div></article>;
}
