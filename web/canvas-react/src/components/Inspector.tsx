import { useEffect } from "react";
import { nodeCatalog, promptL0Options, type NodeKind, type WorkflowData, type WorkflowNode } from "../model";
import { uploadDraftFile } from "../api";
import { useWorkflowStore } from "../workflowStore";
import { Field, formatNodeValue, SectionTitle, Select, Tag } from "./ui";

function BasicFields({ node }: { node: WorkflowNode }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const update = (patch: Partial<WorkflowData>) => updateNodeData(node.id, patch);
  return <>
    <SectionTitle>基本信息</SectionTitle>
    <Field label="节点类型"><select className="input" value={node.data.kind} onChange={event => { const kind = event.target.value as NodeKind; update({ kind, title: node.data.title === nodeCatalog[node.data.kind].title ? nodeCatalog[kind].title : node.data.title, description: nodeCatalog[kind].description, status: nodeCatalog[kind].status }); }}><option value="input">素材输入</option><option value="prompt">槽位化提示词</option><option value="generator">3 秒视频片段</option><option value="output">成片合成</option><option value="sound">声音与文字</option><option value="custom">自定义处理</option></select></Field>
    <Field label="节点名称"><input className="input" value={node.data.title} onChange={event => update({ title: event.target.value })} /></Field>
    <Field label="节点说明"><textarea className="input textarea" value={node.data.description} onChange={event => update({ description: event.target.value })} /></Field>
  </>;
}

function AssetFields({ node, onToast }: { node: WorkflowNode; onToast: (message: string) => void }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const draftId = useWorkflowStore(state => state.draftId);
  const data = node.data;
  useEffect(() => () => {
    if (data.imagePreview?.startsWith("blob:")) URL.revokeObjectURL(data.imagePreview);
  }, [data.imagePreview]);
  return <>
    <SectionTitle>素材与菜品</SectionTitle>
    <Field label="当前菜品"><input className="input" value={formatNodeValue(data.dishName, "")} onChange={event => updateNodeData(node.id, { dishName: event.target.value })} /></Field>
    <Field label="菜品类型"><Select value={formatNodeValue(data.foodType, "热食")} options={["冷食", "热食"]} onChange={value => updateNodeData(node.id, { foodType: value })} /></Field>
    <Field label="素材模式"><Select value={formatNodeValue(data.assetMode, "单图模式")} options={["单图模式", "首尾帧模式"]} onChange={value => updateNodeData(node.id, { assetMode: value })} /></Field>
    <Field label="首帧 / 菜品图片"><input className="input" type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (!file) return; const localUrl = URL.createObjectURL(file); updateNodeData(node.id, { imageName: file.name, imagePreview: localUrl }); uploadDraftFile(draftId, file, "image").then(result => { URL.revokeObjectURL(localUrl); updateNodeData(node.id, { imagePreview: result.url }); onToast("图片已上传并持久化"); }).catch(() => { URL.revokeObjectURL(localUrl); updateNodeData(node.id, { imagePreview: undefined }); onToast("图片上传失败"); }); }} /></Field>
  </>;
}

function PromptFields({ node }: { node: WorkflowNode }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const data = node.data;
  const update = (patch: Partial<WorkflowData>) => updateNodeData(node.id, patch);
  const l0 = data.promptL0 ?? [];
  return <>
    <SectionTitle>提示词槽位</SectionTitle>
    <Field label="模式"><Select value={formatNodeValue(data.promptMode, "单图模式")} options={["单图模式", "首尾帧模式"]} onChange={value => update({ promptMode: value })} /></Field>
    <Field label="L0 · 画面元素"><div className="check-grid">{promptL0Options.map(item => <label className={`check ${l0.includes(item) ? "checked" : ""}`} key={item}><input type="checkbox" checked={l0.includes(item)} onChange={event => update({ promptL0: event.target.checked ? [...l0, item] : l0.filter(value => value !== item) })} />{item}</label>)}</div></Field>
    <Field label="镜头运动"><Select value={formatNodeValue(data.promptMotion, "小角度顺时针环绕")} options={["小角度顺时针环绕", "缓慢推进", "固定机位", "右向横移"]} onChange={value => update({ promptMotion: value })} /></Field>
    <Field label="幅度"><Select value={formatNodeValue(data.promptAmplitude, "极轻微（约 8%）")} options={["极轻微（约 8%）", "轻微（约 15%）", "明显（约 25%）"]} onChange={value => update({ promptAmplitude: value })} /></Field>
    <Field label="L1 · 主运动对象"><Select value={formatNodeValue(data.promptL1, "菜品主体·热食")} options={["菜品主体·热食", "菜品主体·冷食", "手部", "无（纯运镜）"]} onChange={value => update({ promptL1: value })} /></Field>
    <Field label="L2 · 动态 1"><div className="field-grid"><Select value={formatNodeValue(data.promptL2Type1, "高光滑移")} options={["高光滑移", "热气 / 蒸汽", "液体晃动", "无"]} onChange={value => update({ promptL2Type1: value })} /><Select value={formatNodeValue(data.promptL2Target1, "菜品")} options={["菜品", "汤汁", "餐具"]} onChange={value => update({ promptL2Target1: value })} /></div></Field>
    <Field label="L2 · 动态 2"><div className="field-grid"><Select value={formatNodeValue(data.promptL2Type2, "（无）")} options={["（无）", "热气 / 蒸汽", "高光滑移", "液体晃动"]} onChange={value => update({ promptL2Type2: value })} /><Select value={formatNodeValue(data.promptL2Target2, "菜品")} options={["菜品", "汤汁", "餐具"]} onChange={value => update({ promptL2Target2: value })} /></div></Field>
    <div className="preview-box">已选择 {l0.length} 个 L0 元素。锁定层保持静止，提示词将按当前槽位实时装配。</div>
  </>;
}

function SoundFields({ node }: { node: WorkflowNode }) {
  const activePanel = useWorkflowStore(state => state.activePanel);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const bgmName = useWorkflowStore(state => state.bgmName);
  const draftId = useWorkflowStore(state => state.draftId);
  const setBgm = useWorkflowStore(state => state.setBgm);
  const data = node.data;
  return <>
    <div className="tabs"><button type="button" className={`tab ${activePanel === "voice" ? "active" : ""}`} onClick={() => setActivePanel("voice")}>声音</button><button type="button" className={`tab ${activePanel === "overlay" ? "active" : ""}`} onClick={() => setActivePanel("overlay")}>文字</button></div>
    {activePanel === "overlay" ? <>
      <SectionTitle>画面文字</SectionTitle>
      <Field label="主文案"><input className="input" value={formatNodeValue(data.overlayMain, "")} onChange={event => updateNodeData(node.id, { overlayMain: event.target.value })} /></Field>
      <Field label="片尾 CTA"><input className="input" value={formatNodeValue(data.overlayCta, "")} onChange={event => updateNodeData(node.id, { overlayCta: event.target.value })} /></Field>
      <Field label="显示位置"><Select value={formatNodeValue(data.overlayPosition, "底部安全区")} options={["底部安全区", "画面中央", "顶部安全区"]} onChange={value => updateNodeData(node.id, { overlayPosition: value })} /></Field>
      <div className="field-grid"><Field label="开始"><input className="input" value={formatNodeValue(data.overlayStart, "0.0s")} onChange={event => updateNodeData(node.id, { overlayStart: event.target.value })} /></Field><Field label="结束"><input className="input" value={formatNodeValue(data.overlayEnd, "2.5s")} onChange={event => updateNodeData(node.id, { overlayEnd: event.target.value })} /></Field></div>
    </> : <>
      <SectionTitle>人声与 BGM</SectionTitle>
      <Field label="引流文案"><textarea className="input textarea" value={formatNodeValue(data.voiceText, "")} onChange={event => updateNodeData(node.id, { voiceText: event.target.value })} /></Field>
      <Field label="音色"><Select value={formatNodeValue(data.voiceName, "女声 · 温暖自然")} options={["女声 · 温暖自然", "男声 · 稳重清晰"]} onChange={value => updateNodeData(node.id, { voiceName: value })} /></Field>
      <Field label="音量"><input className="range" type="range" min="0" max="100" value={formatNodeValue(data.voiceVolume, "85")} onChange={event => updateNodeData(node.id, { voiceVolume: event.target.value })} /></Field>
      <Field label="BGM"><div className="upload-row"><input className="input" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac" onChange={event => { const file = event.target.files?.[0]; if (!file) return; setBgm(file.name, ""); uploadDraftFile(draftId, file, "audio").then(result => setBgm(file.name, result.url)).catch(() => setBgm(file.name, "")); }} /><span>{bgmName}</span></div></Field>
    </>}
  </>;
}

function TypeFields({ node, onToast }: { node: WorkflowNode; onToast: (message: string) => void }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const update = (patch: Partial<WorkflowData>) => updateNodeData(node.id, patch);
  const data = node.data;
  if (data.kind === "input") return <AssetFields node={node} onToast={onToast} />;
  if (data.kind === "prompt") return <PromptFields node={node} />;
  if (data.kind === "generator") return <><SectionTitle>视频规格</SectionTitle><Field label="视频时长"><Select value={formatNodeValue(data.duration, "3s")} options={["3s", "5s"]} onChange={value => update({ duration: value })} /></Field><Field label="分辨率"><Select value={formatNodeValue(data.resolution, "1080p")} options={["1080p", "720p"]} onChange={value => update({ resolution: value })} /></Field><Field label="音频"><Select value={formatNodeValue(data.audio, "无声")} options={["无声", "有声"]} onChange={value => update({ audio: value })} /></Field><Field label="分镜"><Select value={formatNodeValue(data.storyboard, "单分镜")} options={["单分镜", "多分镜"]} onChange={value => update({ storyboard: value })} /></Field></>;
  if (data.kind === "output") return <><SectionTitle>视频合成</SectionTitle><Field label="合成目标"><input className="input" value={formatNodeValue(data.outputTarget, "")} onChange={event => update({ outputTarget: event.target.value })} /></Field><Field label="成片时长"><Select value={formatNodeValue(data.outputDuration, "12-15s")} options={["12-15s", "15-20s"]} onChange={value => update({ outputDuration: value })} /></Field><Field label="画幅"><Select value={formatNodeValue(data.outputAspect, "9:16")} options={["9:16", "1:1"]} onChange={value => update({ outputAspect: value })} /></Field></>;
  if (data.kind === "sound") return <SoundFields node={node} />;
  return <><SectionTitle>自定义处理</SectionTitle><div className="preview-box">{data.description}</div></>;
}

export function Inspector({ onToast }: { onToast: (message: string) => void }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const selectedEdgeId = useWorkflowStore(state => state.selectedEdgeId);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const deleteSelected = useWorkflowStore(state => state.deleteSelected);
  const duplicateSelected = useWorkflowStore(state => state.duplicateSelected);
  const node = nodes.find(item => item.id === selectedNodeId);
  if (selectedEdgeId) return <aside className="inspector"><div className="inspector-head"><div><h2>连接线</h2><p>选中后可删除当前连接</p></div></div><button type="button" className="btn btn-danger full" onClick={() => { deleteSelected(); onToast("连接线已删除"); }}>删除连接</button></aside>;
  if (!node) return <aside className="inspector"><div className="empty-state">选择节点查看可编辑属性</div></aside>;
  return <aside className="inspector"><div className="inspector-head"><div><h2>节点属性</h2><p>{node.data.title} · 可编辑</p></div><Tag>{node.data.kind}</Tag></div><BasicFields node={node} /><TypeFields node={node} onToast={onToast} /><div className="inspector-actions"><button type="button" className="btn btn-primary full" onClick={() => onToast("节点修改已同步到画布")}>保存节点</button><button type="button" className="btn full" onClick={() => { duplicateSelected(); onToast("节点已复制"); }}>复制节点</button><button type="button" className="btn btn-danger full" onClick={() => { deleteSelected(); setSelection(null); onToast("节点已删除"); }}>删除节点</button></div></aside>;
}
