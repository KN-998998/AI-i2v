# -*- coding: utf-8 -*-
"""
阿里百炼 wan2.6-i2v-flash 图生视频 API 调用
=============================================

模型：wan2.6-i2v-flash（性价比最高：1080P无声 ¥0.25/秒）
图片限制：宽高 360-2000px，≤10MB（所以务必先用 prep_images.py 预处理！）
输出限制：2-15秒整数秒，480P/720P/1080P，9:16 竖版优先

前置：
  1. 注册阿里云百炼 → https://bailian.console.aliyun.com/
  2. 开通 wan2.6-i2v-flash 模型，充值余额
  3. 获取 API Key（华北2北京区），设置环境变量：
       set DASHSCOPE_API_KEY=sk-xxxx
     或直接填入下方 API_KEY 变量
  4. 先跑 prep_images.py 把素材压缩到 720×1280 / 1080×1920

用法：
  # 单图生成 5秒 1080P 无声
  python scripts/wan26_flash_api.py --image "input/xxx_9x16.jpg" \
                                     --prompt "镜头缓缓推进，鳗鱼的酱汁在光线下流动，热气升腾" \
                                     --duration 5 --resolution 1080P

  # 批量：对 input_images/ 下所有 jpg 生成
  python scripts/wan26_flash_api.py --dir "pipeline/input_images" \
                                     --prompt-file "prompts/图生视频提示词模板.md"
  先运行 prep_images.py 把素材缩到 API 可用尺寸！
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# ── 配置 ─────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
# 老接口地址（无 WorkspaceId 也能用，最通用）
BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
CREATE_URL = BASE_URL + "/services/aigc/video-generation/video-synthesis"
QUERY_URL = BASE_URL + "/tasks/{task_id}"

MODEL = "wan2.6-i2v-flash"
# 模型定价（参考）
PRICING = {
    ("720P", False):  0.15,   # 元/秒，无声
    ("1080P", False): 0.25,
    ("720P", True):   0.30,   # 有声
    ("1080P", True):  0.50,
}

# 图片输入硬限制
IMG_MAX_BYTES = 10 * 1024 * 1024   # 10 MB
IMG_MIN_SIDE  = 360
IMG_MAX_SIDE  = 2000

POLL_INTERVAL = 8    # 轮询间隔（秒）。wan2.6-flash 通常 20-60s 出片
POLL_TIMEOUT  = 600  # 超时 10 分钟


def check_api_key():
    if not API_KEY:
        print("=" * 60)
        print("[错误] 未配置 DASHSCOPE_API_KEY")
        print()
        print("配置方式：")
        print("  set DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx")
        print("  或直接编辑 scripts/wan26_flash_api.py 顶部 API_KEY 变量")
        print()
        print("获取 Key：https://bailian.console.aliyun.com/")
        print("  → 右上角「API Key」管理 → 创建华北2北京区的 Key")
        print("=" * 60)
        sys.exit(1)


def session_with_retry():
    s = requests.Session()
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


def validate_image(path):
    """检查图片是否符合 API 输入限制。返回 (ok, reason)"""
    if not os.path.exists(path):
        return False, f"文件不存在: {path}"
    size = os.path.getsize(path)
    if size > IMG_MAX_BYTES:
        return False, f"文件过大: {size/1024/1024:.1f}MB（限制 10MB）"
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
            if w < IMG_MIN_SIDE or h < IMG_MIN_SIDE:
                return False, f"尺寸过小: {w}x{h}（需≥{IMG_MIN_SIDE}）"
            if w > IMG_MAX_SIDE or h > IMG_MAX_SIDE:
                return False, f"尺寸过大: {w}x{h}（需≤{IMG_MAX_SIDE}，请先跑 prep_images.py）"
    except Exception as e:
        return False, f"无法读取图片: {e}"
    return True, "OK"


def image_to_base64_datauri(path):
    """读取图片 → data:image/jpeg;base64,xxxx"""
    from PIL import Image
    # 先转成 jpeg（确保格式），再 base64
    with Image.open(path) as im:
        if im.mode != 'RGB':
            im = im.convert('RGB')
        import io
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=92)
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f"data:image/jpeg;base64,{b64}"


def create_task(session, image_path, prompt, duration=5,
                resolution="1080P", silent=True,
                prompt_extend=True, shot_type="single",
                negative_prompt="模糊、变形、不自然、文字乱码、多余物体、画面抖动"):
    """创建图生视频异步任务，返回 task_id"""
    ok, reason = validate_image(image_path)
    if not ok:
        raise RuntimeError(f"图片校验失败: {reason}")

    img_data = image_to_base64_datauri(image_path)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
        "X-DashScope-Async": "enable",   # 必须！否则报错"不支持同步调用"
    }

    # parameters：参考官方文档
    parameters = {
        "resolution": resolution,
        "duration": duration,
        "prompt_extend": prompt_extend,
        "watermark": False,
    }
    if silent:
        parameters["audio"] = False  # 生成无声视频（降价50%）

    payload = {
        "model": MODEL,
        "input": {
            "img_url": img_data,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        },
        "parameters": parameters,
    }
    # shot_type 仅 wan2.6 有效
    payload["parameters"]["shot_type"] = shot_type

    r = session.post(CREATE_URL, headers=headers, json=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f"创建任务失败 HTTP {r.status_code}: {r.text[:500]}")

    if r.status_code != 200:
        raise RuntimeError(f"创建任务失败 HTTP {r.status_code}: "
                           f"{data.get('code', '')} {data.get('message', '') or r.text[:300]}")

    task_id = data.get("output", {}).get("task_id") or data.get("task_id")
    if not task_id:
        raise RuntimeError(f"响应无 task_id: {json.dumps(data, ensure_ascii=False)[:500]}")
    return task_id, data


def query_task(session, task_id):
    """查询任务。返回 (status, output)。"""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    url = QUERY_URL.format(task_id=task_id)
    r = session.get(url, headers=headers, timeout=30)
    try:
        data = r.json()
    except Exception:
        return "unknown", {"error": f"HTTP {r.status_code}: {r.text[:300]}"}

    status = (data.get("output", {}).get("task_status")
              or data.get("task_status") or "unknown")
    return status, data


def wait_for_video(session, task_id):
    """轮询直到完成/失败。返回 (video_url, full_resp)"""
    start = time.time()
    last_status = ""
    while time.time() - start < POLL_TIMEOUT:
        status, data = query_task(session, task_id)
        elapsed = int(time.time() - start)
        if status != last_status:
            last_status = status
            print(f"    [{elapsed:>4}s] 状态: {status}")

        if status in ("SUCCEEDED", "succeeded", "completed"):
            vid = (data.get("output", {}).get("video_url")
                   or data.get("video_url"))
            return vid, data
        if status in ("FAILED", "failed", "error"):
            return None, data
        if status in ("UNKNOWN", "unknown") and data.get("error"):
            return None, data

        time.sleep(POLL_INTERVAL)
    return None, {"error": f"超时（>{POLL_TIMEOUT}s）"}


def download_video(session, url, out_path):
    """下载视频到本地（OSS 签名直链，1小时有效）"""
    r = session.get(url, stream=True, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"下载失败 HTTP {r.status_code}")
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(64*1024):
            f.write(chunk)
    return os.path.getsize(out_path)


def estimate_cost(duration, resolution, silent):
    unit = PRICING.get((resolution, not silent), PRICING[("1080P", True)])
    return duration * unit


def generate_one(image_path, prompt, out_dir="output/clips",
                 duration=5, resolution="1080P", silent=True):
    """生成单条视频。返回 (out_path, cost) 或 (None, 0)"""
    session = session_with_retry()
    est = estimate_cost(duration, resolution, silent)
    print(f"\n🎬 {Path(image_path).name}")
    print(f"   时长:{duration}s  分辨率:{resolution}  {'无声' if silent else '有声'}  预估成本:¥{est:.2f}")

    try:
        task_id, _ = create_task(session, image_path, prompt, duration, resolution, silent)
        print(f"   task_id: {task_id}")
        video_url, info = wait_for_video(session, task_id)
        if not video_url:
            err = (info.get("output", {}).get("message")
                   or info.get("message")
                   or info.get("error")
                   or str(info)[:300])
            print(f"   ❌ 失败: {err}")
            return None, 0
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        return None, 0

    os.makedirs(out_dir, exist_ok=True)
    base = Path(image_path).stem
    out_path = os.path.join(out_dir, f"{base}_{resolution}_{duration}s.mp4")
    size = download_video(session, video_url, out_path)
    actual_cost = est
    print(f"   ✅ 完成: {out_path}  ({size/1024/1024:.1f}MB)  成本 ¥{actual_cost:.2f}")
    return out_path, actual_cost


def main():
    check_api_key()
    ap = argparse.ArgumentParser(description="wan2.6-i2v-flash 图生视频")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--image", help="单张图片路径（必须先用 prep_images.py 预处理过）")
    g.add_argument("--dir", help="文件夹：批量处理其中所有 jpg/jpeg/png")
    ap.add_argument("--prompt", default=None, help="提示词（单图必填，批量会读同名 txt）")
    ap.add_argument("--prompt-file", default=None, help="从 txt 文件读默认提示词（批量用）")
    ap.add_argument("--out", default="output/clips", help="输出目录")
    ap.add_argument("--duration", type=int, default=5, choices=range(2, 16),
                    help="生成时长 2-15秒")
    ap.add_argument("--resolution", default="1080P", choices=["480P", "720P", "1080P"])
    ap.add_argument("--audio", action="store_true", help="生成有声视频（默认无声，更便宜）")
    args = ap.parse_args()

    silent = not args.audio

    # 取默认提示词
    default_prompt = ""
    if args.prompt_file and os.path.exists(args.prompt_file):
        default_prompt = open(args.prompt_file, encoding='utf-8').read().strip()
        print(f"[提示词模板] 已从 {args.prompt_file} 载入，{len(default_prompt)} 字符")

    if args.image:
        if not args.prompt and not default_prompt:
            print("[错误] 单图模式必须用 --prompt 或 --prompt-file 提供提示词")
            sys.exit(1)
        generate_one(args.image, args.prompt or default_prompt,
                     args.out, args.duration, args.resolution, silent)
    else:
        import glob
        exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG"]
        files = []
        for e in exts:
            files.extend(glob.glob(os.path.join(args.dir, e)))
        files.sort()
        if not files:
            print(f"[错误] {args.dir} 内无图片")
            sys.exit(1)
        print(f"\n批量处理 {len(files)} 张图")
        total_cost = 0
        ok = 0
        for i, f in enumerate(files, 1):
            # 找同名 .txt 的提示词文件
            p_txt = Path(f).with_suffix('.txt')
            prompt = None
            if p_txt.exists():
                prompt = open(p_txt, encoding='utf-8').read().strip()
            if not prompt:
                # 从文件名猜菜名 + 默认模板
                name = Path(f).stem
                prompt = (f"美食特写镜头，{name}，镜头缓慢推进，"
                          "热气和蒸汽自然升腾，食材纹理清晰，"
                          "油亮光泽诱人，餐厅高级质感，电影级布光")
            print(f"\n[{i}/{len(files)}] ", end="")
            out_path, cost = generate_one(f, prompt or default_prompt,
                                          args.out, args.duration, args.resolution, silent)
            if out_path:
                ok += 1
                total_cost += cost
        print(f"\n{'='*60}")
        print(f"批量完成: {ok}/{len(files)} 成功，总成本约 ¥{total_cost:.2f}")
        print(f"输出目录: {args.out}")
        print("="*60)


if __name__ == "__main__":
    main()
