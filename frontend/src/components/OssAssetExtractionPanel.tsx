import { useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  approveOssAssetJob,
  cancelOssAssetJob,
  createOssAssetJob,
  fetchOssInventory,
  flagOssAssetForRegeneration,
  getOssAssetJob,
  type OssAssetJob,
  type OssInventory,
} from "../api";

const ACTIVE_STATUSES = new Set<OssAssetJob["status"]>([
  "queued",
  "selecting_materials",
  "downloading",
  "preprocessing",
]);

const STATUS_LABELS: Record<OssAssetJob["status"], string> = {
  queued: "排队中",
  selecting_materials: "抽取不重复菜品",
  downloading: "下载图片",
  preprocessing: "处理图片并适配 9:16",
  awaiting_review: "等待人工审查",
  completed: "已确认",
  error: "失败",
  cancelled: "已取消",
};

function assetUrl(path?: string): string | undefined {
  return path ? `${API_BASE_URL}${path}` : undefined;
}

function normalizeCount(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, Math.min(20, Math.round(parsed))) : 0;
}

export function OssAssetExtractionPanel({ onToast }: { onToast: (message: string) => void }) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [inventory, setInventory] = useState<OssInventory | null>(null);
  const [job, setJob] = useState<OssAssetJob | null>(null);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [busy, setBusy] = useState(false);
  const categories = inventory?.categories ?? [];

  useEffect(() => {
    let cancelled = false;
    setLoadingCategories(true);
    fetchOssInventory().then(next => {
      if (cancelled) return;
      setInventory(next);
      setCounts(current => Object.fromEntries(next.categories.map(item => [item.category, Math.min(current[item.category] ?? 0, item.dish_count)])));
    }).catch(error => {
      if (!cancelled) setInventory({ status: "error", categories: [], error: error instanceof Error ? error.message : "OSS 库存扫描失败" });
    }).finally(() => {
      if (!cancelled) setLoadingCategories(false);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!inventory || (!inventory.refreshing && inventory.status !== "scanning")) return undefined;
    const timer = window.setTimeout(() => { void fetchOssInventory().then(setInventory); }, 2000);
    return () => window.clearTimeout(timer);
  }, [inventory]);

  useEffect(() => {
    if (!job || !ACTIVE_STATUSES.has(job.status)) return undefined;
    const timer = window.setTimeout(() => {
      void getOssAssetJob(job.job_id).then(setJob).catch(error => onToast(error instanceof Error ? error.message : "素材任务状态读取失败"));
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [job, onToast]);

  const selectedCount = useMemo(() => Object.values(counts).reduce((total, count) => total + count, 0), [counts]);
  const isActive = Boolean(job && ACTIVE_STATUSES.has(job.status));
  const canSubmit = selectedCount > 0 && !busy && !isActive && categories.length > 0 && inventory?.status !== "scanning";

  const updateCount = (category: string, value: string, maximum: number) => {
    setCounts(current => ({ ...current, [category]: Math.min(normalizeCount(value), maximum) }));
  };

  const extract = async () => {
    const selections = categories
      .map(item => ({ category: item.category, count: counts[item.category] ?? 0 }))
      .filter(item => item.count > 0);
    if (!selections.length) {
      onToast("请至少填写一个分类数量");
      return;
    }
    setBusy(true);
    try {
      const created = await createOssAssetJob(selections);
      setJob(created);
      onToast("已提交 OSS 素材抽取任务");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "OSS 素材抽取失败");
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!job) return;
    setBusy(true);
    try {
      setJob(await approveOssAssetJob(job.job_id));
      onToast("素材已确认，抽取结果已保留在本次任务中");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "素材确认失败");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!job) return;
    setBusy(true);
    try {
      setJob(await cancelOssAssetJob(job.job_id));
      onToast("素材任务已取消");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "取消素材任务失败");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async (assetId: string) => {
    if (!job) return;
    setBusy(true);
    try {
      setJob(await flagOssAssetForRegeneration(job.job_id, assetId));
      onToast("已标记该素材，后续可重新生成对应片段");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "标记重新生成失败");
    } finally {
      setBusy(false);
    }
  };

  return <section className="step-panel asset-library-batch-panel">
    <div className="panel-section-head">
      <div>
        <span className="panel-label">FIXED OSS ASSET LIBRARY</span>
        <h2>从云端素材库抽取</h2>
        <p className="muted">素材库由服务器固定配置，系统会按分类数量随机抽取不同菜品文件夹中的一张图片。</p>
      </div>
      {job && <span className={`node-status ${job.status === "error" ? "source-pending" : "source-ready"}`}>{STATUS_LABELS[job.status]}</span>}
    </div>

    {loadingCategories && <small className="muted">正在读取固定素材库分类...</small>}
    {inventory?.status === "error" && <div className="source-pending">{inventory.error || "OSS 库存扫描失败"}</div>}
    {inventory?.status === "stale" && <div className="source-pending">正在更新 OSS 库存数量，当前显示上次扫描结果；更新完成后会自动刷新。</div>}
    {!loadingCategories && inventory?.status !== "error" && <>
      <div className="asset-category-grid oss-category-counts">
        {categories.map(item => <label className="field" key={item.category}>
          <span>{item.category}数量（可用 {item.dish_count}）</span>
          <input className="input" type="number" min="0" max={item.dish_count} value={counts[item.category] ?? 0} onChange={event => updateCount(item.category, event.target.value, item.dish_count)} disabled={isActive || busy || inventory?.status === "scanning"} />
        </label>)}
      </div>
      <div className="compose-actions">
        <button type="button" className="btn btn-primary" disabled={!canSubmit} onClick={() => void extract()}>{busy ? "处理中..." : "抽取素材"}</button>
        {isActive && <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void cancel()}>取消任务</button>}
        {job?.status === "awaiting_review" && <button type="button" className="btn" disabled={busy} onClick={() => void approve()}>确认素材</button>}
      </div>
      <small className="muted">已选择 {selectedCount} 张；每个分类内不会重复抽取同一个菜品文件夹。{inventory?.scanned_at ? ` 最近扫描：${new Date(inventory.scanned_at).toLocaleString("zh-CN")}` : "正在首次扫描 OSS..."}</small>
    </>}

    {job?.status === "error" && <div className="source-pending">{job.error || "素材任务失败"}</div>}
    {job && job.assets.length > 0 && <section className="asset-category-results">
      <div className="panel-section-head"><div><span className="panel-label">EXTRACTION RESULT</span><h3>本次抽取结果</h3><p className="muted">图片已下载并完成 EXIF 修正与 9:16 标准化，原始 OSS 文件不会被修改。</p></div></div>
      <div className="asset-plan-list oss-asset-result-list">
        {job.assets.map(asset => {
          const previewPath = asset.status === "ready_for_review" || asset.status === "completed"
            ? asset.normalized_url
            : asset.status === "downloaded" ? asset.source_url : undefined;
          const preview = assetUrl(previewPath);
          return <article className="asset-plan-item" key={asset.asset_id}>
            {preview ? <img src={preview} alt={asset.dish_name} /> : <div className="asset-plan-placeholder">处理中</div>}
            <span><strong>{asset.dish_name}</strong><small>{asset.category} · {asset.status === "ready_for_review" ? "待审查" : asset.status}{asset.normalized_width && asset.normalized_height ? ` · ${asset.normalized_width}×${asset.normalized_height}` : ""}</small>{asset.skip_reason && <small className="source-pending">{asset.skip_reason}</small>}</span>
            {(job.status === "awaiting_review" || job.status === "completed") && <button type="button" className="btn" disabled={busy} onClick={() => void regenerate(asset.asset_id)}>重新生成</button>}
          </article>;
        })}
      </div>
    </section>}
  </section>;
}
