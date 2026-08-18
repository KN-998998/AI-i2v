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
        "label": "\u63a8\u8fd1\u7248",
        "selected": True,
        "camera": "\u5f00\u573a\u7b2c\u4e00\u5e27\uff0c\u955c\u5934\u7acb\u5373\u4ece45\u5ea6\u4fa7\u524d\u65b9\u63a8\u8fd1\uff0c\u524d0.8\u79d2\u5b8c\u6210\u6e05\u6670\u53ef\u89c1\u768410%\u63a8\u8fd1\uff0c\u968f\u540e\u4fdd\u6301\u7a33\u5b9a\u7684\u6162\u901f\u63a8\u8fd1\uff0c\u4e0d\u8981\u9759\u6b62\u5f00\u573a",
        "stability": "\u4e3b\u5149\u65b9\u5411\u548c\u6574\u4f53\u4eae\u5ea6\u7a33\u5b9a\uff0c\u4e0d\u62c9\u7126\uff0c\u4e0d\u626b\u5149",
        "background": "\u80cc\u666f\u4fdd\u6301\u539f\u56fe\u72b6\u6001\uff0c\u53ea\u4fdd\u7559\u81ea\u7136\u6d45\u666f\u6df1",
    },
    {
        "id": "v2",
        "label": "\u5c0f\u5e45\u5f27\u7ebf\u7248",
        "selected": False,
        "camera": "\u5f00\u573a\u7b2c\u4e00\u5e27\uff0c\u955c\u5934\u7acb\u5373\u987a\u65f6\u9488\u5c0f\u5e45\u5f27\u7ebf\u79fb\u52a8\u7ea610\u5ea6\uff0c\u540c\u65f6\u8f7b\u5fae\u63a8\u8fd1\uff0c\u4e0d\u505a360\u5ea6\u73af\u7ed5",
        "stability": "\u4e3b\u5149\u65b9\u5411\u548c\u6574\u4f53\u4eae\u5ea6\u7a33\u5b9a\uff0c\u7126\u70b9\u56fa\u5b9a\u5728\u4e3b\u4f53\uff0c\u4e0d\u626b\u5149",
        "background": "\u80cc\u666f\u4fdd\u6301\u539f\u56fe\u72b6\u6001\uff0c\u4e0d\u589e\u52a0\u65b0\u5143\u7d20",
    },
    {
        "id": "v3",
        "label": "\u6a2a\u79fb\u7248",
        "selected": False,
        "camera": "\u5f00\u573a\u7b2c\u4e00\u5e27\uff0c\u955c\u5934\u7acb\u5373\u4ece\u5de6\u5411\u53f3\u5e73\u7a33\u6a2a\u79fb\u7ea610%\uff0c\u4fdd\u6301\u4e3b\u4f53\u6e05\u6670\uff0c\u4e0d\u505a\u5feb\u901f\u6447\u955c",
        "stability": "\u4e3b\u5149\u65b9\u5411\u548c\u6574\u4f53\u4eae\u5ea6\u7a33\u5b9a\uff0c\u4e0d\u62c9\u7126\uff0c\u4e0d\u626b\u5149",
        "background": "\u80cc\u666f\u4fdd\u6301\u539f\u56fe\u72b6\u6001\uff0c\u4e0d\u505a\u989d\u5916\u89c6\u5dee\u52a8\u753b",
    },
]

SYSTEM_PROMPT = """\u4f60\u662f\u9910\u996e\u56fe\u751f\u89c6\u9891\u7684\u52a8\u6001\u7f16\u5bfc\u3002\u8f93\u5165\u56fe\u7247\u5df2\u7ecf\u5b9a\u4e49\u4e3b\u4f53\u3001\u6446\u76d8\u548c\u73af\u5883\uff0c\u4f60\u53ea\u4e3a\u83dc\u54c1\u8865\u5145\u4e00\u4e2a\u53ef\u89c1\u3001\u4e0d\u5938\u5f20\u7684\u5fae\u52a8\u3002

\u89c4\u5219\uff1a
1. \u53ea\u8f93\u51fa\u83dc\u54c1\u81ea\u8eab\u7684\u4e00\u4e2a\u4e3b\u52a8\u6001\uff0c\u5fc5\u987b\u4ece\u5f00\u573a\u7b2c\u4e00\u5e27\u5c31\u53ef\u89c1\u3002\u4e0d\u5199\u955c\u5934\u3001\u5149\u7ebf\u3001\u80cc\u666f\u3001\u666f\u6df1\u6216\u65f6\u95f4\u8f74\u3002
2. \u53ea\u80fd\u52a8\u753b\u9762\u4e2d\u5df2\u53ef\u89c1\u6216\u6839\u636e\u83dc\u54c1\u7c7b\u578b\u786e\u5b9e\u5408\u7406\u7684\u7279\u5f81\u3002\u4e0d\u65b0\u589e\u9171\u6c41\u3001\u51b0\u5757\u3001\u84b8\u6c7d\u3001\u914d\u83dc\u6216\u88c5\u9970\u3002
3. \u51b7\u83dc\u3001\u523a\u8eab\u3001\u751f\u98df\u53ea\u80fd\u5199\u6e7f\u6da6\u5149\u6cfd\u3001\u81ea\u7136\u53cd\u5149\u6216\u5df2\u53ef\u89c1\u7684\u51b7\u51dd\u6c34\u73e0\u3002\u4e25\u7981\u8089\u4f53\u6536\u7f29\u3001\u8df3\u52a8\u3001\u547c\u5438\u3001\u51fa\u6c41\u3001\u84b8\u817e\u6216\u878d\u5316\u3002
4. \u70ed\u83dc\u53ea\u80fd\u5728\u7b26\u5408\u83dc\u54c1\u7c7b\u578b\u65f6\u5199\u6781\u6de1\u70ed\u6c14\u3001\u6cb9\u5149\u6216\u53ef\u89c1\u9171\u6599\u7684\u81ea\u7136\u6d41\u52a8\u3002
5. \u53e5\u5b50\u4e0d\u8d85\u8fc735\u4e2a\u6c49\u5b57\uff0c\u4e0d\u8d85\u8fc7\u4e24\u4e2a\u5206\u53e5\uff0c\u4e0d\u4f7f\u7528\u201c\u8f7b\u5fae\u6536\u7f29\u201d\u3001\u201c\u7f13\u7f13\u6e17\u51fa\u201d\u7b49\u4f1a\u9020\u6210\u751f\u7269\u53d8\u5f62\u7684\u63cf\u8ff0\u3002
6. \u4e0d\u751f\u6210\u4eba\u7269\u3001\u624b\u90e8\u3001\u6587\u5b57\u3001Logo\u3002

\u8f93\u51fa JSON\uff1a
{
  "core_action": "\u4e00\u4e2a\u7b26\u5408\u83dc\u54c1\u7684\u77ed\u53e5\u5fae\u52a8\uff0c\u4f8b\u5982\uff1a\u8868\u9762\u6e7f\u6da6\u5149\u6cfd\u968f\u955c\u5934\u4ea7\u751f\u7ec6\u5fae\u53cd\u5149",
  "subtitle": "\u83dc\u540d + \u4e00\u4e2a\u5f62\u5bb9\u8bcd",
  "caption": "15-20\u5b57\u7684\u5230\u5e97\u5438\u5f15\u6587\u6848"
}
"""


def build_motion_brief(category: str = "", highlight: str = "", variant: dict | None = None) -> str:
    variant = variant or PROMPT_VARIANTS[0]
    return "\uFF0C".join([
        variant["camera"],
        variant["stability"],
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
