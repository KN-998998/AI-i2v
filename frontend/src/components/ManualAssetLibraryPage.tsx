import { useEffect, useMemo, useRef, useState, type ChangeEvent, type InputHTMLAttributes } from "react";
import { organizeManualAssetLibrary, pickAssetLibraryFolder, scanManualAssetLibrary, scanManualAssetLibraryUpload } from "../api";
import type { ManualAssetReviewScan } from "../model";
import { navigate } from "../router";

type Props = { onToast: (message: string) => void };
type FoodType = "冷食" | "热食";
type Selection = { category: string; foodType: FoodType | "" };
type FolderInputAttributes = InputHTMLAttributes<HTMLInputElement> & { webkitdirectory?: string; directory?: string };

const CATEGORIES = ["寿司", "刺身", "前菜/小菜", "炸物", "主菜", "主食", "汤品", "甜品", "水果", "饮品", "其他"] as const;
const DEFAULT_TARGET_ROOT = "E:\\图片素材库";
const STORAGE_KEY = "restaurant-video.manual-asset-library-review";

function defaultFoodType(category: string): FoodType | "" {
  return ["寿司", "刺身", "前菜/小菜", "甜品", "水果", "饮品"].includes(category) ? "冷食" : "";
}

function loadSavedState(): { scan: ManualAssetReviewScan | null; targetRoot: string; selections: Record<string, Selection> } {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { scan: null, targetRoot: DEFAULT_TARGET_ROOT, selections: {} };
    const value = JSON.parse(raw) as Partial<{ scan: ManualAssetReviewScan; targetRoot: string; selections: Record<string, Selection> }>;
    return { scan: value.scan ?? null, targetRoot: value.targetRoot || DEFAULT_TARGET_ROOT, selections: value.selections ?? {} };
  } catch {
    return { scan: null, targetRoot: DEFAULT_TARGET_ROOT, selections: {} };
  }
}

export function ManualAssetLibraryPage({ onToast }: Props) {
  const [saved] = useState(loadSavedState);
  const [sourceRoot, setSourceRoot] = useState(saved.scan?.assetRoot ?? "");
  const [targetRoot, setTargetRoot] = useState(saved.targetRoot);
  const [scan, setScan] = useState<ManualAssetReviewScan | null>(saved.scan);
  const [selections, setSelections] = useState<Record<string, Selection>>(saved.selections);
  const [folderBusy, setFolderBusy] = useState<"source" | "target" | null>(null);
  const [scanning, setScanning] = useState(false);
  const [organizing, setOrganizing] = useState(false);
  const sourceFolderInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ scan, targetRoot, selections })); } catch { /* Browser storage is optional. */ }
  }, [scan, targetRoot, selections]);

  const confirmedCount = useMemo(() => scan?.items.filter(item => Boolean(selections[item.dishKey]?.category && selections[item.dishKey]?.foodType)).length ?? 0, [scan, selections]);
  const allConfirmed = Boolean(scan?.items.length && confirmedCount === scan.items.length);

  const chooseFolder = async (kind: "source" | "target") => {
    if (kind === "source") {
      sourceFolderInput.current?.click();
      return;
    }
    setFolderBusy(kind);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 30_000);
    try {
      const path = await pickAssetLibraryFolder("选择标准图片素材库目录", controller.signal);
      if (path) setTargetRoot(path);
    } catch (error) {
      onToast(error instanceof DOMException && error.name === "AbortError" ? "系统文件夹选择器未响应，请直接填写目录路径" : error instanceof Error ? error.message : "文件夹选择失败");
    } finally {
      window.clearTimeout(timeout);
      setFolderBusy(null);
    }
  };

  const importSourceFolder = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    setFolderBusy("source");
    try {
      const result = await scanManualAssetLibraryUpload(files);
      setScan(result);
      setSourceRoot(result.assetRoot);
      setSelections({});
      onToast(`已导入并扫描 ${result.items.length} 个菜品，等待人工分类`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "文件夹导入失败");
    } finally {
      setFolderBusy(null);
    }
  };

  const scanSource = async () => {
    if (!sourceRoot.trim()) return onToast("请先选择待整理的原始图片素材目录");
    setScanning(true);
    try {
      const result = await scanManualAssetLibrary(sourceRoot.trim());
      setScan(result);
      setSourceRoot(result.assetRoot);
      setSelections({});
      onToast(`已扫描 ${result.items.length} 个菜品，等待人工分类`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "扫描失败");
    } finally {
      setScanning(false);
    }
  };

  const updateSelection = (dishKey: string, patch: Partial<Selection>) => {
    setSelections(current => {
      const previous = current[dishKey] ?? { category: "", foodType: "" };
      return { ...current, [dishKey]: { ...previous, ...patch } };
    });
  };

  const organize = async () => {
    if (!scan || !allConfirmed) return onToast("请先完成所有菜品的分类和冷/热食标记");
    if (!targetRoot.trim()) return onToast("请先选择标准图片素材库目录");
    setOrganizing(true);
    try {
      const classifications = scan.items.map(item => ({ dishKey: item.dishKey, category: selections[item.dishKey].category, foodType: selections[item.dishKey].foodType as FoodType }));
      const result = await organizeManualAssetLibrary(scan.scanId, targetRoot.trim(), classifications);
      onToast(`已复制 ${result.imageCount} 张图片至标准素材库`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : "整理入库失败");
    } finally {
      setOrganizing(false);
    }
  };

  return <main className="step-main manual-library-page">
    <div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/workflow/assets")}>素材与菜品</button><span>/</span><strong>人工整理工作台</strong></div>
    <div className="step-header"><div><span className="panel-label">MANUAL ASSET LIBRARY</span><h1>人工整理图片素材库</h1><p>扫描只读取文件夹和图片。分类、冷热食全部由人工确认，不调用 AI 或本地规则；原始素材只复制，不移动、不删除。</p></div></div>
    <section className="step-panel manual-library-controls">
      <div className="manual-library-paths">
        <label className="field"><span>原始图片素材目录</span><div className="asset-path-control"><input className="input" value={sourceRoot} onChange={event => setSourceRoot(event.target.value)} placeholder="选择文件夹后自动导入，或手动填写目录路径" /><input ref={sourceFolderInput} className="folder-input-hidden" type="file" multiple {...({ webkitdirectory: "", directory: "" } as FolderInputAttributes)} onChange={event => void importSourceFolder(event)} /><button type="button" className="btn" disabled={folderBusy !== null} onClick={() => void chooseFolder("source")}>{folderBusy === "source" ? "导入中..." : "选择文件夹"}</button></div></label>
        <label className="field"><span>标准素材库目录</span><div className="asset-path-control"><input className="input" value={targetRoot} onChange={event => setTargetRoot(event.target.value)} /><button type="button" className="btn" disabled={folderBusy !== null} onClick={() => void chooseFolder("target")}>{folderBusy === "target" ? "选择中..." : "选择文件夹"}</button></div></label>
      </div>
      <div className="manual-library-actions"><button type="button" className="btn btn-primary" disabled={scanning || organizing} onClick={() => void scanSource()}>{scanning ? "扫描中..." : "扫描待整理菜品"}</button><span className="muted">{scan ? `已确认 ${confirmedCount}/${scan.items.length} 个菜品` : "尚未扫描"}</span><button type="button" className="btn btn-danger" disabled={!allConfirmed || organizing || scanning} onClick={() => void organize()}>{organizing ? "正在复制入库..." : "全部确认并整理入库"}</button></div>
    </section>
    {scan && <section className="manual-review-grid">{scan.items.map((item, index) => {
      const selection = selections[item.dishKey] ?? { category: "", foodType: "" };
      const complete = Boolean(selection.category && selection.foodType);
      return <article className={`manual-review-card ${complete ? "is-complete" : ""}`} key={item.dishKey}>
        <div className="manual-review-head"><span>{String(index + 1).padStart(3, "0")}</span><div><strong>{item.displayName}</strong><small>{item.folderCount > 1 ? `已合并 ${item.folderCount} 个同名/简繁体文件夹` : "1 个来源文件夹"} · {item.imageCount} 张图片</small></div><b>{complete ? "已确认" : "待确认"}</b></div>
        <div className="manual-review-previews">{item.previewUrls.map((url, previewIndex) => <img key={url} src={url} alt={`${item.dishName} ${previewIndex + 1}`} loading="lazy" />)}{item.imageCount > item.previewUrls.length && <span>+{item.imageCount - item.previewUrls.length}</span>}</div>
        <div className="manual-review-fields"><label className="field"><span>菜品分类</span><select className="input" value={selection.category} onChange={event => { const category = event.target.value; updateSelection(item.dishKey, { category, foodType: defaultFoodType(category) }); }}><option value="">选择分类</option>{CATEGORIES.map(category => <option value={category} key={category}>{category}</option>)}</select></label><label className="field"><span>冷热属性</span><select className="input" value={selection.foodType} onChange={event => updateSelection(item.dishKey, { foodType: event.target.value as FoodType })} disabled={!selection.category}><option value="">选择冷/热食</option><option value="冷食">冷食</option><option value="热食">热食</option></select></label></div>
      </article>;
    })}</section>}
  </main>;
}
