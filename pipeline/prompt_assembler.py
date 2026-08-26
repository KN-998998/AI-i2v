# -*- coding: utf-8 -*-
"""
可灵 3.0 图生视频 · 提示词组装模块（纯函数）
================================================
规格来源: 08_技术方案/kling-prompt规划_cc版.md (CC v1.0) + 通用图生视频提示词装配方案.md

纯函数: assemble_prompt(config) -> PromptResult
无副作用、无网络请求、同输入必同输出。

设计原则（违反前必须先问用户）:
  1. 可灵是扩散模型不是 LLM —— 禁止任务概括/示例进 prompt
  2. 否定句走 negative_prompt —— 空槽位整段删除，禁止"无XX"占位句
  3. 一条 3 秒切片只能有一个镜头动作 —— camera_move 单选
  4. 注意力预算有限 —— 次级动态(L2)上限 2 项
  5. 条件逻辑在前端解决 —— 禁止"若/如果"条件句式
  6. 分段结构 = 指令隔离 —— 六段顺序固定不调整
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ──────────────────────────────────────────────────────────────
# 数据契约
# ──────────────────────────────────────────────────────────────

Mode = str          # "single_image" | "keyframes"
CameraMove = str    # dolly_in / dolly_out / crane_down / crane_up / truck_left / truck_right / orbit_right / locked_off
Amplitude = str     # subtle / light / medium
ShotSize = str      # close_up / medium_close / medium / wide
Element = str       # dish_cold / dish_hot / garnish / tableware / surface / hand / chef / backdrop
L1Subject = str     # dish_cold / dish_hot / tableware / hand / chef / none
ActionLevel = int   # 1 / 2 / 3
ActionVerb = str    # sprinkle_seasoning / pour_sauce / steady_plate / rotate_plate / pick_food / cut_slice / lift_plate / place_garnish
L2Type = str        # steam / liquid_pour / liquid_ripple / flame / ice_mist / specular / fabric_sway / person_idle
SpeedCurve = str    # uniform / ease_in / ease_out


@dataclass
class L2Item:
    type: L2Type
    target: str          # 作用对象名词，1-8 字符，见校验


@dataclass
class PromptConfig:
    mode: Mode
    camera_move: CameraMove
    camera_amplitude: Amplitude
    elements: list                       # L0 画面元素勾选，长度 >= 1
    l1_subject: L1Subject                # L1 主运动对象
    shot_size: ShotSize = "close_up"
    l1_action_level: Optional[int] = None   # 仅 hand/chef 时非空
    l1_action_verb: Optional[str] = None    # 仅 action_level ∈ {2,3} 时非空
    l2_dynamics: list = field(default_factory=list)   # L2 次级动态，0..2 项
    speed_curve: Optional[str] = None    # 仅 keyframes 时非空
    seamless_loop: bool = False


@dataclass
class Issue:
    code: str
    message: str
    field: str


@dataclass
class PromptResult:
    blocked: bool
    errors: list
    warnings: list
    prompt: str
    negative_prompt: str
    cfg_scale: float
    suggested_trim: str = ""       # 二期: 智能裁切建议, 本期返回空


# ──────────────────────────────────────────────────────────────
# 枚举与文案词典（中文文案为精确字符串，逐字复制）
# ──────────────────────────────────────────────────────────────

CAMERA_TEXT = {
    "dolly_in":    "缓慢推进（dolly in）",
    "dolly_out":   "缓慢后拉（dolly out）",
    "crane_down":  "缓慢俯视下降（crane down）",
    "crane_up":    "缓慢上升（crane up）",
    "truck_left":  "极小幅左横移（truck left）",
    "truck_right": "极小幅右横移（truck right）",
    "orbit_right": "小角度顺时针环绕（orbit right）",
    "locked_off":  "固定机位不动（locked-off）",
}

AMPLITUDE_TEXT = {
    "subtle": "画面极轻微变化（约8%）",
    "light":  "画面轻微变化（约15%）",
    "medium": "画面中等变化（约25%）",
}

SHOT_SIZE_TEXT = {
    "close_up": "特写，菜品主体约占画面70%-85%，突出食材质感与细节，保持原图构图和主体位置不变",
    "medium_close": "近景，菜品主体约占画面55%-70%，兼顾菜品细节与摆盘关系，保持原图构图和主体位置不变",
    "medium": "中景，菜品主体约占画面35%-55%，保留餐具与桌面环境，保持原图构图和主体位置不变",
    "wide": "远景，菜品主体约占画面20%-35%，展示完整餐桌与环境氛围，保持原图构图和主体位置不变",
}

ELEMENT_LABEL = {
    "dish_cold":  "菜品",
    "dish_hot":   "菜品",
    "garnish":    "配菜与装饰",
    "tableware":  "餐具器皿",
    "surface":    "桌面",
    "hand":       "手部",
    "chef":       "人物",
    "backdrop":   "背景陈设",
}

CAN_BE_L1 = {"dish_cold", "dish_hot", "tableware", "hand", "chef"}

# 单图模式 L1 主运动文案
L1_SINGLE = {
    "dish_cold": "菜品与摆盘保持原位不动，仅湿润切面高光随镜头角度缓慢滑移",
    "dish_hot":  "菜品保持原位不动，仅表面油光随镜头角度缓慢流动",
    "tableware": "餐具保持原位不动，仅釉面与金属反光随镜头角度缓慢滑过",
    "none":      "画面内所有元素保持完全静止，仅视角发生变化",
}

# 首尾帧模式 L1 主运动文案
L1_KEYFRAMES = {
    "dish_cold":  "菜品位置与形态不变，仅视角与高光从首帧状态连续过渡到尾帧状态",
    "dish_hot":   "菜品位置与形态不变，仅视角与高光从首帧状态连续过渡到尾帧状态",
    "tableware":  "餐具位置不变，仅反光与视角从首帧状态连续过渡到尾帧状态",
    "none":       "镜头从首帧机位连续{camera}至尾帧机位",
}

# 动作幅度（S = 手/厨师, V = 动词）
ACTION_SINGLE = {
    1: "{S}保持当前姿势与握持关系不变，仅有极轻微自然稳定微动",
    2: "{S}做出{V}的动作片段，动作缓慢连贯，握持关系不变，动作不完成",
    3: "{S}在三秒内缓慢完成一次{V}并自然停住",
}
ACTION_KEYFRAMES = {
    1: "{S}姿态从首帧连续过渡到尾帧，过程中仅有极轻微自然微动",
    2: "{S}连贯自然地从首帧姿态过渡到尾帧姿态，完成{V}的动作片段，中途不停顿、不回退",
    3: "{S}连贯自然地从首帧姿态过渡到尾帧姿态，完成一次{V}，中途不停顿、不回退",
}

SUBJECT_NOUN = {"hand": "手", "chef": "厨师"}

ACTION_VERB_TEXT = {
    "sprinkle_seasoning": "撒落调味",
    "pour_sauce":         "淋下酱汁",
    "steady_plate":       "轻扶盘沿",
    "rotate_plate":       "缓慢转动餐盘",
    "pick_food":          "夹起食材",
    "cut_slice":          "切下一刀",
    "lift_plate":         "端起餐盘",
    "place_garnish":      "摆放装饰",
}

L2_TEXT = {
    "steam":        ("极轻缓热气自{T}持续缓慢上升，不成团、不遮挡主体", "浓烟, 白雾遮挡, 云雾成团, 烟雾旋转"),
    "liquid_pour":  ("细流从{T}匀速落下，落点固定，流量恒定", "飞溅, 液体倒流, 液面暴涨, 外溢, 容器变形, 液体凭空出现"),
    "liquid_ripple": ("{T}表面极轻微晃动，反光随之位移，液面不溢出", "沸腾, 翻涌, 液面剧烈起伏, 溢出"),
    "flame":        ("{T}处小簇火焰边缘轻微摇曳，火势范围不变", "火势蔓延, 冒黑烟, 食材碳化, 焦化加深, 爆燃"),
    "ice_mist":     ("极淡冷雾贴{T}表面缓慢流动，冷凝水珠保持附着不滑落", "水珠滑落, 结霜蔓延, 融化, 白雾弥漫"),
    "specular":     ("{T}湿润表面高光随镜头角度缓慢滑移", ""),
    "fabric_sway":  ("{T}边缘极轻微自然飘动", "剧烈飘动, 形变"),
    "person_idle":  ("{T}保持姿态不变，仅极轻微呼吸起伏与自然眨眼", "五官变形, 手指畸形, 表情夸张, 身体扭曲"),
}

SPEED_CURVE_TEXT = {
    "uniform": "全程匀速",
    "ease_in": "慢起后转匀速",
    "ease_out": "匀速后自然减速",
}

NEGATIVE_BASE = (
    "变形，融化，收缩，蠕动，主体位移，新增元素，元素消失，多余的手，文字，logo，水印，"
    "抖动，晃动，快速运镜，镜头切换，分镜，画面跳变，曝光跳变，闪烁，重新打光，色彩漂移，"
    "涂抹感，二次构图，画质劣化"
)
NEGATIVE_KEYFRAMES_EXTRA = "闪切，跳帧，转场特效，叠化，画面突变，中途重构，动作回退"
NEGATIVE_HAND_EXTRA = "面部入镜，人物面部，全身入镜"


# ──────────────────────────────────────────────────────────────
# 校验规则
# ──────────────────────────────────────────────────────────────

def _run_blocking_rules(cfg: PromptConfig) -> list:
    errs = []
    L1_LABEL = ELEMENT_LABEL.get(cfg.l1_subject, "")

    # V1: L1 未在 elements 中勾选（none 除外）
    if cfg.l1_subject != "none" and cfg.l1_subject not in cfg.elements:
        errs.append(Issue("V1", "主运动对象必须先在画面元素中勾选", "l1_subject"))

    # V2: L2 超过 2 项
    if len(cfg.l2_dynamics) > 2:
        errs.append(Issue("V2", "3 秒最多承载 2 个次级动态，超出会导致每项都退化为轻微抖动", "l2_dynamics"))

    # V3: L2 target 与 L1 元素 label 相同
    # 豁免：L1 是菜品主体(dish_cold/dish_hot) 且 L2 是 steam/specular 时，
    #   target="菜品" 指主体表面（蒸汽从菜品表面升起 / 高光在表面滑移），
    #   这是合理场景，不算冲突。其余组合仍互斥（如 flame target=菜品 会报 V3）。
    l1_is_dish = cfg.l1_subject in ("dish_cold", "dish_hot")
    for item in cfg.l2_dynamics:
        surface_ok = l1_is_dish and item.type in ("steam", "specular")
        if item.target == L1_LABEL and not surface_ok:
            errs.append(Issue("V3", "次级动态不能指向主运动对象，二者会互相抵消", "l2_dynamics"))
            break

    # V4: flame 与 ice_mist 互斥
    types = [i.type for i in cfg.l2_dynamics]
    if "flame" in types and "ice_mist" in types:
        errs.append(Issue("V4", "火焰与冰雾互斥，不能同时生成", "l2_dynamics"))

    # V5: seamless_loop 与不可逆动作冲突
    if cfg.seamless_loop and ("liquid_pour" in types or (cfg.l1_action_level or 0) >= 2):
        errs.append(Issue("V5", "无缝循环要求首尾状态一致，与不可逆动作冲突", "seamless_loop"))

    # V6: action_level 仅适用 hand/chef
    if cfg.l1_action_level is not None and cfg.l1_subject not in ("hand", "chef"):
        errs.append(Issue("V6", "动作幅度仅适用于手部或厨师主体", "l1_action_level"))

    # V7: keyframes 未上传尾帧（由 UI 层保证，此处校验 cfg.speed_curve 兜底）
    if cfg.mode == "keyframes" and cfg.speed_curve is None:
        errs.append(Issue("V7", "首尾帧模式需要上传尾帧图片", "end_image"))

    # V8: single_image 不应有 speed_curve
    if cfg.mode == "single_image" and cfg.speed_curve is not None:
        errs.append(Issue("V8", "速度曲线仅适用于首尾帧模式", "speed_curve"))

    # V9: l2 target 校验
    for item in cfg.l2_dynamics:
        if not _validate_target(item.target):
            errs.append(Issue("V9", "作用对象只能填写简短名词（1-8字，无标点，无条件/否定词）", "l2_dynamics"))
            break

    # V10: action_level ∈ {2,3} 必须有 verb
    if (cfg.l1_action_level in (2, 3)) and not cfg.l1_action_verb:
        errs.append(Issue("V10", "请选择具体动作", "l1_action_verb"))

    # V11: elements 为空
    if not cfg.elements:
        errs.append(Issue("V11", "请至少勾选一项画面元素", "elements"))

    # V12: seamless_loop 与 camera_move
    if cfg.seamless_loop and cfg.camera_move not in ("truck_left", "truck_right", "locked_off"):
        errs.append(Issue("V12", "无缝循环仅支持极小幅横移或固定机位（推进/后拉无法闭环）", "camera_move"))

    return errs


def _validate_target(t: str) -> bool:
    t = t.strip()
    if not (1 <= len(t) <= 8):
        return False
    for ch in t:
        if not ch.isalnum():
            return False   # 允许中文名词，拒绝空格、标点和符号
    for w in ("若", "如果", "则", "当", "存在", "或者", "否则", "不", "无", "没有", "禁止"):
        if w in t:
            return False
    return True


def _run_warning_rules(cfg: PromptConfig) -> list:
    warns = []
    types = [i.type for i in cfg.l2_dynamics]
    if "liquid_pour" in types and cfg.camera_move == "dolly_in":
        warns.append(Issue("W1", "推进会拉长流体运动路径，飞溅风险较高，建议改用固定机位", "camera_move"))
    if cfg.mode == "single_image" and cfg.l1_action_level == 3:
        warns.append(Issue("W2", "单图模式下模型需自行编造动作终点，3 秒内成片率较低。建议改用首尾帧模式，由尾帧给定终点", "mode"))
    if len(cfg.elements) < 2:
        warns.append(Issue("W3", "画面元素勾选过少，锁定层约束偏弱，非主体元素可能出现意外变化", "elements"))
    if cfg.camera_move == "locked_off" and cfg.camera_amplitude != "subtle":
        warns.append(Issue("W4", "固定机位下运动幅度设置无效，将被忽略", "camera_amplitude"))
    if cfg.mode == "single_image" and cfg.l1_subject == "none" and not cfg.l2_dynamics:
        warns.append(Issue("W5", "当前配置下画面几乎完全静止，生成结果可能接近静态图", "l1_subject"))
    return warns


# ──────────────────────────────────────────────────────────────
# 组装算法
# ──────────────────────────────────────────────────────────────

def _compute_locked_set(cfg: PromptConfig) -> list:
    """锁定层 = elements 的 label 集合 - L1 - L2 target 命中，按行序去重。"""
    locked = [ELEMENT_LABEL[e] for e in cfg.elements]
    # 移除 L1 对应元素
    if cfg.l1_subject != "none":
        locked = [x for x in locked if x != ELEMENT_LABEL.get(cfg.l1_subject, "")]
    # 移除被 L2 target 命中的
    targets = {i.target for i in cfg.l2_dynamics}
    locked = [x for x in locked if x not in targets]
    # 去重保序（dish_cold/dish_hot 都映射"菜品"）
    seen, out = set(), []
    for x in locked:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _l1_text(cfg: PromptConfig) -> str:
    if cfg.l1_subject in ("hand", "chef"):
        S = SUBJECT_NOUN[cfg.l1_subject]
        level = cfg.l1_action_level or 1
        table = ACTION_KEYFRAMES if cfg.mode == "keyframes" else ACTION_SINGLE
        tpl = table[level]
        text = tpl.replace("{S}", S)
        if cfg.l1_action_verb:
            V = ACTION_VERB_TEXT.get(cfg.l1_action_verb, "")
            text = text.replace("{V}", V)
        if cfg.l1_subject == "chef":
            text += "，面部表情平静自然，五官稳定"
        return text
    table = L1_KEYFRAMES if cfg.mode == "keyframes" else L1_SINGLE
    text = table.get(cfg.l1_subject, "")
    if cfg.l1_subject == "none" and cfg.mode == "keyframes":
        text = text.replace("{camera}", CAMERA_TEXT.get(cfg.camera_move, ""))
    return text


def _build_sections(cfg: PromptConfig, locked: list) -> list:
    sections = []
    sections.append(f"【景别】{SHOT_SIZE_TEXT.get(cfg.shot_size, SHOT_SIZE_TEXT['close_up'])}。")

    if cfg.mode == "single_image":
        # 镜头段
        if cfg.camera_move == "locked_off":
            sections.append("【镜头】固定机位不动（locked-off），画面构图保持不变。")
        else:
            sections.append(
                f"【镜头】{CAMERA_TEXT.get(cfg.camera_move, '')}，极慢匀速，单镜头一镜到底，"
                f"{AMPLITUDE_TEXT.get(cfg.camera_amplitude, '')}。"
            )
        # 主运动
        sections.append(f"【主运动】{_l1_text(cfg)}。")
        # 次级动态
        if cfg.l2_dynamics:
            l2_texts = []
            for item in cfg.l2_dynamics:
                tpl, _ = L2_TEXT[item.type]
                l2_texts.append(tpl.replace("{T}", item.target))
            sections.append(f"【次级动态】{'；'.join(l2_texts)}，幅度极小，不影响主体形态。")
        # 锁定（空则整段删除）
        if locked:
            sections.append(f"【锁定】{'、'.join(locked)}保持绝对静止，位置、数量、形状、颜色不变。")
        # 光线
        sections.append("【光线】光源固定，明暗关系不变，无重新打光。")
        # 节奏（循环特例）
        if cfg.seamless_loop:
            sections.append("【节奏】动作与运镜同步开始，全程匀速连续，首尾画面状态接近，可无缝循环。")
        else:
            sections.append("【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。")
    else:
        # keyframes 模式：不输出镜头段
        sections.append("【过渡】从首帧画面平滑连续过渡到尾帧画面，单镜头一镜到底，无切换、无叠化。")
        speed = SPEED_CURVE_TEXT.get(cfg.speed_curve or "uniform", "全程匀速")
        sections.append(f"【主运动】{_l1_text(cfg)}，{speed}。")
        if cfg.l2_dynamics:
            l2_texts = []
            for item in cfg.l2_dynamics:
                tpl, _ = L2_TEXT[item.type]
                l2_texts.append(tpl.replace("{T}", item.target))
            sections.append(f"【次级动态】{'；'.join(l2_texts)}，全程连续不中断。")
        if locked:
            sections.append(f"【锁定】{'、'.join(locked)}在整个过渡过程中保持位置与形态不变。")
        sections.append("【光线】光源固定，明暗随视角连续渐变，不跳变。")
        sections.append("【节奏】过渡末端稳定停在尾帧状态。")

    return sections


def _build_negative(cfg: PromptConfig) -> str:
    parts = [NEGATIVE_BASE]
    if cfg.mode == "keyframes":
        parts.append(NEGATIVE_KEYFRAMES_EXTRA)
    if cfg.l1_subject == "hand":
        parts.append(NEGATIVE_HAND_EXTRA)
    for item in cfg.l2_dynamics:
        _, neg = L2_TEXT[item.type]
        if neg:
            parts.append(neg)
    # 去重保序
    seen, out = set(), []
    for part in parts:
        for word in part.split("，") if "，" in part else part.split(", "):
            w = word.strip()
            if w and w not in seen:
                seen.add(w)
                out.append(w)
    return "，".join(out)


def _map_cfg_scale(cfg: PromptConfig) -> float:
    """经验起点（CC §5.5）。可灵 API 2.0 无此参数，调用层按需兼容处理。"""
    if cfg.mode == "keyframes":
        return 0.45
    if cfg.l1_subject in ("dish_cold", "dish_hot", "tableware", "none"):
        return 0.70
    level = cfg.l1_action_level or 1
    return {1: 0.60, 2: 0.50, 3: 0.40}[level]


# ──────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────

def assemble_prompt(cfg: PromptConfig) -> PromptResult:
    errors = _run_blocking_rules(cfg)
    warnings = _run_warning_rules(cfg)

    if errors:
        return PromptResult(
            blocked=True, errors=errors, warnings=warnings,
            prompt="", negative_prompt="", cfg_scale=0.0,
        )

    locked = _compute_locked_set(cfg)
    sections = _build_sections(cfg, locked)
    prompt = "\n".join(s for s in sections if s.strip())

    return PromptResult(
        blocked=False, errors=[], warnings=warnings,
        prompt=prompt,
        negative_prompt=_build_negative(cfg),
        cfg_scale=_map_cfg_scale(cfg),
    )


if __name__ == "__main__":
    # 简单自测
    c = PromptConfig(
        mode="single_image", camera_move="dolly_in", camera_amplitude="light",
        elements=["dish_cold", "garnish", "tableware", "surface"],
        l1_subject="dish_cold", l2_dynamics=[],
    )
    r = assemble_prompt(c)
    print(r.prompt)
    print("---")
    print("cfg_scale:", r.cfg_scale, "| blocked:", r.blocked, "| warnings:", [w.code for w in r.warnings])
