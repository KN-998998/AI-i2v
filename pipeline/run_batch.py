# -*- coding: utf-8 -*-
"""
批量生产入口脚本
================

按顺序执行 Step 1 → 2 → 3 → 4 → 5 → 6。
每个 step 可单独运行，也可通过此脚本串联。

用法：
  # 全流程（step4 需人工审核后手动继续）
  python pipeline/run_batch.py --config pipeline/batch_20260814.yaml

  # 只跑到 step3（生成视频片段后暂停，等待人工审核）
  python pipeline/run_batch.py --config pipeline/batch_20260814.yaml --stop 3

  # 从 step5 继续（人工审核 CSV 后）
  python pipeline/run_batch.py --config pipeline/batch_20260814.yaml --start 5

  # 单步执行
  python pipeline/run_batch.py --config pipeline/batch_20260814.yaml --only 1
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


STEPS = {
    1: ("Step 1: 匹配素材图片 + 预处理",     "pipeline.step1_match_images", "run"),
    2: ("Step 2: DeepSeek 生成提示词",        "pipeline.step2_gen_prompts",  "run"),
    3: ("Step 3: Kling API 批量图生视频",      "pipeline.step3_gen_videos",   "run"),
    4: ("Step 4: 生成人工审核清单",            "pipeline.step4_manual_review","run"),
    5: ("Step 5: ffmpeg 合成无声成片",         "pipeline.step5_compose",      "run"),
    6: ("Step 6: AI 配音 + BGM",              "pipeline.step6_voice_bgm",    "run"),
}


def run_step(step_num, config_path):
    """执行单个 step。"""
    desc, module_name, func_name = STEPS[step_num]
    print(f"\n{'#'*60}")
    print(f"# {desc}")
    print(f"{'#'*60}\n")

    import importlib
    module = importlib.import_module(module_name)
    func = getattr(module, func_name)
    return func(config_path)


def main():
    ap = argparse.ArgumentParser(description="批量生产入口脚本")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    ap.add_argument("--start", type=int, default=1, choices=range(1, 7),
                    help="从第几步开始（默认1）")
    ap.add_argument("--stop", type=int, default=6, choices=range(1, 7),
                    help="跑到第几步停止（默认6）")
    ap.add_argument("--only", type=int, default=None, choices=range(1, 7),
                    help="只执行单步")
    args = ap.parse_args()

    if args.only:
        run_step(args.only, args.config)
        return

    for step_num in range(args.start, args.stop + 1):
        try:
            run_step(step_num, args.config)
        except Exception as e:
            print(f"\n[错误] Step {step_num} 执行失败: {e}")
            if step_num == 4:
                print("\nStep 4 是人工审核环节：")
                print("  1. 打开 04_selected/review.html 查看视频片段")
                print("  2. 在 04_selected/checklist.csv 中标记 selected=y")
                print("  3. 重新运行: python pipeline/run_batch.py --config xxx --start 5")
            sys.exit(1)

        # Step 4 后暂停（需要人工审核）
        if step_num == 4:
            print("\n" + "=" * 60)
            print("Step 4 完成！请进行人工审核：")
            print("  1. 打开 04_selected/review.html 查看视频片段")
            print("  2. 在 04_selected/checklist.csv 中标记 selected=y")
            print("  3. 审核完成后继续运行:")
            print(f"     python pipeline/run_batch.py --config {args.config} --start 5")
            print("=" * 60)
            if args.stop == 6:
                print("\n（人工审核环节，脚本暂停）")
                sys.exit(0)

    print(f"\n全流程完成！最终视频在 06_final/ 目录下。")


if __name__ == "__main__":
    main()
