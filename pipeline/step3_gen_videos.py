# -*- coding: utf-8 -*-
"""
Step 3: 图片 + 提示词 → Kling API 批量图生视频
================================================

输入：01_images/ 预处理图片 + 02_prompts/ 提示词
输出：03_clips/ 每道菜的 4-5s 无声 9:16 视频片段（每菜 ROLL_COUNT 个版本）

可灵官方 API：
  - Base URL: https://api.klingai.com
  - 认证: JWT（AccessKey + SecretKey, HS256, 30min TTL）
  - 图生视频: POST /v1/videos/image2video
  - 轮询任务: GET /v1/tasks/{task_id}

注意：Kling API 要求 image 参数为公开可访问的 URL，不支持本地路径。
      需要先上传图片到图床或云存储。当前提供两种上传方式：
      1. sm.ms 免费图床（默认，无需注册即可用，有速率限制）
      2. 自定义上传（修改 upload_image 函数）

用法：
  set KLING_ACCESS_KEY=xxxx
  set KLING_SECRET_KEY=xxxx
  python pipeline/step3_gen_videos.py --config pipeline/batch_20260814.yaml
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    KLING_API_KEY, KLING_API_SECRET, KLING_BASE_URL, KLING_MODEL,
    VIDEO_RESOLUTION, VIDEO_DURATION, VIDEO_SILENT, ROLL_COUNT,
    NEGATIVE_PROMPT,
    get_batch_dir, batch_subdirs,
)

# ── Kling API 配置 ────────────────────────────────────────────────
KLING_ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", KLING_API_KEY)
KLING_SECRET_KEY = os.environ.get("KLING_SECRET_KEY", KLING_API_SECRET)

# 根据账号区域选择：国内用 api.klingai.com，国际用 api-singapore.klingai.com
KLING_API_BASE = os.environ.get("KLING_API_BASE", "https://api.klingai.com")

POLL_INTERVAL = 10       # 轮询间隔（秒）
POLL_TIMEOUT  = 600      # 超时 10 分钟
MAX_CONCURRENT = 3       # 最大并发（可灵个人限流 3 并发）


def check_credentials():
    """检查 API 凭证。"""
    if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
        print("=" * 60)
        print("[错误] 未配置 KLING_ACCESS_KEY / KLING_SECRET_KEY")
        print()
        print("配置方式：")
        print("  1. 登录 klingai.com → 开发者中心 → 创建 API 应用")
        print("  2. 获取 AccessKey 和 SecretKey")
        print("  3. 设置环境变量：")
        print("     set KLING_ACCESS_KEY=xxxx")
        print("     set KLING_SECRET_KEY=xxxx")
        print("=" * 60)
        sys.exit(1)


def generate_jwt() -> str:
    """用 AccessKey + SecretKey 生成 JWT Token（HS256, 30min TTL）。"""
    import jwt
    headers = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": KLING_ACCESS_KEY,
        "exp": int(time.time()) + 1800,
        "nbf": int(time.time()) - 5,
    }
    return jwt.encode(payload, KLING_SECRET_KEY, algorithm="HS256", headers=headers)


def session_with_retry():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


# ── 图片上传 ──────────────────────────────────────────────────────

def upload_image_smms(image_path: str) -> str:
    """上传图片到 sm.ms 免费图床，返回公开 URL。"""
    url = "https://sm.ms/api/v2/upload"
    headers = {"Authorization": ""}  # 匿名上传
    with open(image_path, "rb") as f:
        files = {"smfile": f}
        resp = requests.post(url, headers=headers, files=files, timeout=60)
    # sm.ms 有时返回 200 + 已存在链接
    data = resp.json()
    if data.get("success"):
        return data["data"]["url"]
    elif data.get("code") == "image_repeated":
        return data["images"]
    else:
        raise RuntimeError(f"sm.ms 上传失败: {data.get('message', resp.text[:200])}")


def upload_image(image_path: str) -> str:
    """上传图片到公开可访问的 URL。默认用 sm.ms，可替换为其他方案。"""
    # 方案1: sm.ms 免费图床
    try:
        return upload_image_smms(image_path)
    except Exception as e:
        print(f"    [上传] sm.ms 失败: {e}")

    # 方案2: 如有自己的图床/OSS，在此添加
    # from your_upload_module import upload_to_oss
    # return upload_to_oss(image_path)

    raise RuntimeError("图片上传失败，请配置图床或云存储")


# ── Kling API 调用 ────────────────────────────────────────────────

def create_task(session, image_url, prompt, negative_prompt,
                duration=5, mode="standard"):
    """创建图生视频任务，返回 task_id。"""
    token = generate_jwt()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model_name": KLING_MODEL,
        "image": image_url,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration": str(duration),
        "aspect_ratio": "9:16",
        "mode": mode,
        "callback_url": "",  # 可选回调 URL
    }

    resp = session.post(
        f"{KLING_API_BASE}/v1/videos/image2video",
        headers=headers, json=payload, timeout=60,
    )
    data = resp.json()

    if resp.status_code != 200 or data.get("code") != 0:
        err = data.get("message", resp.text[:300])
        raise RuntimeError(f"创建任务失败: {err}")

    task_id = data["data"]["task_id"]
    return task_id


def query_task(session, task_id):
    """查询任务状态。"""
    token = generate_jwt()
    headers = {"Authorization": f"Bearer {token}"}
    resp = session.get(
        f"{KLING_API_BASE}/v1/tasks/{task_id}",
        headers=headers, timeout=30,
    )
    data = resp.json()
    return data


def wait_for_video(session, task_id):
    """轮询直到完成/失败。返回 (video_url, full_resp)。"""
    start = time.time()
    last_status = ""
    while time.time() - start < POLL_TIMEOUT:
        data = query_task(session, task_id)
        status = data.get("data", {}).get("task_status", "unknown")
        elapsed = int(time.time() - start)

        if status != last_status:
            last_status = status
            print(f"    [{elapsed:>4}s] 状态: {status}")

        if status == "succeed":
            videos = data.get("data", {}).get("task_result", {}).get("videos", [])
            if videos:
                return videos[0]["url"], data
            return None, data
        if status == "failed":
            return None, data

        time.sleep(POLL_INTERVAL)

    return None, {"error": f"超时（>{POLL_TIMEOUT}s）"}


def download_video(session, url, out_path):
    """下载视频到本地。"""
    resp = session.get(url, stream=True, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"下载失败 HTTP {resp.status_code}")
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(64 * 1024):
            f.write(chunk)
    return os.path.getsize(out_path)


# ── 主流程 ────────────────────────────────────────────────────────

def run(config_path: str):
    """主入口：读取图片和提示词 → 批量调用 Kling API 生成视频。"""
    check_credentials()

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    batch_date = cfg["batch"]["date"]
    batch_dir = get_batch_dir(batch_date)
    dirs = batch_subdirs(batch_dir)

    # 读取 step1 和 step2 的清单
    images_manifest = dirs["images"] / "manifest.json"
    prompts_manifest = dirs["prompts"] / "manifest.json"

    if not images_manifest.exists() or not prompts_manifest.exists():
        print("[错误] 请先运行 step1 和 step2")
        sys.exit(1)

    with open(images_manifest, encoding="utf-8") as f:
        images_data = json.load(f)
    with open(prompts_manifest, encoding="utf-8") as f:
        prompts_data = json.load(f)

    # 合并数据：菜名 → {image_path, prompt, negative_prompt}
    prompt_map = {p["dish"]: p for p in prompts_data if "video_prompt" in p}

    tasks = []
    for img_info in images_data:
        if img_info["status"] != "ok":
            continue
        dish = img_info["dish"]
        if dish not in prompt_map:
            print(f"  [跳过] {dish} 无提示词")
            continue
        p = prompt_map[dish]
        for img_path in img_info["images"]:
            for roll in range(1, ROLL_COUNT + 1):
                tasks.append({
                    "dish": dish,
                    "image_path": img_path,
                    "prompt": p["video_prompt"],
                    "negative_prompt": p.get("negative_prompt", NEGATIVE_PROMPT),
                    "roll": roll,
                })

    print(f"{'='*60}")
    print(f"Step 3: Kling API 批量图生视频")
    print(f"  菜品数: {len(prompt_map)}")
    print(f"  总任务数: {len(tasks)}（{len(prompt_map)} 菜 × {ROLL_COUNT} roll）")
    print(f"  规格: {VIDEO_RESOLUTION} / {VIDEO_DURATION}s / {'无声' if VIDEO_SILENT else '有声'} / 9:16")
    print(f"  并发: {MAX_CONCURRENT}")
    print(f"  输出: {dirs['clips']}")
    print(f"{'='*60}")

    session = session_with_retry()
    results = []

    for i, task in enumerate(tasks, 1):
        dish = task["dish"]
        roll = task["roll"]
        img_path = task["image_path"]
        prompt = task["prompt"]

        print(f"\n[{i}/{len(tasks)}] {dish} roll{roll}")
        print(f"  图片: {os.path.basename(img_path)}")
        print(f"  提示词: {prompt[:60]}...")

        try:
            # 1. 上传图片到公开 URL
            print(f"  [上传] 上传图片到图床...", end="")
            image_url = upload_image(img_path)
            print(f" OK: {image_url[:60]}...")

            # 2. 创建生成任务
            task_id = create_task(
                session, image_url, prompt, task["negative_prompt"],
                duration=VIDEO_DURATION,
            )
            print(f"  [任务] task_id: {task_id}")

            # 3. 轮询等待
            video_url, info = wait_for_video(session, task_id)

            if not video_url:
                err = (info.get("data", {}).get("task_status_msg", "")
                       or str(info)[:300])
                print(f"  [失败] {err}")
                results.append({**task, "status": "failed", "error": err})
                continue

            # 4. 下载视频
            out_name = f"{dish}_roll{roll}_{VIDEO_RESOLUTION}_{VIDEO_DURATION}s.mp4"
            out_path = str(dirs["clips"] / out_name)
            size = download_video(session, video_url, out_path)
            print(f"  [完成] {out_path} ({size/1024/1024:.1f}MB)")

            results.append({
                **task,
                "status": "ok",
                "output": out_path,
                "video_url": video_url,
                "task_id": task_id,
            })

        except Exception as e:
            print(f"  [异常] {e}")
            results.append({**task, "status": "error", "error": str(e)})

    # 汇总清单
    manifest_path = dirs["clips"] / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n{'='*60}")
    print(f"完成: {ok}/{len(tasks)} 个视频生成成功")
    print(f"清单: {manifest_path}")
    print(f"{'='*60}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Step 3: Kling API 批量图生视频")
    ap.add_argument("--config", required=True, help="batch.yaml 路径")
    args = ap.parse_args()
    run(args.config)
