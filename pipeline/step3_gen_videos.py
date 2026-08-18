# -*- coding: utf-8 -*-
"""
Step 3: 图片 + 提示词 → Kling API 批量图生视频
================================================

输入：01_images/ 预处理图片 + 02_prompts/ 提示词
输出：03_clips/ 每道菜的 5s 无声 9:16 视频片段（每菜 ROLL_COUNT 个版本）

可灵官方 API（v2.6）：
  - 认证: API Key + Bearer Token
  - 图生视频: POST /v1/videos/image2video
  - 任务查询: GET /v1/videos/image2video/{task_id}
  - 图片: 支持 base64 直传（无需图床！）
  - 模型: 可灵 2.6 对应 model_name=kling-v2-6
  - 时长: 精确 5s 或 10s
  - 分辨率: mode=pro → 1080p
  - 宽高比: 自动跟随输入图（预处理为 9:16 则输出 9:16）

用法：
  set KLING_API_KEY=你的key
  python pipeline/step3_gen_videos.py --config pipeline/batch_20260814.yaml
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import jwt
import requests
import yaml
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import (
    KLING_API_KEY, KLING_ACCESS_KEY, KLING_SECRET_KEY,
    KLING_BASE_URL, KLING_MODEL,
    VIDEO_RESOLUTION, VIDEO_DURATION, VIDEO_SILENT, ROLL_COUNT,
    NEGATIVE_PROMPT,
    get_batch_dir, batch_subdirs,
)

POLL_INTERVAL = 5        # 轮询间隔（秒）
POLL_TIMEOUT  = 300      # 超时 5 分钟
MAX_CONCURRENT = 3       # 最大并发

# 图片大小限制（10MB，API 要求）
MAX_IMAGE_SIZE = 10 * 1024 * 1024


def check_credentials():
    """检查 API Key。"""
    if not ((KLING_ACCESS_KEY and KLING_SECRET_KEY) or KLING_API_KEY):
        print("=" * 60)
        print("[错误] 未配置 Kling 鉴权信息")
        print()
        print("配置方式：")
        print("  1. 登录可灵开发者平台 → API 密钥")
        print("  2. 设置环境变量：KLING_API_KEY=你的key")
        print("  3. 新版接口域名建议：KLING_BASE_URL=https://api-beijing.klingai.com")
        print("=" * 60)
        sys.exit(1)


def build_auth_token():
    """生成 Kling Authorization token。优先按官方 AK/SK 生成 JWT。"""
    if KLING_ACCESS_KEY and KLING_SECRET_KEY:
        now = int(time.time())
        payload = {
            "iss": KLING_ACCESS_KEY,
            "exp": now + 1800,
            "nbf": now - 5,
        }
        headers = {
            "alg": "HS256",
            "typ": "JWT",
        }
        return jwt.encode(payload, KLING_SECRET_KEY, algorithm="HS256", headers=headers)
    return KLING_API_KEY


def auth_headers(content_type=False):
    """构造请求头。"""
    headers = {"Authorization": f"Bearer {build_auth_token()}"}
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def parse_json_response(resp, action):
    """解析 JSON，保留非 JSON 响应正文，方便定位鉴权/网关错误。"""
    try:
        return resp.json()
    except ValueError:
        text = resp.text.strip().replace("\n", " ")
        raise RuntimeError(f"{action}失败: HTTP {resp.status_code} 非JSON响应: {text[:300]}")


def session_with_retry():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


def image_to_base64(image_path: str) -> str:
    """读取图片并转换为 base64（不带 data: 前缀）。"""
    with open(image_path, "rb") as f:
        data = f.read()
    if len(data) > MAX_IMAGE_SIZE:
        raise RuntimeError(f"图片过大: {len(data)/1024/1024:.1f}MB > 10MB 限制")
    return base64.b64encode(data).decode("utf-8")


def create_task(session, image_base64, prompt, negative_prompt,
                duration=5, mode="pro", sound="off"):
    """创建图生视频任务，返回 task_id。"""
    headers = auth_headers(content_type=True)
    payload = {
        "model_name": KLING_MODEL,
        "image": image_base64,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration": duration,
        "mode": mode,
        "sound": sound,
        "watermark": {"enabled": False},
    }

    resp = session.post(
        f"{KLING_BASE_URL}/v1/videos/image2video",
        headers=headers, json=payload, timeout=120,
    )
    data = parse_json_response(resp, "创建任务")

    if resp.status_code != 200 or data.get("code") != 0:
        err = data.get("message", resp.text[:300])
        raise RuntimeError(f"创建任务失败: {err}")

    task_id = data["data"]["task_id"]
    return task_id


def query_task(session, task_id):
    """查询任务状态。"""
    headers = auth_headers()
    resp = session.get(
        f"{KLING_BASE_URL}/v1/videos/image2video/{task_id}",
        headers=headers, timeout=30,
    )
    data = parse_json_response(resp, "查询任务")
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
            msg = data.get("data", {}).get("task_status_msg", "")
            return None, {"error": msg or "任务失败"}

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

    images_manifest = dirs["images"] / "manifest.json"
    prompts_manifest = dirs["prompts"] / "manifest.json"

    if not images_manifest.exists() or not prompts_manifest.exists():
        print("[错误] 请先运行 step1 和 step2")
        sys.exit(1)

    with open(images_manifest, encoding="utf-8") as f:
        images_data = json.load(f)
    with open(prompts_manifest, encoding="utf-8") as f:
        prompts_data = json.load(f)

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
    print(f"  规格: 1080p / 5s / 无声 / 9:16")
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
            # 1. 图片转 base64（直传，无需图床）
            print(f"  [编码] 图片转 base64...", end="")
            img_b64 = image_to_base64(img_path)
            print(f" OK ({len(img_b64)/1024:.0f}KB base64)")

            # 2. 创建生成任务
            task_id = create_task(
                session, img_b64, prompt, task["negative_prompt"],
                duration=VIDEO_DURATION, mode="pro", sound="off",
            )
            print(f"  [任务] task_id: {task_id}")

            # 3. 轮询等待
            video_url, info = wait_for_video(session, task_id)

            if not video_url:
                err = info.get("error", str(info)[:300])
                print(f"  [失败] {err}")
                results.append({**task, "status": "failed", "error": err})
                continue

            # 4. 下载视频
            out_name = f"{dish}_roll{roll}_1080p_5s.mp4"
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
