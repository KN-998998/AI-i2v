import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { createWeeklyPlan, fetchWeeklyPlanReadiness, fetchWeeklyPlans, updateWeeklyPlanDay, updateWeeklyPlanStatus, uploadAssetLibraryFolder, type WeeklyDailyPlan, type WeeklyPlan, type WeeklyPlanReadiness } from "../api";
import { batchPlanReadiness, missingTemplateKinds } from "../batchPlanReadiness";
import { DRAFT_ID_STORAGE_KEY } from "../draftIdentity";
import { DISH_CATEGORY_OPTIONS } from "../model";
import { navigate } from "../router";
import { useWorkflowStore } from "../workflowStore";

type Props = { onToast: (message: string) => void };
type DailyForm = { candidate_count: number; video_count: number; clips_per_video: number; category_counts: Record<string, number> };

const blankCounts = (): Record<string, number> => Object.fromEntries(DISH_CATEGORY_OPTIONS.map(category => [category, 0]));
const defaultForm = (): DailyForm => ({ candidate_count: 40, video_count: 10, clips_per_video: 4, category_counts: blankCounts() });
/** 后端对候选片段数的上限（weekly_plans.py::_positive）。每天条数的上限跟着它走。 */
const MAX_CANDIDATES_PER_DAY = 80;

function currentDate(): string {
  const current = new Date();
  const offset = current.getTimezoneOffset();
  return new Date(current.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function asForm(day: WeeklyDailyPlan): DailyForm {
  return { candidate_count: day.candidateCount, video_count: day.videoCount, clips_per_video: day.clipsPerVideo, category_counts: { ...blankCounts(), ...day.categoryCounts } };
}

/**
 * 批量生产入口。
 *
 * 这一页以前是三张并排的工程表单卡片：排期 3 个字段、两个文件夹路径、
 * 4 个数量字段、1 个开关，一共 10 个要填的框，而且每次都要重新传一遍素材文件夹。
 * 现在一屏只问三件事——用哪个素材库、每天出几条、用哪个样板什么时候开工。
 *
 * 其余参数不做成「高级设置」那种藏起来的抽屉，而是写成一行看得见的默认值
 * （每条几段 · 每天抽几道菜 · 分类怎么分），点「改」才就地展开：人第一次来
 * 就知道系统替他定了什么，不点又完全不占地方。12 个分类配额再深一层，
 * 勾了才出现——日常批量生产基本用不到。
 *
 * 缺素材、缺背景、样板不完整都在点按钮之前就说清楚，免得计划建好了、
 * 第二天早上才执行失败。
 */
export function WeeklyPlanPage({ onToast }: Props) {
  const draftId = useWorkflowStore(state => state.draftId);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const nodes = useWorkflowStore(state => state.nodes);
  const [plans, setPlans] = useState<WeeklyPlan[]>([]);
  const [startDate, setStartDate] = useState(currentDate);
  const [durationDays, setDurationDays] = useState(7);
  const [assetRoot, setAssetRoot] = useState("");
  const [backgroundRoot, setBackgroundRoot] = useState("");
  const [runAt, setRunAt] = useState("09:00");
  const [form, setForm] = useState<DailyForm>(defaultForm);
  const [manualCounts, setManualCounts] = useState(false);
  const [manualCandidates, setManualCandidates] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [customRoots, setCustomRoots] = useState(false);
  const [readiness, setReadiness] = useState<WeeklyPlanReadiness | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(true);
  const [busy, setBusy] = useState(false);
  const [folderBusy, setFolderBusy] = useState<"asset" | "background" | null>(null);
  const [folderUploadSummary, setFolderUploadSummary] = useState<{ asset?: string; background?: string }>({});
  const assetFolderInputRef = useRef<HTMLInputElement>(null);
  const backgroundFolderInputRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<DailyForm>(defaultForm);

  const selectedPlan = plans[0] ?? null;
  // 每天要抽多少道菜：默认就是「成片数 × 每条片段数」，不用再单独填一个数。
  const candidateCount = manualCandidates ? form.candidate_count : Math.min(MAX_CANDIDATES_PER_DAY, form.video_count * form.clips_per_video);
  const maxVideoCount = Math.max(1, Math.floor(MAX_CANDIDATES_PER_DAY / Math.max(1, form.clips_per_video)));
  const total = useMemo(() => Object.values(form.category_counts).reduce((sum, value) => sum + value, 0), [form]);
  const templateDishes = nodes.filter(node => node.data.kind === "input" && node.data.dishName).length;
  // 这三个参数以前藏在「高级设置」里，人不点开根本不知道系统替他定了什么。现在写成一句话常显。
  const tweaked = form.clips_per_video !== defaultForm().clips_per_video || manualCandidates || manualCounts;
  const categorySummary = manualCounts ? `分类已手动指定（合计 ${total} 道）` : "分类由库存自动分配";
  const missingKinds = useMemo(() => missingTemplateKinds(nodes), [nodes]);
  const ready = batchPlanReadiness({
    loading: readinessLoading,
    library: customRoots || !readiness ? null : readiness,
    customRoots: customRoots ? { asset: assetRoot, background: backgroundRoot } : null,
    missingKinds,
    candidateCount,
    clipsPerVideo: form.clips_per_video,
  });

  const refresh = async () => {
    try { setPlans(await fetchWeeklyPlans()); }
    catch (error) { onToast(error instanceof Error ? error.message : "周计划加载失败"); }
  };
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    let cancelled = false;
    setReadinessLoading(true);
    fetchWeeklyPlanReadiness()
      .then(result => { if (!cancelled) setReadiness(result); })
      .catch(error => { if (!cancelled) onToast(error instanceof Error ? error.message : "素材库情况读取失败"); })
      .finally(() => { if (!cancelled) setReadinessLoading(false); });
    return () => { cancelled = true; };
  }, [onToast]);
  // 已经有计划在跑时，先让人看到今天的进度，创建表单收起来。
  useEffect(() => { setShowCreate(plans.length === 0); }, [plans.length]);
  useEffect(() => {
    for (const input of [assetFolderInputRef.current, backgroundFolderInputRef.current]) {
      input?.setAttribute("webkitdirectory", "");
      input?.setAttribute("directory", "");
    }
  }, [customRoots]);

  const uploadFolder = async (kind: "asset" | "background", event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    setFolderBusy(kind);
    try {
      const result = await uploadAssetLibraryFolder(draftId, kind === "asset" ? "assets" : "backgrounds", files);
      if (kind === "asset") setAssetRoot(result.root);
      else setBackgroundRoot(result.root);
      const size = result.totalSize >= 1024 * 1024
        ? `${(result.totalSize / (1024 * 1024)).toFixed(1)} MB`
        : `${Math.max(1, Math.ceil(result.totalSize / 1024))} KB`;
      const summary = `已上传 ${result.fileCount} 个文件（${size}）`;
      setFolderUploadSummary(current => ({ ...current, [kind]: summary }));
      onToast(`${kind === "asset" ? "菜品" : "背景"}素材库${summary}`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "文件夹上传失败");
    } finally {
      setFolderBusy(null);
    }
  };

  const create = async () => {
    if (!ready.ok) return onToast(ready.blocker);
    const sourceAsset = customRoots ? assetRoot.trim() : readiness?.assetRoot ?? "";
    const sourceBackground = customRoots ? backgroundRoot.trim() : readiness?.backgroundRoot ?? "";
    if (!sourceAsset || !sourceBackground) return onToast("没有可用的素材库文件夹");
    if (manualCounts && total !== candidateCount) return onToast(`手动分类数量合计必须等于每天要抽的 ${candidateCount} 道菜`);
    setBusy(true);
    try {
      await saveDraft();
      const plan = await createWeeklyPlan({
        start_date: startDate, duration_days: durationDays, asset_root: sourceAsset, background_root: sourceBackground, template_draft_id: draftId, run_at: runAt,
        defaults: { ...form, candidate_count: candidateCount, category_counts: manualCounts ? form.category_counts : blankCounts() },
      });
      setPlans(current => [plan, ...current]);
      onToast(`已排好 ${durationDays} 天：每天 ${runAt} 自动出 ${form.video_count} 条`);
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

  const changePlanStatus = async (action: "pause" | "resume" | "cancel") => {
    if (!selectedPlan) return;
    if (action === "cancel" && !window.confirm("取消后，尚未执行的日期不会再生成；已生成内容和审核记录会保留。确定取消吗？")) return;
    setBusy(true);
    try {
      const updated = await updateWeeklyPlanStatus(selectedPlan.id, action);
      setPlans(current => current.map(plan => plan.id === updated.id ? updated : plan));
      onToast(action === "pause" ? "计划已暂停；后续未执行日期不会自动生成" : action === "resume" ? "计划已恢复；未来未执行日期将按时生成" : "计划已取消；尚未执行日期已停止");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "计划状态更新失败");
    } finally { setBusy(false); }
  };

  const goFix = () => {
    if (ready.action === "library") return navigate("/workflow/asset-library-review");
    if (ready.action === "background") return navigate("/workflow/image-processing");
    if (ready.action === "template") return navigate("/workflow/assets");
  };
  const fixLabel = ready.action === "library" ? "去整理素材库" : ready.action === "background" ? "去传背景图" : ready.action === "template" ? "去调样板" : "";

  const libraryLine = readinessLoading
    ? "正在读取素材库…"
    : customRoots
      ? "用自定义文件夹"
      : readiness
        ? `整理好的素材库 · ${readiness.dishCount} 道菜可用 · 背景图 ${readiness.backgroundCount} 张`
        : "没读到素材库情况";

  const entry = <>
    <section className="batch-start">
      <ol className="batch-rows">
        <li className="batch-row">
          <span className="batch-row-index">1</span>
          <div className="batch-row-body">
            <h2>用哪个素材库</h2>
            <p className="batch-row-value">{libraryLine}</p>
            {!customRoots && readiness && readiness.pendingCount > 0 && <p className="batch-row-hint">还有 {readiness.pendingCount} 道菜没确认分类，抽不到它们。<button type="button" className="link-button" onClick={() => navigate("/workflow/asset-library-review")}>去确认</button></p>}
          </div>
          <button type="button" className="link-button batch-row-switch" onClick={() => setCustomRoots(value => !value)}>{customRoots ? "改回整理好的素材库" : "改用其他文件夹"}</button>
        </li>
        {customRoots && <li className="batch-row batch-row-expand">
          <span className="batch-row-index" aria-hidden="true" />
          <div className="batch-row-body batch-custom-roots">
            <label className="field"><span>菜品文件夹</span><div className="asset-path-control"><input className="input" value={assetRoot} onChange={event => setAssetRoot(event.target.value)} placeholder="上传后自动填写" /><button type="button" className="btn" disabled={folderBusy !== null || busy} onClick={() => assetFolderInputRef.current?.click()}>{folderBusy === "asset" ? "上传中..." : "上传文件夹"}</button></div><input ref={assetFolderInputRef} className="visually-hidden" type="file" multiple onChange={event => void uploadFolder("asset", event)} /><small className="muted">JPG、JPEG、PNG、WEBP、GIF · 单文件 ≤ 50 MB。{folderUploadSummary.asset ? ` ${folderUploadSummary.asset}` : ""}</small></label>
            <label className="field"><span>背景文件夹</span><div className="asset-path-control"><input className="input" value={backgroundRoot} onChange={event => setBackgroundRoot(event.target.value)} placeholder="上传后自动填写" /><button type="button" className="btn" disabled={folderBusy !== null || busy} onClick={() => backgroundFolderInputRef.current?.click()}>{folderBusy === "background" ? "上传中..." : "上传文件夹"}</button></div><input ref={backgroundFolderInputRef} className="visually-hidden" type="file" multiple onChange={event => void uploadFolder("background", event)} /><small className="muted">JPG、JPEG、PNG、WEBP、GIF · 单文件 ≤ 50 MB。{folderUploadSummary.background ? ` ${folderUploadSummary.background}` : ""}</small></label>
          </div>
        </li>}
        <li className="batch-row">
          <span className="batch-row-index">2</span>
          <div className="batch-row-body">
            <h2>每天出多少条</h2>
            <div className="batch-stepper">
              <button type="button" className="btn batch-step-button" disabled={form.video_count <= 1} onClick={() => setForm(value => ({ ...value, video_count: Math.max(1, value.video_count - 1) }))} aria-label="少一条">−</button>
              <input className="input batch-step-input" type="number" min="1" max={maxVideoCount} value={form.video_count} onChange={event => setForm(value => ({ ...value, video_count: Math.min(maxVideoCount, Math.max(1, Number(event.target.value) || 1)) }))} />
              <button type="button" className="btn batch-step-button" disabled={form.video_count >= maxVideoCount} onClick={() => setForm(value => ({ ...value, video_count: Math.min(maxVideoCount, value.video_count + 1) }))} aria-label="多一条">+</button>
              <span className="batch-step-unit">条 / 天</span>
            </div>
            <p className="batch-row-hint">每条拼 {form.clips_per_video} 段，所以每天抽 {candidateCount} 道菜；同一道菜 3 天内不会重复出现。{!customRoots && readiness && ready.maxVideosPerDay > 0 ? ` 按现在的库存，每天最多 ${ready.maxVideosPerDay} 条。` : ""}</p>
          </div>
        </li>
        <li className="batch-row">
          <span className="batch-row-index">3</span>
          <div className="batch-row-body">
            <h2>用哪个样板、什么时候开工</h2>
            <p className="batch-row-value">{templateDishes > 0 ? `当前样板 · ${templateDishes} 道菜的设置` : "当前样板 · 还没调过，会用默认参数"}<button type="button" className="link-button batch-row-switch" onClick={() => navigate("/workflow/assets")}>去调样板</button></p>
            <div className="batch-schedule">
              <span>从</span>
              <input className="input" type="date" value={startDate} onChange={event => setStartDate(event.target.value)} />
              <span>起连续</span>
              <input className="input batch-schedule-days" type="number" min="1" max="14" value={durationDays} onChange={event => setDurationDays(Math.min(14, Math.max(1, Number(event.target.value) || 1)))} />
              <span>天，每天</span>
              <input className="input batch-schedule-time" type="time" value={runAt} onChange={event => setRunAt(event.target.value)} />
              <span>自动开工。</span>
            </div>
          </div>
        </li>
      </ol>
      <div className="batch-defaults">
        <span>{tweaked ? "当前设置" : "默认设置"}：每条 {form.clips_per_video} 段 · 每天抽 {candidateCount} 道菜 · {categorySummary}</span>
        <button type="button" className="link-button" onClick={() => setShowAdvanced(value => !value)}>{showAdvanced ? "收起" : "改"}</button>
      </div>
      {showAdvanced && <div className="batch-defaults-open">
        <div className="weekly-output-fields">
          <label className="field"><span>每条成片几段</span><input className="input" type="number" min="1" max="8" value={form.clips_per_video} onChange={event => setForm(value => ({ ...value, clips_per_video: Math.min(8, Math.max(1, Number(event.target.value) || 1)) }))} /><small className="muted">一段约 3 秒</small></label>
          <label className="field"><span>每天抽多少道菜</span><input className="input" type="number" min="1" max={MAX_CANDIDATES_PER_DAY} value={candidateCount} disabled={!manualCandidates} onChange={event => setForm(value => ({ ...value, candidate_count: Math.min(MAX_CANDIDATES_PER_DAY, Math.max(1, Number(event.target.value) || 1)) }))} /><small className="muted">{manualCandidates ? "多抽一些可以在审片时挑" : "默认等于「条数 × 每条段数」"}</small></label>
          <label className="field"><span>3 天去重需要的库存</span><output className="input weekly-readonly">{candidateCount * 3} 道菜</output></label>
        </div>
        <label className="form-check"><input className="form-check-input" type="checkbox" checked={manualCandidates} onChange={event => { setManualCandidates(event.target.checked); if (event.target.checked) setForm(value => ({ ...value, candidate_count: candidateCount })); }} /><span className="form-check-label">手动指定每天抽多少道菜</span></label>
        <label className="form-check"><input className="form-check-input" type="checkbox" checked={manualCounts} onChange={event => setManualCounts(event.target.checked)} /><span className="form-check-label">手动指定每个分类抽几道</span></label>
        {manualCounts && <div className="batch-category-block"><p className="muted">合计必须等于每天抽的 {candidateCount} 道菜；全部留空则由库存自动分配。当前合计 {total}。</p><CategoryFields form={form} setForm={setForm} /></div>}
      </div>}
      <div className="batch-footer">
        <button type="button" className="btn btn-primary batch-go" disabled={busy || !ready.ok} onClick={() => void create()}>{busy ? "正在排计划..." : "开始批量生产"}</button>
        <p className={`batch-footer-note ${ready.ok ? "" : "is-blocked"}`}>
          {ready.ok ? `这 ${durationDays} 天一共 ${durationDays * form.video_count} 条成片，生成好会进「片段审核」等你过目。` : ready.blocker}
          {fixLabel && <button type="button" className="link-button" onClick={goFix}>{fixLabel}</button>}
        </p>
        {ready.ok && ready.note && <p className="batch-footer-note">{ready.note}</p>}
      </div>
    </section>
  </>;

  return <main className="step-main weekly-plan-page">
    <div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/")}>工作台首页</button><span>/</span><strong>批量生产</strong></div>
    <div className="step-header"><div><h1>批量生产</h1><p className="step-goal"><strong>这一页做什么：</strong>选好素材库、定下每天出几条，点开始。之后工具每天按时自动抽菜、抠图、生成、选片、合成，你只需要来审片。</p></div></div>
    {selectedPlan && <section className="weekly-plan-days"><div className="panel-section-head"><div><h2>已排好的计划（{selectedPlan.durationDays} 天）</h2><p className="muted">从 {selectedPlan.startDate} 起。同一道菜用过之后，接下来 2 天不会再被抽到；第 4 天起才重新参与。</p></div><div className="compose-actions"><span className="weekly-run-at">{selectedPlan.status === "active" ? `执行中 · 每天 ${selectedPlan.runAt}` : selectedPlan.status === "paused" ? "已暂停" : "已取消"}</span>{selectedPlan.status === "active" && <button type="button" className="btn" disabled={busy} onClick={() => void changePlanStatus("pause")}>暂停计划</button>}{selectedPlan.status === "paused" && <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void changePlanStatus("resume")}>恢复计划</button>}{selectedPlan.status !== "cancelled" && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void changePlanStatus("cancel")}>取消计划</button>}</div></div><small className="muted">暂停不会中断已开始的任务；取消会停止所有尚未执行的日期，并保留已生成内容和审核记录。</small><div className="weekly-day-grid">{selectedPlan.days.map(day => <article key={day.id} className={`weekly-day-card ${day.status}`}><div className="weekly-day-head"><div><span>{new Date(`${day.runDate}T00:00:00`).toLocaleDateString("zh-CN", { weekday: "short", month: "numeric", day: "numeric" })}</span><strong>{day.status === "scheduled" ? "待执行" : day.status === "review" ? "待片段审核" : day.status === "error" ? "执行失败" : day.status === "cancelled" ? "已取消" : "自动生成中"}</strong></div><small>{day.reservations.length}/{day.candidateCount} 道菜已排好</small></div>{editing === day.id ? <><DayFields form={editForm} setForm={setEditForm} /><div className="compose-actions"><button type="button" className="btn btn-primary" disabled={busy} onClick={() => void saveDay(day)}>保存当天</button><button type="button" className="btn" onClick={() => setEditing(null)}>取消</button></div></> : <><p>{day.videoCount} 条成片 × {day.clipsPerVideo} 段 · 抽 {day.candidateCount} 道菜</p><div className="weekly-category-summary">{Object.entries(day.categoryCounts).filter(([, count]) => count > 0).map(([category, count]) => <span key={category}>{category} {count}</span>)}{Object.values(day.categoryCounts).every(count => count === 0) && <span>分类自动分配</span>}</div><small className="muted">{day.reservations.slice(0, 4).map(item => item.dish_name).join("、")}{day.reservations.length > 4 ? ` 等 ${day.reservations.length} 道菜` : ""}</small>{day.error && <small className="text-destructive">{day.error}</small>}<div className="compose-actions">{day.status === "scheduled" && <button type="button" className="btn" onClick={() => { setEditing(day.id); setEditForm(asForm(day)); }}>编辑当天</button>}{day.status === "review" && <button type="button" className="btn btn-primary" onClick={() => openReview(day)}>进入片段审核</button>}</div></>}</article>)}</div></section>}
    {showCreate ? entry : <div className="batch-recreate"><button type="button" className="btn" onClick={() => setShowCreate(true)}>再排一个计划</button></div>}
  </main>;
}

function CategoryFields({ form, setForm }: { form: DailyForm; setForm: React.Dispatch<React.SetStateAction<DailyForm>> }) {
  return <div className="asset-category-grid weekly-category-fields">{DISH_CATEGORY_OPTIONS.map(category => <label className="field" key={category}><span>{category}</span><input className="input" type="number" min="0" value={form.category_counts[category] ?? 0} onChange={event => setForm(value => ({ ...value, category_counts: { ...value.category_counts, [category]: Math.max(0, Number(event.target.value)) } }))} /></label>)}</div>;
}

function DayFields({ form, setForm }: { form: DailyForm; setForm: React.Dispatch<React.SetStateAction<DailyForm>> }) {
  return <><div className="weekly-day-fields"><label className="field"><span>抽多少道菜</span><input className="input" type="number" value={form.candidate_count} onChange={event => setForm(value => ({ ...value, candidate_count: Number(event.target.value) }))} /></label><label className="field"><span>成片</span><input className="input" type="number" value={form.video_count} onChange={event => setForm(value => ({ ...value, video_count: Number(event.target.value) }))} /></label><label className="field"><span>每条几段</span><input className="input" type="number" value={form.clips_per_video} onChange={event => setForm(value => ({ ...value, clips_per_video: Number(event.target.value) }))} /></label></div><CategoryFields form={form} setForm={setForm} /></>;
}
