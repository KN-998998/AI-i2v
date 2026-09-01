import { useEffect, useState } from "react";
import { createAssetLibraryPlan, fetchAssetLibraryClassifications, fetchAssetLibraryRules, pickAssetLibraryFolder, saveAssetLibraryRule, type AssetLibraryRule } from "../api";
import type { AssetLibraryClassificationItem, AssetLibraryPlan, AssetLibraryReviewItem } from "../model";
import { useWorkflowStore } from "../workflowStore";

const CATEGORIES = ["寿司", "刺身", "前菜/小菜", "炸物", "主菜", "主食", "汤品", "甜品", "水果", "饮品", "其他"] as const;
const FOOD_TYPES = ["冷食", "热食"] as const;
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

function defaultFoodType(category: string): "冷食" | "热食" | "" {
  return ["甜品", "水果"].includes(category) ? "冷食" : "";
}

export function AssetLibraryBatchPanel({ onToast }: { onToast: (message: string) => void }) {
  const draftId = useWorkflowStore(state => state.draftId);
  const saveDraft = useWorkflowStore(state => state.saveDraft);
  const savedPlan = useWorkflowStore(state => state.assetLibraryPlan);
  const setAssetLibraryPlan = useWorkflowStore(state => state.setAssetLibraryPlan);
  const updateAssetLibraryReviewClassification = useWorkflowStore(state => state.updateAssetLibraryReviewClassification);
  const createBatchWorkflows = useWorkflowStore(state => state.createBatchWorkflows);
  const runBatchGeneration = useWorkflowStore(state => state.runBatchGeneration);
  const [assetRoot, setAssetRoot] = useState(() => rememberedPath(ASSET_ROOT_STORAGE_KEY));
  const [backgroundRoot, setBackgroundRoot] = useState(() => rememberedPath(BACKGROUND_ROOT_STORAGE_KEY));
  const [counts, setCounts] = useState<Record<string, number>>(() => Object.fromEntries(CATEGORIES.map(category => [category, 0])));
  const [createdGeneratorIds, setCreatedGeneratorIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [folderBusy, setFolderBusy] = useState<"asset" | "background" | null>(null);
  const [reviewCategories, setReviewCategories] = useState<Record<string, string>>({});
  const [reviewFoodTypes, setReviewFoodTypes] = useState<Record<string, "冷食" | "热食" | "">>({});
  const [activeReviewItem, setActiveReviewItem] = useState<string | null>(null);
  const [savingRule, setSavingRule] = useState<string | null>(null);
  const [rulesChanged, setRulesChanged] = useState(false);
  const [categoryRules, setCategoryRules] = useState<AssetLibraryRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [ruleSaving, setRuleSaving] = useState<string | null>(null);
  const [pendingRuleCategories, setPendingRuleCategories] = useState<Record<string, string>>({});
  const [pendingRuleFoodTypes, setPendingRuleFoodTypes] = useState<Record<string, "冷食" | "热食" | "">>({});

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
        setPendingRuleFoodTypes(Object.fromEntries(rules.map(rule => [rule.dishName, rule.foodType ?? defaultFoodType(rule.category)])));
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
    setReviewFoodTypes(Object.fromEntries((plan.reviewItems ?? []).map(item => [item.dishName, item.foodType ?? defaultFoodType(item.suggestedCategory ?? item.sourceCategory)])));
    setPendingRuleCategories(current => ({ ...current, ...Object.fromEntries((plan.classificationResults ?? []).map(item => [item.dishName, item.category])) }));
    setPendingRuleFoodTypes(current => ({ ...current, ...Object.fromEntries((plan.classificationResults ?? []).map(item => [item.dishName, item.foodType ?? defaultFoodType(item.category)])) }));
    if (!plan.classificationResults?.length && plan.assetRoot) {
      let active = true;
      fetchAssetLibraryClassifications(plan.assetRoot).then(result => {
        if (!active || !result.classificationResults?.length) return;
        setAssetLibraryPlan({ ...plan, ...result });
        void saveDraft();
      }).catch(() => {
        // Keep the persisted plan visible if the original asset folder is unavailable.
      });
      return () => { active = false; };
    }
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
      setReviewFoodTypes(Object.fromEntries((next.reviewItems ?? []).map(item => [item.dishName, item.foodType ?? defaultFoodType(item.suggestedCategory ?? item.sourceCategory)])));
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
    const foodType = reviewFoodTypes[item.dishName] || defaultFoodType(category);
    if (!foodType) {
      onToast("请先选择冷食或热食，再保存分类规则");
      return;
    }
    setSavingRule(item.dishName);
    try {
      await saveAssetLibraryRule(item.dishName, category, foodType);
      const nextPlan = plan ? {
        ...plan,
        selected: plan.selected.map(selected => selected.dishName === item.dishName
          ? { ...selected, sourceCategory: category, suggestedCategory: category, foodType, reviewRequired: false, classificationReason: "已使用人工确认规则", categoryCandidates: [category] }
          : selected),
        reviewItems: (plan.reviewItems ?? []).filter(review => review.dishName !== item.dishName),
        classificationResults: (plan.classificationResults ?? []).map(result => result.dishName === item.dishName
          ? { ...result, category, sourceCategory: category, suggestedCategory: category, foodType, reviewRequired: false, classificationSource: "人工规则" as const, classificationReason: "已使用人工确认规则", categoryCandidates: [category] }
          : result),
      } : null;
      setAssetLibraryPlan(nextPlan);
      setCategoryRules(current => current.some(rule => rule.dishName === item.dishName)
        ? current.map(rule => rule.dishName === item.dishName ? { ...rule, category, foodType } : rule)
        : [...current, { dishName: item.dishName, category, foodType }]);
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

  const saveManagedRule = async (rule: AssetLibraryClassificationItem | AssetLibraryRule) => {
    const category = pendingRuleCategories[rule.dishName] ?? rule.category;
    const foodType = pendingRuleFoodTypes[rule.dishName] || defaultFoodType(category);
    if (category === rule.category && foodType === (rule.foodType ?? defaultFoodType(rule.category))) return;
    if (!foodType) {
      onToast("请先选择冷食或热食，再保存分类规则");
      return;
    }
    setRuleSaving(rule.dishName);
    try {
      const saved = await saveAssetLibraryRule(rule.dishName, category, foodType);
      setCategoryRules(current => current.map(item => item.dishName === rule.dishName ? saved : item));
      if (plan?.classificationResults?.some(item => item.dishName === rule.dishName)) {
        setAssetLibraryPlan({
          ...plan,
          classificationResults: plan.classificationResults.map(item => item.dishName === rule.dishName
            ? { ...item, category, sourceCategory: category, suggestedCategory: category, foodType, reviewRequired: false, classificationSource: "人工规则" as const, classificationReason: "已使用人工确认规则", categoryCandidates: [category] }
            : item),
        });
        await saveDraft();
      }
      setCategoryRules(current => current.some(item => item.dishName === rule.dishName) ? current : [...current, saved]);
      setPendingRuleCategories(current => ({ ...current, [rule.dishName]: category }));
      setPendingRuleFoodTypes(current => ({ ...current, [rule.dishName]: foodType }));
      onToast(`已将“${rule.dishName}”调整为${category}`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "分类规则保存失败");
    } finally {
      setRuleSaving(null);
    }
  };

  const scannedResults = plan?.classificationResults ?? [];
  const scannedNames = new Set(scannedResults.map(item => item.dishName));
  const managedItems: Array<AssetLibraryClassificationItem | AssetLibraryRule> = [
    ...scannedResults,
    ...categoryRules.filter(rule => !scannedNames.has(rule.dishName)),
  ];
  const groupedRules = CATEGORIES.map(category => ({
    category,
    items: managedItems.filter(item => (pendingRuleCategories[item.dishName] ?? item.category) === category),
  }));

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
      <div className="panel-section-head"><div><span className="panel-label">FULL CLASSIFICATION REVIEW</span><h2>分类结果管理</h2><p className="muted">这里展示最近一次扫描发现的全部去重菜品，包括本地规则自动确认项和待确认项。请逐项检查分类与冷热属性，修改后点击保存即可记入人工规则。</p></div><span className="muted">{rulesLoading ? "加载中..." : `${managedItems.length} 个菜品`}</span></div>
      <div className="asset-category-result-list">{groupedRules.map(group => <details className="asset-category-result" key={group.category} open={group.items.length > 0}><summary><span>{group.category}</span><strong>{group.items.length}</strong></summary><div className="asset-category-result-items">{group.items.length ? group.items.map(rule => { const category = pendingRuleCategories[rule.dishName] ?? rule.category; const foodType = pendingRuleFoodTypes[rule.dishName] || defaultFoodType(category); const originalFoodType = rule.foodType ?? defaultFoodType(rule.category); const unchanged = category === rule.category && foodType === originalFoodType; const classificationSource = "classificationSource" in rule ? rule.classificationSource : "人工规则"; const reviewRequired = "reviewRequired" in rule ? rule.reviewRequired : !foodType; const reason = "classificationReason" in rule ? rule.classificationReason : "已使用人工确认规则"; return <div className={`asset-rule-row ${reviewRequired ? "is-review" : ""}`} key={rule.dishName}><div className="asset-rule-name"><strong title={rule.dishName}>{rule.dishName}</strong><small>{classificationSource} · {reviewRequired ? "待确认" : "已确认"}{reason ? ` · ${reason}` : ""}</small></div><select className="input" value={category} onChange={event => { const nextCategory = event.target.value; setPendingRuleCategories(current => ({ ...current, [rule.dishName]: nextCategory })); setPendingRuleFoodTypes(current => ({ ...current, [rule.dishName]: defaultFoodType(nextCategory) })); }}>{CATEGORIES.map(categoryOption => <option key={categoryOption} value={categoryOption}>{categoryOption}</option>)}</select><select className="input" value={foodType} onChange={event => setPendingRuleFoodTypes(current => ({ ...current, [rule.dishName]: event.target.value as "冷食" | "热食" | "" }))}><option value="">选择冷/热食</option>{FOOD_TYPES.map(type => <option key={type} value={type}>{type}</option>)}</select><button type="button" className="btn" disabled={ruleSaving !== null || unchanged || !foodType} onClick={() => void saveManagedRule(rule)}>{ruleSaving === rule.dishName ? "保存中..." : "保存"}</button></div>; }) : <small className="muted">暂无菜品</small>}</div></details>)}</div>
    </section>
    {plan && <div className="asset-library-plan">
      <strong>扫描结果：已抽取 {plan.selected.length} 个方案 · {plan.reviewItems?.length ?? 0} 个待确认</strong>
      {plan.warnings.map(warning => <small className="source-pending" key={warning}>{warning}</small>)}
      {(plan.reviewItems ?? []).length > 0 && <div className="asset-library-review">
        <div><strong>分类确认页面</strong><small>这里列出素材库中所有无法可靠判断的菜品。选择真实分类并保存后，会写入本地规则；点击上方“按最新规则重新抽取”后，新规则会参与分类数量抽取。</small></div>
        {(plan.reviewItems ?? []).map(item => <div className={`asset-review-item ${activeReviewItem === item.dishName ? "is-active" : ""}`} key={item.dishName} onClick={() => setActiveReviewItem(item.dishName)}>
          <span><strong>{item.displayName ?? item.dishName}</strong><small>{item.classificationReason} · {item.folderCount && item.folderCount > 1 ? `已归并 ${item.folderCount} 个同名/简繁体文件夹 · ` : ""}候选：{item.categoryCandidates?.join("、") || "无"}</small></span>
          <select className="input" value={reviewCategories[item.dishName] ?? item.sourceCategory} onChange={event => { const category = event.target.value; const foodType = defaultFoodType(category); setReviewCategories(current => ({ ...current, [item.dishName]: category })); setReviewFoodTypes(current => ({ ...current, [item.dishName]: foodType })); updateAssetLibraryReviewClassification(item.dishName, category, foodType || null); void saveDraft(); }}>{CATEGORIES.map(category => <option key={category} value={category}>{category}</option>)}</select>
          <select className="input" value={reviewFoodTypes[item.dishName] ?? ""} onChange={event => { const foodType = event.target.value as "冷食" | "热食" | ""; setReviewFoodTypes(current => ({ ...current, [item.dishName]: foodType })); updateAssetLibraryReviewClassification(item.dishName, reviewCategories[item.dishName] ?? item.sourceCategory, foodType || null); void saveDraft(); }} disabled={["甜品", "水果"].includes(reviewCategories[item.dishName] ?? item.sourceCategory)}><option value="">选择冷/热食</option>{FOOD_TYPES.map(type => <option key={type} value={type}>{type}</option>)}</select>
          <button type="button" className="btn" disabled={savingRule !== null || !(reviewFoodTypes[item.dishName] || defaultFoodType(reviewCategories[item.dishName] ?? item.sourceCategory))} onClick={() => void confirmCategory(item)}>{savingRule === item.dishName ? "保存中..." : "保存规则"}</button>
        </div>)}
      </div>}
      {rulesChanged && (plan.reviewItems ?? []).length === 0 && <small className="source-ready">分类规则已保存。建议重新抽取，使本次方案按最新分类数量重新分配。</small>}
      <div className="asset-plan-list">{plan.selected.map(item => <div className="asset-plan-item" key={item.storedName}><img src={item.imagePreview} alt={item.displayName ?? item.dishName} /><span><strong>{item.displayName ?? item.dishName}</strong><small>{item.sourceCategory} · {item.foodType} · 背景：{item.background.name}{item.sourceFolderCount && item.sourceFolderCount > 1 ? ` · 已合并 ${item.sourceFolderCount} 个来源文件夹` : ""}</small></span></div>)}</div>
    </div>}
  </section>;
}
