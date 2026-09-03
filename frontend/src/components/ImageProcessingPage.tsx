import { useEffect, useMemo, useState } from "react";
import { fetchBackgroundTemplates, uploadBackgroundTemplate } from "../api";
import { navigate } from "../router";
import { useWorkflowStore } from "../workflowStore";
import { ImageProcessControlFields } from "./ImageProcessControls";
import { Inspector } from "./Inspector";

export function ImageProcessingPage({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const draftId = useWorkflowStore(state => state.draftId);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const processImageNode = useWorkflowStore(state => state.processImageNode);
  const addNode = useWorkflowStore(state => state.addNode);
  const processingNodes = nodes.filter(item => item.data.kind === "image_process");
  const inputNodes = nodes.filter(item => item.data.kind === "input");
  const node = processingNodes.find(item => item.id === selectedNodeId) ?? processingNodes[0];
  const sourceNode = inputNodes[0];
  const preserveOriginal = Boolean(node && node.data.visualSubjectType && node.data.visualSubjectType !== "菜品主体");
  const [templates, setTemplates] = useState<Awaited<ReturnType<typeof fetchBackgroundTemplates>>>([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);

  const activeTemplate = useMemo(() => templates.find(item => item.id === node?.data.backgroundTemplateId), [node?.data.backgroundTemplateId, templates]);
  useEffect(() => { if (node) setSelection(node.id); }, [node, setSelection]);
  useEffect(() => { fetchBackgroundTemplates().then(setTemplates).catch(error => onToast(error instanceof Error ? error.message : "背景模板加载失败")); }, [onToast]);

  if (!node) return <main className="step-main"><div className="step-header"><div><span className="panel-label">WORKFLOW STEP 2</span><h1>图片处理</h1><p>抠图、背景模板和首帧合成。</p></div></div><section className="step-panel empty-panel"><h2>尚未创建图片处理节点</h2><p>新增节点后，将其连接在“素材与菜品”和“提示词装配”之间。</p><button type="button" className="btn btn-primary" onClick={() => addNode("image_process")}>新增图片处理节点</button></section></main>;

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
    if (!sourceNode?.data.imagePreview) return onToast("请先在素材与菜品页面上传菜品图片");
    setBusy(true);
    try {
      const result = await processImageNode(node.id);
      onToast(result.processingMode === "preserve_original" ? "已保留原图并跳过抠图，可进入提示词装配" : "已完成抠图和背景合成，可进入提示词装配");
    } catch (error) {
      onToast(error instanceof Error ? error.message : "图片处理失败");
    } finally {
      setBusy(false);
    }
  };

  return <main className="step-main">
    <div className="step-breadcrumb"><button type="button" className="link-button" onClick={() => navigate("/canvas-mvp")}>流程画布</button><span>/</span><strong>图片处理</strong></div>
    <div className="step-header"><div><span className="panel-label">WORKFLOW STEP 2</span><h1>图片处理</h1><p>{preserveOriginal ? "当前素材包含人物，保留原图并让 Kling 生成动作片段。" : "调用腾讯云 GoodsMatting 抠出菜品，再与本地背景模板合成为 Kling 视频首帧。"}</p></div></div>
    <div className="step-guide"><span>操作提示</span><p>{preserveOriginal ? "手部或人物素材无需选背景，点击“保留原图并继续”即可。" : "先选一个背景模板，再点击“开始抠图并合成”；原图会始终保留，处理图可重复生成。"}</p></div>
    <div className="step-page-grid"><div className="step-page-main">
      <section className="step-panel"><div className="panel-section-head"><div><span className="panel-label">IMAGE PROCESSING NODE</span><h2>{node.data.title}</h2><p className="muted">原图不会被覆盖；{preserveOriginal ? "人物素材会保留原图，不使用背景模板。" : "处理后首帧单独保存，并优先用于后续视频生成。"}</p></div><div className="panel-actions"><select className="input compact-select" value={node.id} onChange={event => setSelection(event.target.value)}>{processingNodes.map(item => <option key={item.id} value={item.id}>{item.data.title}</option>)}</select><button type="button" className="btn btn-primary" disabled={busy} onClick={process}>{busy ? "正在处理..." : preserveOriginal ? "保留原图并继续" : node.data.processedImagePreview ? "重新处理图片" : "开始抠图并合成"}</button></div></div>
        {preserveOriginal && <div className="source-ready">画面主体：{node.data.visualSubjectType}。此节点不会调用 GoodsMatting，也不会把背景模板合成到原图上。</div>}
        <div className="image-process-grid"><div className="image-process-stage"><span>原始菜品图</span><div className="image-process-preview">{sourceNode?.data.imagePreview ? <img src={sourceNode.data.imagePreview} alt="原始菜品" /> : <em>请先上传菜品图片</em>}</div><small>{sourceNode?.data.dishName || "未选择菜品"}</small></div><div className="image-process-stage"><span>{preserveOriginal ? "后续生成使用的原图" : "处理后首帧"}</span><div className="image-process-preview">{node.data.processedImagePreview ? <img src={node.data.processedImagePreview} alt="处理后首帧" /> : <em>{preserveOriginal ? "点击“保留原图并继续”" : "选择背景并执行处理"}</em>}</div><small>{node.data.processedImageName || "尚未生成"}</small></div></div>
      </section>
      <section className={`step-panel ${preserveOriginal ? "is-disabled-panel" : ""}`}><div className="panel-section-head"><div><span className="panel-label">BACKGROUND TEMPLATE</span><h2>背景模板</h2><p className="muted">{preserveOriginal ? "当前主体类型为人物画面，背景模板不会参与处理。" : "优先使用真实门店桌面或吧台，处理时自动裁为 9:16、虚化并压暗。"}</p></div><label className="btn upload-button">{uploading ? "上传中..." : "上传背景"}<input type="file" accept="image/*" disabled={uploading || preserveOriginal} onChange={event => upload(event.target.files?.[0])} /></label></div><div className="background-template-grid">{templates.map(template => <button key={template.id} type="button" disabled={preserveOriginal} className={`background-template ${template.id === activeTemplate?.id ? "selected" : ""}`} onClick={() => selectTemplate(template.id)}><img src={template.url} alt={template.name} /><span>{template.name}</span></button>)}{templates.length === 0 && <div className="empty-state compact">还没有背景模板。可上传已筛选的门店、吧台或桌面图片。</div>}</div></section>
      <section className="step-panel"><div className="panel-section-head"><div><span className="panel-label">COMPOSITE CONTROLS</span><h2>主体与背景</h2></div></div><div className="field-grid image-process-controls"><ImageProcessControlFields data={node.data} update={update} /></div>{node.data.processedImageAnalysis && <div className="media-analysis"><div><strong>处理图质量 {node.data.processedImageAnalysis.qualityScore}/100</strong></div>{node.data.processedImageAnalysis.qualityWarnings.map(item => <small key={item}>提示：{item}</small>)}</div>}</section>
      <div className="step-context"><button type="button" className="btn btn-primary" disabled={!node.data.processedImagePreview} onClick={() => navigate("/workflow/prompts")}>进入提示词装配</button><span className="muted">{node.data.processedImagePreview ? "处理完成，可进入下一步" : "下一步条件：完成图片处理"} · 草稿：{draftId} · 状态：{node.data.status}</span></div>
    </div><Inspector onToast={onToast} /></div>
  </main>;
}
