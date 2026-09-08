import { useEffect, useMemo, useState } from "react";
import { createWeeklyPlan, fetchWeeklyPlans, updateWeeklyPlanDay, type WeeklyDailyPlan, type WeeklyPlan } from "../api";
import { DRAFT_ID_STORAGE_KEY } from "../draftIdentity";
import { DISH_CATEGORY_OPTIONS } from "../model";
import { navigate } from "../router";
import { useWorkflowStore } from "../workflowStore";

type Props = { onToast: (message: string) => void };
type DailyForm = { candidate_count: number; video_count: number; clips_per_video: number; category_counts: Record<string, number> };

const blankCounts = (): Record<string, number> => Object.fromEntries(DISH_CATEGORY_OPTIONS.map(category => [category, 0]));
const defaultForm = (): DailyForm => ({ candidate_count: 40, video_count: 10, clips_per_video: 4, category_counts: blankCounts() });

function mondayFor(value: Date): string {
  const current = new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const offset = (current.getDay() + 6) % 7;
  current.setDate(current.getDate() - offset);
  return current.toISOString().slice(0, 10);
}

function asForm(day: WeeklyDailyPlan): DailyForm {
  return { candidate_count: day.candidateCount, video_count: day.videoCount, clips_per_video: day.clipsPerVideo, category_counts: { ...blankCounts(), ...day.categoryCounts } };
}

export function WeeklyPlanPage({ onToast }: Props) {
  const draftId = useWorkflowStore(state => state.draftId);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const [plans, setPlans] = useState<WeeklyPlan[]>([]);
  const [weekStart, setWeekStart] = useState(() => mondayFor(new Date()));
  const [assetRoot, setAssetRoot] = useState("");
  const [backgroundRoot, setBackgroundRoot] = useState("");
  const [runAt, setRunAt] = useState("09:00");
  const [form, setForm] = useState<DailyForm>(defaultForm);
  const [manualCounts, setManualCounts] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<DailyForm>(defaultForm);

  const selectedPlan = plans[0] ?? null;
  const total = useMemo(() => Object.values(form.category_counts).reduce((sum, value) => sum + value, 0), [form]);

  const refresh = async () => {
    try { setPlans(await fetchWeeklyPlans()); }
    catch (error) { onToast(error instanceof Error ? error.message : "周计划加载失败"); }
  };
  useEffect(() => { void refresh(); }, []);

  const create = async () => {
    if (!assetRoot.trim() || !backgroundRoot.trim()) return onToast("请填写菜品素材库和背景素材库路径");
    if (manualCounts && total !== form.candidate_count) return onToast("手动分类数量合计必须等于候选片段数");
    setBusy(true);
    try {
      await saveDraft();
      const plan = await createWeeklyPlan({
        week_start: weekStart, asset_root: assetRoot.trim(), background_root: backgroundRoot.trim(), template_draft_id: draftId, run_at: runAt,
        defaults: { ...form, category_counts: manualCounts ? form.category_counts : blankCounts() },
      });
      setPlans(current => [plan, ...current]);
      onToast("已预分配未来 7 天的菜品素材；同一菜品 3 天内不会重复");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "周计划创建失败");
    } finally { setBusy(false); }
  };

  const saveDay = async (day: WeeklyDailyPlan) => {
    const next = editForm;
    const sum = Object.values(next.category_counts).reduce((value, count) => value + count, 0);
    if (sum !== 0 && sum !== next.candidate_count) return onToast("分类数量必须全部留空，或合计等于候选片段数");
    setBusy(true);
    try {
      await updateWeeklyPlanDay(day.id, next);
      await refresh();
      setEditing(null);
      onToast("当天计划和素材预留已更新");
    } catch (error) { onToast(error instanceof Error ? error.message : "当天计划保存失败"); }
    finally { setBusy(false); }
  };

  const openReview = (day: WeeklyDailyPlan) => {
    if (!day.draftId) return;
    window.localStorage.setItem(DRAFT_ID_STORAGE_KEY, day.draftId);
    window.location.assign("/workflow/clip-review");
  };

  return <main className="step-main weekly-plan-page">
    <div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>流程画布</button><span>/</span><strong>周计划生产</strong></div>
    <div className="step-header"><div><span className="panel-label">WEEKLY PRODUCTION</span><h1>周计划生产</h1><p>先预留菜品文件夹，再由服务端每天按时生成候选片段。菜品按文件夹名连续 3 天去重；审核通过前不能合成无声成片。</p></div></div>
    <section className="step-panel weekly-plan-config">
      <div className="panel-section-head"><div><span className="panel-label">NEW 7-DAY PLAN</span><h2>创建一周自动生产计划</h2><p className="muted">默认每天 40 个候选片段，用于组合 10 条、每条 4 个片段的成片。</p></div><button type="button" className="btn btn-primary" disabled={busy} onClick={() => void create()}>{busy ? "保存中..." : "保存并预分配本周素材"}</button></div>
      <div className="weekly-form-grid">
        <label className="field"><span>周一日期</span><input className="input" type="date" value={weekStart} onChange={event => setWeekStart(event.target.value)} /></label>
        <label className="field"><span>每天执行时间</span><input className="input" type="time" value={runAt} onChange={event => setRunAt(event.target.value)} /></label>
        <label className="field"><span>菜品素材库路径</span><input className="input" value={assetRoot} onChange={event => setAssetRoot(event.target.value)} placeholder="ECS 挂载目录或已上传素材目录" /></label>
        <label className="field"><span>背景素材库路径</span><input className="input" value={backgroundRoot} onChange={event => setBackgroundRoot(event.target.value)} placeholder="ECS 挂载目录或已上传背景目录" /></label>
        <label className="field"><span>候选片段 / 天</span><input className="input" type="number" min="1" max="80" value={form.candidate_count} onChange={event => setForm(value => ({ ...value, candidate_count: Number(event.target.value) }))} /></label>
        <label className="field"><span>成片数 / 天</span><input className="input" type="number" min="1" max="30" value={form.video_count} onChange={event => setForm(value => ({ ...value, video_count: Number(event.target.value) }))} /></label>
        <label className="field"><span>每条成片片段数</span><input className="input" type="number" min="1" max="8" value={form.clips_per_video} onChange={event => setForm(value => ({ ...value, clips_per_video: Number(event.target.value) }))} /></label>
        <label className="field"><span>3 天去重最低菜品数</span><output className="input weekly-readonly">{form.candidate_count * 3} 个菜品文件夹</output></label>
      </div>
      <label className="form-check"><input className="form-check-input" type="checkbox" checked={manualCounts} onChange={event => setManualCounts(event.target.checked)} /><span className="form-check-label">手动指定分类数量（否则按可用库存自动随机分配）</span></label>
      {manualCounts && <CategoryFields form={form} setForm={setForm} />}
    </section>
    {selectedPlan && <section className="weekly-plan-days"><div className="panel-section-head"><div><span className="panel-label">{selectedPlan.weekStart}</span><h2>已预分配的一周</h2><p className="muted">同一菜品文件夹在第 1 天使用后，第 2、3 天不会再被分配；第 4 天起才可重新参与抽取。</p></div><span className="weekly-run-at">每天 {selectedPlan.runAt}</span></div><div className="weekly-day-grid">{selectedPlan.days.map(day => <article key={day.id} className={`weekly-day-card ${day.status}`}><div className="weekly-day-head"><div><span>{new Date(`${day.runDate}T00:00:00`).toLocaleDateString("zh-CN", { weekday: "short", month: "numeric", day: "numeric" })}</span><strong>{day.status === "scheduled" ? "待执行" : day.status === "review" ? "待片段审核" : day.status === "error" ? "执行失败" : "自动生成中"}</strong></div><small>{day.reservations.length}/{day.candidateCount} 个菜品已预留</small></div>{editing === day.id ? <><DayFields form={editForm} setForm={setEditForm} /><div className="compose-actions"><button type="button" className="btn btn-primary" disabled={busy} onClick={() => void saveDay(day)}>保存当天</button><button type="button" className="btn" onClick={() => setEditing(null)}>取消</button></div></> : <><p>{day.videoCount} 条成片 × {day.clipsPerVideo} 段 · {day.candidateCount} 个候选片段</p><div className="weekly-category-summary">{Object.entries(day.categoryCounts).filter(([, count]) => count > 0).map(([category, count]) => <span key={category}>{category} {count}</span>)}{Object.values(day.categoryCounts).every(count => count === 0) && <span>自动分类分配</span>}</div><small className="muted">{day.reservations.slice(0, 4).map(item => item.dish_name).join("、")}{day.reservations.length > 4 ? ` 等 ${day.reservations.length} 个菜品` : ""}</small>{day.error && <small className="text-destructive">{day.error}</small>}<div className="compose-actions">{day.status === "scheduled" && <button type="button" className="btn" onClick={() => { setEditing(day.id); setEditForm(asForm(day)); }}>编辑当天</button>}{day.status === "review" && <button type="button" className="btn btn-primary" onClick={() => openReview(day)}>进入片段审核</button>}</div></>}</article>)}</div></section>}
  </main>;
}

function CategoryFields({ form, setForm }: { form: DailyForm; setForm: React.Dispatch<React.SetStateAction<DailyForm>> }) {
  return <div className="asset-category-grid weekly-category-fields">{DISH_CATEGORY_OPTIONS.map(category => <label className="field" key={category}><span>{category}</span><input className="input" type="number" min="0" value={form.category_counts[category] ?? 0} onChange={event => setForm(value => ({ ...value, category_counts: { ...value.category_counts, [category]: Math.max(0, Number(event.target.value)) } }))} /></label>)}</div>;
}

function DayFields({ form, setForm }: { form: DailyForm; setForm: React.Dispatch<React.SetStateAction<DailyForm>> }) {
  return <><div className="weekly-day-fields"><label className="field"><span>候选</span><input className="input" type="number" value={form.candidate_count} onChange={event => setForm(value => ({ ...value, candidate_count: Number(event.target.value) }))} /></label><label className="field"><span>成片</span><input className="input" type="number" value={form.video_count} onChange={event => setForm(value => ({ ...value, video_count: Number(event.target.value) }))} /></label><label className="field"><span>每条片段</span><input className="input" type="number" value={form.clips_per_video} onChange={event => setForm(value => ({ ...value, clips_per_video: Number(event.target.value) }))} /></label></div><CategoryFields form={form} setForm={setForm} /></>;
}
