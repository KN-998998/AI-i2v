import { useState, type ReactNode } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { inferDishCategory, nodeCatalog, type Panel, type WorkflowNode } from "../model";
import { ACTION_VERB_OPTIONS, assemblePrompt, ELEMENT_OPTIONS, promptConfigFromData, SHOT_SIZE_OPTIONS } from "../promptAssembler";
import { useWorkflowStore } from "../workflowStore";
import { navigate } from "../router";
import { ActionButton, Footer, formatNodeValue, Row, Tag } from "./ui";

export function WorkflowNodeCard({ id, data, selected }: NodeProps<WorkflowNode>) {
  const updateNodeData = useWorkflowStore(state => state.updateNodeData);
  const generateNode = useWorkflowStore(state => state.generateNode);
  const setSelection = useWorkflowStore(state => state.setSelection);
  const setActivePanel = useWorkflowStore(state => state.setActivePanel);
  const activeWorkspace = useWorkflowStore(state => state.composeWorkspaces.find(workspace => workspace.id === state.activeComposeWorkspaceId));
  const legacyBgmName = useWorkflowStore(state => state.bgmName);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const kind = data.kind;
  const promptResult = kind === "prompt" ? assemblePrompt(promptConfigFromData(data)) : null;
  const promptConfig = kind === "prompt" ? promptConfigFromData(data) : null;
  const dishCategory = data.dishCategory ?? (data.dishName ? inferDishCategory(data.dishName) : "正餐");
  const soundConfig = activeWorkspace?.soundConfig;
  const preserveOriginal = data.processingMode === "preserve_original" || data.visualSubjectType === "手部" || data.visualSubjectType === "厨师上半身" || data.visualSubjectType === "手部+厨师上半身";
  const actionLabel = promptConfig && (promptConfig.l1_subject === "hand" || promptConfig.l1_subject === "chef")
    ? ACTION_VERB_OPTIONS.find(item => item.value === promptConfig.l1_action_verb)?.label ?? "动作待选择"
    : null;

  const action = (nextPanel?: Panel) => {
    setSelection(id);
    if (nextPanel) setActivePanel(nextPanel);
  };

  const generate = async () => {
    if (generating) return;
    setGenerationError(null);
    setGenerating(true);
    try {
      await generateNode(id);
    } catch (error) {
      setGenerationError(error instanceof Error ? error.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  const body: Record<typeof kind, ReactNode> = {
    input: <>
      <div className="dish-preview"><div className="dish-image-fallback">{data.imagePreview ? <img src={data.imagePreview} alt={formatNodeValue(data.dishName, "菜品素材")} /> : "素材"}</div></div>
      <Row label="当前菜品" value={formatNodeValue(data.dishName, "未选择菜品")} />
      <Row label="首帧 / 尾帧" value={`${formatNodeValue(data.imageName, "未上传")} / 可选`} />
      <div className="tag-list"><Tag good>{formatNodeValue(data.foodType, "待确认")}</Tag><Tag>{dishCategory}</Tag><Tag>{formatNodeValue(data.visualSubjectType, "菜品主体")}</Tag><Tag>{formatNodeValue(data.assetMode, "单图模式")}</Tag></div>
      <Footer><ActionButton onClick={() => action()}>编辑素材</ActionButton></Footer>
    </>,
    image_process: <>
      <div className="dish-preview"><div className="dish-image-fallback">{data.processedImagePreview ? <img src={data.processedImagePreview} alt="处理后首帧" /> : preserveOriginal && data.imagePreview ? <img src={data.imagePreview} alt="原始动作素材" /> : data.backgroundPreview ? <img src={data.backgroundPreview} alt="背景模板" /> : "待处理"}</div></div>
      <Row label="处理方式" value={preserveOriginal ? "保留原图（动作素材）" : "GoodsMatting 抠图"} />
      {preserveOriginal && <Row label="抠图 / 背景" value="已跳过 / 未应用" />}
      <Row label={preserveOriginal ? "画面主体" : "背景"} value={preserveOriginal ? `${formatNodeValue(data.visualSubjectType, "动作主体")} · 保留原环境` : formatNodeValue(data.backgroundTemplateName, "未选择")} />
      <Row label="输出" value={formatNodeValue(data.processedImageName, "尚未生成") } />
      <Footer><ActionButton primary onClick={() => { setSelection(id); navigate("/workflow/image-processing"); }}>编辑图片处理</ActionButton></Footer>
    </>,
    prompt: <>
      <Row label="L0 画面元素" value={`${promptConfig?.elements.length ?? 0} / 8 项`} />
      <Row label="景别" value={SHOT_SIZE_OPTIONS.find(item => item.value === promptConfig?.shot_size)?.label ?? "特写"} />
      <Row label="L1 主运动" value={promptConfig?.l1_subject === "none" ? "无（纯运镜）" : `${ELEMENT_OPTIONS.find(item => item.id === promptConfig?.l1_subject)?.label ?? "待配置"}${actionLabel ? ` · ${actionLabel}` : ""}`} />
      <Row label="L2 次级动态" value={`${promptConfig?.l2_dynamics.length ?? 0} / 2 项`} />
      <div className="tag-list"><Tag good={!promptResult?.blocked} warn={Boolean(promptResult?.blocked)}>{promptResult?.blocked ? `阻断 ${promptResult.errors[0]?.code ?? ""}` : "校验通过"}</Tag>{promptResult?.warnings.slice(0, 1).map(warning => <Tag warn key={warning.code}>{warning.code}</Tag>)}</div>
      <Footer><ActionButton onClick={() => action("prompt")}>编辑槽位</ActionButton><ActionButton primary onClick={() => updateNodeData(id, { status: "已装配" })}>实时装配</ActionButton></Footer>
    </>,
    generator: <>
      <Row label="规格" value={`${formatNodeValue(data.duration, "3s")} · ${formatNodeValue(data.resolution, "1080p")}`} />
      <Row label="音频 / 分镜" value={`${formatNodeValue(data.audio, "无声")} / ${formatNodeValue(data.storyboard, "单分镜")}`} />
      {generationError && <Tag warn>{generationError}</Tag>}
      <Footer><ActionButton primary onClick={generate}>{generating ? "生成中..." : data.status === "已生成" ? "再次生成" : "生成片段"}</ActionButton></Footer>
    </>,
    output: <>
      <Row label="目标" value={formatNodeValue(data.outputTarget, "5-6 道菜")} />
      <Row label="时长 / 画幅" value={`${formatNodeValue(data.outputDuration, "12-15s")} / ${formatNodeValue(data.outputAspect, "9:16")}`} />
      <Footer><ActionButton primary onClick={() => { setSelection(id); navigate("/workflow/compose"); }}>进入合成</ActionButton></Footer>
    </>,
    sound: <>
      <Row label="BGM" value={soundConfig?.bgmName ?? legacyBgmName ?? "未上传"} />
      <Row label="人声 / 文字" value={`${formatNodeValue(soundConfig?.voiceName ?? data.voiceName, "无")} / ${formatNodeValue(soundConfig?.overlayMain ?? data.overlayMain, "未设置")}`} />
      <Footer><ActionButton onClick={() => action("voice")}>编辑声音</ActionButton><ActionButton onClick={() => action("overlay")}>编辑文字</ActionButton></Footer>
    </>,
    custom: <><Row label="类型" value={data.title} /><Row label="状态" value="草稿" /><p className="node-description">{data.description}</p><Footer><ActionButton onClick={() => action()}>编辑属性</ActionButton></Footer></>,
  };

  return <article className={`workflow-node-card ${selected ? "selected" : ""}`}>
    {kind !== "input" && <Handle type="target" position={Position.Left} className="workflow-handle" />}
    {kind !== "sound" && <Handle type="source" position={Position.Right} className="workflow-handle" />}
    <div className="node-head"><div><div className="node-kicker">{nodeCatalog[kind].kicker}</div><div className="node-title">{data.title}</div></div><span className="node-status">{data.status}</span></div>
    <div className="node-body">{body[kind]}</div>
  </article>;
}
