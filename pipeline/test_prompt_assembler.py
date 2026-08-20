# -*- coding: utf-8 -*-
"""prompt_assembler 验收测试 — 对照 kling-prompt规划_cc版.md §7 五个用例"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.prompt_assembler import PromptConfig, L2Item, assemble_prompt

PASS = 0
FAIL = 0


def check(name, actual, expected, label=""):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f"  ✅ {name} {label}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {label}")
        print(f"    --- 期望 ---\n{expected}")
        print(f"    --- 实际 ---\n{actual}")


# ── 用例 1：冷食刺身特写（单图）─────────────────────────────────
print("用例1: 冷食刺身特写（单图）")
c1 = PromptConfig(
    mode="single_image", camera_move="dolly_in", camera_amplitude="light",
    elements=["dish_cold", "garnish", "tableware", "surface"],
    l1_subject="dish_cold", l2_dynamics=[],
)
r1 = assemble_prompt(c1)
exp1 = """【镜头】缓慢推进（dolly in），极慢匀速，单镜头一镜到底，画面轻微变化（约15%）。
【主运动】菜品与摆盘保持原位不动，仅湿润切面高光随镜头角度缓慢滑移。
【锁定】配菜与装饰、餐具器皿、桌面保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。"""
check("用例1 prompt", r1.prompt, exp1)
check("用例1 cfg_scale", r1.cfg_scale, 0.70, "=0.70")
check("用例1 warnings", [w.code for w in r1.warnings], [], "=[]")
check("用例1 次级动态段不出现", "次级动态" in r1.prompt, False, "（空槽位整段删除）")

# ── 用例 2：厨师淋酱（首尾帧）────────────────────────────────────
print("用例2: 厨师淋酱（首尾帧）")
c2 = PromptConfig(
    mode="keyframes", camera_move="locked_off", camera_amplitude="subtle",
    elements=["dish_hot", "tableware", "surface", "hand"],
    l1_subject="hand", l1_action_level=2, l1_action_verb="pour_sauce",
    l2_dynamics=[L2Item(type="steam", target="菜品"), L2Item(type="liquid_pour", target="酱汁壶")],
    speed_curve="uniform",
)
r2 = assemble_prompt(c2)
exp2_prompt = """【过渡】从首帧画面平滑连续过渡到尾帧画面，单镜头一镜到底，无切换、无叠化。
【主运动】手连贯自然地从首帧姿态过渡到尾帧姿态，完成淋下酱汁的动作片段，中途不停顿、不回退，全程匀速。
【次级动态】极轻缓热气自菜品持续缓慢上升，不成团、不遮挡主体；细流从酱汁壶匀速落下，落点固定，流量恒定，全程连续不中断。
【锁定】餐具器皿、桌面在整个过渡过程中保持位置与形态不变。
【光线】光源固定，明暗随视角连续渐变，不跳变。
【节奏】过渡末端稳定停在尾帧状态。"""
exp2_neg = "变形，融化，收缩，蠕动，主体位移，新增元素，元素消失，多余的手，文字，logo，水印，抖动，晃动，快速运镜，镜头切换，分镜，画面跳变，曝光跳变，闪烁，重新打光，色彩漂移，涂抹感，二次构图，画质劣化，闪切，跳帧，转场特效，叠化，画面突变，中途重构，动作回退，面部入镜，人物面部，全身入镜，浓烟，白雾遮挡，云雾成团，烟雾旋转，飞溅，液体倒流，液面暴涨，外溢，容器变形，液体凭空出现"
check("用例2 prompt", r2.prompt, exp2_prompt)
check("用例2 negative", r2.negative_prompt, exp2_neg)
check("用例2 cfg_scale", r2.cfg_scale, 0.45, "=0.45")
check("用例2 dish_hot被steam命中→不在锁定层", "菜品" not in r2.prompt.split("【锁定】")[1].split("。")[0], True)
check("用例2 hand(L1)→不在锁定层", "手部" not in r2.prompt.split("【锁定】")[1].split("。")[0], True)

# ── 用例 3：俯拍纯运镜（单图）────────────────────────────────────
print("用例3: 俯拍纯运镜（单图）")
c3 = PromptConfig(
    mode="single_image", camera_move="crane_down", camera_amplitude="subtle",
    elements=["dish_cold", "garnish", "tableware"],
    l1_subject="none", l2_dynamics=[],
)
r3 = assemble_prompt(c3)
exp3 = """【镜头】缓慢俯视下降（crane down），极慢匀速，单镜头一镜到底，画面极轻微变化（约8%）。
【主运动】画面内所有元素保持完全静止，仅视角发生变化。
【锁定】菜品、配菜与装饰、餐具器皿保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。"""
check("用例3 prompt", r3.prompt, exp3)
check("用例3 cfg_scale", r3.cfg_scale, 0.70, "=0.70")
check("用例3 warnings=[W5]", [w.code for w in r3.warnings], ["W5"])

# ── 用例 4：阻断校验 ─────────────────────────────────────────────
print("用例4: 阻断校验")
c4 = PromptConfig(
    mode="single_image", camera_move="dolly_in", camera_amplitude="medium",
    elements=["dish_hot", "tableware"],
    l1_subject="dish_hot",
    l2_dynamics=[L2Item(type="flame", target="菜品"), L2Item(type="ice_mist", target="餐具器皿"), L2Item(type="steam", target="菜品")],
)
r4 = assemble_prompt(c4)
check("用例4 blocked", r4.blocked, True)
codes4 = sorted([e.code for e in r4.errors])
check("用例4 errors 含 V2/V3/V4", codes4, ["V2", "V3", "V4"], f"got {codes4}")
check("用例4 prompt 为空", r4.prompt, "")
check("用例4 cfg_scale=0", r4.cfg_scale, 0.0)

# ── 用例 5：单图完整级动作（触发引导）────────────────────────────
print("用例5: 单图完整级动作")
c5 = PromptConfig(
    mode="single_image", camera_move="locked_off", camera_amplitude="subtle",
    elements=["dish_cold", "tableware", "hand"],
    l1_subject="hand", l1_action_level=3, l1_action_verb="pick_food",
    l2_dynamics=[],
)
r5 = assemble_prompt(c5)
exp5 = """【镜头】固定机位不动（locked-off），画面构图保持不变。
【主运动】手在三秒内缓慢完成一次夹起食材并自然停住。
【锁定】菜品、餐具器皿保持绝对静止，位置、数量、形状、颜色不变。
【光线】光源固定，明暗关系不变，无重新打光。
【节奏】动作与运镜同步开始，全程连续无停顿，末端自然减速停住。"""
check("用例5 prompt", r5.prompt, exp5)
check("用例5 cfg_scale", r5.cfg_scale, 0.40, "=0.40")
check("用例5 warnings 含 W2", [w.code for w in r5.warnings], ["W2"])

print(f"\n{'='*50}")
print(f"通过 {PASS} / {PASS+FAIL}")
sys.exit(1 if FAIL else 0)
