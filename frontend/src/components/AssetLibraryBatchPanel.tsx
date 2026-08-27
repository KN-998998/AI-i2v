import { useState } from "react";
import { createAssetLibraryPlan, type AssetLibraryPlan } from "../api";
import { useWorkflowStore } from "../workflowStore";

const CATEGORIES = ["寿司", "刺身", "甜品", "主食", "水果", "其他"] as const;

export function AssetLibraryBatchPanel({ onToast }: { onToast: (message: string) => void }) {
  const draftId = useWorkflowStore(state => state.draftId);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const createBatchWorkflows = useWorkflowStore(state => state.createBatchWorkflows);
  const runBatchGeneration = useWorkflowStore(state => state.runBatchGeneration);
  const [assetRoot, setAssetRoot] = useState("");
  const [backgroundRoot, setBackgroundRoot] = useState("");
  const [counts, setCounts] = useState<Record<string, number>>(() => Object.fromEntries(CATEGORIES.map(category => [category, 0])));
  const [plan, setPlan] = useState<AssetLibraryPlan | null>(null);
  const [createdGeneratorIds, setCreatedGeneratorIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const updateCount = (category: string, value: number) => setCounts(current => ({ ...current, [category]: Math.max(0, Math.min(50, Number.isFinite(value) ? Math.round(value) : 0)) }));

  const buildPlan = async () => {
    if (!assetRoot.trim() || !backgroundRoot.trim()) return onToast("请填写菜品素材库和背景素材库路径");
    if (!Object.values(counts).some(value => value > 0)) return onToast("请至少填写一个分类数量");
    setBusy(true);
    try {
      const next = await createAssetLibraryPlan(draftId, assetRoot.trim(), backgroundRoot.trim(), counts);
      setPlan(next);
      setCreatedGeneratorIds([]);
      onToast(`已抽取 ${next.selected.length} 个待确认方案`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "素材库扫描失败");
    } finally {
      setBusy(false);
    }
  };

  const applyPlan = async () => {
    if (!plan) return;
    const ids = createBatchWorkflows(plan.selected);
    setCreatedGeneratorIds(ids);
    await saveDraft();
    onToast(`已创建 ${ids.length} 条流程，请先检查节点信息`);
  };

  const execute = async () => {
    if (!createdGeneratorIds.length) return;
    setBusy(true);
    try {
      await runBatchGeneration(createdGeneratorIds);
      onToast("批量抠图和视频生成任务已提交");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "批量执行失败");
    } finally {
      setBusy(false);
    }
  };

  return <section className="step-panel asset-library-batch-panel">
    <div className="panel-section-head"><div><span className="panel-label">ASSET LIBRARY AUTOMATION</span><h2>素材库批量建稿</h2><p className="muted">按“菜品文件夹名”识别菜品，随机抽图和背景，先生成待确认流程，再决定是否调用抠图与 Kling。</p></div></div>
    <div className="field-grid asset-library-paths"><label className="field"><span>菜品素材库路径</span><input className="input" value={assetRoot} onChange={event => setAssetRoot(event.target.value)} placeholder="例如：F:\\...\\鮨政exp" /></label><label className="field"><span>背景素材库路径</span><input className="input" value={backgroundRoot} onChange={event => setBackgroundRoot(event.target.value)} placeholder="例如：F:\\...\\背景模板" /></label></div>
    <div className="asset-category-grid">{CATEGORIES.map(category => <label className="field" key={category}><span>{category}数量</span><input className="input" type="number" min="0" max="50" value={counts[category]} onChange={event => updateCount(category, Number(event.target.value))} /></label>)}</div>
    <div className="compose-actions"><button type="button" className="btn btn-primary" disabled={busy} onClick={() => void buildPlan()}>{busy ? "处理中..." : "随机抽取并生成待确认方案"}</button><button type="button" className="btn" disabled={!plan || busy} onClick={() => void applyPlan()}>应用到画布</button><button type="button" className="btn btn-danger" disabled={!createdGeneratorIds.length || busy} onClick={() => void execute()}>确认并执行抠图 + 生成</button></div>
    {plan && <div className="asset-library-plan"><strong>待确认方案：{plan.selected.length} 个</strong>{plan.warnings.map(warning => <small className="source-pending" key={warning}>{warning}</small>)}<div className="asset-plan-list">{plan.selected.map(item => <div className="asset-plan-item" key={item.storedName}><img src={item.imagePreview} alt={item.dishName} /><span><strong>{item.dishName}</strong><small>{item.sourceCategory} · {item.foodType} · 背景：{item.background.name}</small></span></div>)}</div></div>}
  </section>;
}
