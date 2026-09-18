import { assetIdForDishName, captionSegmentsFromData, captionSegmentsPatch, captionSegmentsWithTimings, connectWouldCycle, createPendingGeneratorClip, createWorkflowNode, DISH_CATEGORY_OPTIONS, inferDishCategory, initialEdges, initialNodes, normalizeDishCategory, OVERLAY_FONT_OPTIONS, overlayCoordinatesFromItem, overlayItemsFromData, overlayStyleFromItem, randomizeClipSelection, recommendClipSelection, reconcileStalePendingGeneratorClips, removeNodeAndEdges, reorderById, repairCaptionVoiceSegments, resolveDishCategory, resolveGeneratorNodeStatus, soundConfigFromData, totalTimelineDuration, voiceItemsFromData } from "./model.ts";
import { applyPromptPreset, assemblePrompt, availablePromptPresets, CAMERA_OPTIONS, DEFAULT_PROMPT_CONFIG, ELEMENT_OPTIONS, L2_OPTIONS, matchPromptPreset, PROMPT_PRESETS, SHOT_SIZE_OPTIONS, type PromptConfig } from "./promptAssembler.ts";
import { browserDraftId, DRAFT_ID_STORAGE_KEY } from "./draftIdentity.ts";
import { deriveWorkflowProgress, firstIncompleteWorkflowRoute, isWorkflowRouteUnlocked } from "./workflowProgress.ts";
import { routeForPath } from "./router.ts";
import { canAssemblePromptNode, promptAssemblyBlockReason, promptUpstreamNodes } from "./promptAssemblyReadiness.ts";
import { generatorGenerationBlockReason } from "./generatorReadiness.ts";
import { batchPlanReadiness, missingTemplateKinds, REQUIRED_TEMPLATE_KINDS } from "./batchPlanReadiness.ts";

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

console.log("model tests passed");
