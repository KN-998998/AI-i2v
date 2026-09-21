# -*- coding: utf-8 -*-
"""第十三批：第 3 步「动态效果」的规则，后端这一份必须和前端逐项一致。

批量生产只在后端跑，每道菜的效果要在这里按它自己的冷热现算；分步流程生成时也走这里。
对照表 tests/fixtures/effect_presets.json 由前端 applyPromptPreset 生成，前端测试读的是同一份。
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline import prompt_presets
from pipeline.prompt_assembler import L2Item, PromptConfig, assemble_prompt

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "effect_presets.json"


def _instruction(config: dict) -> str:
    result = assemble_prompt(PromptConfig(
        mode=config["mode"], camera_move=config["camera_move"], camera_amplitude=config["camera_amplitude"],
        shot_size=config["shot_size"], elements=list(config["elements"]), l1_subject=config["l1_subject"],
        l1_action_level=config["l1_action_level"], l1_action_verb=config["l1_action_verb"],
        l2_dynamics=[L2Item(type=item["type"], target=item["target"]) for item in config["l2_dynamics"]],
        speed_curve=config["speed_curve"], seamless_loop=config["seamless_loop"],
        food_type=config.get("food_type") or "", visual_subject_type=config["visual_subject_type"],
    ))
    assert not result.blocked, [error.message for error in result.errors]
    return result.prompt


LEGACY_HOT_TEMPLATE = {
    "mode": "single_image", "camera_move": "orbit_right", "camera_amplitude": "subtle", "shot_size": "close_up",
    "elements": ["dish_hot", "garnish", "tableware", "surface", "backdrop"], "l1_subject": "dish_hot",
    "l1_action_level": None, "l1_action_verb": None, "l2_dynamics": [{"type": "specular", "target": "菜品"}],
    "speed_curve": None, "seamless_loop": False, "visual_subject_type": "菜品主体",
}


def test_rule_mode_matches_the_shared_preset_table():
    table = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(table["cases"]) > 200
    for case in table["cases"]:
        klass = prompt_presets.effect_class(case["food_type"], case["visual_subject_type"])
        prompt_data = {"effectMode": "rule", "effectRules": {klass: case["preset"]}, "promptConfig": {"mode": case["mode"]}}
        input_data = {"foodType": case["food_type"], "visualSubjectType": case["visual_subject_type"]}
        actual = prompt_presets.effective_prompt_config(prompt_data, input_data)
        for key in table["slot_keys"]:
            assert actual.get(key) == case["expected"][key], (
                f"{case['preset']} · {case['food_type']}/{case['visual_subject_type']}/{case['mode']} 在 {key} 上和前端不一致"
            )


def test_every_effect_in_the_table_can_actually_be_generated():
    table = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in table["cases"]:
        _instruction(case["expected"])


def test_effect_classes_and_their_defaults():
    assert prompt_presets.DEFAULT_EFFECT_RULES == {"cold": "glow", "hot": "steam", "mixed": "glow", "person": "glow"}
    assert prompt_presets.effect_class("冷食", "菜品主体") == "cold"
    assert prompt_presets.effect_class("热食", "菜品主体") == "hot"
    assert prompt_presets.effect_class("混合/多温", "菜品主体") == "mixed"
    assert prompt_presets.effect_class(None, "菜品主体") == "mixed", "没标冷热的按混合处理，默认效果两边都安全"
    assert prompt_presets.effect_class("热食", "手部") == "person"
    assert prompt_presets.effect_class("冷食", "厨师上半身") == "person"


def test_a_rule_the_dish_cannot_use_falls_back_to_glow():
    assert prompt_presets.preset_for_dish("冷食", "手部", {"person": "steam"}) == "glow", "冷菜不能冒热气"
    assert prompt_presets.preset_for_dish("热食", "手部", {"person": "steam"}) == "steam"
    assert prompt_presets.preset_for_dish("冷食", "菜品主体", {"cold": "pour"}) == "glow", "没有手的图不能淋酱"
    assert prompt_presets.preset_for_dish("冷食", "菜品主体", None) == "glow"


def test_the_cold_sushi_no_longer_gets_an_oily_sheen():
    """Patrick 9/21 实测：老模板存的是热菜写法，冷的玉子寿司拿到的指令是「表面油光」。"""
    legacy = {"kind": "prompt", "promptConfig": {**LEGACY_HOT_TEMPLATE, "food_type": "冷食"}}

    config = prompt_presets.effective_prompt_config(legacy, {"foodType": "冷食", "visualSubjectType": "菜品主体"})

    assert config["l1_subject"] == "dish_cold"
    instruction = _instruction(config)
    assert "湿润切面高光" in instruction
    assert "油光" not in instruction


def test_a_steaming_template_does_not_make_cold_dishes_steam():
    """样板选了热气升腾，批量抽到冷菜：原来照样冒热气，而且没有任何提醒。"""
    template = {"kind": "prompt", "effectRules": {"hot": "steam"}, "promptConfig": {
        **LEGACY_HOT_TEMPLATE, "camera_move": "dolly_in", "l2_dynamics": [{"type": "steam", "target": "菜品"}],
    }}

    config = prompt_presets.effective_prompt_config(template, {"foodType": "冷食", "visualSubjectType": "菜品主体"})

    assert not any(item["type"] == "steam" for item in config["l2_dynamics"])
    assert "热气" not in _instruction(config)


def test_a_changed_rule_applies_to_its_whole_class_only():
    rules = {"kind": "prompt", "effectRules": {"cold": "push_in"}}

    cold = prompt_presets.effective_prompt_config(rules, {"foodType": "冷食", "visualSubjectType": "菜品主体"})
    hot = prompt_presets.effective_prompt_config(rules, {"foodType": "热食", "visualSubjectType": "菜品主体"})

    assert (cold["camera_move"], cold["camera_amplitude"], cold["shot_size"]) == ("dolly_in", "light", "medium_close")
    assert any(item["type"] == "steam" for item in hot["l2_dynamics"]), "改冷菜规则不能影响热菜"


def test_a_hand_tuned_config_is_kept_but_matches_the_dish_temperature():
    custom = {"kind": "prompt", "effectMode": "custom", "promptConfig": {
        **LEGACY_HOT_TEMPLATE, "camera_move": "locked_off", "elements": ["dish_hot", "tableware"], "l2_dynamics": [],
    }}

    config = prompt_presets.effective_prompt_config(custom, {"foodType": "冷食", "visualSubjectType": "菜品主体"})

    assert config["camera_move"] == "locked_off"
    assert config["l2_dynamics"] == []
    assert config["l1_subject"] == "dish_cold"
    assert "dish_cold" in config["elements"] and "dish_hot" not in config["elements"]


def test_a_hand_tuned_config_still_follows_the_hands_in_the_photo():
    """原来 _prompt_data_for_asset 对有手的素材做的事，自定义模式里照旧。"""
    custom = {"kind": "prompt", "effectMode": "custom", "promptConfig": dict(LEGACY_HOT_TEMPLATE)}

    config = prompt_presets.effective_prompt_config(custom, {"foodType": "热食", "visualSubjectType": "手部"})

    assert "hand" in config["elements"]
    assert config["l1_subject"] == "hand"
    assert config["l1_action_level"] == 2
    assert config["l1_action_verb"] == "steady_plate"
