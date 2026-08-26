export type PromptMode = "single_image" | "keyframes";
export type CameraMove = "dolly_in" | "dolly_out" | "crane_down" | "crane_up" | "truck_left" | "truck_right" | "orbit_right" | "locked_off";
export type Amplitude = "subtle" | "light" | "medium";
export type ShotSize = "close_up" | "medium_close" | "medium" | "wide";
export type ElementId = "dish_cold" | "dish_hot" | "garnish" | "tableware" | "surface" | "hand" | "chef" | "backdrop";
export type L1Subject = "dish_cold" | "dish_hot" | "tableware" | "hand" | "chef" | "none";
export type ActionLevel = 1 | 2 | 3;
export type ActionVerb = "sprinkle_seasoning" | "pour_sauce" | "steady_plate" | "rotate_plate" | "pick_food" | "cut_slice" | "lift_plate" | "place_garnish";
export type L2Type = "steam" | "liquid_pour" | "liquid_ripple" | "flame" | "ice_mist" | "specular" | "fabric_sway" | "person_idle";
export type SpeedCurve = "uniform" | "ease_in" | "ease_out";

export type L2Item = { type: L2Type; target: string };

export type PromptConfig = {
  mode: PromptMode;
  camera_move: CameraMove;
  camera_amplitude: Amplitude;
  shot_size: ShotSize;
  elements: ElementId[];
  l1_subject: L1Subject;
  l1_action_level: ActionLevel | null;
  l1_action_verb: ActionVerb | null;
  l2_dynamics: L2Item[];
  speed_curve: SpeedCurve | null;
  seamless_loop: boolean;
  endImageReady?: boolean;
};

export type PromptIssue = { code: string; message: string; field: string };

export type PromptResult = {
  blocked: boolean;
  errors: PromptIssue[];
  warnings: PromptIssue[];
  prompt: string;
  negative_prompt: string;
  cfg_scale: number;
};

export const ELEMENT_OPTIONS: ReadonlyArray<{ id: ElementId; label: string; lockLabel: string; canBeL1: boolean }> = [
  { id: "dish_cold", label: "菜品主体·冷食", lockLabel: "菜品", canBeL1: true },
  { id: "dish_hot", label: "菜品主体·热食", lockLabel: "菜品", canBeL1: true },
  { id: "garnish", label: "配菜／装饰", lockLabel: "配菜与装饰", canBeL1: false },
  { id: "tableware", label: "餐具器皿", lockLabel: "餐具器皿", canBeL1: true },
  { id: "surface", label: "桌面／台面", lockLabel: "桌面", canBeL1: false },
  { id: "hand", label: "手部", lockLabel: "手部", canBeL1: true },
  { id: "chef", label: "厨师上半身", lockLabel: "人物", canBeL1: true },
  { id: "backdrop", label: "背景陈设", lockLabel: "背景陈设", canBeL1: false },
];

export const CAMERA_OPTIONS: ReadonlyArray<{ value: CameraMove; label: string; text: string }> = [
  { value: "dolly_in", label: "缓慢推进", text: "缓慢推进（dolly in）" },
  { value: "dolly_out", label: "缓慢后拉", text: "缓慢后拉（dolly out）" },
  { value: "crane_down", label: "缓慢俯视下降", text: "缓慢俯视下降（crane down）" },
  { value: "crane_up", label: "缓慢上升", text: "缓慢上升（crane up）" },
  { value: "truck_left", label: "极小幅左横移", text: "极小幅左横移（truck left）" },
  { value: "truck_right", label: "极小幅右横移", text: "极小幅右横移（truck right）" },
  { value: "orbit_right", label: "小角度顺时针环绕", text: "小角度顺时针环绕（orbit right）" },
  { value: "locked_off", label: "固定机位", text: "固定机位不动（locked-off）" },
];

export const AMPLITUDE_OPTIONS: ReadonlyArray<{ value: Amplitude; label: string; text: string }> = [
  { value: "subtle", label: "极轻微（约8%）", text: "画面极轻微变化（约8%）" },
  { value: "light", label: "轻微（约15%）", text: "画面轻微变化（约15%）" },
  { value: "medium", label: "中等（约25%）", text: "画面中等变化（约25%）" },
];

export const SHOT_SIZE_OPTIONS: ReadonlyArray<{ value: ShotSize; label: string; text: string }> = [
  { value: "close_up", label: "特写", text: "特写，菜品主体约占画面70%-85%，突出食材质感与细节，保持原图构图和主体位置不变" },
  { value: "medium_close", label: "近景", text: "近景，菜品主体约占画面55%-70%，兼顾菜品细节与摆盘关系，保持原图构图和主体位置不变" },
  { value: "medium", label: "中景", text: "中景，菜品主体约占画面35%-55%，保留餐具与桌面环境，保持原图构图和主体位置不变" },
  { value: "wide", label: "远景", text: "远景，菜品主体约占画面20%-35%，展示完整餐桌与环境氛围，保持原图构图和主体位置不变" },
];

export const ACTION_LEVEL_OPTIONS: ReadonlyArray<{ value: ActionLevel; label: string }> = [
  { value: 1, label: "存在感级" },
  { value: 2, label: "片段级" },
  { value: 3, label: "完整级" },
];

export const ACTION_VERB_OPTIONS: ReadonlyArray<{ value: ActionVerb; label: string }> = [
  { value: "sprinkle_seasoning", label: "撒落调味" },
  { value: "pour_sauce", label: "淋下酱汁" },
  { value: "steady_plate", label: "轻扶盘沿" },
  { value: "rotate_plate", label: "缓慢转动餐盘" },
  { value: "pick_food", label: "夹起食材" },
  { value: "cut_slice", label: "切下一刀" },
  { value: "lift_plate", label: "端起餐盘" },
  { value: "place_garnish", label: "摆放装饰" },
];

export const L2_OPTIONS: ReadonlyArray<{ value: L2Type; label: string; text: string; negative: string }> = [
  { value: "steam", label: "热气／蒸汽", text: "极轻缓热气自{T}持续缓慢上升，不成团、不遮挡主体", negative: "浓烟, 白雾遮挡, 云雾成团, 烟雾旋转" },
  { value: "liquid_pour", label: "液体·倾倒", text: "细流从{T}匀速落下，落点固定，流量恒定", negative: "飞溅, 液体倒流, 液面暴涨, 外溢, 容器变形, 液体凭空出现" },
  { value: "liquid_ripple", label: "液体·晃动", text: "{T}表面极轻微晃动，反光随之位移，液面不溢出", negative: "沸腾, 翻涌, 液面剧烈起伏, 溢出" },
  { value: "flame", label: "火焰／炙烤", text: "{T}处小簇火焰边缘轻微摇曳，火势范围不变", negative: "火势蔓延, 冒黑烟, 食材碳化, 焦化加深, 爆燃" },
  { value: "ice_mist", label: "冰雾／冷凝", text: "极淡冷雾贴{T}表面缓慢流动，冷凝水珠保持附着不滑落", negative: "水珠滑落, 结霜蔓延, 融化, 白雾弥漫" },
  { value: "specular", label: "高光滑移", text: "{T}湿润表面高光随镜头角度缓慢滑移", negative: "" },
  { value: "fabric_sway", label: "织物／植物飘动", text: "{T}边缘极轻微自然飘动", negative: "剧烈飘动, 形变" },
  { value: "person_idle", label: "人物微动", text: "{T}保持姿态不变，仅极轻微呼吸起伏与自然眨眼", negative: "五官变形, 手指畸形, 表情夸张, 身体扭曲" },
];

export const SPEED_CURVE_OPTIONS: ReadonlyArray<{ value: SpeedCurve; label: string; text: string }> = [
  { value: "uniform", label: "全程匀速（推荐）", text: "全程匀速" },
  { value: "ease_in", label: "慢起匀速收", text: "慢起后转匀速" },
  { value: "ease_out", label: "匀速慢收", text: "匀速后自然减速" },
];

const L1_SINGLE: Record<Exclude<L1Subject, "hand" | "chef">, string> = {
  dish_cold: "菜品与摆盘保持原位不动，仅湿润切面高光随镜头角度缓慢滑移",
  dish_hot: "菜品保持原位不动，仅表面油光随镜头角度缓慢流动",
  tableware: "餐具保持原位不动，仅釉面与金属反光随镜头角度缓慢滑过",
  none: "画面内所有元素保持完全静止，仅视角发生变化",
};

const L1_KEYFRAMES: Record<Exclude<L1Subject, "hand" | "chef">, string> = {
  dish_cold: "菜品位置与形态不变，仅视角与高光从首帧状态连续过渡到尾帧状态",
  dish_hot: "菜品位置与形态不变，仅视角与高光从首帧状态连续过渡到尾帧状态",
  tableware: "餐具位置不变，仅反光与视角从首帧状态连续过渡到尾帧状态",
  none: "镜头从首帧机位连续{camera}至尾帧机位",
};

const ACTION_SINGLE: Record<ActionLevel, string> = {
  1: "{S}保持当前姿势与握持关系不变，仅有极轻微自然稳定微动",
  2: "{S}做出{V}的动作片段，动作缓慢连贯，握持关系不变，动作不完成",
  3: "{S}在三秒内缓慢完成一次{V}并自然停住",
};

const ACTION_KEYFRAMES: Record<ActionLevel, string> = {
  1: "{S}姿态从首帧连续过渡到尾帧，过程中仅有极轻微自然微动",
  2: "{S}连贯自然地从首帧姿态过渡到尾帧姿态，完成{V}的动作片段，中途不停顿、不回退",
  3: "{S}连贯自然地从首帧姿态过渡到尾帧姿态，完成一次{V}，中途不停顿、不回退",
};

const BASE_NEGATIVE = "变形，融化，收缩，蠕动，主体位移，新增元素，元素消失，多余的手，文字，logo，水印，抖动，晃动，快速运镜，镜头切换，分镜，画面跳变，曝光跳变，闪烁，重新打光，色彩漂移，涂抹感，二次构图，画质劣化";
const KEYFRAME_NEGATIVE = "闪切，跳帧，转场特效，叠化，画面突变，中途重构，动作回退";
const HAND_NEGATIVE = "面部入镜，人物面部，全身入镜";

export const DEFAULT_PROMPT_CONFIG: PromptConfig = {
  mode: "single_image",
  camera_move: "orbit_right",
  camera_amplitude: "subtle",
  shot_size: "close_up",
  elements: ["dish_hot", "garnish", "tableware", "surface", "backdrop"],
  l1_subject: "dish_hot",
  l1_action_level: null,
  l1_action_verb: null,
  l2_dynamics: [{ type: "specular", target: "菜品" }],
  speed_curve: null,
  seamless_loop: false,
  endImageReady: false,
};

function issue(code: string, message: string, field: string): PromptIssue {
  return { code, message, field };
}

function element(id: ElementId | string) {
  return ELEMENT_OPTIONS.find(item => item.id === id);
}

function l2Type(type: L2Type) {
  return L2_OPTIONS.find(item => item.value === type);
}

function normalizeConfig(config: PromptConfig): PromptConfig {
  return {
    ...config,
    shot_size: SHOT_SIZE_OPTIONS.some(item => item.value === config.shot_size) ? config.shot_size : DEFAULT_PROMPT_CONFIG.shot_size,
    elements: [...config.elements],
    l2_dynamics: config.l2_dynamics.map(item => ({ ...item })),
  };
}

function validateTarget(target: string): boolean {
  const value = target.trim();
  if (value.length < 1 || value.length > 8) return false;
  if (![...value].every(char => /[\p{L}\p{N}]/u.test(char))) return false;
  return !["若", "如果", "则", "当", "存在", "或者", "否则", "不", "无", "没有", "禁止"].some(word => value.includes(word));
}

function blockingRules(config: PromptConfig): PromptIssue[] {
  const errors: PromptIssue[] = [];
  const l1 = element(config.l1_subject);
  if (config.l1_subject !== "none" && !config.elements.includes(config.l1_subject)) errors.push(issue("V1", "主运动对象必须先在画面元素中勾选", "l1_subject"));
  if (config.l2_dynamics.length > 2) errors.push(issue("V2", "3 秒最多承载 2 个次级动态，超出会导致每项都退化为轻微抖动", "l2_dynamics"));
  for (const item of config.l2_dynamics) {
    if (l1?.lockLabel === item.target) {
      const dishSurfaceException = (config.l1_subject === "dish_cold" || config.l1_subject === "dish_hot") && (item.type === "steam" || item.type === "specular");
      if (!dishSurfaceException) {
        errors.push(issue("V3", "次级动态不能指向主运动对象，二者会互相抵消", "l2_dynamics"));
        break;
      }
    }
  }
  const types = config.l2_dynamics.map(item => item.type);
  if (types.includes("flame") && types.includes("ice_mist")) errors.push(issue("V4", "火焰与冰雾互斥，不能同时生成", "l2_dynamics"));
  if (config.seamless_loop && (types.includes("liquid_pour") || (config.l1_action_level ?? 0) >= 2)) errors.push(issue("V5", "无缝循环要求首尾状态一致，与不可逆动作冲突", "seamless_loop"));
  if (config.l1_action_level !== null && !["hand", "chef"].includes(config.l1_subject)) errors.push(issue("V6", "动作幅度仅适用于手部或厨师主体", "l1_action_level"));
  if (config.mode === "keyframes" && !config.endImageReady) errors.push(issue("V7", "首尾帧模式需要上传尾帧图片", "end_image"));
  if (config.mode === "single_image" && config.speed_curve !== null) errors.push(issue("V8", "速度曲线仅适用于首尾帧模式", "speed_curve"));
  if (config.l2_dynamics.some(item => !validateTarget(item.target))) errors.push(issue("V9", "作用对象只能填写简短名词（1-8字，无标点，无条件/否定词）", "l2_dynamics"));
  if ([2, 3].includes(config.l1_action_level ?? 0) && !config.l1_action_verb) errors.push(issue("V10", "请选择具体动作", "l1_action_verb"));
  if (config.elements.length === 0) errors.push(issue("V11", "请至少勾选一项画面元素", "elements"));
  if (config.seamless_loop && !["truck_left", "truck_right", "locked_off"].includes(config.camera_move)) errors.push(issue("V12", "无缝循环仅支持极小幅横移或固定机位（推进／后拉无法闭环）", "camera_move"));
  return errors;
}

function warningRules(config: PromptConfig): PromptIssue[] {
  const warnings: PromptIssue[] = [];
  const types = config.l2_dynamics.map(item => item.type);
  if (types.includes("liquid_pour") && config.camera_move === "dolly_in") warnings.push(issue("W1", "推进会拉长流体运动路径，飞溅风险较高，建议改用固定机位", "camera_move"));
  if (config.mode === "single_image" && config.l1_action_level === 3) warnings.push(issue("W2", "单图模式下模型需自行编造动作终点，3 秒内成片率较低。建议改用首尾帧模式，由尾帧给定终点", "mode"));
  if (config.elements.length < 2) warnings.push(issue("W3", "画面元素勾选过少，锁定层约束偏弱，非主体元素可能出现意外变化", "elements"));
  if (config.camera_move === "locked_off" && config.camera_amplitude !== "subtle") warnings.push(issue("W4", "固定机位下运动幅度设置无效，将被忽略", "camera_amplitude"));
  if (config.mode === "single_image" && config.l1_subject === "none" && config.l2_dynamics.length === 0) warnings.push(issue("W5", "当前配置下画面几乎完全静止，生成结果可能接近静态图", "l1_subject"));
  return warnings;
}

function lockedSet(config: PromptConfig): string[] {
  const targets = new Set(config.l2_dynamics.map(item => item.target));
  const removed = config.l1_subject === "none" ? new Set<string>() : new Set([element(config.l1_subject)?.lockLabel]);
  const result: string[] = [];
  for (const item of config.elements.map(element).filter(Boolean)) {
    const label = item!.lockLabel;
    if (!removed.has(label) && !targets.has(label) && !result.includes(label)) result.push(label);
  }
  return result;
}

function actionText(config: PromptConfig): string {
  const subject = config.l1_subject === "hand" ? "手" : config.l1_subject === "chef" ? "厨师" : "";
  if (subject) {
    const level = config.l1_action_level ?? 1;
    const verb = ACTION_VERB_OPTIONS.find(item => item.value === config.l1_action_verb)?.label ?? "";
    const template = (config.mode === "keyframes" ? ACTION_KEYFRAMES : ACTION_SINGLE)[level];
    const text = template.replace("{S}", subject).replace("{V}", verb);
    return config.l1_subject === "chef" ? `${text}，面部表情平静自然，五官稳定` : text;
  }
  const table = config.mode === "keyframes" ? L1_KEYFRAMES : L1_SINGLE;
  const text = table[config.l1_subject as Exclude<L1Subject, "hand" | "chef">] ?? "";
  return config.l1_subject === "none" && config.mode === "keyframes" ? text.replace("{camera}", CAMERA_OPTIONS.find(item => item.value === config.camera_move)?.text ?? "") : text;
}

function dynamicText(config: PromptConfig): string[] {
  return config.l2_dynamics.map(item => (l2Type(item.type)?.text ?? "").replace("{T}", item.target));
}

function buildPrompt(config: PromptConfig, locked: string[]): string {
  const dynamics = dynamicText(config);
  const sections: string[] = [];
  sections.push(`【景别】${SHOT_SIZE_OPTIONS.find(item => item.value === config.shot_size)?.text ?? SHOT_SIZE_OPTIONS[0].text}。`);
  if (config.mode === "single_image") {
    if (config.camera_move === "locked_off") sections.push("【镜头】固定机位不动（locked-off），画面构图保持不变。");
    else sections.push(`【镜头】${CAMERA_OPTIONS.find(item => item.value === config.camera_move)?.text ?? ""}，极慢匀速，单镜头一镜到底，${AMPLITUDE_OPTIONS.find(item => item.value === config.camera_amplitude)?.text ?? ""}。`);
    sections.push(`【主运动】${actionText(config)}。`);
    if (dynamics.length) sections.push(`【次级动态】${dynamics.join("；")}，幅度极小，不影响主体形态。`);
    if (locked.length) sections.push(`【锁定】${locked.join("、")}保持绝对静止，位置、数量、形状、颜色不变。`);
    sections.push("【光线】光源固定，明暗关系不变，无重新打光。");
    sections.push(config.seamless_loop ? "【节奏】动作与运镜同步开始，全程匀速连续，首尾画面状态接近，可无缝循环。" : "【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。");
  } else {
    sections.push("【过渡】从首帧画面平滑连续过渡到尾帧画面，单镜头一镜到底，无切换、无叠化。");
    sections.push(`【主运动】${actionText(config)}，${SPEED_CURVE_OPTIONS.find(item => item.value === (config.speed_curve ?? "uniform"))?.text ?? "全程匀速"}。`);
    if (dynamics.length) sections.push(`【次级动态】${dynamics.join("；")}，全程连续不中断。`);
    if (locked.length) sections.push(`【锁定】${locked.join("、")}在整个过渡过程中保持位置与形态不变。`);
    sections.push("【光线】光源固定，明暗随视角连续渐变，不跳变。");
    sections.push("【节奏】过渡末端稳定停在尾帧状态。");
  }
  return sections.join("\n");
}

function buildNegative(config: PromptConfig): string {
  const parts = [BASE_NEGATIVE];
  if (config.mode === "keyframes") parts.push(KEYFRAME_NEGATIVE);
  if (config.l1_subject === "hand") parts.push(HAND_NEGATIVE);
  config.l2_dynamics.forEach(item => { const negative = l2Type(item.type)?.negative; if (negative) parts.push(negative); });
  const words: string[] = [];
  parts.join("，").split(/[，,]\s*/).forEach(word => { if (word && !words.includes(word)) words.push(word); });
  return words.join("，");
}

function cfgScale(config: PromptConfig): number {
  if (config.mode === "keyframes") return 0.45;
  if (["dish_cold", "dish_hot", "tableware", "none"].includes(config.l1_subject)) return 0.70;
  return ({ 1: 0.60, 2: 0.50, 3: 0.40 } as Record<ActionLevel, number>)[config.l1_action_level ?? 1];
}

export function assemblePrompt(input: PromptConfig): PromptResult {
  const config = normalizeConfig(input);
  const errors = blockingRules(config);
  const warnings = warningRules(config);
  if (errors.length) return { blocked: true, errors, warnings, prompt: "", negative_prompt: "", cfg_scale: 0 };
  return { blocked: false, errors: [], warnings, prompt: buildPrompt(config, lockedSet(config)), negative_prompt: buildNegative(config), cfg_scale: cfgScale(config) };
}

type LegacyPromptData = {
  promptConfig?: PromptConfig;
  promptMode?: string;
  promptL0?: string[];
  promptMotion?: string;
  promptAmplitude?: string;
  promptShotSize?: string;
  promptL1?: string;
  promptL1ActionLevel?: ActionLevel | null;
  promptL1ActionVerb?: string | null;
  promptL2Type1?: string;
  promptL2Target1?: string;
  promptL2Type2?: string;
  promptL2Target2?: string;
  promptSpeedCurve?: SpeedCurve | null;
  promptSeamlessLoop?: boolean;
  promptEndImageName?: string;
  promptEndImagePreview?: string;
};

const findByLabel = <T extends { label: string }>(items: ReadonlyArray<T>, value: string | undefined, fallback: T): T => items.find(item => item.label === value) ?? fallback;

export function promptConfigFromData(data: LegacyPromptData): PromptConfig {
  if (data.promptConfig) return normalizeConfig(data.promptConfig);
  const camera = findByLabel(CAMERA_OPTIONS, data.promptMotion, CAMERA_OPTIONS[6]);
  const amplitude = findByLabel(AMPLITUDE_OPTIONS, data.promptAmplitude?.replace("约 8%", "约8%"), AMPLITUDE_OPTIONS[0]);
  const shotSize = findByLabel(SHOT_SIZE_OPTIONS, data.promptShotSize, SHOT_SIZE_OPTIONS[0]);
  const mode: PromptMode = data.promptMode === "首尾帧模式" ? "keyframes" : "single_image";
  const elements = ELEMENT_OPTIONS.filter(item => data.promptL0?.includes(item.label.replace("／", "/")) || data.promptL0?.includes(item.label)).map(item => item.id);
  const subjectOption = ELEMENT_OPTIONS.find(item => item.label === data.promptL1 && item.canBeL1);
  const subject: L1Subject = (subjectOption?.id as L1Subject | undefined) ?? (data.promptL1 === "无（纯运镜）" ? "none" : "dish_hot");
  const l2: L2Item[] = [];
  for (const [typeValue, targetValue] of [[data.promptL2Type1, data.promptL2Target1], [data.promptL2Type2, data.promptL2Target2]]) {
    const type = L2_OPTIONS.find(item => item.label === typeValue || item.label.replace("／", " / ") === typeValue);
    if (type && typeValue !== "无" && typeValue !== "（无）") l2.push({ type: type.value, target: targetValue || "菜品" });
  }
  return {
    ...DEFAULT_PROMPT_CONFIG,
    mode,
    camera_move: camera.value,
    camera_amplitude: amplitude.value,
    shot_size: shotSize.value,
    elements: elements.length ? elements : [...DEFAULT_PROMPT_CONFIG.elements],
    l1_subject: subject,
    l1_action_level: data.promptL1ActionLevel ?? null,
    l1_action_verb: ACTION_VERB_OPTIONS.some(item => item.value === data.promptL1ActionVerb) ? data.promptL1ActionVerb as ActionVerb : null,
    l2_dynamics: l2,
    speed_curve: mode === "keyframes" ? (data.promptSpeedCurve ?? "uniform") : null,
    seamless_loop: data.promptSeamlessLoop ?? false,
    endImageReady: Boolean(data.promptEndImageName || data.promptEndImagePreview),
  };
}

export type PromptLegacyPatch = Omit<LegacyPromptData, "promptL1ActionVerb"> & { promptL1ActionVerb?: ActionVerb | null };

export function promptLegacyPatch(config: PromptConfig): PromptLegacyPatch {
  const l2 = [config.l2_dynamics[0], config.l2_dynamics[1]];
  const labelFor = (id: ElementId) => element(id)?.label ?? id;
  const subject = config.l1_subject === "none" ? "无（纯运镜）" : labelFor(config.l1_subject);
  const camera = CAMERA_OPTIONS.find(item => item.value === config.camera_move)!;
  const amplitude = AMPLITUDE_OPTIONS.find(item => item.value === config.camera_amplitude)!;
  const shotSize = SHOT_SIZE_OPTIONS.find(item => item.value === config.shot_size) ?? SHOT_SIZE_OPTIONS[0];
  const l2Label = (item: L2Item | undefined) => item ? l2Type(item.type)?.label ?? item.type : "（无）";
  return {
    promptMode: config.mode === "keyframes" ? "首尾帧模式" : "单图模式",
    promptL0: config.elements.map(labelFor),
    promptMotion: camera.label,
    promptAmplitude: amplitude.label,
    promptShotSize: shotSize.label,
    promptL1: subject,
    promptL1ActionLevel: config.l1_action_level,
    promptL1ActionVerb: config.l1_action_verb,
    promptL2Type1: l2Label(l2[0]),
    promptL2Target1: l2[0]?.target ?? "菜品",
    promptL2Type2: l2Label(l2[1]),
    promptL2Target2: l2[1]?.target ?? "菜品",
    promptSpeedCurve: config.speed_curve,
    promptSeamlessLoop: config.seamless_loop,
  };
}
