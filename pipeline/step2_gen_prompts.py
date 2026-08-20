# -*- coding: utf-8 -*-
"""
Step 2: 菜名 → 发布文案（DeepSeek）+ 图生视频提示词（槽位化确定性组装）
============================================================================

输入：batch.yaml 中的菜品清单（菜名、类型、亮点）
输出：02_prompts/ 目录下每道菜的提示词 .txt + 文案 .json

分工（v2.0，2026-08-14）：
- 视频提示词（video_prompt / negative_prompt）→ pipeline.prompt_assembler
  确定性槽位化组装，不调 LLM 写动态（可灵是扩散模型，LLM 自由描述易翻车）
- 发布文案（subtitle / caption）→ DeepSeek 生成（运营需要）

用法：
  set DEEPSEEK_API_KEY=sk-xxxx
  python pipeline/step2_gen_prompts.py --config pipeline/batch_20260814.yaml
"""
import argparse
import json
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    get_batch_dir,
    batch_subdirs,
)

# ── 三变体框架（前端依赖 v1/v2/v3，映射到装配器的镜头运动）──────────────
PROMPT_VARIANTS = [
    {
        "id": "v1",
        "label": "推近版",
        "selected": True,
        "camera_move": "dolly_in",
    },
    {
        "id": "v2",
        "label": "小弧线版",
        "selected": False,
        "camera_move": "orbit_right",
    },
    {
        "id": "v3",
        "label": "横移版",
        "selected": False,
        "camera_move": "truck_right",
    },
]

SYSTEM_PROMPT = """你是餐饮品牌的发布文案编辑。根据输入的菜品信息，输出发布所需的简短文案。

规则：
1. 只输出字幕与发布文案，不描述视频画面、镜头、运镜。
2. subtitle = 菜名 + 一个形容词，10 字以内。
3. caption = 15-25 字的到店吸引文案，带 emoji 或语气词更佳。
4. 不生成人物、手部、文字 Logo 相关内容。

输出 JSON：
{
  "subtitle": "菜名 + 一个形容词",
  "caption": "15-25 字的到店吸引文案"
}
"""


# ── 菜品类型 → 槽位默认映射 ─────────────────────────────────────────
# 热/炸/煲 → dish_hot + 蒸汽；冷/刺身/生 → dish_cold + 高光
HOT_KEYWORDS = ("热", "烤", "炸", "煲", "烧", "煎", "炒", "铁板", "天妇罗", "丼")
COLD_KEYWORDS = ("刺身", "生", "冷", "冰", "寿司", "前菜", "沙拉", "酒")


def build_slot_config(dish_name: str, category: str, highlight: str, variant: dict | None = None):
    """根据菜品类型 + 变体构建 PromptConfig（装配器输入）。"""
    from pipeline.prompt_assembler import L2Item, PromptConfig

    variant = variant or PROMPT_VARIANTS[0]
    cat = category or ""

    # L0 画面元素：按冷热选主体 + 常见器皿/桌面/背景
    is_hot = any(k in cat for k in HOT_KEYWORDS)
    is_cold = any(k in cat for k in COLD_KEYWORDS) and not is_hot
    if is_hot:
        l1_subject = "dish_hot"
        elements = ["dish_hot", "tableware", "surface", "backdrop"]
    elif is_cold:
        l1_subject = "dish_cold"
        elements = ["dish_cold", "garnish", "tableware", "surface"]
    else:
        l1_subject = "dish_cold"
        elements = ["dish_cold", "tableware", "surface", "backdrop"]

    # L2 次级动态：热菜默认蒸汽，冷菜默认高光滑移
    l2 = []
    if is_hot:
        l2.append(L2Item(type="steam", target="菜品"))
    else:
        l2.append(L2Item(type="specular", target="菜品"))

    # 变体 → 镜头运动（v1 推近 / v2 环绕 / v3 横移）
    return PromptConfig(
        mode="single_image",
        camera_move=variant.get("camera_move", "dolly_in"),
        camera_amplitude="subtle",
        elements=elements,
        l1_subject=l1_subject,
        l2_dynamics=l2,
    )


def slot_to_dict(cfg) -> dict:
    """PromptConfig → dict（供前端回填槽位表单）。"""
    return {
        "mode": cfg.mode,
        "camera_move": cfg.camera_move,
        "camera_amplitude": cfg.camera_amplitude,
        "elements": list(cfg.elements),
        "l1_subject": cfg.l1_subject,
        "l1_action_level": cfg.l1_action_level,
        "l1_action_verb": cfg.l1_action_verb,
        "l2_dynamics": [{"type": i.type, "target": i.target} for i in cfg.l2_dynamics],
        "speed_curve": cfg.speed_curve,
        "seamless_loop": cfg.seamless_loop,
    }


def build_motion_brief(category: str = "", highlight: str = "", variant: dict | None = None) -> str:
    """兼容旧接口：返回变体镜头描述（已由装配器取代，保留供旧调用方使用）。"""
    variant = variant or PROMPT_VARIANTS[0]
    return variant.get("label", "推近版")


def call_deepseek(dish_name: str, category: str, highlight: str, variant: dict | None = None) -> dict:
    """调用 DeepSeek 生成发布文案（subtitle + caption）。"""
    variant = variant or PROMPT_VARIANTS[0]
    user_msg = (
        f"菜名：{dish_name}\n"
        f"类型：{category}\n"
        f"亮点：{highlight}\n"
        "请输出该菜的发布文案（subtitle + caption）。"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.45,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    result = json.loads(content)
    result["variant_id"] = variant["id"]
    result["variant_label"] = variant["label"]
    result["selected"] = variant.get("selected", False)
    return result


def build_full_prompt(
    ai_result: dict,
    dish_name: str = "",
    category: str = "",
    highlight: str = "",
    variant: dict | None = None,
) -> str:
    """兼容旧接口：由装配器确定性生成提示词。

    新调用方请直接使用 build_slot_config + assemble_prompt。
    """
    from pipeline.prompt_assembler import assemble_prompt

    cfg = build_slot_config(dish_name, category, highlight, variant)
    return assemble_prompt(cfg).prompt


def run(config_path: str):
    if not DEEPSEEK_API_KEY:
        print("[错误] 未配置 DEEPSEEK_API_KEY（仅文案需要，视频提示词由装配器生成）")
        # 文案缺失时用菜名兜底，不阻断视频提示词
        deepseek_ok = False
    else:
        deepseek_ok = True

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)
    dishes = cfg["dishes"]
    total = len(dishes) * len(PROMPT_VARIANTS)

    print(f"{'='*60}")
    print(f"Step 2: 提示词装配（确定性） + 发布文案（DeepSeek）")
    print(f"  菜品数量: {len(dishes)}  每道菜变体数: {len(PROMPT_VARIANTS)}")
    print(f"  输出目录: {dirs['prompts']}")
    print(f"{'='*60}")

    all_results = []
    done = 0
    for i, dish in enumerate(dishes, 1):
        name = dish["name"]
        category = dish.get("category", "")
        highlight = dish.get("highlight", "")

        print(f"\n[{i}/{len(dishes)}] {name}...", end="")

        try:
            for variant in PROMPT_VARIANTS:
                # 视频提示词：装配器确定性生成（不调 LLM 写动态）
                from pipeline.prompt_assembler import assemble_prompt

                slot_cfg = build_slot_config(name, category, highlight, variant)
                assembled = assemble_prompt(slot_cfg)

                full_prompt = assembled.prompt
                negative_prompt = assembled.negative_prompt

                prompt_path = dirs["prompts"] / f"{name}_{variant['id']}_prompt.txt"
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(full_prompt)

                # 发布文案：DeepSeek（可选，失败用菜名兜底）
                subtitle, caption = name, ""
                if deepseek_ok:
                    try:
                        ai_result = call_deepseek(name, category, highlight, variant)
                        subtitle = ai_result.get("subtitle", name)
                        caption = ai_result.get("caption", "")
                    except Exception as e:
                        print(f"\n  [文案失败] {e}")

                result = {
                    "dish": name,
                    "category": category,
                    "highlight": highlight,
                    "variant_id": variant["id"],
                    "variant_label": variant["label"],
                    "selected": variant.get("selected", False),
                    "video_prompt": full_prompt,
                    "negative_prompt": negative_prompt,
                    "slots": slot_to_dict(slot_cfg),
                    "warnings": [w.code for w in assembled.warnings],
                    "subtitle": subtitle,
                    "caption": caption,
                }
                json_path = dirs["prompts"] / f"{name}_{variant['id']}_meta.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                all_results.append(result)
                done += 1
                print(f"\n  {variant['label']} OK ({done}/{total})")
                print(f"    提示词: {full_prompt[:72]}...")
        except Exception as e:
            print(f" 失败: {e}")
            all_results.append({"dish": name, "status": "error", "error": str(e)})

    manifest_path = dirs["prompts"] / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in all_results if "video_prompt" in r)
    print(f"\n{'='*60}")
    print(f"完成: {ok}/{len(all_results)} 条提示词生成成功")
    print(f"清单: {manifest_path}")
    print(f"{'='*60}")
    return all_results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 2: 提示词装配 + 文案生成")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
