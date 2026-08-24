import { connectWouldCycle, initialEdges, initialNodes, removeNodeAndEdges, reorderById, totalTimelineDuration } from "./model.ts";
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
