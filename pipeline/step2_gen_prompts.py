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
import os
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    NEGATIVE_PROMPT, PROMPT_PREFIX, PROMPT_SUFFIX,
    get_batch_dir, batch_subdirs,
)

# ── 系统提示词（指导 DeepSeek 如何生成） ──────────────────────────
SYSTEM_PROMPT = """你是一个餐饮短视频AI提示词专家。你的任务是为「图生视频」模型编写提示词。

规则：
1. 提示词描述的是「静态食物图片如何变成动态视频」，不是菜谱。
2. 动态效果必须在开头1秒内发生（因为成片每段只用2-3秒）。
3. 只描述画面动态，不要描述镜头外的东西。
4. 语言简洁，一个句子描述一个动态效果，不超过50字。
5. 不要写"镜头慢慢推进后..."这种延迟描述，写"热气持续升起"这种即时描述。

输出格式（JSON）：
{
  "video_prompt": "动态描述，如：酱汁正在从上方淋下，食物表面油润光泽",
  "subtitle": "字幕文案，格式：菜名 + 一个形容词，如：海胆天妇罗 酥脆爆浆",
  "caption": "发布文案，一句话吸引到店，15-20字"
}
"""


def call_deepseek(dish_name: str, category: str, highlight: str) -> dict:
    """调用 DeepSeek 生成提示词和文案。"""
    user_msg = f"菜名：{dish_name}\n类型：{category}\n亮点：{highlight}"

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
        "temperature": 0.7,
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
    return json.loads(content)


def build_full_prompt(ai_result: dict) -> str:
    """拼接完整提示词 = 固定前缀 + AI动态描述 + 固定后缀 + 负向约束。"""
    dynamic = ai_result["video_prompt"]
    return f"{PROMPT_PREFIX}{dynamic}，{PROMPT_SUFFIX}"


def run(config_path: str):
    """主入口。"""
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

    print(f"{'='*60}")
    print(f"Step 2: DeepSeek 生成提示词 + 文案")
    print(f"  菜品数量: {len(dishes)}")
    print(f"  输出目录: {dirs['prompts']}")
    print(f"{'='*60}")

    all_results = []
    for i, dish in enumerate(dishes, 1):
        name = dish["name"]
        category = dish.get("category", "")
        highlight = dish.get("highlight", "")

        print(f"\n[{i}/{len(dishes)}] {name}...", end="")

        try:
            ai_result = call_deepseek(name, category, highlight)
            full_prompt = build_full_prompt(ai_result)

            # 保存提示词 .txt
            prompt_path = dirs["prompts"] / f"{name}_prompt.txt"
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(full_prompt)

            # 保存完整结果 .json（含字幕、发布文案）
            result = {
                "dish": name,
                "category": category,
                "highlight": highlight,
                "video_prompt": full_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "subtitle": ai_result["subtitle"],
                "caption": ai_result["caption"],
            }
            json_path = dirs["prompts"] / f"{name}_meta.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            all_results.append(result)
            print(f" OK")
            print(f"  提示词: {full_prompt[:60]}...")
            print(f"  字幕: {ai_result['subtitle']}")

        except Exception as e:
            print(f" 失败: {e}")
            all_results.append({
                "dish": name,
                "status": "error",
                "error": str(e),
            })

    # 汇总清单
    manifest_path = dirs["prompts"] / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in all_results if "video_prompt" in r)
    print(f"\n{'='*60}")
    print(f"完成: {ok}/{len(dishes)} 道菜提示词生成成功")
    print(f"清单: {manifest_path}")
    print(f"{'='*60}")
    return all_results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 2: DeepSeek 生成提示词")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
