import { useEffect, useState } from "react";
import { createAssetLibraryPlan, fetchAssetLibraryRules, pickAssetLibraryFolder, saveAssetLibraryRule, type AssetLibraryRule } from "../api";
import type { AssetLibraryPlan, AssetLibraryReviewItem } from "../model";
import { useWorkflowStore } from "../workflowStore";

const CATEGORIES = ["寿司", "刺身", "前菜/小菜", "主菜", "主食", "汤品", "甜品", "水果", "饮品", "其他"] as const;
const ASSET_ROOT_STORAGE_KEY = "restaurant-video.asset-library.asset-root";
const BACKGROUND_ROOT_STORAGE_KEY = "restaurant-video.asset-library.background-root";

function rememberedPath(key: string): string {
  try {
    return window.localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function rememberPath(key: string, value: string): void {
  try {
    if (value.trim()) window.localStorage.setItem(key, value);
    else window.localStorage.removeItem(key);
  } catch {
    // Private browsing or browser policy may disable local storage.
  }
}

export function AssetLibraryBatchPanel({ onToast }: { onToast: (message: string) => void }) {
  const draftId = useWorkflowStore(state => state.draftId);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const savedPlan = useWorkflowStore(state => state.assetLibraryPlan);
  const setAssetLibraryPlan = useWorkflowStore(state => state.setAssetLibraryPlan);
  const updateAssetLibraryReviewCategory = useWorkflowStore(state => state.updateAssetLibraryReviewCategory);
  const createBatchWorkflows = useWorkflowStore(state => state.createBatchWorkflows);
  const runBatchGeneration = useWorkflowStore(state => state.runBatchGeneration);
  const [assetRoot, setAssetRoot] = useState(() => rememberedPath(ASSET_ROOT_STORAGE_KEY));
  const [backgroundRoot, setBackgroundRoot] = useState(() => rememberedPath(BACKGROUND_ROOT_STORAGE_KEY));
  const [counts, setCounts] = useState<Record<string, number>>(() => Object.fromEntries(CATEGORIES.map(category => [category, 0])));
  const [createdGeneratorIds, setCreatedGeneratorIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [folderBusy, setFolderBusy] = useState<"asset" | "background" | null>(null);
  const [reviewCategories, setReviewCategories] = useState<Record<string, string>>({});
  const [activeReviewItem, setActiveReviewItem] = useState<string | null>(null);
  const [savingRule, setSavingRule] = useState<string | null>(null);
  const [rulesChanged, setRulesChanged] = useState(false);
  const [categoryRules, setCategoryRules] = useState<AssetLibraryRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [ruleSaving, setRuleSaving] = useState<string | null>(null);
  const [pendingRuleCategories, setPendingRuleCategories] = useState<Record<string, string>>({});

  const plan: AssetLibraryPlan | null = savedPlan;

  useEffect(() => rememberPath(ASSET_ROOT_STORAGE_KEY, assetRoot), [assetRoot]);
  useEffect(() => rememberPath(BACKGROUND_ROOT_STORAGE_KEY, backgroundRoot), [backgroundRoot]);
  useEffect(() => {
    let active = true;
    setRulesLoading(true);
    fetchAssetLibraryRules()
      .then(rules => {
        if (!active) return;
        setCategoryRules(rules);
        setPendingRuleCategories(Object.fromEntries(rules.map(rule => [rule.dishName, rule.category])));
      })
      .catch(error => { if (active) onToast(error instanceof Error ? error.message : "分类规则加载失败"); })
      .finally(() => { if (active) setRulesLoading(false); });
    return () => { active = false; };
  }, [onToast]);
  useEffect(() => {
    if (!plan) return;
    setAssetRoot(current => current || plan.assetRoot);
    setBackgroundRoot(current => current || plan.backgroundRoot);
    setCounts(current => Object.values(current).some(value => value > 0) ? current : { ...current, ...plan.categoryCounts });
    setReviewCategories(Object.fromEntries((plan.reviewItems ?? []).map(item => [item.dishName, item.suggestedCategory ?? item.sourceCategory])));
  }, [plan]);

  const updateCount = (category: string, value: number) => setCounts(current => ({ ...current, [category]: Math.max(0, Math.min(50, Number.isFinite(value) ? Math.round(value) : 0)) }));

  const chooseFolder = async (kind: "asset" | "background") => {
    setFolderBusy(kind);
    try {
      const path = await pickAssetLibraryFolder(kind === "asset" ? "选择菜品素材库文件夹" : "选择背景素材库文件夹");
      if (path) {
        if (kind === "asset") setAssetRoot(path);
        else setBackgroundRoot(path);
      }
    } catch (error) {
      onToast(error instanceof Error ? error.message : "文件夹选择失败");
    } finally {
      setFolderBusy(null);
    }
  };

  const buildPlan = async () => {
    if (!assetRoot.trim() || !backgroundRoot.trim()) return onToast("请填写菜品素材库和背景素材库路径");
    if (!Object.values(counts).some(value => value > 0)) return onToast("请至少填写一个分类数量");
    setBusy(true);
    try {
      const next = await createAssetLibraryPlan(draftId, assetRoot.trim(), backgroundRoot.trim(), counts);
      setAssetLibraryPlan(next);
      setReviewCategories(Object.fromEntries((next.reviewItems ?? []).map(item => [item.dishName, item.suggestedCategory ?? item.sourceCategory])));
      setActiveReviewItem(null);
      setRulesChanged(false);
      setCreatedGeneratorIds([]);
      await saveDraft();
      onToast(`已抽取 ${next.selected.length} 个待确认方案`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "素材库扫描失败");
    } finally {
      setBusy(false);
    }
  };

  const confirmCategory = async (item: AssetLibraryReviewItem) => {
    const category = reviewCategories[item.dishName] ?? item.sourceCategory;
    setSavingRule(item.dishName);
    try {
      await saveAssetLibraryRule(item.dishName, category);
      const nextPlan = plan ? {
        ...plan,
        selected: plan.selected.map(selected => selected.dishName === item.dishName
          ? { ...selected, sourceCategory: category, suggestedCategory: category, reviewRequired: false, classificationReason: "已使用人工确认规则", categoryCandidates: [category] }
          : selected),
        reviewItems: (plan.reviewItems ?? []).filter(review => review.dishName !== item.dishName),
      } : null;
      setAssetLibraryPlan(nextPlan);
      await saveDraft();
      setRulesChanged(true);
      onToast(`已保存“${item.dishName}”的分类规则`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "分类规则保存失败");
    } finally {
      setSavingRule(null);
    }
  };

  const applyPlan = async () => {
    if (!plan) return;
    if ((plan.reviewItems ?? []).length > 0) {
      onToast("请先完成所有菜品分类确认，再应用到画布");
      return;
    }
    const ids = createBatchWorkflows(plan.selected);
    setCreatedGeneratorIds(ids);
    await saveDraft();
    onToast(`已创建 ${ids.length} 条流程，请先检查节点信息`);
  };

  const saveManagedRule = async (rule: AssetLibraryRule) => {
    const category = pendingRuleCategories[rule.dishName] ?? rule.category;
    if (category === rule.category) return;
    setRuleSaving(rule.dishName);
    try {
      const saved = await saveAssetLibraryRule(rule.dishName, category);
      setCategoryRules(current => current.map(item => item.dishName === rule.dishName ? saved : item));
      onToast(`已将“${rule.dishName}”调整为${category}`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "分类规则保存失败");
    } finally {
      setRuleSaving(null);
    }
  };

  const groupedRules = CATEGORIES.map(category => ({ category, items: categoryRules.filter(rule => rule.category === category) }));

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
    <small className="muted">可选择包含多层分类目录的上级文件夹，系统会扫描实际存放图片的最深层菜品文件夹。</small>
    <div className="panel-section-head"><div><span className="panel-label">ASSET LIBRARY AUTOMATION</span><h2>素材库批量建稿</h2><p className="muted">按“菜品文件夹名”识别菜品，随机抽图和背景，先生成待确认流程，再决定是否调用抠图与 Kling。</p></div></div>
    <div className="field-grid asset-library-paths"><label className="field"><span>菜品素材库路径</span><div className="asset-path-control"><input className="input" value={assetRoot} onChange={event => setAssetRoot(event.target.value)} placeholder="例如：F:\\...\\鮨政exp" /><button type="button" className="btn" disabled={folderBusy !== null} onClick={() => void chooseFolder("asset")}>{folderBusy === "asset" ? "选择中..." : "选择文件夹"}</button></div></label><label className="field"><span>背景素材库路径</span><div className="asset-path-control"><input className="input" value={backgroundRoot} onChange={event => setBackgroundRoot(event.target.value)} placeholder="例如：F:\\...\\背景模板" /><button type="button" className="btn" disabled={folderBusy !== null} onClick={() => void chooseFolder("background")}>{folderBusy === "background" ? "选择中..." : "选择文件夹"}</button></div></label></div>
    <div className="asset-category-grid">{CATEGORIES.map(category => <label className="field" key={category}><span>{category}数量</span><input className="input" type="number" min="0" max="50" value={counts[category]} onChange={event => updateCount(category, Number(event.target.value))} /></label>)}</div>
    <div className="compose-actions"><button type="button" className="btn btn-primary" disabled={busy} onClick={() => void buildPlan()}>{busy ? "处理中..." : rulesChanged ? "按最新规则重新抽取" : "扫描并生成待确认方案"}</button><button type="button" className="btn" disabled={!plan || busy || (plan.reviewItems ?? []).length > 0} onClick={() => void applyPlan()}>应用到画布</button><button type="button" className="btn btn-danger" disabled={!createdGeneratorIds.length || busy} onClick={() => void execute()}>确认并执行抠图 + 生成</button></div>
    <section className="asset-category-results">
      <div className="panel-section-head"><div><span className="panel-label">SAVED CLASSIFICATION RULES</span><h2>分类结果管理</h2><p className="muted">这里展示已确认、会参与后续扫描的菜品分类。修改后点击保存，下一次扫描会直接使用新分类。</p></div><span className="muted">{rulesLoading ? "加载中..." : `${categoryRules.length} 个菜品`}</span></div>
      <div className="asset-category-result-list">{groupedRules.map(group => <details className="asset-category-result" key={group.category} open={group.items.length > 0}><summary><span>{group.category}</span><strong>{group.items.length}</strong></summary><div className="asset-category-result-items">{group.items.length ? group.items.map(rule => <div className="asset-rule-row" key={rule.dishName}><strong title={rule.dishName}>{rule.dishName}</strong><select className="input" value={pendingRuleCategories[rule.dishName] ?? rule.category} onChange={event => setPendingRuleCategories(current => ({ ...current, [rule.dishName]: event.target.value }))}>{CATEGORIES.map(category => <option key={category} value={category}>{category}</option>)}</select><button type="button" className="btn" disabled={ruleSaving !== null || (pendingRuleCategories[rule.dishName] ?? rule.category) === rule.category} onClick={() => void saveManagedRule(rule)}>{ruleSaving === rule.dishName ? "保存中..." : "保存"}</button></div>) : <small className="muted">暂无已确认菜品</small>}</div></details>)}</div>
    </section>
    {plan && <div className="asset-library-plan">
      <strong>扫描结果：已抽取 {plan.selected.length} 个方案 · {plan.reviewItems?.length ?? 0} 个待确认</strong>
      {plan.warnings.map(warning => <small className="source-pending" key={warning}>{warning}</small>)}
      {(plan.reviewItems ?? []).length > 0 && <div className="asset-library-review">
        <div><strong>分类确认页面</strong><small>这里列出素材库中所有无法可靠判断的菜品。选择真实分类并保存后，会写入本地规则；点击上方“按最新规则重新抽取”后，新规则会参与分类数量抽取。</small></div>
        {(plan.reviewItems ?? []).map(item => <div className={`asset-review-item ${activeReviewItem === item.dishName ? "is-active" : ""}`} key={item.dishName} onClick={() => setActiveReviewItem(item.dishName)}>
          <span><strong>{item.dishName}</strong><small>{item.classificationReason} · {item.folderCount && item.folderCount > 1 ? `共 ${item.folderCount} 个同名文件夹 · ` : ""}候选：{item.categoryCandidates?.join("、") || "无"}</small></span>
          <select className="input" value={reviewCategories[item.dishName] ?? item.sourceCategory} onChange={event => { const category = event.target.value; setReviewCategories(current => ({ ...current, [item.dishName]: category })); updateAssetLibraryReviewCategory(item.dishName, category); void saveDraft(); }}>{CATEGORIES.map(category => <option key={category} value={category}>{category}</option>)}</select>
          <button type="button" className="btn" disabled={savingRule !== null} onClick={() => void confirmCategory(item)}>{savingRule === item.dishName ? "保存中..." : "保存规则"}</button>
        </div>)}
      </div>}
      {rulesChanged && (plan.reviewItems ?? []).length === 0 && <small className="source-ready">分类规则已保存。建议重新抽取，使本次方案按最新分类数量重新分配。</small>}
      <div className="asset-plan-list">{plan.selected.map(item => <div className="asset-plan-item" key={item.storedName}><img src={item.imagePreview} alt={item.dishName} /><span><strong>{item.dishName}</strong><small>{item.sourceCategory} · {item.foodType} · 背景：{item.background.name}</small></span></div>)}</div>
    </div>}
  </section>;
}
