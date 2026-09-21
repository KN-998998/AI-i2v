# -*- coding: utf-8 -*-
"""
第 3 步「动态效果」的规则（后端这一份）
========================================
每道菜的效果按它自己的冷热和画面主体现算，不再照搬提示词节点里存着的那一份配置。

起因（Patrick 2026-09-21 实测）：模板是在知道这道菜是冷食之前建的，存的是热菜写法，
冷的玉子寿司拿到的指令是「仅表面油光随镜头角度缓慢流动」；批量生产又把样板的提示词
节点原样复制给每道菜，样板选了「热气升腾」的话冷菜也照样冒热气，校验还不拦。

这是 frontend/src/effectRules.ts 的 Python 版：批量生产只在后端跑，效果必须在这里也能
算一遍。两边由 tests/fixtures/effect_presets.json（272 条，用前端 applyPromptPreset 生成）
逐项锁住，改一边另一边会立刻红。
"""
from __future__ import annotations

from typing import Any, Optional

EffectClass = str          # cold / hot / mixed / person
PresetId = str             # glow / steam / chill / flame / push_in / orbit / loop / pour / sprinkle / plating

# 冷菜和没标冷热的都用光泽流转：它对任何菜都成立。热菜用热气升腾。
# 原图有手或厨师时同样用光泽流转——人保持姿势不动，只有高光在走，让 AI 去动一只手
# 远比让它动高光容易出废片。
DEFAULT_EFFECT_RULES: dict[EffectClass, PresetId] = {"cold": "glow", "hot": "steam", "mixed": "glow", "person": "glow"}

_PERSON_SUBJECTS = ("手部", "厨师上半身", "手部+厨师上半身")
_VISUAL_SUBJECTS = ("菜品主体",) + _PERSON_SUBJECTS
_FOOD_TYPES = ("冷食", "热食", "混合/多温")

# (效果, 只适用于这种冷热, 是否需要画面里有人)，和前端 PROMPT_PRESETS 同序同内容。
_PRESETS: tuple[tuple[PresetId, Optional[str], bool], ...] = (
    ("glow", None, False),
    ("steam", "热食", False),
    ("chill", "冷食", False),
    ("flame", "热食", False),
    ("push_in", None, False),
    ("orbit", None, False),
    ("loop", None, False),
    ("pour", None, True),
    ("sprinkle", None, True),
    ("plating", None, True),
)


def _default_config() -> dict[str, Any]:
    """前端 DEFAULT_PROMPT_CONFIG 的等价物。每次新建，免得共用同一个 list。"""
    return {
        "mode": "single_image",
        "camera_move": "orbit_right",
        "camera_amplitude": "subtle",
        "shot_size": "close_up",
        "elements": ["dish_hot", "garnish", "tableware", "surface", "backdrop"],
        "l1_subject": "dish_hot",
        "l1_action_level": None,
        "l1_action_verb": None,
        "l2_dynamics": [{"type": "specular", "target": "菜品"}],
        "speed_curve": None,
        "seamless_loop": False,
    }


def _normalized_visual(value: Any) -> str:
    """认不出来的值（没填、乱填）一律当「菜品主体」，和前端的归一化一致。"""
    text = str(value or "")
    return text if text in _VISUAL_SUBJECTS else "菜品主体"


def _normalized_food(value: Any) -> str:
    text = str(value or "")
    return text if text in _FOOD_TYPES else ""


def _person_subject(visual: str) -> Optional[str]:
    if visual == "厨师上半身":
        return "chef"
    if visual in ("手部", "手部+厨师上半身"):
        return "hand"
    return None


def available_presets(food_type: Any, visual_subject_type: Any) -> list[PresetId]:
    """这道菜用得了哪些效果。口径照搬前端 availablePromptPresets。"""
    food = _normalized_food(food_type)
    person = _person_subject(_normalized_visual(visual_subject_type))
    usable = []
    for preset_id, only_food, needs_person in _PRESETS:
        if needs_person and not person:
            continue
        # 混合/多温 两头都算数；没标冷热的不拦，冷热本来就未知。
        if only_food and food and food != "混合/多温" and food != only_food:
            continue
        usable.append(preset_id)
    return usable


def effect_class(food_type: Any, visual_subject_type: Any) -> EffectClass:
    """
    四类菜。原图有手或厨师的单独一类：它能不能淋酱、撒料，跟冷热无关。
    没标冷热的归入「冷热混合」，因为这一类的默认效果冷热两边都成立。
    """
    if str(visual_subject_type or "") in _PERSON_SUBJECTS:
        return "person"
    food = _normalized_food(food_type)
    if food == "冷食":
        return "cold"
    if food == "热食":
        return "hot"
    return "mixed"


def preset_for_dish(food_type: Any, visual_subject_type: Any, rules: Any = None) -> PresetId:
    """
    这道菜该用的效果：先看样板规则里它那一类改成了什么，没改过就用默认。
    取到的效果这道菜用不了时（冷菜配到热气升腾、没有手的图配到淋酱）退回光泽流转——
    宁可退回一个一定成立的效果，也不要让它在生成时被校验拦掉。
    """
    klass = effect_class(food_type, visual_subject_type)
    wanted = None
    if isinstance(rules, dict):
        wanted = rules.get(klass)
    wanted = str(wanted or "") or DEFAULT_EFFECT_RULES[klass]
    return wanted if wanted in available_presets(food_type, visual_subject_type) else "glow"


def apply_preset(config: dict[str, Any], preset_id: PresetId) -> dict[str, Any]:
    """把效果套到配置上。逐行对应前端 applyPromptPreset，改动必须两边一起改。"""
    current = dict(config)
    visual = _normalized_visual(current.get("visual_subject_type"))
    current["visual_subject_type"] = visual
    dish = "dish_cold" if current.get("food_type") == "冷食" else "dish_hot"
    person = _person_subject(visual)
    elements = [dish, "garnish", "tableware", "surface", "backdrop"]
    if visual in ("手部", "手部+厨师上半身"):
        elements.append("hand")
    if visual in ("厨师上半身", "手部+厨师上半身"):
        elements.append("chef")
    mode = str(current.get("mode") or "single_image")
    base = {
        **current,
        "mode": mode,
        "elements": elements,
        "seamless_loop": False,
        "speed_curve": (current.get("speed_curve") or "uniform") if mode == "keyframes" else None,
    }

    def idle(subject: str) -> dict[str, Any]:
        # 有人物入镜时主运动对象必须是人物，「不做动作」就是存在感级（1）。
        if person:
            return {"l1_subject": person, "l1_action_level": 1, "l1_action_verb": None}
        return {"l1_subject": subject, "l1_action_level": None, "l1_action_verb": None}

    def act(verb: str) -> dict[str, Any]:
        actor = person or "hand"
        if actor not in elements:
            elements.append(actor)
        return {"l1_subject": actor, "l1_action_level": 2, "l1_action_verb": verb}

    if preset_id == "glow":
        return {**base, "camera_move": "orbit_right", "camera_amplitude": "subtle", "shot_size": "close_up", **idle(dish), "l2_dynamics": [{"type": "specular", "target": "菜品"}]}
    if preset_id == "steam":
        return {**base, "camera_move": "dolly_in", "camera_amplitude": "subtle", "shot_size": "close_up", **idle(dish), "l2_dynamics": [{"type": "steam", "target": "菜品"}]}
    # 冰雾、火焰不在「主运动对象 = 菜品」的次级动态豁免名单里，所以主运动改为纯运镜。
    if preset_id == "chill":
        return {**base, "camera_move": "dolly_in", "camera_amplitude": "subtle", "shot_size": "close_up", **idle("none"), "l2_dynamics": [{"type": "ice_mist", "target": "菜品"}]}
    if preset_id == "flame":
        return {**base, "camera_move": "dolly_in", "camera_amplitude": "subtle", "shot_size": "close_up", **idle("none"), "l2_dynamics": [{"type": "flame", "target": "菜品"}]}
    # 纯运镜也保留一项高光滑移：镜头动时高光本来就会动，且避免「几乎没有任何动作」的警告。
    if preset_id == "push_in":
        return {**base, "camera_move": "dolly_in", "camera_amplitude": "light", "shot_size": "medium_close", **idle("none"), "l2_dynamics": [{"type": "specular", "target": "菜品"}]}
    if preset_id == "orbit":
        return {**base, "camera_move": "orbit_right", "camera_amplitude": "light", "shot_size": "close_up", **idle("none"), "l2_dynamics": [{"type": "specular", "target": "菜品"}]}
    if preset_id == "loop":
        return {**base, "camera_move": "locked_off", "camera_amplitude": "subtle", "shot_size": "close_up", **idle(dish), "seamless_loop": True,
                "l2_dynamics": [{"type": "steam" if dish == "dish_hot" else "specular", "target": "菜品"}]}
    if preset_id == "pour":
        return {**base, "camera_move": "locked_off", "camera_amplitude": "subtle", "shot_size": "medium_close", **act("pour_sauce"), "l2_dynamics": []}
    if preset_id == "sprinkle":
        return {**base, "camera_move": "locked_off", "camera_amplitude": "subtle", "shot_size": "medium_close", **act("sprinkle_seasoning"), "l2_dynamics": []}
    if preset_id == "plating":
        return {**base, "camera_move": "orbit_right", "camera_amplitude": "subtle", "shot_size": "medium_close", **act("place_garnish"), "l2_dynamics": []}
    raise ValueError(f"未知的动态效果：{preset_id}")


def _match_dish_temperature(config: dict[str, Any], food: str) -> dict[str, Any]:
    """菜品主体元素跟着这道菜的冷热走；混合和没标冷热的不动，套餐里两种都可能是对的。"""
    if food not in ("冷食", "热食"):
        return config
    wanted = "dish_cold" if food == "冷食" else "dish_hot"
    stale = "dish_hot" if food == "冷食" else "dish_cold"
    elements: list[str] = []
    for item in config.get("elements") or []:
        value = wanted if item == stale else item
        if value not in elements:
            elements.append(value)
    subject = config.get("l1_subject")
    return {**config, "elements": elements, "l1_subject": wanted if subject == stale else subject}


def _follow_visual_subject(config: dict[str, Any], visual: str) -> dict[str, Any]:
    """
    有手或厨师入镜时，主运动对象必须是人物，不然校验会拦。
    这就是原来 canvas_generation._prompt_data_for_asset 里那段补人物的逻辑。
    """
    if visual == "菜品主体":
        return {**config, "visual_subject_type": visual}
    required = {"手部": ["hand"], "厨师上半身": ["chef"], "手部+厨师上半身": ["hand", "chef"]}[visual]
    elements = list(config.get("elements") or [])
    for item in required:
        if item not in elements:
            elements.append(item)
    allowed = {"chef"} if visual == "厨师上半身" else {"hand", "chef"}
    subject = str(config.get("l1_subject") or "")
    if subject not in allowed:
        subject = "chef" if visual == "厨师上半身" else "hand"
    return {
        **config,
        "visual_subject_type": visual,
        "elements": elements,
        "l1_subject": subject,
        "l1_action_level": config.get("l1_action_level") or 2,
        "l1_action_verb": config.get("l1_action_verb") or ("lift_plate" if subject == "chef" else "steady_plate"),
    }


def effective_prompt_config(prompt_data: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
    """
    这道菜实际会用的 promptConfig。

    规则模式（effectMode 是 "rule"，或者根本没有这个字段——所有老草稿都是这样）：现算。
    节点里存着的配置只取 mode（首尾帧时再取 speed_curve 和尾帧状态），其余一律不看，
    免得再出现「模板存的是热菜写法、这道菜其实是冷食」那种对不上。

    自定义模式：在高级设置里手调过，按存着的配置原样用，只把冷热和人物对上这道菜自己的。
    """
    raw = prompt_data.get("promptConfig")
    stored = dict(raw) if isinstance(raw, dict) else {}
    visual = _normalized_visual(input_data.get("visualSubjectType"))
    food = _normalized_food(input_data.get("foodType"))

    if str(prompt_data.get("effectMode") or "") == "custom":
        base = {**_default_config(), **stored}
        if food:
            base["food_type"] = food
        return _follow_visual_subject(_match_dish_temperature(base, food), visual)

    mode = "keyframes" if stored.get("mode") == "keyframes" else "single_image"
    base = {**_default_config(), "mode": mode, "visual_subject_type": visual}
    if food:
        base["food_type"] = food
    if mode == "keyframes":
        base["speed_curve"] = stored.get("speed_curve") or "uniform"
        if "endImageReady" in stored:
            base["endImageReady"] = stored["endImageReady"]
    return apply_preset(base, preset_for_dish(food, visual, prompt_data.get("effectRules")))
