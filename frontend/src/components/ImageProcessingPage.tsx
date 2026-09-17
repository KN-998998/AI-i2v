import { useEffect, useMemo, useRef, useState } from "react";
import { fetchBackgroundTemplates, uploadBackgroundTemplate } from "../api";
import { navigate } from "../router";
import { requestTutorial } from "../tutorial";
import { useWorkflowStore } from "../workflowStore";
import { ImageProcessControlFields } from "./ImageProcessControls";
import { Inspector } from "./Inspector";
import { StepHeading } from "./ui";

function imageProcessingErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "图片处理失败";
  if (message.includes("ImageTooLarge") || message.toLowerCase().includes("size exceeded limit")) {
    return "原图仍超过抠图接口限制，请换用更小的图片后重试";
  }
  return message;
}

export function ImageProcessingPage({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const edges = useWorkflowStore(state => state.edges);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const processImageNode = useWorkflowStore(state => state.processImageNode);
  const recomposeImageNode = useWorkflowStore(state => state.recomposeImageNode);
  const addNode = useWorkflowStore(state => state.addNode);
  const processingNodes = nodes.filter(item => item.data.kind === "image_process");
  const inputNodes = nodes.filter(item => item.data.kind === "input");
  const node = processingNodes.find(item => item.id === selectedNodeId) ?? processingNodes[0];
  // Each processing node belongs to the input node directly connected to it.
  // Falling back to the first input keeps legacy drafts without an edge usable.
  const sourceNode = inputNodes.find(input => edges.some(edge => edge.source === input.id && edge.target === node?.id)) ?? inputNodes[0];
  const sourcePreview = sourceNode?.data.imagePreview ?? node?.data.imagePreview;
  const preserveOriginal = Boolean(node && node.data.visualSubjectType && node.data.visualSubjectType !== "菜品主体");
  const [templates, setTemplates] = useState<Awaited<ReturnType<typeof fetchBackgroundTemplates>>>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [recomposing, setRecomposing] = useState(false);
  const [showSource, setShowSource] = useState(false);
  // 抠图结果留在服务器上以后，背景 / 参数的改动只需重新合成（约 1 秒），不再调抠图接口。
  const canRecompose = Boolean(node && !preserveOriginal && node.data.processedCutoutName && node.data.processedImagePreview);
  const paramKey = node ? [node.data.backgroundTemplateId ?? "", node.data.backgroundBlur ?? "", node.data.backgroundBrightness ?? "", node.data.subjectScale ?? "", node.data.subjectX ?? "", node.data.subjectY ?? ""].join("|") : "";
  const appliedKey = useRef(paramKey);
  const nodeId = node?.id;
  useEffect(() => { appliedKey.current = paramKey; /* 切换菜品时以它当前的参数为基准，不触发合成 */ }, [nodeId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!nodeId || !canRecompose || busy || paramKey === appliedKey.current) return;
    // 拖动滑块时 onChange 连续触发；每次都重置计时，松手 700ms 后只合成一次。
    const timer = window.setTimeout(async () => {
      appliedKey.current = paramKey;
      setRecomposing(true);
      try {
        await recomposeImageNode(nodeId);
      } catch (error) {
        onToast(error instanceof Error ? error.message : "重新合成失败");
      } finally {
        setRecomposing(false);
      }
    }, 700);
    return () => window.clearTimeout(timer);
  }, [paramKey, canRecompose, busy, nodeId, recomposeImageNode, onToast]);

  const activeTemplate = useMemo(() => templates.find(item => item.id === node?.data.backgroundTemplateId), [node?.data.backgroundTemplateId, templates]);
  const sourceFor = (processNodeId: string) => {
    const processNode = processingNodes.find(item => item.id === processNodeId);
    return inputNodes.find(input => edges.some(edge => edge.source === input.id && edge.target === processNode?.id))
      ?? inputNodes.find(input => input.data.imagePreview)
      ?? inputNodes[0];
  };
  useEffect(() => { if (node) setSelection(node.id); }, [node, setSelection]);
  useEffect(() => { fetchBackgroundTemplates().then(setTemplates).catch(error => onToast(error instanceof Error ? error.message : "背景模板加载失败")); }, [onToast]);

  if (!node) return <main className="step-main"><div className="step-header"><StepHeading route="/workflow/image-processing" /></div><section className="step-panel empty-panel"><h2>尚未创建图片处理节点</h2><p>新增节点后，将其连接在“素材与菜品”和“提示词装配”之间。</p><button type="button" className="btn btn-primary" onClick={() => addNode("image_process")}>新增图片处理节点</button></section></main>;

  const update = (patch: Partial<typeof node.data>) => updateNodeData(node.id, patch);
  const selectTemplate = (id: string) => {
    if (preserveOriginal) return;
    const template = templates.find(item => item.id === id);
    update({ backgroundTemplateId: template?.id, backgroundTemplateName: template?.name, backgroundPreview: template?.url, status: node.data.processedImagePreview ? "已处理" : "待处理" });
  };
  const upload = async (file: File | undefined) => {
    if (!file || preserveOriginal) return;
    setUploading(true);
    try {
      const template = await uploadBackgroundTemplate(file);
      setTemplates(current => [template, ...current]);
      update({ backgroundTemplateId: template.id, backgroundTemplateName: template.name, backgroundPreview: template.url, status: node.data.processedImagePreview ? "已处理" : "待处理" });
      onToast("背景模板已上传并选中");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "背景模板上传失败");
    } finally {
      setUploading(false);
    }
  };
  const process = async () => {
    if (!sourcePreview) return onToast("请先在素材与菜品页面上传菜品图片");
    setBusy(true);
    try {
      const result = await processImageNode(node.id);
      onToast(result.processingMode === "preserve_original" ? "已保留原图并跳过抠图，可进入提示词装配" : "已完成抠图和背景合成，可进入提示词装配");
    } catch (error) {
      onToast(imageProcessingErrorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const dishName = sourceNode?.data.dishName || node.data.dishName || "未选择菜品";
  const frameImage = showSource || !node.data.processedImagePreview ? sourcePreview : node.data.processedImagePreview;
  const liveState = busy ? { className: "is-busy", text: preserveOriginal ? "处理中…" : "抠图中…" }
    : recomposing ? { className: "is-busy", text: "更新预览…" }
    : canRecompose ? { className: "is-live", text: "松手后约 1 秒自动更新" }
    : preserveOriginal ? { className: "", text: "人物素材保留原图" }
    : { className: "", text: "先执行一次抠图" };
  const primaryLabel = busy ? "正在处理..." : preserveOriginal ? "保留原图并继续" : node.data.processedCutoutName ? "重新抠图" : "开始抠图并合成";
  const doneCount = processingNodes.filter(item => item.data.processedImagePreview).length;

  return <main className="step-main">
    <div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>流程画布</button><span>/</span><strong>图片处理</strong></div>
    <div className="step-header"><StepHeading route="/workflow/image-processing" /><button type="button" className="btn step-tutorial-button" onClick={() => requestTutorial("/workflow/image-processing")}>查看本步骤教学</button></div>
    <div className="step-guide"><span>操作提示</span><p>{preserveOriginal ? "手部或人物素材无需选背景，点击“保留原图并继续”即可。" : "先选背景，点“开始抠图并合成”做一次抠图；之后换背景、拖滑块都会自动更新左侧预览，原图始终保留。"}</p></div>
    <div className="step-page-grid"><div className="step-page-main">
      <section className="step-panel image-process-node-overview"><div className="panel-section-head"><div><h2>待处理菜品 · {processingNodes.length} 道</h2><p className="muted">点一张卡片切换当前要处理的菜。</p></div><span className="image-process-queue-count">{doneCount}/{processingNodes.length} 已完成</span></div><div className="image-process-node-grid">{processingNodes.map((item, index) => { const source = sourceFor(item.id); const preview = source?.data.imagePreview ?? item.data.imagePreview; const selected = item.id === node.id; const preserve = item.data.visualSubjectType && item.data.visualSubjectType !== "菜品主体"; return <button type="button" className={"image-process-node-card" + (selected ? " selected" : "")} key={item.id} onClick={() => setSelection(item.id)}><div className="image-process-node-card-head"><span className="node-record-index">{String(index + 1).padStart(2, "0")}</span><strong>{item.data.title || source?.data.dishName || "未命名菜品"}</strong><span className="node-status">{item.data.status}</span></div><div className="image-process-node-thumb">{preview ? <img src={preview} alt={(source?.data.dishName || item.data.title || "菜品") + "原始素材"} /> : <em>未上传原图</em>}</div><div className="image-process-node-meta"><span>背景：{item.data.backgroundTemplateName || (preserve ? "不使用" : "未选择")}</span><span>{item.data.processedImagePreview ? "首帧已生成" : "首帧未生成"}</span></div></button>; })}</div></section>

      <section className="step-panel ip-studio">
        <div className="ip-preview">
          <div className="ip-preview-head"><h2>{preserveOriginal ? "后续生成使用的原图" : "首帧预览"}</h2><span className={`ip-live ${liveState.className}`}>{liveState.text}</span></div>
          <div className={`ip-preview-frame ${recomposing ? "is-updating" : ""}`}>
            {frameImage ? <img src={frameImage} alt={showSource ? "原始菜品" : "处理后首帧"} /> : <em>请先在“素材与菜品”上传这道菜的图片</em>}
            {frameImage && node.data.processedImagePreview && <span className="ip-frame-tag">{showSource ? "原图" : "9:16 首帧"}</span>}
            {recomposing && <span className="ip-frame-veil">更新中…</span>}
          </div>
          <div className="ip-preview-foot">
            {sourcePreview && <img src={sourcePreview} alt="原图缩略" />}
            <span>原图：{dishName} · 不会被覆盖</span>
            {node.data.processedImagePreview && sourcePreview && <button type="button" className="btn" onClick={() => setShowSource(value => !value)}>{showSource ? "看处理结果" : "对比原图"}</button>}
          </div>
          <div className="ip-preview-actions">
            <button type="button" className={`btn ${node.data.processedCutoutName ? "" : "btn-primary"}`} disabled={busy || recomposing} onClick={process}>{primaryLabel}</button>
            {node.data.processedImageAnalysis && <span className="muted">处理图质量 {node.data.processedImageAnalysis.qualityScore}/100 · 状态：{node.data.status}</span>}
          </div>
          {node.data.processedImageAnalysis?.qualityWarnings.length ? <div className="media-analysis">{node.data.processedImageAnalysis.qualityWarnings.map(item => <small key={item}>提示：{item}</small>)}</div> : null}
        </div>
        <div className="ip-controls">
          {preserveOriginal ? <div className="source-ready">画面主体：{node.data.visualSubjectType}。这类素材保留原图直接生成动作片段，不抠图、不换背景；点左侧“保留原图并继续”即可。</div> : <>
            <h2>背景</h2><p className="ip-sub">优先用真实门店桌面或吧台；会自动裁成 9:16。</p>
            <div className="background-template-grid ip-bg-grid">{templates.map(template => <button key={template.id} type="button" className={`background-template ${template.id === activeTemplate?.id ? "selected" : ""}`} onClick={() => selectTemplate(template.id)}><img src={template.url} alt={template.name} /><span>{template.name}</span></button>)}{templates.length === 0 && <div className="empty-state compact">还没有背景模板。可上传已筛选的门店、吧台或桌面图片。</div>}</div>
            <div className="ip-bg-actions"><span>已选：{activeTemplate?.name ?? node.data.backgroundTemplateName ?? "未选择"}</span><label className="btn upload-button">{uploading ? "上传中..." : "上传背景"}<input type="file" accept="image/*" disabled={uploading} onChange={event => upload(event.target.files?.[0])} /></label></div>
            <div className="ip-divider" />
            <h2>菜品与背景</h2><p className="ip-sub">{canRecompose ? "拖动滑块，松手后左侧预览会跟着变；不用再点“重新处理”。" : "先做一次抠图，之后这里的调整会自动更新预览。"}</p>
            <div className="ip-params"><ImageProcessControlFields data={node.data} update={update} /></div>
          </>}
        </div>
      </section>

      <div className="step-context"><button type="button" className="btn btn-primary ip-next" disabled={!node.data.processedImagePreview} onClick={() => navigate("/workflow/prompts")}>下一步：提示词装配</button><span className="muted">{node.data.processedImagePreview ? "这张首帧会用于后面的视频生成" : "先完成这道菜的图片处理"}</span></div>
    </div><Inspector onToast={onToast} /></div>
  </main>;
}
