# -*- coding: utf-8 -*-
"""Prompt assembler acceptance cases from the Kling prompt specification."""

from pipeline.prompt_assembler import L2Item, PromptConfig, assemble_prompt


def test_single_image_cold_dish_close_up():
    result = assemble_prompt(PromptConfig(
        mode="single_image", camera_move="dolly_in", camera_amplitude="light",
        elements=["dish_cold", "garnish", "tableware", "surface"],
        l1_subject="dish_cold", l2_dynamics=[],
    ))

    assert result.prompt == """【镜头】缓慢推进（dolly in），极慢匀速，单镜头一镜到底，画面轻微变化（约15%）。
【主运动】菜品与摆盘保持原位不动，仅湿润切面高光随镜头角度缓慢滑移。
【锁定】配菜与装饰、餐具器皿、桌面保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。"""
    assert result.cfg_scale == 0.70
    assert [warning.code for warning in result.warnings] == []
    assert "次级动态" not in result.prompt


def test_keyframes_chef_pours_sauce():
    result = assemble_prompt(PromptConfig(
        mode="keyframes", camera_move="locked_off", camera_amplitude="subtle",
        elements=["dish_hot", "tableware", "surface", "hand"],
        l1_subject="hand", l1_action_level=2, l1_action_verb="pour_sauce",
        l2_dynamics=[
            L2Item(type="steam", target="菜品"),
            L2Item(type="liquid_pour", target="酱汁壶"),
        ],
        speed_curve="uniform",
    ))

    assert result.prompt == """【过渡】从首帧画面平滑连续过渡到尾帧画面，单镜头一镜到底，无切换、无叠化。
【主运动】手连贯自然地从首帧姿态过渡到尾帧姿态，完成淋下酱汁的动作片段，中途不停顿、不回退，全程匀速。
【次级动态】极轻缓热气自菜品持续缓慢上升，不成团、不遮挡主体；细流从酱汁壶匀速落下，落点固定，流量恒定，全程连续不中断。
【锁定】餐具器皿、桌面在整个过渡过程中保持位置与形态不变。
【光线】光源固定，明暗随视角连续渐变，不跳变。
【节奏】过渡末端稳定停在尾帧状态。"""
    assert result.negative_prompt == "变形，融化，收缩，蠕动，主体位移，新增元素，元素消失，多余的手，文字，logo，水印，抖动，晃动，快速运镜，镜头切换，分镜，画面跳变，曝光跳变，闪烁，重新打光，色彩漂移，涂抹感，二次构图，画质劣化，闪切，跳帧，转场特效，叠化，画面突变，中途重构，动作回退，面部入镜，人物面部，全身入镜，浓烟，白雾遮挡，云雾成团，烟雾旋转，飞溅，液体倒流，液面暴涨，外溢，容器变形，液体凭空出现"
    assert result.cfg_scale == 0.45
    locked = result.prompt.split("【锁定】")[1].split("。")[0]
    assert "菜品" not in locked
    assert "手部" not in locked


def test_single_image_crane_down_warns_about_low_motion():
    result = assemble_prompt(PromptConfig(
        mode="single_image", camera_move="crane_down", camera_amplitude="subtle",
        elements=["dish_cold", "garnish", "tableware"],
        l1_subject="none", l2_dynamics=[],
    ))

    assert result.prompt == """【镜头】缓慢俯视下降（crane down），极慢匀速，单镜头一镜到底，画面极轻微变化（约8%）。
【主运动】画面内所有元素保持完全静止，仅视角发生变化。
【锁定】菜品、配菜与装饰、餐具器皿保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。"""
    assert result.cfg_scale == 0.70
    assert [warning.code for warning in result.warnings] == ["W5"]


def test_invalid_prompt_is_blocked_without_prompt_output():
    result = assemble_prompt(PromptConfig(
        mode="single_image", camera_move="dolly_in", camera_amplitude="medium",
        elements=["dish_hot", "tableware"], l1_subject="dish_hot",
        l2_dynamics=[
            L2Item(type="flame", target="菜品"),
            L2Item(type="ice_mist", target="餐具器皿"),
            L2Item(type="steam", target="菜品"),
        ],
    ))

    assert result.blocked is True
    assert sorted(error.code for error in result.errors) == ["V2", "V3", "V4"]
    assert result.prompt == ""
    assert result.cfg_scale == 0.0


def test_complete_single_image_action_warns_about_motion_risk():
    result = assemble_prompt(PromptConfig(
        mode="single_image", camera_move="locked_off", camera_amplitude="subtle",
        elements=["dish_cold", "tableware", "hand"],
        l1_subject="hand", l1_action_level=3, l1_action_verb="pick_food",
        l2_dynamics=[],
    ))

    assert result.prompt == """【镜头】固定机位不动（locked-off），画面构图保持不变。
【主运动】手在三秒内缓慢完成一次夹起食材并自然停住。
【锁定】菜品、餐具器皿保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。"""
    assert result.cfg_scale == 0.40
    assert [warning.code for warning in result.warnings] == ["W2"]
