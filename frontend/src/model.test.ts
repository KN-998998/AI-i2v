import { assetIdForDishName, bgmModeFor, captionSegmentsFromData, captionSegmentsPatch, captionSegmentsWithTimings, connectWouldCycle, createPendingGeneratorClip, createWorkflowNode, dataFor, DISH_CATEGORY_OPTIONS, inferDishCategory, initialEdges, initialNodes, normalizeDishCategory, OVERLAY_FONT_OPTIONS, overlayCoordinatesFromItem, overlayItemsFromData, overlayStyleFromItem, randomizeClipSelection, recommendClipSelection, reconcileStalePendingGeneratorClips, removeNodeAndEdges, reorderById, repairCaptionVoiceSegments, resolveDishCategory, resolveGeneratorNodeStatus, soundConfigFromData, totalTimelineDuration, type TimelineClip, voiceItemsFromData } from "./model.ts";
import { applyPromptPreset, assemblePrompt, availablePromptPresets, CAMERA_OPTIONS, DEFAULT_PROMPT_CONFIG, ELEMENT_OPTIONS, L2_OPTIONS, matchPromptPreset, PROMPT_PRESETS, SHOT_SIZE_OPTIONS, type PromptConfig } from "./promptAssembler.ts";
import { browserDraftId, DRAFT_ID_STORAGE_KEY } from "./draftIdentity.ts";
import { deriveWorkflowProgress, firstIncompleteWorkflowRoute, isWorkflowRouteUnlocked } from "./workflowProgress.ts";
import { routeForPath, workflowRoutes } from "./router.ts";
import { canAssemblePromptNode, promptAssemblyBlockReason, promptUpstreamNodes } from "./promptAssemblyReadiness.ts";
import { generatorGenerationBlockReason } from "./generatorReadiness.ts";
import { batchPlanReadiness, missingTemplateKinds, REQUIRED_TEMPLATE_KINDS } from "./batchPlanReadiness.ts";
import { workflowSeed } from "./seed.ts";
import { DEFAULT_EFFECT_RULES, EFFECT_CLASS_LABELS, EFFECT_COPY, effectClassFor, effectivePromptConfig, effectReason, presetForDish, withEffectRule } from "./effectRules.ts";
import { tutorialChapters } from "./tutorial.ts";
import { readFileSync } from "node:fs";
import { reconcileDraftClips } from "./clipLibrary.ts";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const draftStorage = new Map<string, string>();
const draftId = browserDraftId({ getItem: key => draftStorage.get(key) ?? null, setItem: (key, value) => draftStorage.set(key, value) });
assert(/^draft_[A-Za-z0-9_-]{1,58}$/.test(draftId), "browser draft id is invalid");
assert(draftStorage.get(DRAFT_ID_STORAGE_KEY) === draftId, "browser draft id was not persisted");
assert(browserDraftId({ getItem: key => draftStorage.get(key) ?? null, setItem: (key, value) => draftStorage.set(key, value) }) === draftId, "browser draft id was not reused");
assert(assetIdForDishName(" 玉子寿司 ") === assetIdForDishName("玉子寿司"), "dish asset identity should ignore surrounding whitespace");
assert(assetIdForDishName("玉子  寿司") === assetIdForDishName("玉子 寿司"), "dish asset identity should collapse spacing differences");
assert(assetIdForDishName("ＡＢＣ") === assetIdForDishName("abc"), "dish asset identity should normalize full-width and case variants");

assert(connectWouldCycle(initialEdges, "sound", "assets") === true, "cycle connection was accepted");
assert(connectWouldCycle(initialEdges, "assets", "sound") === false, "acyclic connection was rejected");

const lockedProgress = deriveWorkflowProgress(initialNodes, [], [], initialEdges);
assert(lockedProgress.steps[0].unlocked && !lockedProgress.steps[0].complete, "first workflow step should be the only initial entry point");
assert(!lockedProgress.steps[1].unlocked && !isWorkflowRouteUnlocked("/canvas-mvp", lockedProgress), "new users should not access later workflow or overview routes");
assert(firstIncompleteWorkflowRoute(lockedProgress) === "/workflow/assets", "new users should be directed to the asset step");
const initialGenerator = initialNodes.find(node => node.id === "clips");
if (!initialGenerator) throw new Error("workflow seed is missing the generator node");
assert(generatorGenerationBlockReason(initialGenerator, initialNodes, initialEdges)?.includes("原始图片") === true, "generator without an image must be blocked");
const outOfOrderNodes = initialNodes.map(node => ({ ...node, data: { ...node.data } }));
const outOfOrderPrompt = outOfOrderNodes.find(node => node.data.kind === "prompt");
if (!outOfOrderPrompt) throw new Error("workflow seed is missing the prompt node");
outOfOrderPrompt.data.status = "已装配";
const outOfOrderProgress = deriveWorkflowProgress(outOfOrderNodes, [], [], initialEdges);
assert(!outOfOrderProgress.steps[3].unlocked, "a completed prompt must not unlock generation before assets and image processing are complete");
const completedNodes = initialNodes.map(node => ({ ...node, data: { ...node.data } }));
const completedInput = completedNodes.find(node => node.data.kind === "input");
const completedImageProcess = completedNodes.find(node => node.data.kind === "image_process");
const completedPrompt = completedNodes.find(node => node.data.kind === "prompt");
if (!completedInput || !completedImageProcess || !completedPrompt) throw new Error("workflow seed is missing required nodes");
completedInput.data.imagePreview = "/assets/dish.png";
completedImageProcess.data.processedImagePreview = "/assets/dish-processed.png";
completedPrompt.data.status = "已装配";
const generatedProgress = deriveWorkflowProgress(completedNodes, [{ id: "generated", dish: "dish", label: "", tone: "", timelineDuration: 3, generatorNodeId: "clips", sourcePath: "clip.mp4", isSelected: true }], [], initialEdges);
assert(generatedProgress.steps[4].unlocked && !generatedProgress.steps[5].unlocked, "completed clips should unlock composition but not sound");
const partialNodes = initialNodes.map(node => ({ ...node, data: { ...node.data } }));
const secondaryInput = createWorkflowNode("input", "secondary_input", { x: 0, y: 0 });
secondaryInput.data = { ...secondaryInput.data, dishName: "secondary dish", imagePreview: "/assets/secondary.png" };
const secondaryProcess = createWorkflowNode("image_process", "secondary_process", { x: 0, y: 0 });
secondaryProcess.data = { ...secondaryProcess.data, processedImagePreview: "/assets/secondary-processed.png" };
const secondaryPrompt = createWorkflowNode("prompt", "secondary_prompt", { x: 0, y: 0 });
secondaryPrompt.data = { ...secondaryPrompt.data, status: "已装配" };
const secondaryGenerator = createWorkflowNode("generator", "secondary_generator", { x: 0, y: 0 });
partialNodes.push(secondaryInput, secondaryProcess, secondaryPrompt, secondaryGenerator);
const partialEdges = [
  ...initialEdges,
  { id: "secondary-input-process", source: "secondary_input", target: "secondary_process" },
  { id: "secondary-process-prompt", source: "secondary_process", target: "secondary_prompt" },
  { id: "secondary-prompt-generator", source: "secondary_prompt", target: "secondary_generator" },
];
const partialProgress = deriveWorkflowProgress(partialNodes, [{ id: "secondary-clip", dish: "secondary dish", label: "", tone: "", timelineDuration: 3, generatorNodeId: "secondary_generator", sourcePath: "secondary.mp4", isSelected: true }], [], partialEdges);
assert(partialProgress.steps[4].unlocked, "one completed dish chain should unlock composition despite untouched example nodes");

const readyPromptNodes = initialNodes.map(node => ({ ...node, data: { ...node.data } }));
const readyInput = readyPromptNodes.find(node => node.data.kind === "input");
const readyProcess = readyPromptNodes.find(node => node.data.kind === "image_process");
const readyPrompt = readyPromptNodes.find(node => node.data.kind === "prompt");
if (!readyInput || !readyProcess || !readyPrompt) throw new Error("workflow seed is missing prompt chain");
readyInput.data.imagePreview = "/assets/dish.png";
readyProcess.data.processedImagePreview = "/assets/dish-processed.png";
assert(promptUpstreamNodes(readyPrompt, readyPromptNodes, initialEdges).input?.id === readyInput.id, "prompt readiness used the wrong input ancestor");
assert(promptUpstreamNodes(readyPrompt, readyPromptNodes, initialEdges).process?.id === readyProcess.id, "prompt readiness used the wrong processing ancestor");
assert(canAssemblePromptNode(readyPrompt, readyPromptNodes, initialEdges), "a ready prompt chain should be assembleable");
const unrelatedNodes = readyPromptNodes.map(node => ({ ...node, data: { ...node.data } }));
const unrelatedInput = unrelatedNodes.find(node => node.data.kind === "input");
const unrelatedProcess = unrelatedNodes.find(node => node.data.kind === "image_process");
if (!unrelatedInput || !unrelatedProcess) throw new Error("workflow seed is missing unrelated chain nodes");
unrelatedInput.data.imagePreview = undefined;
unrelatedProcess.data.processedImagePreview = undefined;
assert(canAssemblePromptNode(readyPrompt, unrelatedNodes, initialEdges) === false, "prompt readiness should require its own upstream chain");
readyProcess.data.status = "处理失败";
readyProcess.data.processedImagePreview = undefined;
assert(promptAssemblyBlockReason(readyPrompt, readyPromptNodes, initialEdges)?.includes("图片处理失败") === true, "failed image processing should explain why prompt assembly is disabled");

const next = removeNodeAndEdges(initialNodes, initialEdges, "prompt");
assert(!next.nodes.some(node => node.id === "prompt"), "node was not removed");
assert(next.edges.length === 3, "connected edges were not removed");
assert(!next.edges.some(edge => edge.source === "prompt" || edge.target === "prompt"), "dangling edge remained");

const timeline = [
  { id: "a", dish: "A", label: "", tone: "", timelineDuration: 2 },
  { id: "b", dish: "B", label: "", tone: "", timelineDuration: 3 },
  { id: "c", dish: "C", label: "", tone: "", timelineDuration: 4 },
];
assert(JSON.stringify(reorderById(timeline, "c", "a").map(clip => clip.id)) === JSON.stringify(["c", "a", "b"]), "timeline order was not updated");
assert(totalTimelineDuration(timeline) === 9, "timeline duration is incorrect");

const pendingClip = createPendingGeneratorClip("clips", 1, "炙烤三文鱼");
assert(pendingClip.id === "clips_clip" && pendingClip.generatorNodeId === "clips", "generator clip is not linked to node");
assert(DISH_CATEGORY_OPTIONS.includes("套餐"), "package category is missing");
const packagePrompt = assemblePrompt({
  mode: "single_image", camera_move: "locked_off", camera_amplitude: "subtle", shot_size: "close_up",
  elements: ["dish_hot", "tableware", "surface"], l1_subject: "dish_hot", l1_action_level: null,
  l1_action_verb: null, l2_dynamics: [], speed_curve: null, seamless_loop: false, food_type: "混合/多温",
});
assert(packagePrompt.prompt.includes("包含冷食与热食"), "package prompt lost mixed temperature attribute");
assert(pendingClip.status === "pending" && !pendingClip.sourcePath, "generator clip should wait for a real file");
assert(resolveGeneratorNodeStatus("生成中", { status: "generated", sourcePath: "clip.mp4" }) === "已生成", "linked generator clip should be completed");
assert(resolveGeneratorNodeStatus("生成中") === "待生成", "stale generator status should reset when its clip is gone");
assert(pendingClip.dishCategory === "其他", "pending generator clip should have a default dish category");

const stalePlaceholder = { ...pendingClip, id: "generator_pending", generatorNodeId: "generator", status: "pending" as const, sourcePath: undefined };
const completedGeneratorClip = { ...pendingClip, id: "generator_v1", generatorNodeId: "generator", status: "generated" as const, sourcePath: "generator-v1.mp4", clipVersion: 1 };
assert(reconcileStalePendingGeneratorClips([stalePlaceholder], [completedGeneratorClip], new Set()).length === 0, "stale pending placeholder was not removed after its MP4 arrived");
const activePending = reconcileStalePendingGeneratorClips([stalePlaceholder], [completedGeneratorClip], new Set(["generator"]));
assert(activePending.length === 1 && activePending[0].id === "generator_pending", "active regeneration placeholder was removed");
const repairedTimeline = reconcileStalePendingGeneratorClips([stalePlaceholder], [completedGeneratorClip], new Set(), "replace");
assert(repairedTimeline.length === 1 && repairedTimeline[0].sourcePath === "generator-v1.mp4", "stale composition reference was not repaired");

assert(inferDishCategory("蜜瓜") === "水果", "fruit fallback classification is incorrect");
assert(inferDishCategory("抹茶布丁") === "甜品", "dessert fallback classification is incorrect");
assert(inferDishCategory("冷食三文鱼") === "其他", "food temperature must not imply fruit classification");
assert(normalizeDishCategory("正餐") === "主菜" && normalizeDishCategory("小吃") === "前菜/小菜", "legacy categories were not migrated");
assert(resolveDishCategory({ dish: "冷食三文鱼", dishCategory: "主菜" }) === "主菜", "explicit dish category was ignored");

const overlays = overlayItemsFromData({ overlayMain: "开胃钩子", overlayCta: "现在预订", overlayPosition: "中上钩子区", overlayStart: "0s", overlayEnd: "2.5s" });
assert(overlays.length === 2 && overlays[0].position === "upper" && overlays[1].position === "top", "legacy overlay fields were not migrated");
assert(overlayItemsFromData({ overlayItems: [{ id: "one", text: "上方文案", startSeconds: 1, endSeconds: 3, position: "top" }] }).length === 1, "explicit overlay timeline was not preserved");
assert(OVERLAY_FONT_OPTIONS.includes("KaiTi") && OVERLAY_FONT_OPTIONS.includes("Arial Black"), "expanded overlay font options are missing");
const centeredOverlay = overlayCoordinatesFromItem({ position: "custom" });
assert(centeredOverlay.x === 0.5 && centeredOverlay.y === 0.5, "custom overlay position should default to center");
const draggedOverlay = overlayItemsFromData({ overlayItems: [{ id: "dragged", text: "可拖动", startSeconds: 0, endSeconds: 2, position: "custom", x: 0.21, y: 0.74 }] })[0];
assert(draggedOverlay.x === 0.21 && draggedOverlay.y === 0.74, "custom overlay coordinates were not persisted");
const hiddenOverlay = overlayItemsFromData({ overlayItems: [{ id: "hidden", text: "仅保留人声", enabled: false, startSeconds: 0, endSeconds: 2, position: "upper" }] })[0];
assert(hiddenOverlay.enabled === false, "overlay visibility switch was not persisted");
const animatedOverlay = overlayItemsFromData({ overlayItems: [{ id: "typed", text: "typewriter", startSeconds: 0, endSeconds: 2, position: "upper", animation: "typewriter", syncVoiceId: "voice_1" }] })[0];
assert(animatedOverlay.animation === "typewriter" && animatedOverlay.syncVoiceId === "voice_1", "overlay animation binding was not persisted");
const defaultOverlayStyle = overlayStyleFromItem({ style: {} });
assert(defaultOverlayStyle.singleLine === true && defaultOverlayStyle.textBoxWidth === 0.84, "overlay text layout defaults are incorrect");
const savedCaptionSource = soundConfigFromData({ captionSourceText: "完整引流文案" });
assert(savedCaptionSource.captionSourceText === "完整引流文案", "caption source text was not persisted in sound config");

const legacyVoice = voiceItemsFromData({ voiceText: "legacy voice", voiceName: "voice", voiceVolume: "85" });
assert(legacyVoice.length === 1 && legacyVoice[0].startSeconds === 0 && legacyVoice[0].endSeconds === 4, "legacy voice fields were not migrated");
const segmentedVoice = voiceItemsFromData({
  voiceItems: [
    { id: "voice_1", text: "opening", startSeconds: 0, endSeconds: 4, volume: 80 },
    { id: "voice_2", text: "closing", startSeconds: 10, endSeconds: 15, volume: 75 },
  ],
});
assert(segmentedVoice.length === 2 && segmentedVoice[1].startSeconds === 10 && segmentedVoice[1].endSeconds === 15, "voice segment timing was not preserved");
const qwenVoice = voiceItemsFromData({ voiceText: "qwen", voiceName: "女声 · 温暖自然", voiceVolume: "85" });
assert(qwenVoice[0].voiceId === "Cherry" && qwenVoice[0].provider === "qwen", "legacy voice was not migrated to Qwen");
const repairedVoiceLabel = voiceItemsFromData({ voiceItems: [{ id: "voice_mojibake", text: "测试", voiceId: "Chelsie", voiceName: "å¥³å£° · Chelsie · æ´»æ³¼æ¸æ°", startSeconds: 0, endSeconds: 2 }] });
assert(repairedVoiceLabel[0].voiceName === "女声 · Chelsie · 活泼清晰", "segmented voice label mojibake was not repaired");
const noVoice = voiceItemsFromData({ voiceText: "", voiceName: "无", voiceVolume: "85" });
assert(noVoice.length === 0, "default no-voice state should not create a TTS segment");
const disabledExplicitVoice = voiceItemsFromData({ voiceItems: [{ id: "voice_none", text: "只显示文字", voiceId: "none", enabled: true, startSeconds: 0, endSeconds: 2 }] });
assert(disabledExplicitVoice.length === 1 && disabledExplicitVoice[0].enabled === false, "explicit no-voice item should be disabled");
const textWithNoVoice = captionSegmentsFromData({
  overlayItems: [{ id: "overlay_only", text: "只显示文字", startSeconds: 0, endSeconds: 2, position: "upper" }],
  voiceItems: [{ id: "voice_none", text: "不应播报", voiceId: "none", startSeconds: 0, endSeconds: 2 }],
});
assert(textWithNoVoice[0].overlay.enabled !== false && textWithNoVoice[0].voice.enabled === false, "text-only segment should not enter TTS");

const captionSegments = captionSegmentsFromData({
  overlayItems: [{ id: "overlay_1", text: "screen copy", startSeconds: 0, endSeconds: 2, position: "upper" }],
  voiceItems: [{ id: "voice_1", text: "voice copy", startSeconds: 1, endSeconds: 4, voiceId: "Cherry" }],
});
assert(captionSegments.length === 1 && captionSegments[0].voice.id === "voice_1" && captionSegments[0].overlay.syncVoiceId === undefined, "caption tracks were not auto-paired");
assert(captionSegments[0].overlay.text === "screen copy" && captionSegments[0].overlay.startSeconds === 0, "overlay text and timing should remain independent");
assert(captionSegments[0].voice.text === "voice copy" && captionSegments[0].voice.startSeconds === 1, "voice text and timing should remain independent");
const independentPatch = captionSegmentsPatch(captionSegments);
assert(independentPatch.overlayItems?.[0].text === "screen copy" && independentPatch.voiceItems?.[0].text === "voice copy", "caption patch overwrote independent track text");
const measuredCaptions = captionSegmentsWithTimings(captionSegments, { voice_1: { startSeconds: 1, endSeconds: 3.6 } });
const captionPatch = captionSegmentsPatch(measuredCaptions);
assert(captionPatch.overlayItems?.[0].endSeconds === 3.6 && captionPatch.voiceItems?.[0].endSeconds === 3.6, "actual TTS duration was not written to both tracks");
assert(captionPatch.overlayItems?.[0].syncVoiceId === undefined, "automatic binding was converted into an explicit binding");
const unboundCaption = captionSegmentsFromData({
  overlayItems: [{ id: "overlay_unbound", text: "仅显示文字", syncVoiceId: "", startSeconds: 0, endSeconds: 2, position: "upper" }],
  voiceItems: [{ id: "voice_unbound", text: "不应同步", voiceId: "Cherry", startSeconds: 0, endSeconds: 2 }],
});
assert(unboundCaption.length === 2 && unboundCaption[0].voice.enabled !== true && unboundCaption[1].overlay.enabled === false, "explicitly unbound tracks were paired");
assert(captionSegmentsPatch(unboundCaption).overlayItems?.[0].syncVoiceId === "", "explicit unbound state was not persisted");
const textOnlyPatch = captionSegmentsPatch(captionSegmentsFromData({
  overlayItems: [{ id: "overlay_text_only", text: "仅显示文字", startSeconds: 0, endSeconds: 2, position: "upper" }],
}));
assert(textOnlyPatch.voiceItems?.length === 0, "text-only placeholder voice should not be persisted");
const repairedCaptionVoices = repairCaptionVoiceSegments({
  overlayItems: [
    { id: "overlay_1", text: "第一段", startSeconds: 0, endSeconds: 2, position: "upper" },
    { id: "overlay_2", text: "第二段", startSeconds: 2, endSeconds: 4, position: "upper" },
    { id: "overlay_3", text: "第三段", startSeconds: 4, endSeconds: 6, position: "upper" },
  ],
  voiceItems: [
    { id: "voice_1", text: "第一段", voiceId: "Cherry", voiceName: "女声", enabled: true, startSeconds: 0, endSeconds: 2 },
    { id: "voice_2", text: "第二段", voiceId: "Cherry", voiceName: "女声", enabled: true, startSeconds: 2, endSeconds: 4 },
  ],
});
assert(repairedCaptionVoices?.voiceItems?.length === 3, "missing caption voice was not restored");
assert(repairedCaptionVoices?.overlayItems?.every(item => Boolean(item.syncVoiceId)), "repaired captions were not bound to voices");
const repairedDisabledVoices = repairCaptionVoiceSegments({
  overlayItems: [
    { id: "overlay_enabled", text: "已有声音", syncVoiceId: "voice_enabled", startSeconds: 0, endSeconds: 2, position: "upper" },
    { id: "overlay_disabled", text: "错误无声段", syncVoiceId: "voice_disabled", startSeconds: 2, endSeconds: 4, position: "upper" },
  ],
  voiceItems: [
    { id: "voice_enabled", text: "已有声音", voiceId: "Cherry", enabled: true, startSeconds: 0, endSeconds: 2 },
    { id: "voice_disabled", text: "错误无声段", voiceId: "none", enabled: false, startSeconds: 2, endSeconds: 4 },
  ],
});
assert(repairedDisabledVoices?.voiceItems?.length === 2 && repairedDisabledVoices.voiceItems.some(item => item.id === "voice_repaired_overlay_disabled" && item.voiceId === "Cherry"), "bound no-voice segment was not repaired");
const textOnlyCaption = repairCaptionVoiceSegments({
  overlayItems: [{ id: "overlay_text_only", text: "只显示文字", syncVoiceId: "voice_text_only", startSeconds: 0, endSeconds: 2, position: "upper" }],
  voiceItems: [{ id: "voice_text_only", text: "只显示文字", voiceId: "none", enabled: false, ttsDisabledByUser: true, startSeconds: 0, endSeconds: 2 }],
});
assert(textOnlyCaption === null, "explicit text-only caption unexpectedly gained a voice");
assert(overlayItemsFromData({ overlayItems: [{ id: "overlay_for_voice_old", text: "历史占位", startSeconds: 0, endSeconds: 2, position: "upper" }] })[0].placeholder === true, "legacy overlay placeholder was not recognized");
assert(overlayItemsFromData({ overlayItems: [{ id: "overlay_stale_binding", text: "失效绑定", syncVoiceId: "voice_for_overlay_old", startSeconds: 0, endSeconds: 2, position: "upper" }] })[0].syncVoiceId === "", "stale generated binding was not cleared");
assert(voiceItemsFromData({ voiceItems: [{ id: "voice_for_overlay_old", text: "历史占位", voiceId: "none", startSeconds: 0, endSeconds: 2 }] })[0].placeholder === true, "legacy voice placeholder was not recognized");
const explicitlyBoundCaption = captionSegmentsFromData({
  overlayItems: [{ id: "overlay_bound", text: "绑定第二段", syncVoiceId: "voice_b", startSeconds: 0, endSeconds: 2, position: "upper" }],
  voiceItems: [
    { id: "voice_a", text: "第一段声音", voiceId: "Cherry", startSeconds: 0, endSeconds: 2 },
    { id: "voice_b", text: "第二段声音", voiceId: "Serena", startSeconds: 2, endSeconds: 4 },
  ],
});
assert(explicitlyBoundCaption[0].voice.id === "voice_b" && captionSegmentsPatch(explicitlyBoundCaption).overlayItems?.[0].syncVoiceId === "voice_b", "explicit voice binding was not applied");
const duplicateBinding = captionSegmentsFromData({
  overlayItems: [
    { id: "overlay_a", text: "同一声音的文字一", syncVoiceId: "voice_b", startSeconds: 0, endSeconds: 2, position: "upper" },
    { id: "overlay_b", text: "同一声音的文字二", syncVoiceId: "voice_b", startSeconds: 2, endSeconds: 4, position: "upper" },
  ],
  voiceItems: [
    { id: "voice_a", text: "未绑定声音", voiceId: "Cherry", startSeconds: 0, endSeconds: 2 },
    { id: "voice_b", text: "可复用声音", voiceId: "Serena", startSeconds: 2, endSeconds: 4 },
  ],
});
assert(captionSegmentsPatch(duplicateBinding).voiceItems?.length === 2, "rebinding duplicated voice entities");

const composePool = [
  { id: "main-1", dish: "三文鱼", label: "", tone: "", timelineDuration: 2, sourcePath: "main-1.mp4", dishCategory: "主菜" as const },
  { id: "main-2", dish: "天妇罗", label: "", tone: "", timelineDuration: 2, sourcePath: "main-2.mp4", dishCategory: "炸物" as const },
  { id: "fruit-1", dish: "蜜瓜", label: "", tone: "", timelineDuration: 2, sourcePath: "fruit-1.mp4", dishCategory: "水果" as const },
  { id: "dessert-1", dish: "布丁", label: "", tone: "", timelineDuration: 2, sourcePath: "dessert-1.mp4", dishCategory: "甜品" as const },
];
const randomized = randomizeClipSelection(composePool, 3, () => 0.5);
assert(randomized.length === 3, "random composition did not fill the requested count");
assert(randomized.filter(clip => ["甜品", "水果"].includes(resolveDishCategory(clip))).length === 1, "random composition selected multiple dessert or fruit clips");
assert(["甜品", "水果"].includes(resolveDishCategory(randomized.at(-1)!)), "dessert or fruit clip was not placed last");
assert(new Set(randomized.map(clip => clip.id)).size === randomized.length, "random composition duplicated a clip");
const singleSpecial = randomizeClipSelection(composePool, 1, () => 0);
assert(singleSpecial.length === 1 && ["甜品", "水果"].includes(resolveDishCategory(singleSpecial[0])), "single-clip composition did not prefer dessert or fruit");
const ordinaryOnly = randomizeClipSelection(composePool.slice(0, 2), 3, () => 0);
assert(ordinaryOnly.length === 2 && ordinaryOnly.every(clip => !["甜品", "水果"].includes(resolveDishCategory(clip))), "ordinary-only composition changed its available pool incorrectly");

const recommended = recommendClipSelection([
  { ...composePool[0], qualityScore: 62, qualityWarnings: ["暗部"] },
  { ...composePool[1], qualityScore: 95, qualityWarnings: [] },
  { ...composePool[2], qualityScore: 99, qualityWarnings: [] },
  { id: "same-dish", dish: "天妇罗", label: "重复菜品", tone: "", timelineDuration: 2, sourcePath: "same-dish.mp4", dishCategory: "炸物" as const, qualityScore: 100, qualityWarnings: [] },
], 3);
assert(recommended.length === 3, "smart recommendation did not fill the requested count");
assert(recommended[0].id === "same-dish", "smart recommendation did not prioritize high quality clips");
assert(new Set(recommended.slice(0, 2).map(clip => clip.dish)).size === 2, "smart recommendation did not diversify dishes");
assert(["甜品", "水果"].includes(resolveDishCategory(recommended.at(-1)!)), "smart recommendation did not place the special clip last");

assert(ELEMENT_OPTIONS.length === 8, "L0 options are incomplete");
assert(CAMERA_OPTIONS.length === 8, "camera options are incomplete");
assert(SHOT_SIZE_OPTIONS.length === 4, "shot size options are incomplete");
assert(L2_OPTIONS.length === 8, "L2 options are incomplete");

const validPrompt: PromptConfig = {
  mode: "keyframes",
  camera_move: "locked_off",
  camera_amplitude: "subtle",
  shot_size: "medium",
  elements: ["dish_hot", "tableware", "surface", "hand"],
  l1_subject: "hand",
  l1_action_level: 2,
  l1_action_verb: "pour_sauce",
  l2_dynamics: [{ type: "steam", target: "菜品" }, { type: "liquid_pour", target: "酱汁壶" }],
  speed_curve: "uniform",
  seamless_loop: false,
  endImageReady: true,
};
const assembled = assemblePrompt(validPrompt);
assert(assembled.blocked === false, "valid structured prompt was blocked");
assert(assembled.prompt.includes("【过渡】") && assembled.prompt.includes("淋下酱汁"), "keyframe prompt sections were not assembled");
assert(assembled.prompt.includes("【景别】中景，菜品主体约占画面35%-55%"), "shot size was not assembled");
assert(assembled.negative_prompt.includes("飞溅") && assembled.cfg_scale === 0.45, "negative prompt or cfg scale was not assembled");

const invalidPrompt = assemblePrompt({ ...validPrompt, l2_dynamics: [...validPrompt.l2_dynamics, { type: "flame", target: "菜品" }] });
assert(invalidPrompt.blocked && invalidPrompt.errors.some(item => item.code === "V2"), "L2 upper bound was not blocked");
assert(invalidPrompt.prompt === "" && invalidPrompt.cfg_scale === 0, "blocked prompt still produced output");

const missingEndImage = assemblePrompt({ ...validPrompt, endImageReady: false });
assert(missingEndImage.errors.some(item => item.code === "V7"), "missing tail frame was not detected");
// 效果预设：在所有“菜品温度 × 主体类型 × 模式”组合下，每个可用预设都必须一次通过校验且没有警告，
// 并且套用后能被 matchPromptPreset 认回来（否则界面上没有高亮，用户不知道自己选了什么）。
const presetFoodTypes: Array<PromptConfig["food_type"]> = [undefined, "热食", "冷食", "混合/多温"];
const presetSubjects: Array<PromptConfig["visual_subject_type"]> = ["菜品主体", "手部", "厨师上半身", "手部+厨师上半身"];
const presetModes: Array<Pick<PromptConfig, "mode" | "endImageReady" | "speed_curve">> = [
  { mode: "single_image", endImageReady: false, speed_curve: null },
  { mode: "keyframes", endImageReady: true, speed_curve: "ease_out" },
];
let presetCases = 0;
for (const food_type of presetFoodTypes) for (const visual_subject_type of presetSubjects) for (const modeFields of presetModes) {
  const context: PromptConfig = { ...DEFAULT_PROMPT_CONFIG, ...modeFields, food_type, visual_subject_type, elements: [], l2_dynamics: [] };
  const available = availablePromptPresets(context);
  assert(available.length >= 5, `too few presets for ${food_type}/${visual_subject_type}`);
  assert(available.some(preset => preset.needsPerson) === (visual_subject_type !== "菜品主体"), "person presets should follow the visual subject type");
  for (const preset of available) {
    const applied = applyPromptPreset(context, preset.id);
    const result = assemblePrompt(applied);
    const label = `${preset.id} @ ${food_type}/${visual_subject_type}/${modeFields.mode}`;
    assert(!result.blocked, `preset ${label} is blocked: ${result.errors.map(item => item.code).join(",")}`);
    assert(result.warnings.length === 0, `preset ${label} has warnings: ${result.warnings.map(item => item.code).join(",")}`);
    assert(applied.mode === context.mode && applied.food_type === food_type && applied.visual_subject_type === visual_subject_type, `preset ${label} changed mode or dish context`);
    assert(matchPromptPreset(applied) === preset.id, `preset ${label} does not round-trip through matchPromptPreset`);
    presetCases += 1;
  }
}
assert(presetCases > 100, "preset matrix was not exercised");
assert(availablePromptPresets({ ...DEFAULT_PROMPT_CONFIG, food_type: "冷食" }).every(preset => preset.id !== "steam" && preset.id !== "flame"), "hot-only presets leaked into cold dishes");
assert(availablePromptPresets({ ...DEFAULT_PROMPT_CONFIG, food_type: "热食" }).every(preset => preset.id !== "chill"), "cold-only preset leaked into hot dishes");
assert(matchPromptPreset(DEFAULT_PROMPT_CONFIG) === "glow", "the factory default config should read as the “光泽流转” preset");
assert(matchPromptPreset({ ...DEFAULT_PROMPT_CONFIG, camera_amplitude: "medium" }) === null, "a hand-tuned config should read as custom");
assert(new Set(PROMPT_PRESETS.map(preset => preset.label)).size === PROMPT_PRESETS.length, "preset labels must be unique");

// 首页：「/」是独立路由（不再落到画布），且任何进度下都能回。
assert(routeForPath("/") === "/", "root path should resolve to the home route");
assert(routeForPath("/canvas-mvp") === "/canvas-mvp", "canvas path should still resolve to the canvas");
assert(routeForPath("/workflow/unknown") === "/canvas-mvp", "unknown workflow paths should still fall back to the canvas");
const emptyProgress = deriveWorkflowProgress([], [], []);
assert(isWorkflowRouteUnlocked("/", emptyProgress), "the home route must stay reachable on an empty draft");

// 批量生产：开工前就要说清楚缺什么，别等到第二天早上执行失败。
assert(missingTemplateKinds(initialNodes).length === 0, "the factory template should already contain every node kind a daily draft needs");
assert(missingTemplateKinds(initialNodes.filter(node => node.data.kind !== "sound")).join(",") === "sound", "a template without the sound node should report exactly that");
const fullLibrary = { dishCount: 120, availableCount: 120, pendingCount: 0, backgroundCount: 8 };
const batchInput = { loading: false, library: fullLibrary, customRoots: null, missingKinds: [], candidateCount: 40, clipsPerVideo: 4 };
const readyPlan = batchPlanReadiness(batchInput);
assert(readyPlan.ok && readyPlan.blocker === "", "a stocked library with a complete template should be ready to start");
assert(readyPlan.maxVideosPerDay === 30, "120 dishes at 4 clips per video should allow 30 videos a day");
assert(!batchPlanReadiness({ ...batchInput, loading: true }).ok, "the start button must stay disabled while the library summary is still loading");
assert(batchPlanReadiness({ ...batchInput, missingKinds: REQUIRED_TEMPLATE_KINDS.slice(0, 1) }).action === "template", "a template gap should send the user to the template, not the library");
assert(batchPlanReadiness({ ...batchInput, library: { ...fullLibrary, dishCount: 0, availableCount: 0 } }).action === "library", "an empty library should send the user to the library");
assert(batchPlanReadiness({ ...batchInput, library: { ...fullLibrary, backgroundCount: 0 } }).action === "background", "a library without backgrounds should send the user to the background upload");
const shortStock = batchPlanReadiness({ ...batchInput, library: { ...fullLibrary, dishCount: 20, availableCount: 20 } });
assert(!shortStock.ok && shortStock.blocker.includes("5 条"), "a short library should say how many videos a day it can still cover");
// 预留是按日期滚动的，占用只提醒不拦。
const crowded = batchPlanReadiness({ ...batchInput, library: { ...fullLibrary, availableCount: 10 } });
assert(crowded.ok && crowded.note.includes("110"), "dishes reserved by another plan should warn rather than block");
assert(batchPlanReadiness({ ...batchInput, library: { ...fullLibrary, pendingCount: 12 } }).note.includes("12"), "unclassified dishes should be surfaced as a note");
const customBlank = batchPlanReadiness({ ...batchInput, library: null, customRoots: { asset: "", background: "" } });
assert(!customBlank.ok, "a custom folder pair with empty paths must not start a plan");
assert(batchPlanReadiness({ ...batchInput, library: null, customRoots: { asset: "/tmp/a", background: "/tmp/b" } }).ok, "two filled custom folders should be allowed to start");

// A 层硬伤：自动选片要避开「建议重做」的片段，好片不够时才退回去用。
const baseClip = (id: string, extra: Record<string, unknown> = {}) => ({
  id, dish: id, label: "生成片段", tone: "#355e62", timelineDuration: 2.5,
  sourcePath: `/tmp/${id}.mp4`, qualityScore: 90, dishCategory: "主菜", ...extra,
}) as TimelineClip;
const mixedClips = [
  baseClip("坏片1", { redoRecommended: true, redoReasons: ["整段几乎没有动"] }),
  baseClip("好片1"),
  baseClip("好片2"),
  baseClip("坏片2", { redoRecommended: true, redoReasons: ["画面亮度忽明忽暗"] }),
  baseClip("好片3"),
];
const picked = recommendClipSelection(mixedClips, 3);
assert(picked.length === 3, "three healthy clips should still fill a three-clip video");
assert(picked.every(clip => !clip.redoRecommended), "clips flagged for redo must be skipped while healthy ones remain");
// 只有 1 条好片、却要 3 条时，不能因为挑剔而交不出成片。
const scarce = [baseClip("好片1"), baseClip("坏片1", { redoRecommended: true }), baseClip("坏片2", { redoRecommended: true })];
const fallback = recommendClipSelection(scarce, 3);
assert(fallback.length === 3, "a short pool must still fill the video rather than returning nothing");
assert(fallback[0].id === "好片1", "the healthy clip must come first when the pool has to include flagged ones");
assert(recommendClipSelection([baseClip("坏片1", { redoRecommended: true })], 1)[0].id === "坏片1", "a single flagged clip is still better than an empty timeline");

// 第十一批：每条成片默认用 6 个片段——参考片的镜头数中位就是 6（p10 也是 6），
// 工具原来默认 3 个，成片明显更单调。
assert(workflowSeed.composeClipCount === 6, "a default video should be cut from six clips, like the published reference videos");

// 第十二批：背景压暗的默认值从 0.72 调到 0.85。参考片画面平均亮度 109–123，
// 工具合成的成片只有 65.7；这一步只能拉到 74 左右，剩下的差距在背景素材本身。
assert(dataFor("image_process").backgroundBrightness === 0.85, "the background should no longer be dimmed to 0.72 by default");

// ---------------------------------------------------------------------------
// 第十三批（一）：批量生产能进审片
// 批量生产的每日草稿编号是 weekly_<32 位 hex>，后端一直接受；前端原来只认 draft_ 开头，
// 「进入片段审核」整页跳转后会把它当成无效编号，换成一份新的空草稿，审片页就是空的。
// ---------------------------------------------------------------------------
const weeklyDraftId = "weekly_" + "0123456789abcdef".repeat(2);
const weeklyStorage = new Map<string, string>([[DRAFT_ID_STORAGE_KEY, weeklyDraftId]]);
assert(browserDraftId({ getItem: key => weeklyStorage.get(key) ?? null, setItem: (key, value) => weeklyStorage.set(key, value) }) === weeklyDraftId, "a batch run's draft id must survive the page reload into clip review");
assert(weeklyStorage.get(DRAFT_ID_STORAGE_KEY) === weeklyDraftId, "opening clip review must not overwrite the batch run's draft id");
const junkStorage = new Map<string, string>([[DRAFT_ID_STORAGE_KEY, "weekly_../../etc"]]);
assert(browserDraftId({ getItem: key => junkStorage.get(key) ?? null, setItem: (key, value) => junkStorage.set(key, value) }) !== "weekly_../../etc", "draft ids with path characters must still be rejected");

// ---------------------------------------------------------------------------
// 第十三批（二）：第 3 步「动态效果」——每道菜按自己的冷热自动配效果
// Patrick 9/21 实测：模板是在知道这道菜是冷食之前建的，冷的玉子寿司拿到的指令是「表面油光」；
// 批量生产照搬样板的效果，样板选了「热气升腾」的话冷菜也照样冒热气。
// 改成：效果不再存死在模板里，而是按「冷菜 / 热菜 / 冷热混合 / 原图有手或厨师」四类规则、
// 用每道菜自己的冷热和画面主体现算；样板里改了某一类，同一类的菜都跟着换。
// ---------------------------------------------------------------------------
assert(effectClassFor("冷食", "菜品主体") === "cold", "a cold dish photo is in the cold class");
assert(effectClassFor("热食", "菜品主体") === "hot", "a hot dish photo is in the hot class");
assert(effectClassFor("混合/多温", "菜品主体") === "mixed", "a mixed platter is in the mixed class");
assert(effectClassFor(undefined, "菜品主体") === "mixed", "an unknown temperature falls back to the mixed class, whose default is safe for both");
assert(effectClassFor("热食", "手部") === "person" && effectClassFor("冷食", "厨师上半身") === "person" && effectClassFor(undefined, "手部+厨师上半身") === "person", "any photo with hands or a chef is in the person class, whatever the temperature");
assert(DEFAULT_EFFECT_RULES.cold === "glow" && DEFAULT_EFFECT_RULES.hot === "steam" && DEFAULT_EFFECT_RULES.mixed === "glow" && DEFAULT_EFFECT_RULES.person === "glow", "defaults: cold and mixed get 光泽流转, hot gets 热气升腾, hands or chef stay still with 光泽流转");
assert(Object.keys(EFFECT_CLASS_LABELS).sort().join(",") === "cold,hot,mixed,person", "the batch rule panel lists exactly four classes");
assert(EFFECT_CLASS_LABELS.cold === "冷菜" && EFFECT_CLASS_LABELS.hot === "热菜", "class labels are plain words the operator uses");

// 前后端共用的对照表：规则模式下，每一类菜 × 每个可用效果 × 两种模式，都必须和现有 applyPromptPreset 逐项一致。
// 后端 pipeline/prompt_presets.py 读同一份文件，两边就不会各配各的。
const effectFixture = JSON.parse(readFileSync(new URL("../../tests/fixtures/effect_presets.json", import.meta.url), "utf-8"));
assert(effectFixture.cases.length > 200, "the shared effect table should cover every class, preset and mode");
for (const item of effectFixture.cases) {
  const input = { foodType: item.food_type ?? undefined, visualSubjectType: item.visual_subject_type };
  const promptData = { effectMode: "rule", effectRules: { [effectClassFor(input.foodType, input.visualSubjectType)]: item.preset }, promptConfig: { ...DEFAULT_PROMPT_CONFIG, mode: item.mode } };
  const actual = effectivePromptConfig(promptData, input);
  for (const key of effectFixture.slot_keys) {
    assert(JSON.stringify(actual[key] ?? null) === JSON.stringify(item.expected[key]), `effect ${item.preset} for ${item.food_type}/${item.visual_subject_type}/${item.mode} differs from the shared table on ${key}`);
  }
}

// Patrick 踩到的那一条：老模板里存的是热菜写法、没有 effectMode，冷的寿司必须拿到冷菜写法
const legacyTemplate = { promptConfig: { ...DEFAULT_PROMPT_CONFIG, food_type: "冷食" } };
const coldSushi = effectivePromptConfig(legacyTemplate, { foodType: "冷食", visualSubjectType: "菜品主体", dishName: "玉子寿司" });
assert(coldSushi.l1_subject === "dish_cold" && coldSushi.elements.includes("dish_cold") && !coldSushi.elements.includes("dish_hot"), "a cold dish gets the cold dish subject even when the template was saved as hot");
const coldSushiPrompt = assemblePrompt(coldSushi).prompt;
assert(coldSushiPrompt.includes("湿润切面高光") && !coldSushiPrompt.includes("油光"), "the cold sushi instruction must not ask for an oily sheen");
assert(matchPromptPreset(coldSushi) === "glow", "the default must be recognised as 光泽流转, not shown as 自定义");

// 热菜默认冒热气；原图有手的，手保持不动
const hotSoup = effectivePromptConfig({}, { foodType: "热食", visualSubjectType: "菜品主体" });
assert(hotSoup.camera_move === "dolly_in" && hotSoup.l2_dynamics.some(item => item.type === "steam"), "a hot dish defaults to 热气升腾");
const heldSushi = effectivePromptConfig({}, { foodType: "冷食", visualSubjectType: "手部" });
assert(heldSushi.l1_subject === "hand" && heldSushi.l1_action_level === 1 && heldSushi.l1_action_verb === null, "a dish held in a hand keeps the hand still by default");
assert(!assemblePrompt(heldSushi).prompt.includes("热气"), "a cold dish in a hand must not steam");

// 样板里改了一类，同一类跟着换，别的类不受影响
const coldRule = { effectRules: { cold: "push_in" } };
const pushedCold = effectivePromptConfig(coldRule, { foodType: "冷食", visualSubjectType: "菜品主体" });
assert(pushedCold.camera_move === "dolly_in" && pushedCold.camera_amplitude === "light" && pushedCold.shot_size === "medium_close", "a cold rule of 只推近镜头 applies to cold dishes");
assert(effectivePromptConfig(coldRule, { foodType: "热食", visualSubjectType: "菜品主体" }).l2_dynamics.some(item => item.type === "steam"), "changing the cold rule must not touch hot dishes");

// 规则对这道菜不适用时退回光泽流转：冷菜不能冒热气，没有手的图不能淋酱
assert(presetForDish("冷食", "手部", { person: "steam" }) === "glow", "a steaming rule falls back to 光泽流转 for a cold dish");
assert(presetForDish("热食", "手部", { person: "steam" }) === "steam", "the same rule still applies where it fits");
assert(presetForDish("冷食", "菜品主体", { cold: "pour" }) === "glow", "a hands-only effect cannot apply to a photo without hands");
assert(presetForDish("冷食", "菜品主体", undefined) === "glow", "no rules means the class default");

// 自定义（在高级设置里手调过）：按原样用，但菜的冷热、手和人要对上
const handTuned = effectivePromptConfig({ effectMode: "custom", promptConfig: { ...DEFAULT_PROMPT_CONFIG, camera_move: "locked_off", l2_dynamics: [] } }, { foodType: "冷食", visualSubjectType: "菜品主体" });
assert(handTuned.camera_move === "locked_off" && handTuned.l2_dynamics.length === 0, "a hand-tuned config is used as it is");
assert(handTuned.l1_subject === "dish_cold" && handTuned.elements.includes("dish_cold") && !handTuned.elements.includes("dish_hot"), "even a hand-tuned config must match the dish temperature");
const handTunedHeld = effectivePromptConfig({ effectMode: "custom", promptConfig: { ...DEFAULT_PROMPT_CONFIG } }, { foodType: "热食", visualSubjectType: "手部" });
assert(handTunedHeld.elements.includes("hand") && handTunedHeld.l1_subject === "hand", "a hand-tuned config still follows the hands in the photo");

// 这一页上给运营看的说法
assert(effectReason({}, { foodType: "冷食", visualSubjectType: "菜品主体" }) === "按冷食自动选", "why a cold dish got its effect");
assert(effectReason({}, { foodType: "热食", visualSubjectType: "菜品主体" }) === "按热食自动选", "why a hot dish got its effect");
assert(effectReason({}, { foodType: "冷食", visualSubjectType: "手部" }).includes("手"), "a hand-held dish explains that the hand stays still");
assert(effectReason(coldRule, { foodType: "冷食", visualSubjectType: "菜品主体" }).includes("你改的"), "an overridden class says the operator changed it");
assert(effectReason({ effectMode: "custom" }, { foodType: "冷食", visualSubjectType: "菜品主体" }).includes("自定义"), "a hand-tuned dish says it is custom");
for (const preset of PROMPT_PRESETS) {
  const copy = EFFECT_COPY[preset.id];
  assert(Boolean(copy?.camera && copy.moving && copy.still), `effect ${preset.id} needs plain-language camera / moving / still lines`);
  assert(copy.sentence("玉子寿司").includes("玉子寿司"), `effect ${preset.id} should describe the dish by name`);
}
assert(!EFFECT_COPY.glow.sentence("玉子寿司").includes("油"), "the default effect sentence must not promise an oily sheen");

// 换效果：写进所有提示词节点的规则里（批量从样板复制的就是它），只把这一道菜改回自动
const effectNodes = [
  { ...createWorkflowNode("prompt", "p_cold", { x: 0, y: 0 }) },
  { ...createWorkflowNode("prompt", "p_other", { x: 0, y: 0 }) },
  { ...createWorkflowNode("input", "not_prompt", { x: 0, y: 0 }) },
];
effectNodes[0].data = { ...effectNodes[0].data, effectMode: "custom", effectRules: { hot: "flame" } };
const switchedNodes = withEffectRule(effectNodes, "p_cold", { foodType: "冷食", visualSubjectType: "菜品主体" }, "push_in");
const switchedCold = switchedNodes.find(node => node.id === "p_cold");
const switchedOther = switchedNodes.find(node => node.id === "p_other");
assert(switchedCold?.data.effectRules?.cold === "push_in" && switchedOther?.data.effectRules?.cold === "push_in", "a rule change is written to every prompt node, so batch runs pick it up");
assert(switchedCold?.data.effectRules?.hot === "flame", "other classes keep their rules");
assert(switchedCold?.data.effectMode === "rule" && switchedOther?.data.effectMode === undefined, "only the dish you changed goes back to automatic mode");
assert(switchedNodes.find(node => node.id === "not_prompt")?.data.effectRules === undefined, "non-prompt nodes are left alone");
assert(withEffectRule(effectNodes, "p_cold", { foodType: "冷食", visualSubjectType: "菜品主体" }, "steam") === effectNodes, "an effect the dish cannot use is refused");

// 第 3 步算不算做完：效果算得出、没有被拦下就算，不再要人点「实时装配」
const autoNodes = initialNodes.map(node => ({ ...node, data: { ...node.data } }));
const autoInput = autoNodes.find(node => node.data.kind === "input");
const autoProcess = autoNodes.find(node => node.data.kind === "image_process");
const autoPrompt = autoNodes.find(node => node.data.kind === "prompt");
if (!autoInput || !autoProcess || !autoPrompt) throw new Error("workflow seed is missing the dish chain");
autoInput.data = { ...autoInput.data, dishName: "玉子寿司", foodType: "冷食", imagePreview: "/assets/dish.png" };
autoProcess.data = { ...autoProcess.data, processedImagePreview: "/assets/dish-processed.png" };
autoPrompt.data = { ...autoPrompt.data, status: "可生成" };
assert(promptAssemblyBlockReason(autoPrompt, autoNodes, initialEdges) === null, "a ready dish chain has nothing to fix on step 3");
const autoProgress = deriveWorkflowProgress(autoNodes, [], [], initialEdges);
assert(autoProgress.steps[2].complete && autoProgress.steps[3].unlocked, "step 3 counts as done once the effect is valid; nobody has to click 实时装配 any more");

// 改名：这一步叫「动态效果」，说法里不再有装配、槽位
const effectStep = workflowRoutes.find(item => item.path === "/workflow/prompts");
assert(effectStep?.label === "动态效果", "step 3 is renamed 动态效果");
assert(Boolean(effectStep) && !effectStep!.goal.includes("装配") && effectStep!.goal.includes("冷热"), "step 3's goal line explains that effects follow each dish's temperature");
const effectChapter = tutorialChapters.find(chapter => chapter.route === "/workflow/prompts");
assert(effectChapter?.title === "动态效果", "the tutorial chapter follows the rename");
assert(Boolean(effectChapter) && !/L0|L1|L2|槽位|装配/.test(`${effectChapter!.description}${effectChapter!.bullets.join("")}${effectChapter!.checkpoint ?? ""}`), "the tutorial no longer teaches slots or assembly");

// ---------------------------------------------------------------------------
// 第十四批（一）：效果换回该类的默认值后，不该再说「你改的」
// 9/21 验收时看到：把热菜从「只推近镜头」换回「热气升腾」，标签仍写「你改的，热菜都用它」。
// ---------------------------------------------------------------------------
assert(effectReason({ effectRules: { hot: "steam" } }, { foodType: "热食", visualSubjectType: "菜品主体" }) === "按热食自动选", "a rule equal to the class default reads as automatic");
assert(effectReason({ effectRules: { cold: "glow" } }, { foodType: "冷食", visualSubjectType: "菜品主体" }) === "按冷食自动选", "same for cold dishes");
assert(effectReason({ effectRules: { hot: "push_in" } }, { foodType: "热食", visualSubjectType: "菜品主体" }).includes("你改的"), "a rule that differs from the default still reads as changed");

// ---------------------------------------------------------------------------
// 第十四批（二）：新草稿不再被片段库里的旧片段污染
// 9/21 实测：新建草稿一打开，候选池里就多了 20 条别的草稿和测试用的片段，第 4 步还没生成
// 就打了勾，「智能推荐方案」会把测试片段挑进成片。根源是 loadClipLibrary 把整个片段库并进
// 候选池，还按 generatorNodeId 用别的草稿的成品替换本草稿的占位（每份草稿都有 "clips" 节点）。
// 改成：片段库里的片段带 draftId，只有本草稿的片段才进候选池、才能替换占位。
// ---------------------------------------------------------------------------
const seedCandidates = workflowSeed.candidateClips.map(clip => ({ ...clip }));
const seedTimeline = workflowSeed.timeline.map(clip => ({ ...clip }));
const libraryOfOthers = [
  { id: "clip_canvas_test_01.mp4", filename: "test_01.mp4", dish: "test_01", label: "本地片段", tone: "", timelineDuration: 2.5, sourcePath: "/clips/test_01.mp4", sourceUrl: "/api/canvas/clips/library/test_01.mp4", status: "generated" as const },
  { id: "clip_canvas_old.mp4", filename: "old.mp4", dish: "玉子寿司", label: "生成片段", tone: "", timelineDuration: 1.8, sourcePath: "/clips/old.mp4", sourceUrl: "/api/canvas/clips/library/old.mp4", status: "generated" as const, generatorNodeId: "clips", generationJobId: "j-old", draftId: "draft_old", isSelected: true },
];
const untouched = reconcileDraftClips({ draftId: "draft_new", candidateClips: seedCandidates, timeline: seedTimeline, available: libraryOfOthers, activeGenerationNodeIds: new Set() });
assert(JSON.stringify(untouched.candidateClips) === JSON.stringify(seedCandidates), "a fresh draft must not inherit clips from the library or from other drafts");
assert(JSON.stringify(untouched.timeline) === JSON.stringify(seedTimeline), "seed placeholders are never swapped for library clips");

const pendingOwn = { ...createPendingGeneratorClip("clips", 1, "玉子寿司", "寿司"), generationJobId: "j-mine" };
const mine = { ...libraryOfOthers[1], id: "clip_canvas_mine.mp4", filename: "mine.mp4", sourcePath: "/clips/mine.mp4", sourceUrl: "/api/canvas/clips/library/mine.mp4", generationJobId: "j-mine", draftId: "draft_a" };
const foreign = reconcileDraftClips({ draftId: "draft_a", candidateClips: [pendingOwn], timeline: [pendingOwn], available: [libraryOfOthers[1]], activeGenerationNodeIds: new Set() });
assert(foreign.candidateClips.length === 1 && !foreign.candidateClips[0].sourcePath && foreign.candidateClips[0].status === "pending", "another draft's finished clip on the same node id must not replace my pending placeholder");
const own = reconcileDraftClips({ draftId: "draft_a", candidateClips: [pendingOwn], timeline: [pendingOwn], available: [mine, libraryOfOthers[0]], activeGenerationNodeIds: new Set() });
assert(own.candidateClips.length === 1 && own.candidateClips[0].sourcePath === "/clips/mine.mp4", "my own finished clip replaces my pending placeholder");
assert(own.timeline.length === 1 && own.timeline[0].sourcePath === "/clips/mine.mp4", "the timeline placeholder is replaced the same way");
assert(!own.candidateClips.some(clip => clip.filename === "test_01.mp4"), "unlinked local test clips never enter the candidate pool");

const persisted = { ...mine, id: "kept-id", qualityScore: 10, sourceStartSeconds: 1.0, sourceEndSeconds: 2.8, timelineDuration: 1.8, trimConfirmed: true };
const refreshed = reconcileDraftClips({ draftId: "draft_a", candidateClips: [persisted], timeline: [], available: [{ ...mine, qualityScore: 99 }], activeGenerationNodeIds: new Set() });
assert(refreshed.candidateClips.length === 1 && refreshed.candidateClips[0].id === "kept-id" && refreshed.candidateClips[0].qualityScore === 99, "a persisted clip is refreshed from the library but keeps its id");
assert(refreshed.candidateClips[0].sourceStartSeconds === 1.0 && refreshed.candidateClips[0].trimConfirmed === true, "the draft stays the source of truth for trims");
const appended = reconcileDraftClips({ draftId: "draft_a", candidateClips: [], timeline: [], available: [mine, libraryOfOthers[0], libraryOfOthers[1]], activeGenerationNodeIds: new Set() });
assert(appended.candidateClips.length === 1 && appended.candidateClips[0].sourcePath === "/clips/mine.mp4", "only my own clips are added when missing from the draft");

// ---------------------------------------------------------------------------
// 第十四批（三）：默认曲库
// 「默认 BGM」原来只是个名字，背后没有文件，没配人声的成片连音轨都没有。现在
// assets/bgm/default/ 里放几首，每条成片随机用一首；人传了自己的就用自己的；也可以不要音乐。
// ---------------------------------------------------------------------------
assert(bgmModeFor({ bgmMode: "none", bgmName: "默认 BGM", bgmUrl: "" }) === "none", "an explicit mode wins");
assert(bgmModeFor({ bgmName: "song.mp3", bgmUrl: "/api/canvas/drafts/d/files/x.mp3" }) === "custom", "an uploaded file means custom");
assert(bgmModeFor({ bgmName: "默认 BGM", bgmUrl: "" }) === "default", "old drafts that say 默认 BGM get the default library");
assert(bgmModeFor({ bgmName: "默认曲库", bgmUrl: "" }) === "default", "the new label too");
assert(bgmModeFor({ bgmName: "", bgmUrl: "" }) === "none", "no name and no file means no music");
assert(soundConfigFromData(dataFor("sound"), "默认 BGM", "").bgmMode === "default", "the seed sound config starts on the default library");
assert(workflowSeed.composeWorkspaces[0].soundConfig?.bgmMode === "default", "a new draft's first workspace uses the default library");

console.log("model tests passed");
