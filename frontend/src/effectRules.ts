// ---------------------------------------------------------------------------
// 第 3 步「动态效果」的规则：每道菜的效果按它自己的冷热和画面主体现算，
// 不再把某一次选好的配置存死在提示词节点里。
//
// 起因（Patrick 2026-09-21 实测）：模板是在知道这道菜是冷食之前建的，存的是热菜
// 写法，冷的玉子寿司拿到的指令是「仅表面油光随镜头角度缓慢流动」；批量生产又把
// 样板的提示词节点原样复制给每道菜，样板选了「热气升腾」的话冷菜也照样冒热气，
// 校验还不拦。
//
// 后端 pipeline/prompt_presets.py 是这一份的 Python 版，两边由
// tests/fixtures/effect_presets.json（272 条）逐项锁住，改一边另一边会立刻红。
// ---------------------------------------------------------------------------
import { applyPromptPreset, availablePromptPresets, DEFAULT_PROMPT_CONFIG, type PromptConfig, type PromptPresetId } from "./promptAssembler.ts";
import type { WorkflowNode } from "./model.ts";

export type EffectClass = "cold" | "hot" | "mixed" | "person";
export type EffectMode = "rule" | "custom";
export type EffectRules = Partial<Record<EffectClass, PromptPresetId>>;

/** 提示词节点上跟效果有关的那几个字段（就是 WorkflowData 的子集，这里不反向依赖它）。 */
export type EffectPromptData = { effectMode?: EffectMode; effectRules?: EffectRules; promptConfig?: PromptConfig };
/** 这条生成链自己的素材节点：冷热和画面主体只认它，不认提示词节点里存着的旧值。 */
export type EffectInputData = { dishName?: string; foodType?: string; visualSubjectType?: string };

// 冷菜和没标冷热的都用光泽流转：它对任何菜都成立，也是参考片里最常见的镜头。
// 热菜用热气升腾。原图有手或厨师时同样用光泽流转——人保持姿势不动，只有高光在走，
// 让 AI 去动一只手远比让它动高光容易出废片。
export const DEFAULT_EFFECT_RULES: Record<EffectClass, PromptPresetId> = { cold: "glow", hot: "steam", mixed: "glow", person: "glow" };

export const EFFECT_CLASS_LABELS: Record<EffectClass, string> = {
  cold: "冷菜",
  hot: "热菜",
  mixed: "冷热混合（套餐）",
  person: "原图有手或厨师",
};

const PERSON_SUBJECTS = ["手部", "厨师上半身", "手部+厨师上半身"];
const VISUAL_SUBJECTS = ["菜品主体", ...PERSON_SUBJECTS];
const FOOD_TYPES = ["冷食", "热食", "混合/多温"];

/** 画面主体：认不出来的值（没填、乱填）一律当「菜品主体」，和 promptAssembler 的归一化一致。 */
function normalizedVisual(value: string | undefined): string {
  return VISUAL_SUBJECTS.includes(value ?? "") ? (value as string) : "菜品主体";
}

function normalizedFood(value: string | undefined): string {
  return FOOD_TYPES.includes(value ?? "") ? (value as string) : "";
}

/** 判断「这个效果这道菜用不用得了」的那份底子，口径和 availablePromptPresets 一致。 */
function availabilityConfig(foodType: string | undefined, visualSubjectType: string | undefined): PromptConfig {
  const food = normalizedFood(foodType);
  return {
    ...DEFAULT_PROMPT_CONFIG,
    visual_subject_type: normalizedVisual(visualSubjectType) as PromptConfig["visual_subject_type"],
    ...(food ? { food_type: food as PromptConfig["food_type"] } : {}),
  };
}

/**
 * 四类菜。原图有手或厨师的单独一类：它能不能淋酱、撒料，跟冷热无关。
 * 没标冷热的归入「冷热混合」，因为这一类的默认效果冷热两边都成立。
 */
export function effectClassFor(foodType?: string, visualSubjectType?: string): EffectClass {
  if (PERSON_SUBJECTS.includes(visualSubjectType ?? "")) return "person";
  const food = normalizedFood(foodType);
  if (food === "冷食") return "cold";
  if (food === "热食") return "hot";
  return "mixed";
}

/**
 * 这道菜该用的效果：先看样板规则里它那一类改成了什么，没改过就用默认。
 * 取到的效果这道菜用不了时（冷菜配到热气升腾、没有手的图配到淋酱）退回光泽流转——
 * 宁可退回一个一定成立的效果，也不要让页面上写着一个生成时会被校验拦掉的效果。
 */
export function presetForDish(foodType?: string, visualSubjectType?: string, rules?: EffectRules): PromptPresetId {
  const wanted = rules?.[effectClassFor(foodType, visualSubjectType)] ?? DEFAULT_EFFECT_RULES[effectClassFor(foodType, visualSubjectType)];
  const usable = availablePromptPresets(availabilityConfig(foodType, visualSubjectType)).some(preset => preset.id === wanted);
  return usable ? wanted : "glow";
}

/** 菜品主体元素跟着这道菜的冷热走；混合和没标冷热的不动，套餐里两种都可能是对的。 */
function matchDishTemperature(config: PromptConfig, foodType: string): PromptConfig {
  if (foodType !== "冷食" && foodType !== "热食") return config;
  const wanted = foodType === "冷食" ? "dish_cold" : "dish_hot";
  const stale = foodType === "冷食" ? "dish_hot" : "dish_cold";
  return {
    ...config,
    elements: config.elements.map(item => item === stale ? wanted : item).filter((item, index, list) => list.indexOf(item) === index),
    l1_subject: config.l1_subject === stale ? wanted : config.l1_subject,
  };
}

/**
 * 有手或厨师入镜时，主运动对象必须是人物，不然校验会拦。
 * 原来这段逻辑同时长在 workflowStore 和后端 _prompt_data_for_asset 里，现在只留这一份。
 */
export function promptConfigForVisualSubject(config: PromptConfig, visualSubjectType: string | undefined): PromptConfig {
  const visual = normalizedVisual(visualSubjectType) as PromptConfig["visual_subject_type"];
  if (visual === "菜品主体") return { ...config, visual_subject_type: visual };
  const required: PromptConfig["elements"] = visual === "手部" ? ["hand"] : visual === "厨师上半身" ? ["chef"] : ["hand", "chef"];
  const elements = [...config.elements];
  required.forEach(item => { if (!elements.includes(item)) elements.push(item); });
  const allowed = visual === "厨师上半身" ? ["chef"] : ["hand", "chef"];
  const subject = allowed.includes(config.l1_subject) ? config.l1_subject : visual === "厨师上半身" ? "chef" : "hand";
  return {
    ...config,
    visual_subject_type: visual,
    elements,
    l1_subject: subject,
    l1_action_level: config.l1_action_level ?? 2,
    l1_action_verb: config.l1_action_verb ?? (subject === "chef" ? "lift_plate" : "steady_plate"),
  };
}

/**
 * 这道菜实际会用的配置。
 *
 * 规则模式（`effectMode` 是 "rule"，或者根本没有这个字段——所有老草稿都是这样）：
 * 现算。节点里存着的 promptConfig 只取 mode（首尾帧时再取 speed_curve 和尾帧状态），
 * 其余一律不看，免得再出现「模板存的是热菜写法、这道菜其实是冷食」那种对不上。
 *
 * 自定义模式：在高级设置里手调过，按存着的配置原样用，只把冷热和人物对上这道菜自己的。
 */
export function effectivePromptConfig(promptData: EffectPromptData, inputData: EffectInputData): PromptConfig {
  const stored = promptData.promptConfig;
  const visual = normalizedVisual(inputData.visualSubjectType) as PromptConfig["visual_subject_type"];
  const food = normalizedFood(inputData.foodType);
  if (promptData.effectMode === "custom") {
    const base: PromptConfig = {
      ...(stored ?? DEFAULT_PROMPT_CONFIG),
      ...(food ? { food_type: food as PromptConfig["food_type"] } : {}),
      elements: [...(stored ?? DEFAULT_PROMPT_CONFIG).elements],
      l2_dynamics: (stored ?? DEFAULT_PROMPT_CONFIG).l2_dynamics.map(item => ({ ...item })),
    };
    return promptConfigForVisualSubject(matchDishTemperature(base, food), visual);
  }
  const mode = stored?.mode === "keyframes" ? "keyframes" : "single_image";
  const base: PromptConfig = {
    ...DEFAULT_PROMPT_CONFIG,
    mode,
    visual_subject_type: visual,
    ...(food ? { food_type: food as PromptConfig["food_type"] } : {}),
    speed_curve: mode === "keyframes" ? (stored?.speed_curve ?? "uniform") : null,
    endImageReady: mode === "keyframes" ? stored?.endImageReady : DEFAULT_PROMPT_CONFIG.endImageReady,
  };
  return applyPromptPreset(base, presetForDish(food, visual, promptData.effectRules));
}

/** 卡片和标题旁那行小字：为什么这道菜配了这个效果。写给运营看，不出现类名和字段名。 */
export function effectReason(promptData: EffectPromptData, inputData: EffectInputData): string {
  if (promptData.effectMode === "custom") return "自定义（高级设置）";
  const klass = effectClassFor(inputData.foodType, inputData.visualSubjectType);
  const overridden = promptData.effectRules?.[klass];
  // 规则改过、而且这道菜确实用得上（没退回光泽流转）时，才说是人改的。
  if (overridden && presetForDish(inputData.foodType, inputData.visualSubjectType, promptData.effectRules) === overridden) {
    return `你改的，${EFFECT_CLASS_LABELS[klass]}都用它`;
  }
  if (klass === "person") {
    return normalizedVisual(inputData.visualSubjectType) === "厨师上半身" ? "有厨师，人保持不动" : "有手，手保持不动";
  }
  if (klass === "cold") return "按冷食自动选";
  if (klass === "hot") return "按热食自动选";
  return "冷热混合，按套餐自动选";
}

/**
 * 给这道菜换效果：规则写进**所有**提示词节点（批量生产复制的是样板的第一个提示词节点，
 * 存在哪个节点上都能被带过去），但只把改的这一道菜切回规则模式，别把别人手调过的配置冲掉。
 * 这道菜用不了这个效果时原样返回同一个数组，调用方据此什么也不做。
 */
export function withEffectRule(nodes: WorkflowNode[], promptNodeId: string, inputData: EffectInputData, presetId: PromptPresetId): WorkflowNode[] {
  const usable = availablePromptPresets(availabilityConfig(inputData.foodType, inputData.visualSubjectType)).some(preset => preset.id === presetId);
  if (!usable) return nodes;
  const klass = effectClassFor(inputData.foodType, inputData.visualSubjectType);
  return nodes.map(node => {
    if (node.data.kind !== "prompt") return node;
    const effectRules: EffectRules = { ...(node.data.effectRules ?? {}), [klass]: presetId };
    return { ...node, data: { ...node.data, effectRules, ...(node.id === promptNodeId ? { effectMode: "rule" as const } : {}) } };
  });
}

/**
 * 10 个效果各一份大白话：镜头怎么走、什么在动、什么不动，以及一句带菜名的说明。
 * 页面上不出现 camera_move / L2 这类字段名——运营要看的是「会怎么动」。
 * 光泽流转那句不提「油」：冷菜的高光是湿润切面，说成油光就是 Patrick 踩的那个坑。
 */
export const EFFECT_COPY: Record<PromptPresetId, { camera: string; moving: string; still: string; sentence: (dish: string) => string }> = {
  glow: {
    camera: "绕着菜小幅转一点",
    moving: "菜品表面湿润的光",
    still: "菜品、盘子、桌面、背景",
    sentence: dish => `镜头绕着${dish}小幅转一点，${dish}本身不动，只有表面湿润的光慢慢滑过；盘子、桌面和背景都保持不动。`,
  },
  steam: {
    camera: "慢慢推近",
    moving: "热气从菜品上轻轻升起",
    still: "菜品、盘子、桌面、背景",
    sentence: dish => `镜头慢慢推近，一缕缕热气从${dish}上轻轻升起，不会遮住菜；盘子、桌面和背景都保持不动。`,
  },
  chill: {
    camera: "慢慢推近",
    moving: "冷雾贴着菜品表面流动",
    still: "菜品、盘子、桌面、背景",
    sentence: dish => `镜头慢慢推近，一层薄薄的冷雾贴着${dish}表面缓缓流动，衬出刚上桌的冰凉感；菜和桌面都保持不动。`,
  },
  flame: {
    camera: "慢慢推近",
    moving: "菜品边缘的小簇火焰",
    still: "菜品、盘子、桌面、背景",
    sentence: dish => `镜头慢慢推近，${dish}边缘有一小簇火焰轻轻摇曳，火苗不会窜大；菜和桌面都保持不动。`,
  },
  push_in: {
    camera: "慢慢推近",
    moving: "只有镜头在动",
    still: "菜品、盘子、桌面、背景",
    sentence: dish => `画面里的东西全都不动，镜头从稍远处慢慢推近${dish}，越看越清楚。`,
  },
  orbit: {
    camera: "绕着菜小幅转一点",
    moving: "只有镜头在动",
    still: "菜品、盘子、桌面、背景",
    sentence: dish => `画面里的东西全都不动，镜头绕着${dish}小幅转一点，换个角度看它。`,
  },
  loop: {
    camera: "固定机位，不动",
    moving: "菜品表面很轻微的动静",
    still: "镜头、盘子、桌面、背景",
    sentence: dish => `机位固定不动，${dish}只有很轻微的动静，首尾画面接得上，适合当循环播放的背景。`,
  },
  pour: {
    camera: "固定机位，不动",
    moving: "手把酱汁淋到菜上",
    still: "镜头、盘子、桌面、背景",
    sentence: dish => `机位固定不动，一只手把酱汁淋到${dish}上，酱汁连续往下走、不飞溅；盘子和桌面都保持不动。`,
  },
  sprinkle: {
    camera: "固定机位，不动",
    moving: "手在菜品上方撒调味",
    still: "镜头、盘子、桌面、背景",
    sentence: dish => `机位固定不动，一只手在${dish}上方撒下调味料，撒完自然收手；盘子和桌面都保持不动。`,
  },
  plating: {
    camera: "绕着菜小幅转一点",
    moving: "手往盘里摆装饰",
    still: "盘子、桌面、背景",
    sentence: dish => `镜头绕着${dish}小幅转一点，同时一只手把装饰摆到盘里，摆好收手；盘子和桌面都保持不动。`,
  },
};
