# -*- coding: utf-8 -*-
"""
Step 2: 菜名 → DeepSeek 生成图生视频提示词 + 字幕文案
======================================================

输入：batch.yaml 中的菜品清单（菜名、类型、亮点）
输出：02_prompts/ 目录下每道菜的提示词 .txt + 文案 .json

DeepSeek API 是 OpenAI 兼容接口，用 requests 直接调用。
固定约束词（负向约束、前缀后缀）从 config.py 读取，不交给 AI 生成。

用法：
  set DEEPSEEK_API_KEY=sk-xxxx
  python pipeline/step2_gen_prompts.py --config pipeline/batch_20260814.yaml
"""
import argparse
import json
import random
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    NEGATIVE_PROMPT,
    PROMPT_PREFIX,
    PROMPT_SUFFIX,
    get_batch_dir,
    batch_subdirs,
)

PROMPT_VARIANTS = [
    {
        "id": "v1",
        "label": "推近版",
        "selected": True,
        "camera": "镜头从45度侧前方缓慢推近，主体逐渐放大",
        "lighting": "左前方暖色主光打亮表面油光，右后方轮廓光勾边",
        "focus": "焦点在食物边缘与表面反光之间轻微拉焦",
        "background": "背景保持暗调餐厅氛围，灯点虚化成柔和散景",
    },
    {
        "id": "v2",
        "label": "环绕版",
        "selected": False,
        "camera": "镜头沿顺时针方向轻微环绕并推近，展示食物侧面层次",
        "lighting": "顶部柔光压住高光，侧后方暖光提亮边缘层次",
        "focus": "焦点沿主要食材、酱汁表面、边缘纹理轻微切换",
        "background": "背景轻微虚化，桌面和餐厅灯光形成深浅层次",
    },
    {
        "id": "v3",
        "label": "横移版",
        "selected": False,
        "camera": "镜头从左侧轻微横移进入主体，背景灯点产生横向视差",
        "lighting": "右侧补光轻扫过食物表面，形成流动高光",
        "focus": "前景食物细节清晰，背景灯光逐渐虚化",
        "background": "背景暗化留白，让主体更突出，画面干净",
    },
]

CATEGORY_HINTS = {
    "炸": ["突出酥脆边缘、油光闪烁和轻微热气"],
    "烤": ["突出焦香边缘、烟气上升和表面微微滋滋作响"],
    "烧": ["突出热气、汁水反光和边缘焦色层次"],
    "煎": ["突出底部焦脆、油脂光泽和热气流动"],
    "刺身": ["突出冰感、湿润光泽和清爽冷调反光"],
    "海鲜": ["突出晶亮水润、壳体高光和轻微蒸汽"],
    "甜": ["突出奶油柔光、酱层细腻和轻盈空气感"],
    "蛋糕": ["突出奶油纹理、糖霜细节和柔和浅景深"],
    "汤": ["突出热气持续上升、汤面轻微波动"],
    "面": ["突出汤汁挂面、蒸汽上升和面条轻微晃动"],
}

SYSTEM_PROMPT = """你是一个餐饮短视频AI提示词专家。你的任务是为「图生视频」模型补充菜品自身动态。

规则：
1. 只写菜品自身的即时动态，不写镜头、机位、灯光、背景、景深。
2. 动态效果必须在开头1秒内发生（因为成片每段只用2-3秒）。
3. 描述具体可见的微运动，例如热气、酱汁、油光、水汽、焦香边缘、奶油纹理。
4. 语言简洁，一个句子描述一个动态效果，不超过45字。
5. 不要写"镜头慢慢推进后..."这种延迟描述，写"热气持续升起"这种即时描述。
6. 不要生成文字、Logo、人物、手部，也不要凭空增加新食材。

输出格式（JSON）：
{
  "core_action": "菜品自身动态，如：酱汁缓缓流动，表面油光轻闪，热气持续升起",
  "subtitle": "字幕文案，格式：菜名 + 一个形容词，如：海胆天妇罗 酥脆爆浆",
  "caption": "发布文案，一句话吸引到店，15-20字"
}
"""


def build_motion_brief(category: str = "", highlight: str = "", variant: dict | None = None) -> str:
    variant = variant or PROMPT_VARIANTS[0]
    text = f"{category} {highlight}"
    detail = ""
    for key, hints in CATEGORY_HINTS.items():
        if key in text:
            detail = f"，{random.choice(hints)}"
            break

    return "，".join([
        variant["camera"],
        variant["lighting"],
        f"{variant['focus']}{detail}",
        variant["background"],
    ])


def call_deepseek(dish_name: str, category: str, highlight: str, variant: dict | None = None) -> dict:
    variant = variant or PROMPT_VARIANTS[0]
    motion_brief = build_motion_brief(category, highlight, variant)
    user_msg = (
        f"菜名：{dish_name}\n"
        f"类型：{category}\n"
        f"亮点：{highlight}\n"
        f"风格标签：{variant['label']}\n"
        f"代码已固定的镜头骨架：{motion_brief}\n"
        "请只补充菜品自身的动态，不要重复或改写镜头、灯光、背景。"
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
        "temperature": 0.8,
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
    result["motion_brief"] = motion_brief
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
    variant = variant or PROMPT_VARIANTS[0]
    motion_brief = ai_result.get("motion_brief") or build_motion_brief(category, highlight, variant)
    core_action = ai_result.get("core_action") or ai_result.get("video_prompt") or ""
    parts = [PROMPT_PREFIX, motion_brief, core_action, PROMPT_SUFFIX]
    return "，".join(part.strip("，") for part in parts if part and part.strip())


def run(config_path: str):
    if not DEEPSEEK_API_KEY:
        print("[错误] 未配置 DEEPSEEK_API_KEY")
        print("  set DEEPSEEK_API_KEY=sk-xxxx")
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)
    dishes = cfg["dishes"]
    total = len(dishes) * len(PROMPT_VARIANTS)

    print(f"{'='*60}")
    print(f"Step 2: DeepSeek 生成提示词 + 文案")
    print(f"  菜品数量: {len(dishes)}")
    print(f"  每道菜变体数: {len(PROMPT_VARIANTS)}")
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
                ai_result = call_deepseek(name, category, highlight, variant)
                full_prompt = build_full_prompt(ai_result, name, category, highlight, variant)

                prompt_path = dirs["prompts"] / f"{name}_{variant['id']}_prompt.txt"
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(full_prompt)

                result = {
                    "dish": name,
                    "category": category,
                    "highlight": highlight,
                    "variant_id": variant["id"],
                    "variant_label": variant["label"],
                    "selected": variant.get("selected", False),
                    "video_prompt": full_prompt,
                    "motion_brief": ai_result.get("motion_brief", ""),
                    "core_action": ai_result.get("core_action", ai_result.get("video_prompt", "")),
                    "negative_prompt": NEGATIVE_PROMPT,
                    "subtitle": ai_result["subtitle"],
                    "caption": ai_result["caption"],
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
    ap = argparse.ArgumentParser(description="Step 2: DeepSeek 生成提示词")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
