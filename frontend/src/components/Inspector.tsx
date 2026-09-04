import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { captionSegmentsFromData, captionSegmentsPatch, DISH_CATEGORY_OPTIONS, FOOD_TYPE_OPTIONS, inferDishCategory, nodeCatalog, OVERLAY_FONT_OPTIONS, OVERLAY_POSITION_OPTIONS, overlayPositionCoordinates, overlayStyleFromItem, VISUAL_SUBJECT_TYPE_OPTIONS, type CaptionSegment, type FoodType, type NodeKind, type OverlayItem, type OverlayStyle, type VoiceItem, type VisualSubjectType, type WorkflowData, type WorkflowNode } from "../model";
import { fetchTTSOptions, splitCaptionText, uploadDraftFile, type TTSVoiceOption } from "../api";
import { ACTION_LEVEL_OPTIONS, ACTION_VERB_OPTIONS, AMPLITUDE_OPTIONS, assemblePrompt, CAMERA_OPTIONS, ELEMENT_OPTIONS, L2_OPTIONS, promptConfigFromData, promptLegacyPatch, SHOT_SIZE_OPTIONS, SPEED_CURVE_OPTIONS, type ActionLevel, type ActionVerb, type ElementId, type L2Item, type L2Type, type PromptConfig, type PromptMode, type SpeedCurve } from "../promptAssembler";
import { useWorkflowStore } from "../workflowStore";
import { ImageProcessControlFields } from "./ImageProcessControls";
import { Field, formatNodeValue, SectionTitle, Select, Tag } from "./ui";

const OVERLAY_STYLE_PRESETS: Array<{ label: string; style: OverlayStyle }> = [
  { label: "经典白字", style: { fontFamily: "Microsoft YaHei", fontSize: 42, textBoxWidth: 0.84, singleLine: true, color: "#FFFFFF", fontWeight: "bold", strokeColor: "#000000", strokeWidth: 2, backgroundEnabled: true, backgroundColor: "#111417", backgroundOpacity: 0.62 } },
  { label: "IG引流风格", style: { fontFamily: "Microsoft YaHei", fontSize: 48, textBoxWidth: 0.84, singleLine: true, color: "#FFD12E", fontWeight: "bold", strokeColor: "#111111", strokeWidth: 3, backgroundEnabled: false, backgroundColor: "#111417", backgroundOpacity: 0.62 } },
  { label: "金色 CTA", style: { fontFamily: "Microsoft YaHei", fontSize: 48, textBoxWidth: 0.84, singleLine: true, color: "#FFD166", fontWeight: "bold", strokeColor: "#2A1B00", strokeWidth: 3, backgroundEnabled: false, backgroundColor: "#111417", backgroundOpacity: 0.62 } },
  { label: "清爽白字", style: { fontFamily: "DengXian", fontSize: 40, textBoxWidth: 0.84, singleLine: true, color: "#FFFFFF", fontWeight: "normal", strokeColor: "#000000", strokeWidth: 1, backgroundEnabled: false, backgroundColor: "#111417", backgroundOpacity: 0.4 } },
  { label: "黑底卡片", style: { fontFamily: "Microsoft YaHei", fontSize: 40, textBoxWidth: 0.84, singleLine: true, color: "#FFFFFF", fontWeight: "bold", strokeColor: "#000000", strokeWidth: 0, backgroundEnabled: true, backgroundColor: "#111417", backgroundOpacity: 0.78 } },
  { label: "醒目红字", style: { fontFamily: "SimHei", fontSize: 44, textBoxWidth: 0.84, singleLine: true, color: "#FF5C5C", fontWeight: "bold", strokeColor: "#000000", strokeWidth: 3, backgroundEnabled: false, backgroundColor: "#111417", backgroundOpacity: 0.62 } },
  { label: "奶油标题", style: { fontFamily: "KaiTi", fontSize: 46, textBoxWidth: 0.84, singleLine: true, color: "#FFF1D6", fontWeight: "bold", strokeColor: "#5C3B1E", strokeWidth: 2, backgroundEnabled: false, backgroundColor: "#111417", backgroundOpacity: 0.62 } },
];

function stylePresetValue(style: OverlayStyle) {
  const preset = OVERLAY_STYLE_PRESETS.find(item => Object.entries(item.style).every(([key, value]) => style[key as keyof OverlayStyle] === value));
  return preset?.label ?? "自定义";
}

function AutoGrowingTextarea({ value, placeholder }: { value: string; placeholder: string }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(84, textarea.scrollHeight)}px`;
  }, [value]);
  return <textarea ref={textareaRef} className="input textarea prompt-preview" readOnly rows={1} value={value} placeholder={placeholder} />;
}

function BasicFields({ node }: { node: WorkflowNode }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const update = (patch: Partial<WorkflowData>) => updateNodeData(node.id, patch);
  return <div className="basic-fields">
    <SectionTitle>基本信息</SectionTitle>
    <div className="basic-fields-left"><Field label="节点类型"><select className="input" value={node.data.kind} onChange={event => { const kind = event.target.value as NodeKind; update({ kind, title: node.data.title === nodeCatalog[node.data.kind].title ? nodeCatalog[kind].title : node.data.title, description: nodeCatalog[kind].description, status: nodeCatalog[kind].status }); }}><option value="input">素材输入</option><option value="image_process">图片处理</option><option value="prompt">槽位化提示词</option><option value="generator">3 秒视频片段</option><option value="output">成片合成</option><option value="sound">声音与文字</option><option value="custom">自定义处理</option></select></Field><Field label="节点名称"><input className="input" value={node.data.title} onChange={event => update({ title: event.target.value })} /></Field></div>
    <div className="basic-fields-description"><Field label="节点说明"><textarea className="input textarea" value={node.data.description} onChange={event => update({ description: event.target.value })} /></Field></div>
  </div>;
}

function AssetFields({ node, onToast }: { node: WorkflowNode; onToast: (message: string) => void }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const draftId = useWorkflowStore(state => state.draftId);
  const data = node.data;
  const dishCategory = data.dishCategory ?? (data.dishName ? inferDishCategory(data.dishName) : "正餐");
  const dishFoodType = dishCategory === "套餐" ? "混合/多温" : formatNodeValue(data.foodType, "热食");
  useEffect(() => () => {
    if (data.imagePreview?.startsWith("blob:")) URL.revokeObjectURL(data.imagePreview);
  }, [data.imagePreview]);
  return <>
    <SectionTitle>素材与菜品</SectionTitle>
    <Field label="当前菜品"><input className="input" value={formatNodeValue(data.dishName, "")} onChange={event => updateNodeData(node.id, { dishName: event.target.value })} /></Field>
    <Field label="菜品类型"><Select value={dishFoodType} options={[...FOOD_TYPE_OPTIONS]} onChange={value => updateNodeData(node.id, { foodType: value as FoodType })} /></Field>
    <Field label="菜品分类"><Select value={dishCategory} options={[...DISH_CATEGORY_OPTIONS]} onChange={value => updateNodeData(node.id, { dishCategory: value as typeof DISH_CATEGORY_OPTIONS[number], foodType: value === "套餐" ? "混合/多温" : value === "甜品" || value === "水果" ? "冷食" : data.foodType })} /></Field>
    <Field label="画面主体类型"><Select value={data.visualSubjectType ?? "菜品主体"} options={[...VISUAL_SUBJECT_TYPE_OPTIONS]} onChange={value => updateNodeData(node.id, { visualSubjectType: value as VisualSubjectType })} /></Field>
    <Field label="素材模式"><Select value={formatNodeValue(data.assetMode, "单图模式")} options={["单图模式", "首尾帧模式"]} onChange={value => updateNodeData(node.id, { assetMode: value })} /></Field>
    <Field label="首帧 / 菜品图片"><input className="input" type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (!file) return; const localUrl = URL.createObjectURL(file); updateNodeData(node.id, { imageName: file.name, imagePreview: localUrl, assetAnalysis: undefined }); uploadDraftFile(draftId, file, "image", { dish: data.dishName, category: dishCategory }).then(result => { URL.revokeObjectURL(localUrl); updateNodeData(node.id, { imagePreview: result.url, assetAnalysis: result.analysis }); onToast("图片已上传并持久化"); }).catch(() => { URL.revokeObjectURL(localUrl); updateNodeData(node.id, { imagePreview: undefined, assetAnalysis: undefined }); onToast("图片上传失败"); }); }} /></Field>
    {data.assetAnalysis && <div className="media-analysis"><div><strong>图片质量 {data.assetAnalysis.qualityScore}/100</strong><Tag good={data.assetAnalysis.qualityLabel === "good"} warn={data.assetAnalysis.qualityLabel !== "good"}>{data.assetAnalysis.qualityLabel === "good" ? "可用" : data.assetAnalysis.qualityLabel === "warning" ? "建议检查" : "不建议使用"}</Tag></div><span>分类：{data.assetAnalysis.category ?? dishCategory} · 分析方式：本地规则</span>{data.assetAnalysis.qualityWarnings.map(warning => <small key={warning}>提示：{warning}</small>)}</div>}
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
  return <div className="prompt-fields-compact">
    <SectionTitle>提示词槽位</SectionTitle>
    <div className="prompt-control-grid">
    <Field label="模式"><Select value={config.mode === "keyframes" ? "首尾帧模式" : "单图模式"} options={["单图模式", "首尾帧模式"]} onChange={value => commit({ mode: value === "首尾帧模式" ? "keyframes" : "single_image" })} /></Field>
    <Field label="镜头运动"><Select value={CAMERA_OPTIONS.find(item => item.value === config.camera_move)?.label ?? CAMERA_OPTIONS[0].label} options={CAMERA_OPTIONS.map(item => item.label)} onChange={value => commit({ camera_move: CAMERA_OPTIONS.find(item => item.label === value)!.value })} /></Field>
    <Field label="幅度"><Select value={AMPLITUDE_OPTIONS.find(item => item.value === config.camera_amplitude)?.label ?? AMPLITUDE_OPTIONS[0].label} options={AMPLITUDE_OPTIONS.map(item => item.label)} onChange={value => commit({ camera_amplitude: AMPLITUDE_OPTIONS.find(item => item.label === value)!.value })} /></Field>
    <Field label="景别"><Select value={SHOT_SIZE_OPTIONS.find(item => item.value === config.shot_size)?.label ?? SHOT_SIZE_OPTIONS[0].label} options={SHOT_SIZE_OPTIONS.map(item => item.label)} onChange={value => commit({ shot_size: SHOT_SIZE_OPTIONS.find(item => item.label === value)!.value })} /></Field>
    <Field label="L1 · 主运动对象"><Select value={subjectLabel} options={[...l1Options.map(item => item.label), "无（纯运镜）"]} onChange={value => commit({ l1_subject: value === "无（纯运镜）" ? "none" : l1Options.find(item => item.label === value)!.id as PromptConfig["l1_subject"] })} /></Field>
    {["hand", "chef"].includes(config.l1_subject) && <><Field label="动作幅度"><Select value={ACTION_LEVEL_OPTIONS.find(item => item.value === (config.l1_action_level ?? 1))!.label} options={ACTION_LEVEL_OPTIONS.map(item => item.label)} onChange={value => commit({ l1_action_level: ACTION_LEVEL_OPTIONS.find(item => item.label === value)!.value })} /></Field>{[2, 3].includes(config.l1_action_level ?? 0) && <Field label="具体动作"><Select value={ACTION_VERB_OPTIONS.find(item => item.value === config.l1_action_verb)?.label ?? ACTION_VERB_OPTIONS[0].label} options={ACTION_VERB_OPTIONS.map(item => item.label)} onChange={value => commit({ l1_action_verb: ACTION_VERB_OPTIONS.find(item => item.label === value)!.value as ActionVerb })} /></Field>}</>}
    </div>
    <Field label={`L0 · 画面元素（${config.elements.length}/8）`}><div className="check-grid">{ELEMENT_OPTIONS.map(item => <label className={`check ${config.elements.includes(item.id) ? "checked" : ""}`} key={item.id}><input type="checkbox" checked={config.elements.includes(item.id)} onChange={event => commit({ elements: event.target.checked ? [...config.elements, item.id] : config.elements.filter(value => value !== item.id) })} />{item.label}</label>)}</div></Field>
    <div className="prompt-l2-grid">{[0, 1].map(index => { const item = config.l2_dynamics[index]; const typeLabel = item ? L2_OPTIONS.find(option => option.value === item.type)?.label ?? "" : "无"; const target = item?.target ?? targetOptions[0] ?? "主体"; return <div className="field" key={index}><span>{`L2 · 动态 ${index + 1}`}</span><div className="field-grid"><Select value={typeLabel} options={["无", ...L2_OPTIONS.map(option => option.label)]} onChange={value => selectL2(index, value === "无" ? null : L2_OPTIONS.find(option => option.label === value)!.value)} />{item && <Select value={targetOptions.includes(target) ? target : "其他"} options={targetOptions} onChange={value => updateL2Target(index, value === "其他" ? "" : value)} />}</div>{item && (!targetOptions.includes(target) || target === "") && <input className="input prompt-target-input" value={target} placeholder="填写1-8字名词" onChange={event => updateL2Target(index, event.target.value)} />}</div>; })}</div>
    {config.mode === "keyframes" && <><Field label="尾帧图片"><div className="upload-row"><input className="input" type="file" accept="image/*" onChange={event => { const file = event.target.files?.[0]; if (file) uploadEndImage(file); }} /><span>{data.promptEndImageName || "未上传"}</span></div></Field><Field label="速度曲线"><Select value={SPEED_CURVE_OPTIONS.find(item => item.value === config.speed_curve)?.label ?? SPEED_CURVE_OPTIONS[0].label} options={SPEED_CURVE_OPTIONS.map(item => item.label)} onChange={value => commit({ speed_curve: SPEED_CURVE_OPTIONS.find(item => item.label === value)!.value as SpeedCurve })} /></Field></>}
    <label className={`check ${config.seamless_loop ? "checked" : ""}`}><input type="checkbox" checked={config.seamless_loop} onChange={event => commit({ seamless_loop: event.target.checked })} />启用无缝循环</label>
    <div className={`prompt-validation ${result.blocked ? "prompt-validation-error" : "prompt-validation-ready"}`}><strong>{result.blocked ? "当前配置阻断生成" : "当前配置可生成"}</strong>{result.errors.map(item => <span key={`${item.code}-${item.field}`}>{formatIssue(item)}</span>)}{result.warnings.map(item => <span key={`${item.code}-${item.field}`}>提示 {formatIssue(item)}</span>)}{result.warnings.some(item => item.code === "W2") && <button type="button" className="btn" onClick={() => commit({ mode: "keyframes" })}>切换到首尾帧模式</button>}</div>
    <div className="prompt-preview-grid"><Field label="正向提示词"><AutoGrowingTextarea value={result.prompt} placeholder="修正阻断项后生成" /></Field><Field label="负向提示词"><AutoGrowingTextarea value={result.negative_prompt} placeholder="修正阻断项后生成" /></Field></div>
    <div className="preview-box">L0 {config.elements.length} 项 · L2 {config.l2_dynamics.length}/2 项 · cfg_scale {result.cfg_scale}</div>
  </div>;
}

function VoiceModelSelectors({ item, options, update }: { item: VoiceItem; options: TTSVoiceOption[]; update: (patch: Partial<VoiceItem>) => void }) {
  const models = Array.from(new Set(options.map(option => option.model)));
  const selectedModel = item.model && models.includes(item.model) ? item.model : models[0] ?? "";
  const voices = options.filter(option => option.model === selectedModel);
  const selectedVoice = voices.some(option => option.voice_id === item.voiceId) ? item.voiceId ?? "none" : "none";
  const selectedOption = voices.find(option => option.voice_id === selectedVoice);
  const selectModel = (model: string) => {
    const nextOption = options.find(option => option.model === model && option.voice_id === item.voiceId);
    update({
      model,
      provider: nextOption?.provider ?? "qwen",
      voiceId: nextOption?.voice_id ?? "none",
      voiceName: nextOption?.label ?? "无",
      enabled: nextOption ? item.enabled !== false : false,
      ttsDisabledByUser: !nextOption,
    });
  };
  const selectVoice = (voiceId: string) => {
    const option = voices.find(candidate => candidate.voice_id === voiceId);
    update({
      model: selectedModel,
      provider: option?.provider ?? "qwen",
      voiceId: option?.voice_id ?? "none",
      voiceName: option?.label ?? "无",
      enabled: Boolean(option),
      ttsDisabledByUser: !option,
    });
  };
  return <div className="field-grid voice-selector-grid">
    <label className="field"><span>合成模型</span><select className="input" value={selectedModel} disabled={models.length === 0} onChange={event => selectModel(event.target.value)}>{models.length === 0 ? <option value="">暂无可用模型</option> : models.map(model => <option key={model} value={model}>{model}</option>)}</select></label>
    <label className="field"><span>音色</span><select className="input" value={selectedVoice} disabled={voices.length === 0} onChange={event => selectVoice(event.target.value)}><option value="none">无（默认，不生成 TTS）</option>{voices.map(option => <option key={option.voice_id} value={option.voice_id}>{option.label}</option>)}</select></label>
    {selectedOption && <small className="voice-selection-hint">当前：{selectedOption.label}</small>}
  </div>;
}

function SoundFields({ node, onToast }: { node: WorkflowNode; onToast: (message: string) => void }) {
  const activePanel = useWorkflowStore(state => state.activePanel);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const activeWorkspace = useWorkflowStore(state => state.composeWorkspaces.find(item => item.id === state.activeComposeWorkspaceId));
  const legacyBgmName = useWorkflowStore(state => state.bgmName);
  const legacyBgmUrl = useWorkflowStore(state => state.bgmUrl);
  const bgmName = activeWorkspace?.soundConfig?.bgmName ?? legacyBgmName;
  const bgmUrl = activeWorkspace?.soundConfig?.bgmUrl ?? legacyBgmUrl;
  const draftId = useWorkflowStore(state => state.draftId);
  const setBgm = useWorkflowStore(state => state.setBgm);
  const [ttsOptions, setTtsOptions] = useState<TTSVoiceOption[]>([]);
  useEffect(() => {
    fetchTTSOptions().then(result => setTtsOptions(result.voices)).catch(() => setTtsOptions([]));
  }, []);
  const [captionSplitBusy, setCaptionSplitBusy] = useState(false);
  const data = node.data.kind === "sound" ? { ...node.data, ...(activeWorkspace?.soundConfig ?? {}) } : node.data;
  const [bulkCaptionText, setBulkCaptionText] = useState(data.captionSourceText ?? "");
  useEffect(() => {
    setBulkCaptionText(data.captionSourceText ?? "");
  }, [node.id, activeWorkspace?.id, data.captionSourceText]);
  const captionSegments = captionSegmentsFromData(data);
  const [collapsedCards, setCollapsedCards] = useState<Record<string, boolean>>(() => Object.fromEntries(captionSegments.flatMap((segment, index) => [[segment.overlay.id, index > 0], [segment.voice.id, index > 0]])));
  useEffect(() => {
    setCollapsedCards(current => {
      const next = { ...current };
      captionSegments.forEach((segment, index) => {
        if (!(segment.overlay.id in next)) next[segment.overlay.id] = index > 0;
        if (!(segment.voice.id in next)) next[segment.voice.id] = index > 0;
      });
      return next;
    });
  }, [node.id, captionSegments.length]);
  const overlayItems = captionSegments.map(segment => segment.overlay).filter(item => !item.placeholder);
  const voiceItems = captionSegments.map(segment => segment.voice).filter(item => !item.placeholder);
  const positionLabel = (value: OverlayItem["position"]) => OVERLAY_POSITION_OPTIONS.find(item => item.value === value)?.label ?? OVERLAY_POSITION_OPTIONS[1].label;
  const commitSegments = (segments: CaptionSegment[]) => updateNodeData(node.id, captionSegmentsPatch(segments));
  const applyBulkCaptionSplit = async (useLlm: boolean) => {
    const source = bulkCaptionText.trim();
    if (!source) {
      onToast("请先输入一整段文案");
      return;
    }
    setCaptionSplitBusy(true);
    try {
      const result = await splitCaptionText(source, useLlm);
      const timestamp = Date.now();
      const voiceTemplate = captionSegments
        .map(segment => segment.voice)
        .find(voice => !voice.placeholder && voice.voiceId !== "none") ?? captionSegments[0]?.voice;
      const nextSegments = result.segments.map((text, index) => {
        const current = captionSegments[index];
        const currentOverlay = current?.overlay;
        const currentVoice = current?.voice;
        // A new split is a new timing plan. Reusing old ranges leaves stale
        // overlaps behind when the number of sentences changes.
        const start = index * 2.5;
        const end = start + 2.5;
        const voiceId = currentVoice && !currentVoice.id.startsWith("voice_for_") ? currentVoice.id : `voice_${timestamp}_${index}`;
        const overlayId = currentOverlay && !currentOverlay.id.startsWith("overlay_for_") ? currentOverlay.id : `overlay_${timestamp}_${index}`;
        const voiceBase = currentVoice?.voiceId !== "none" ? currentVoice : voiceTemplate;
        return {
          id: voiceId,
          overlay: {
            ...(currentOverlay ?? { position: "upper", ...overlayPositionCoordinates("upper") }),
            id: overlayId,
            text,
            placeholder: false,
            startSeconds: start,
            endSeconds: Math.max(start + 0.1, end),
            syncVoiceId: voiceId,
          },
          voice: {
            ...(voiceBase ?? { provider: "qwen", model: "", voiceId: "none", voiceName: "none", volume: 85, enabled: false }),
            id: voiceId,
            text: result.voice_segments[index] ?? text,
            placeholder: false,
            startSeconds: start,
            endSeconds: Math.max(start + 0.1, end),
          },
        };
      });
      updateNodeData(node.id, { ...captionSegmentsPatch(nextSegments), captionSourceText: source });
      onToast(result.warning ?? (result.used_llm ? `Qwen 已优化并生成 ${result.segments.length} 段文案` : `已按本地规则拆分为 ${result.segments.length} 段`));
    } catch (error) {
      onToast(error instanceof Error ? error.message : "文案拆分失败");
    } finally {
      setCaptionSplitBusy(false);
    }
  };
  const updateOverlay = (id: string, patch: Partial<OverlayItem>) => commitSegments(captionSegments.map(segment => {
    if (segment.overlay.id !== id) return segment;
    const overlay = { ...segment.overlay, ...patch };
    const linked = overlay.syncVoiceId !== "";
    const voice = linked ? { ...segment.voice, ...(patch.startSeconds === undefined ? {} : { startSeconds: patch.startSeconds }), ...(patch.endSeconds === undefined ? {} : { endSeconds: patch.endSeconds }) } : segment.voice;
    return { ...segment, overlay, voice };
  }));
  const updateOverlayStyle = (id: string, patch: Partial<OverlayStyle>) => {
    const item = overlayItems.find(candidate => candidate.id === id);
    if (!item) return;
    updateOverlay(id, { style: { ...overlayStyleFromItem(item), ...patch } });
  };
  const removeOverlay = (id: string) => commitSegments(captionSegments.filter(segment => segment.overlay.id !== id));
  const addOverlay = () => {
    const lastEnd = overlayItems.reduce((max, item) => Math.max(max, item.endSeconds), 0);
    const voiceId = `voice_${Date.now()}`;
    commitSegments([...captionSegments, {
      id: voiceId,
      overlay: { id: `overlay_${Date.now()}`, text: "", startSeconds: lastEnd, endSeconds: lastEnd + 2, position: "custom", x: 0.5, y: 0.5, syncVoiceId: voiceId },
      voice: { id: voiceId, text: "", enabled: false, startSeconds: lastEnd, endSeconds: lastEnd + 2, provider: "qwen", model: "", voiceId: "none", voiceName: "无", volume: 85 },
    }]);
  };
  const updateVoice = (id: string, patch: Partial<(typeof voiceItems)[number]>) => commitSegments(captionSegments.map(segment => {
    if (segment.voice.id !== id) return segment;
    const voice = { ...segment.voice, ...patch };
    const linked = segment.overlay.syncVoiceId !== "";
    const overlay = linked ? { ...segment.overlay, ...(patch.startSeconds === undefined ? {} : { startSeconds: patch.startSeconds }), ...(patch.endSeconds === undefined ? {} : { endSeconds: patch.endSeconds }) } : segment.overlay;
    return { ...segment, voice, overlay };
  }));
  const removeVoice = (id: string) => commitSegments(captionSegments.filter(segment => segment.voice.id !== id));
  const addVoice = addOverlay;
  const toggleCard = (id: string) => setCollapsedCards(current => ({ ...current, [id]: !current[id] }));
  return <>
    <div className="tabs"><button type="button" className={`tab ${activePanel === "voice" ? "active" : ""}`} onClick={() => setActivePanel("voice")}>声音</button><button type="button" className={`tab ${activePanel === "overlay" ? "active" : ""}`} onClick={() => setActivePanel("overlay")}>文字</button></div>
    {activePanel === "overlay" ? <>
      <div className="panel-section-head"><SectionTitle>文案段</SectionTitle><button type="button" className="btn" onClick={addOverlay}>＋ 添加文案段</button></div>
      <div className="caption-bulk-tools">
        <div className="caption-bulk-heading"><strong>整段文案拆分</strong><span>按语义生成对应的画面文字与 TTS 人声段</span></div>
        <textarea className="input textarea caption-bulk-input" rows={3} value={bulkCaptionText} placeholder="粘贴一整段引流文案" onChange={event => { const value = event.target.value; setBulkCaptionText(value); updateNodeData(node.id, { captionSourceText: value }); }} />
        <div className="caption-bulk-actions"><button type="button" className="btn" disabled={captionSplitBusy || !bulkCaptionText.trim()} onClick={() => applyBulkCaptionSplit(false)}>本地规则拆分</button><button type="button" className="btn btn-primary" disabled={captionSplitBusy || !bulkCaptionText.trim()} onClick={() => applyBulkCaptionSplit(true)}>{captionSplitBusy ? "拆分中..." : "AI 优化拆分"}</button></div>
        <small className="caption-bulk-hint">逗号、句号用于拆分且默认不显示在画面；人声保留原文停顿。引号、破折号、省略号等表达符号会保留。AI 优化只在点击后调用 Qwen。</small>
      </div>
      <div className="overlay-logic-callout"><strong>文字 1、文字 2 不是两个节点</strong><span>它们是同一个“声音与文字”节点里的多条画面文字轨道。每条文字只在自己的开始到结束时间内显示，并按下方位置设置叠加到画面；绑定人声可选择自动匹配、不绑定或指定某一段人声。</span></div>
      <div className="overlay-editor-list" onClick={event => { const target = event.target as HTMLElement; if (target.closest(".clip-remove")) return; const header = target.closest(".overlay-editor-head"); if (!header) return; const index = Array.from(event.currentTarget.querySelectorAll(".overlay-editor-head")).indexOf(header); const item = overlayItems[index]; if (item) toggleCard(item.id); }}>{overlayItems.map((item, index) => { const style = overlayStyleFromItem(item); const collapsed = Boolean(collapsedCards[item.id]); return <div className={`overlay-editor-item ${collapsed ? "is-collapsed" : ""}`} key={item.id}>
        <div className="overlay-editor-head" role="button" tabIndex={0} aria-expanded={!collapsed} onClick={event => { event.stopPropagation(); toggleCard(item.id); }} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggleCard(item.id); } }}><span className="overlay-collapse-icon" aria-hidden="true">{collapsed ? "▸" : "▾"}</span><div><strong>文案段 {index + 1}</strong><small>{positionLabel(item.position)} · {item.startSeconds.toFixed(1)}s - {item.endSeconds.toFixed(1)}s · {item.text.trim() || "未填写文案"}</small></div><button type="button" className="clip-remove" aria-label={`删除文案段 ${index + 1}`} onClick={event => { event.stopPropagation(); removeOverlay(item.id); }}>×</button></div>
         <textarea className="input textarea overlay-text-input" rows={3} value={item.text} placeholder="输入画面文案" onChange={event => updateOverlay(item.id, { text: event.target.value })} />
        <label className={`check ${item.enabled !== false ? "checked" : ""}`}><input type="checkbox" checked={item.enabled !== false} onChange={event => updateOverlay(item.id, { enabled: event.target.checked })} />显示文字</label>
        <div className="field-grid"><label className="field"><span>开始（秒）</span><input className="input" type="number" min="0" step="0.1" value={item.startSeconds} onChange={event => updateOverlay(item.id, { startSeconds: Math.max(0, Number(event.target.value) || 0) })} /></label><label className="field"><span>结束（秒）</span><input className="input" type="number" min="0.1" step="0.1" value={item.endSeconds} onChange={event => updateOverlay(item.id, { endSeconds: Math.max(item.startSeconds + 0.1, Number(event.target.value) || item.startSeconds + 0.1) })} /></label></div>
         <div className="field-grid"><Field label="文字效果"><Select value={item.animation === "typewriter" ? "打字机" : "静态"} options={["静态", "打字机"]} onChange={value => updateOverlay(item.id, { animation: value === "打字机" ? "typewriter" : "static" })} /></Field><label className="field"><span>绑定人声</span><select className="input" value={item.syncVoiceId === undefined ? "auto" : item.syncVoiceId || "none"} onChange={event => { const value = event.target.value; updateOverlay(item.id, { syncVoiceId: value === "auto" ? undefined : value === "none" ? "" : value }); }}><option value="auto">自动匹配同序人声</option><option value="none">不绑定人声</option>{voiceItems.filter(voice => !voice.placeholder).map((voice, voiceIndex) => <option key={voice.id} value={voice.id}>人声 {voiceIndex + 1} · {voice.text.trim() || "未填写"}{voice.enabled === false ? "（未启用）" : ""}</option>)}</select></label></div>
        <Field label="初始/快捷位置"><Select value={positionLabel(item.position)} options={OVERLAY_POSITION_OPTIONS.map(option => option.label)} onChange={value => { const position = OVERLAY_POSITION_OPTIONS.find(option => option.label === value)!.value; updateOverlay(item.id, { position, ...overlayPositionCoordinates(position) }); }} /></Field>
        <div className="style-editor"><span className="style-editor-label">文字样式</span><Field label="样式模板"><Select value={stylePresetValue(style)} options={["自定义", ...OVERLAY_STYLE_PRESETS.map(preset => preset.label)]} onChange={value => { const preset = OVERLAY_STYLE_PRESETS.find(item => item.label === value); if (preset) updateOverlayStyle(item.id, preset.style); }} /></Field><div className="field-grid"><Field label="字体"><Select value={style.fontFamily} options={[...OVERLAY_FONT_OPTIONS]} onChange={value => updateOverlayStyle(item.id, { fontFamily: value as OverlayStyle["fontFamily"] })} /></Field><Field label="字号"><input className="input" type="number" min="12" max="120" step="1" value={style.fontSize} onChange={event => updateOverlayStyle(item.id, { fontSize: Math.min(120, Math.max(12, Number(event.target.value) || 42)) })} /></Field></div><div className="field-grid"><Field label="文本框宽度 (%)"><input className="input" type="number" min="30" max="95" step="5" value={Math.round(style.textBoxWidth * 100)} onChange={event => updateOverlayStyle(item.id, { textBoxWidth: Math.min(0.95, Math.max(0.3, (Number(event.target.value) || 84) / 100)) })} /></Field><label className={`check ${style.singleLine ? "checked" : ""}`}><input type="checkbox" checked={style.singleLine} onChange={event => updateOverlayStyle(item.id, { singleLine: event.target.checked })} />单行显示</label></div><div className="field-grid"><label className="field"><span>文字颜色</span><input className="color-input" type="color" value={style.color} onChange={event => updateOverlayStyle(item.id, { color: event.target.value.toUpperCase() })} /></label><Field label="字重"><Select value={style.fontWeight === "bold" ? "粗体" : "常规"} options={["常规", "粗体"]} onChange={value => updateOverlayStyle(item.id, { fontWeight: value === "粗体" ? "bold" : "normal" })} /></Field></div><div className="field-grid"><label className="field"><span>描边颜色</span><input className="color-input" type="color" value={style.strokeColor} onChange={event => updateOverlayStyle(item.id, { strokeColor: event.target.value.toUpperCase() })} /></label><Field label="描边宽度"><input className="input" type="number" min="0" max="12" step="1" value={style.strokeWidth} onChange={event => updateOverlayStyle(item.id, { strokeWidth: Math.min(12, Math.max(0, Number(event.target.value) || 0)) })} /></Field></div><label className={`check ${style.backgroundEnabled ? "checked" : ""}`}><input type="checkbox" checked={style.backgroundEnabled} onChange={event => updateOverlayStyle(item.id, { backgroundEnabled: event.target.checked })} />显示文字背景框</label>{style.backgroundEnabled && <div className="field-grid"><label className="field"><span>背景颜色</span><input className="color-input" type="color" value={style.backgroundColor} onChange={event => updateOverlayStyle(item.id, { backgroundColor: event.target.value.toUpperCase() })} /></label><Field label="背景透明度"><input className="input" type="number" min="0" max="100" step="5" value={Math.round(style.backgroundOpacity * 100)} onChange={event => updateOverlayStyle(item.id, { backgroundOpacity: Math.min(1, Math.max(0, (Number(event.target.value) || 0) / 100)) })} /></Field></div>}</div>
      </div>; })}</div>
      {overlayItems.length === 0 && <div className="empty-state compact">还没有文字，点击“添加文字”创建第一条。</div>}
    </> : <>
      <div className="panel-section-head"><SectionTitle>文案段人声配置</SectionTitle><button type="button" className="btn" onClick={addVoice}>＋ 添加文案段</button></div>
      <div className="overlay-logic-callout"><strong>人声和文字一样按时间段播放</strong><span>每段人声独立设置文案、开始时间、结束时间、音色和音量；例如第一段 0-4 秒，第二段 10-15 秒。</span></div>
      <div className="overlay-editor-list" onClick={event => { const target = event.target as HTMLElement; if (target.closest(".clip-remove")) return; const header = target.closest(".overlay-editor-head"); if (!header) return; const index = Array.from(event.currentTarget.querySelectorAll(".overlay-editor-head")).indexOf(header); const item = voiceItems[index]; if (item) toggleCard(item.id); }}>{voiceItems.map((item, index) => { const collapsed = Boolean(collapsedCards[item.id]); const pairedOverlay = overlayItems[index]; const bindingLabel = pairedOverlay?.enabled === false ? "不显示文字" : pairedOverlay?.syncVoiceId === "" ? "未绑定文字" : pairedOverlay?.syncVoiceId ? `绑定文字 ${overlayItems.findIndex(overlay => overlay.id === pairedOverlay.id) + 1}` : "自动匹配文字"; return <div className={`overlay-editor-item voice-editor-item ${collapsed ? "is-collapsed" : ""}`} key={item.id}>
        <div className="overlay-collapse-summary">{item.text.trim() || "未填写人声文案"}</div>
         <div className="overlay-editor-head"><div><strong>文案段人声 {index + 1}</strong><small>{item.startSeconds.toFixed(1)}s - {item.endSeconds.toFixed(1)}s · {bindingLabel}</small></div><button type="button" className="clip-remove" aria-label={`删除文案段 ${index + 1}`} onClick={() => removeVoice(item.id)}>×</button></div>
        <textarea className="input textarea" value={item.text} placeholder="输入这一段人声文案" onChange={event => updateVoice(item.id, { text: event.target.value })} />
         <label className={`check ${item.enabled !== false && item.voiceId !== "none" ? "checked" : ""}`}><input type="checkbox" checked={item.enabled !== false && item.voiceId !== "none"} onChange={event => { if (event.target.checked && item.voiceId === "none") { onToast("请先选择具体音色，再启用人声"); return; } updateVoice(item.id, { enabled: event.target.checked, ttsDisabledByUser: !event.target.checked }); }} />启用人声</label>
         <small className="voice-toggle-hint">{item.voiceId === "none" ? "当前为“无”，不会生成 TTS；选择音色后即可启用。" : item.enabled === false ? "当前已关闭，仅保留这段文字。" : "当前已启用，将生成这段 TTS。"}</small>
        <div className="field-grid"><label className="field"><span>开始（秒）</span><input className="input" type="number" min="0" step="0.1" value={item.startSeconds} onChange={event => updateVoice(item.id, { startSeconds: Math.max(0, Number(event.target.value) || 0) })} /></label><label className="field"><span>结束（秒）</span><input className="input" type="number" min="0.1" step="0.1" value={item.endSeconds} onChange={event => updateVoice(item.id, { endSeconds: Math.max(item.startSeconds + 0.1, Number(event.target.value) || item.startSeconds + 0.1) })} /></label></div>
        <VoiceModelSelectors item={item} options={ttsOptions} update={patch => updateVoice(item.id, patch)} />
        {ttsOptions.length === 0 && <small className="clip-sync-error">未检测到 Qwen TTS 配置，当前只能选择“无”。</small>}
        <Field label="音量"><input className="range" type="range" min="0" max="100" value={item.volume ?? 85} onChange={event => updateVoice(item.id, { volume: Number(event.target.value) })} /></Field>
      </div>; })}</div>
      {voiceItems.length === 0 && <div className="empty-state compact">还没有人声，点击“添加人声”创建第一段。</div>}
      <Field label="BGM 音量"><input className="range" type="range" min="0" max="100" value={formatNodeValue(data.bgmVolume, "30")} onChange={event => updateNodeData(node.id, { bgmVolume: event.target.value })} /></Field>
      <Field label="BGM"><div className="upload-row"><input className="input" type="file" accept="audio/*,.mp3,.wav,.m4a,.aac" onChange={event => { const file = event.target.files?.[0]; if (!file) return; setBgm(file.name, ""); uploadDraftFile(draftId, file, "audio").then(result => { setBgm(file.name, result.url); onToast(`BGM 已上传：${file.name}`); }).catch(() => { setBgm(file.name, ""); onToast("BGM 上传失败"); }); }} /><span>{bgmName || "未上传"}</span>{bgmUrl && <button type="button" className="clip-remove" aria-label="移除 BGM" onClick={() => { setBgm("", ""); onToast("BGM 已移除"); }}>×</button>}</div></Field>
    </>}
  </>;
}

function TypeFields({ node, onToast }: { node: WorkflowNode; onToast: (message: string) => void }) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const update = (patch: Partial<WorkflowData>) => updateNodeData(node.id, patch);
  const data = node.data;
  if (data.kind === "input") return <AssetFields node={node} onToast={onToast} />;
  if (data.kind === "image_process") return <><SectionTitle>图片处理参数</SectionTitle><ImageProcessControlFields data={data} update={update} /><div className="preview-box">背景模板和执行处理在“图片处理”独立页面完成。{data.processedImageName ? ` 当前结果：${data.processedImageName}` : " 尚未生成处理后首帧。"}{data.processedImageMode === "preserve_original" ? " 当前素材包含人物，已保留原图并跳过抠图。" : ""}</div></>;
  if (data.kind === "prompt") return <PromptFields node={node} onToast={onToast} />;
  if (data.kind === "generator") return <><SectionTitle>视频规格</SectionTitle><Field label="视频时长"><Select value={formatNodeValue(data.duration, "3s")} options={["3s", "5s"]} onChange={value => update({ duration: value })} /></Field><Field label="分辨率"><Select value={formatNodeValue(data.resolution, "1080p")} options={["1080p", "720p"]} onChange={value => update({ resolution: value })} /></Field><Field label="音频"><Select value={formatNodeValue(data.audio, "无声")} options={["无声", "有声"]} onChange={value => update({ audio: value })} /></Field><Field label="分镜"><Select value={formatNodeValue(data.storyboard, "单分镜")} options={["单分镜", "多分镜"]} onChange={value => update({ storyboard: value })} /></Field></>;
  if (data.kind === "output") return <><SectionTitle>视频合成</SectionTitle><Field label="合成目标"><input className="input" value={formatNodeValue(data.outputTarget, "")} onChange={event => update({ outputTarget: event.target.value })} /></Field><Field label="成片时长"><Select value={formatNodeValue(data.outputDuration, "12-15s")} options={["12-15s", "15-20s"]} onChange={value => update({ outputDuration: value })} /></Field><Field label="画幅"><Select value={formatNodeValue(data.outputAspect, "9:16")} options={["9:16", "1:1"]} onChange={value => update({ outputAspect: value })} /></Field></>;
  if (data.kind === "sound") return <SoundFields node={node} onToast={onToast} />;
  return <><SectionTitle>自定义处理</SectionTitle><div className="preview-box">{data.description}</div></>;
}

export function Inspector({ onToast, nodeId, embedded = false }: { onToast: (message: string) => void; nodeId?: string | null; embedded?: boolean }) {
  const nodes = useWorkflowStore(state => state.nodes);
  const selectedNodeId = useWorkflowStore(state => state.selectedNodeId);
  const selectedEdgeId = useWorkflowStore(state => state.selectedEdgeId);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const deleteSelected = useWorkflowStore(state => state.deleteSelected);
  const duplicateSelected = useWorkflowStore(state => state.duplicateSelected);
  const resolvedNodeId = nodeId ?? selectedNodeId;
  const node = nodes.find(item => item.id === resolvedNodeId);
  const className = `inspector${embedded ? " inspector-embedded" : ""}`;
  if (!nodeId && selectedEdgeId) return <aside className={className}><div className="inspector-head"><div><h2>连接线</h2><p>选中后可删除当前连接</p></div></div><button type="button" className="btn btn-danger full" onClick={() => { deleteSelected(); onToast("连接线已删除"); }}>删除连接</button></aside>;
  if (!node) return <aside className={className}><div className="empty-state">选择节点查看可编辑属性</div></aside>;
  const selectCurrentNode = () => setSelection(node.id);
  return <aside className={className}><div className="inspector-head"><div><h2>节点属性</h2><p>{node.data.title} · 可编辑</p></div><Tag>{node.data.kind}</Tag></div><BasicFields node={node} /><TypeFields node={node} onToast={onToast} /><div className="inspector-actions"><button type="button" className="btn btn-primary full" onClick={() => onToast("节点修改已同步到画布")}>保存节点</button><button type="button" className="btn full" onClick={() => { selectCurrentNode(); duplicateSelected(); onToast("节点已复制"); }}>复制节点</button><button type="button" className="btn btn-danger full" onClick={() => { selectCurrentNode(); deleteSelected(); setSelection(null); onToast("节点已删除"); }}>删除节点</button></div></aside>;
}
