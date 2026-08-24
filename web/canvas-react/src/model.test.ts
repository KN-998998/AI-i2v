import { connectWouldCycle, createPendingGeneratorClip, inferDishCategory, initialEdges, initialNodes, OVERLAY_FONT_OPTIONS, overlayCoordinatesFromItem, overlayItemsFromData, overlayStyleFromItem, randomizeClipSelection, removeNodeAndEdges, reorderById, resolveDishCategory, totalTimelineDuration, voiceItemsFromData } from "./model.ts";
import { assemblePrompt, CAMERA_OPTIONS, ELEMENT_OPTIONS, L2_OPTIONS, type PromptConfig } from "./promptAssembler.ts";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(connectWouldCycle(initialEdges, "sound", "assets") === true, "cycle connection was accepted");
assert(connectWouldCycle(initialEdges, "assets", "sound") === false, "acyclic connection was rejected");

const next = removeNodeAndEdges(initialNodes, initialEdges, "prompt");
assert(!next.nodes.some(node => node.id === "prompt"), "node was not removed");
assert(next.edges.length === 2, "connected edges were not removed");
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
assert(pendingClip.status === "pending" && !pendingClip.sourcePath, "generator clip should wait for a real file");
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

assert(ELEMENT_OPTIONS.length === 8, "L0 options are incomplete");
assert(CAMERA_OPTIONS.length === 8, "camera options are incomplete");
assert(L2_OPTIONS.length === 8, "L2 options are incomplete");

const validPrompt: PromptConfig = {
  mode: "keyframes",
  camera_move: "locked_off",
  camera_amplitude: "subtle",
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
assert(assembled.negative_prompt.includes("飞溅") && assembled.cfg_scale === 0.45, "negative prompt or cfg scale was not assembled");

const invalidPrompt = assemblePrompt({ ...validPrompt, l2_dynamics: [...validPrompt.l2_dynamics, { type: "flame", target: "菜品" }] });
assert(invalidPrompt.blocked && invalidPrompt.errors.some(item => item.code === "V2"), "L2 upper bound was not blocked");
assert(invalidPrompt.prompt === "" && invalidPrompt.cfg_scale === 0, "blocked prompt still produced output");

const missingEndImage = assemblePrompt({ ...validPrompt, endImageReady: false });
assert(missingEndImage.errors.some(item => item.code === "V7"), "missing tail frame was not detected");
console.log("model tests passed");
