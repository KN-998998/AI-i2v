import { useEffect } from "react";
import { DISH_CATEGORY_OPTIONS, inferDishCategory, nodeCatalog, type NodeKind, type WorkflowData, type WorkflowNode } from "../model";
import { uploadDraftFile } from "../api";
import { ACTION_LEVEL_OPTIONS, ACTION_VERB_OPTIONS, AMPLITUDE_OPTIONS, assemblePrompt, CAMERA_OPTIONS, ELEMENT_OPTIONS, L2_OPTIONS, promptConfigFromData, promptLegacyPatch, SPEED_CURVE_OPTIONS, type ActionLevel, type ActionVerb, type ElementId, type L2Item, type L2Type, type PromptConfig, type PromptMode, type SpeedCurve } from "../promptAssembler";
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
  const dishCategory = data.dishCategory ?? (data.dishName ? inferDishCategory(data.dishName) : "正餐");
  useEffect(() => () => {
    if (data.imagePreview?.startsWith("blob:")) URL.revokeObjectURL(data.imagePreview);
  }, [data.imagePreview]);
  return <>
    <SectionTitle>素材与菜品</SectionTitle>
    <Field label="当前菜品"><input className="input" value={formatNodeValue(data.dishName, "")} onChange={event => updateNodeData(node.id, { dishName: event.target.value })} /></Field>
    <Field label="菜品类型"><Select value={formatNodeValue(data.foodType, "热食")} options={["冷食", "热食"]} onChange={value => updateNodeData(node.id, { foodType: value })} /></Field>
    <Field label="菜品分类"><Select value={dishCategory} options={[...DISH_CATEGORY_OPTIONS]} onChange={value => updateNodeData(node.id, { dishCategory: value as typeof DISH_CATEGORY_OPTIONS[number] })} /></Field>
    <Field label="素材模式"><Select value={formatNodeValue(data.assetMode, "单图模式")} options={["单图模式", "首尾帧模式"]} onChange={value => updateNodeData(node.id, { assetMode: value })} /></Field>
    <Field label="首帧 / 菜品图片"><input className="input" type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (!file) return; const localUrl = URL.createObjectURL(file); updateNodeData(node.id, { imageName: file.name, imagePreview: localUrl }); uploadDraftFile(draftId, file, "image").then(result => { URL.revokeObjectURL(localUrl); updateNodeData(node.id, { imagePreview: result.url }); onToast("图片已上传并持久化"); }).catch(() => { URL.revokeObjectURL(localUrl); updateNodeData(node.id, { imagePreview: undefined }); onToast("图片上传失败"); }); }} /></Field>
  </>;
}

function PromptFields({ node, onToast }: { node: WorkflowNode; onToast: (message: string) => void }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const draftId = useWorkflowStore(state => state.draftId);
  const data = node.data;
  const config = promptConfigFromData(data);
  const result = assemblePrompt(config);
  const commit = (patch: Partial<PromptConfig>) => {
    const next: PromptConfig = { ...config, ...patch, elements: patch.elements ? [...patch.elements] : [...config.elements], l2_dynamics: patch.l2_dynamics ? patch.l2_dynamics.map(item => ({ ...item })) : config.l2_dynamics.map(item => ({ ...item })) };
    if (next.mode === "single_image") next.speed_curve = null;
    if (next.mode === "keyframes" && !next.speed_curve) next.speed_curve = "uniform";
    if (!["hand", "chef"].includes(next.l1_subject)) { next.l1_action_level = null; next.l1_action_verb = null; }
    if (next.l1_action_level === 1) next.l1_action_verb = null;
    updateNodeData(node.id, { promptConfig: next, ...promptLegacyPatch(next) });
  };
  const elementLabels = config.elements.map(id => ELEMENT_OPTIONS.find(item => item.id === id)?.lockLabel).filter((label): label is string => Boolean(label)).filter((label, index, list) => list.indexOf(label) === index);
  const l1Options = ELEMENT_OPTIONS.filter(item => item.canBeL1 && (config.elements.includes(item.id) || item.id === config.l1_subject));
  const subjectLabel = config.l1_subject === "none" ? "无（纯运镜）" : ELEMENT_OPTIONS.find(item => item.id === config.l1_subject)?.label ?? "菜品主体·热食";
  const targetOptions = [...elementLabels, "其他"].filter((value, index, list) => list.indexOf(value) === index);
  const selectL2 = (index: number, type: L2Type | null) => {
    const next = [...config.l2_dynamics];
    if (!type) next.splice(index, 1);
    else next[index] = { type, target: next[index]?.target || elementLabels[0] || "主体" };
    commit({ l2_dynamics: next });
  };
  const updateL2Target = (index: number, target: string) => {
    const next = config.l2_dynamics.map(item => ({ ...item }));
    if (!next[index]) return;
    next[index].target = target;
    commit({ l2_dynamics: next });
  };
  const uploadEndImage = (file: File) => {
    const localUrl = URL.createObjectURL(file);
    updateNodeData(node.id, { promptEndImageName: file.name, promptEndImagePreview: localUrl });
    uploadDraftFile(draftId, file, "image").then(uploaded => {
      URL.revokeObjectURL(localUrl);
      updateNodeData(node.id, { promptEndImagePreview: uploaded.url });
      commit({ endImageReady: true });
      onToast("尾帧图片已上传并持久化");
    }).catch(() => {
      URL.revokeObjectURL(localUrl);
      updateNodeData(node.id, { promptEndImagePreview: undefined, promptEndImageName: undefined });
      commit({ endImageReady: false });
      onToast("尾帧图片上传失败");
    });
  };
  const formatIssue = (item: { code: string; message: string }) => `${item.code}：${item.message}`;
  return <>
    <SectionTitle>提示词槽位</SectionTitle>
    <Field label="模式"><Select value={config.mode === "keyframes" ? "首尾帧模式" : "单图模式"} options={["单图模式", "首尾帧模式"]} onChange={value => commit({ mode: value === "首尾帧模式" ? "keyframes" : "single_image" })} /></Field>
    <Field label={`L0 · 画面元素（${config.elements.length}/8）`}><div className="check-grid">{ELEMENT_OPTIONS.map(item => <label className={`check ${config.elements.includes(item.id) ? "checked" : ""}`} key={item.id}><input type="checkbox" checked={config.elements.includes(item.id)} onChange={event => commit({ elements: event.target.checked ? [...config.elements, item.id] : config.elements.filter(value => value !== item.id) })} />{item.label}</label>)}</div></Field>
    <Field label="镜头运动"><Select value={CAMERA_OPTIONS.find(item => item.value === config.camera_move)?.label ?? CAMERA_OPTIONS[0].label} options={CAMERA_OPTIONS.map(item => item.label)} onChange={value => commit({ camera_move: CAMERA_OPTIONS.find(item => item.label === value)!.value })} /></Field>
    <Field label="幅度"><Select value={AMPLITUDE_OPTIONS.find(item => item.value === config.camera_amplitude)?.label ?? AMPLITUDE_OPTIONS[0].label} options={AMPLITUDE_OPTIONS.map(item => item.label)} onChange={value => commit({ camera_amplitude: AMPLITUDE_OPTIONS.find(item => item.label === value)!.value })} /></Field>
    <Field label="L1 · 主运动对象"><Select value={subjectLabel} options={[...l1Options.map(item => item.label), "无（纯运镜）"]} onChange={value => commit({ l1_subject: value === "无（纯运镜）" ? "none" : l1Options.find(item => item.label === value)!.id as PromptConfig["l1_subject"] })} /></Field>
    {["hand", "chef"].includes(config.l1_subject) && <><Field label="动作幅度"><Select value={ACTION_LEVEL_OPTIONS.find(item => item.value === (config.l1_action_level ?? 1))!.label} options={ACTION_LEVEL_OPTIONS.map(item => item.label)} onChange={value => commit({ l1_action_level: ACTION_LEVEL_OPTIONS.find(item => item.label === value)!.value })} /></Field>{[2, 3].includes(config.l1_action_level ?? 0) && <Field label="具体动作"><Select value={ACTION_VERB_OPTIONS.find(item => item.value === config.l1_action_verb)?.label ?? ACTION_VERB_OPTIONS[0].label} options={ACTION_VERB_OPTIONS.map(item => item.label)} onChange={value => commit({ l1_action_verb: ACTION_VERB_OPTIONS.find(item => item.label === value)!.value as ActionVerb })} /></Field>}</>}
    {[0, 1].map(index => { const item = config.l2_dynamics[index]; const typeLabel = item ? L2_OPTIONS.find(option => option.value === item.type)?.label ?? "" : "无"; const target = item?.target ?? targetOptions[0] ?? "主体"; return <div className="field" key={index}><span>{`L2 · 动态 ${index + 1}`}</span><div className="field-grid"><Select value={typeLabel} options={["无", ...L2_OPTIONS.map(option => option.label)]} onChange={value => selectL2(index, value === "无" ? null : L2_OPTIONS.find(option => option.label === value)!.value)} />{item && <Select value={targetOptions.includes(target) ? target : "其他"} options={targetOptions} onChange={value => updateL2Target(index, value === "其他" ? "" : value)} />}</div>{item && (!targetOptions.includes(target) || target === "") && <input className="input prompt-target-input" value={target} placeholder="填写1-8字名词" onChange={event => updateL2Target(index, event.target.value)} />}</div>; })}
    {config.mode === "keyframes" && <><Field label="尾帧图片"><div className="upload-row"><input className="input" type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (file) uploadEndImage(file); }} /><span>{data.promptEndImageName || "未上传"}</span></div></Field><Field label="速度曲线"><Select value={SPEED_CURVE_OPTIONS.find(item => item.value === config.speed_curve)?.label ?? SPEED_CURVE_OPTIONS[0].label} options={SPEED_CURVE_OPTIONS.map(item => item.label)} onChange={value => commit({ speed_curve: SPEED_CURVE_OPTIONS.find(item => item.label === value)!.value as SpeedCurve })} /></Field></>}
    <label className={`check ${config.seamless_loop ? "checked" : ""}`}><input type="checkbox" checked={config.seamless_loop} onChange={event => commit({ seamless_loop: event.target.checked })} />启用无缝循环</label>
    <div className={`prompt-validation ${result.blocked ? "prompt-validation-error" : "prompt-validation-ready"}`}><strong>{result.blocked ? "当前配置阻断生成" : "当前配置可生成"}</strong>{result.errors.map(item => <span key={`${item.code}-${item.field}`}>{formatIssue(item)}</span>)}{result.warnings.map(item => <span key={`${item.code}-${item.field}`}>提示 {formatIssue(item)}</span>)}{result.warnings.some(item => item.code === "W2") && <button type="button" className="btn" onClick={() => commit({ mode: "keyframes" })}>切换到首尾帧模式</button>}</div>
    <Field label="正向提示词"><textarea className="input textarea prompt-preview" readOnly value={result.prompt} placeholder="修正阻断项后生成" /></Field>
    <Field label="负向提示词"><textarea className="input textarea prompt-preview" readOnly value={result.negative_prompt} placeholder="修正阻断项后生成" /></Field>
    <div className="preview-box">L0 {config.elements.length} 项 · L2 {config.l2_dynamics.length}/2 项 · cfg_scale {result.cfg_scale}</div>
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
  if (data.kind === "prompt") return <PromptFields node={node} onToast={onToast} />;
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
