import { captionSegmentsFromData, captionSegmentsPatch, captionSegmentsWithTimings, connectWouldCycle, createPendingGeneratorClip, DISH_CATEGORY_OPTIONS, inferDishCategory, initialEdges, initialNodes, OVERLAY_FONT_OPTIONS, overlayCoordinatesFromItem, overlayItemsFromData, overlayStyleFromItem, randomizeClipSelection, recommendClipSelection, removeNodeAndEdges, reorderById, resolveDishCategory, resolveGeneratorNodeStatus, totalTimelineDuration, voiceItemsFromData } from "./model.ts";
import { assemblePrompt, CAMERA_OPTIONS, ELEMENT_OPTIONS, L2_OPTIONS, SHOT_SIZE_OPTIONS, type PromptConfig } from "./promptAssembler.ts";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(connectWouldCycle(initialEdges, "sound", "assets") === true, "cycle connection was accepted");
assert(connectWouldCycle(initialEdges, "assets", "sound") === false, "acyclic connection was rejected");

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
assert(pendingClip.dishCategory === "正餐", "pending generator clip should have a default dish category");

assert(inferDishCategory("蜜瓜") === "水果", "fruit fallback classification is incorrect");
assert(inferDishCategory("抹茶布丁") === "甜品", "dessert fallback classification is incorrect");
assert(inferDishCategory("冷食三文鱼") === "其他", "food temperature must not imply fruit classification");
assert(resolveDishCategory({ dish: "冷食三文鱼", dishCategory: "正餐" }) === "正餐", "explicit dish category was ignored");

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
  { id: "main-1", dish: "三文鱼", label: "", tone: "", timelineDuration: 2, sourcePath: "main-1.mp4", dishCategory: "正餐" as const },
  { id: "main-2", dish: "天妇罗", label: "", tone: "", timelineDuration: 2, sourcePath: "main-2.mp4", dishCategory: "小吃" as const },
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
  { id: "same-dish", dish: "天妇罗", label: "重复菜品", tone: "", timelineDuration: 2, sourcePath: "same-dish.mp4", dishCategory: "小吃" as const, qualityScore: 100, qualityWarnings: [] },
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
console.log("model tests passed");
