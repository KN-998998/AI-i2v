# -*- coding: utf-8 -*-
"""
Web 应用后端：Flask API 包装 pipeline
=====================================

启动：
  set DEEPSEEK_API_KEY=sk-xxxx
  set KLING_API_KEY=xxxx
  python web/app.py

然后浏览器打开 http://localhost:5000
"""
import json
import os
import shutil
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, send_file, send_from_directory

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import (
    OUTPUT_ROOT, IMAGE_LIBRARY, EXTRA_IMAGE_LIBS,
    get_batch_dir, batch_subdirs,
    TEMPLATE_5_DISH, TEMPLATE_3_DISH,
    DEEPSEEK_API_KEY, KLING_API_KEY,
)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

# ── 批次状态管理 ──────────────────────────────────────────────────
# 内存中的批次状态（后续可换数据库）
BATCH_STATES = {}


def get_batch_state(batch_id):
    """获取批次状态，不存在则初始化。"""
    if batch_id not in BATCH_STATES:
        BATCH_STATES[batch_id] = {
            "id": batch_id,
            "name": "",
            "date": "",
            "dishes": [],           # [{name, category, highlight, image_path}]
            "status": "created",    # created → configured → generating → reviewing → composing → done
            "current_step": 0,
            "step_progress": {},
            "selected_clips": {},   # {dish: filename}
            "captions": {},         # {video_id: caption_text}
            "videos": [],           # 最终视频列表
            "error": None,
            "created_at": datetime.now().isoformat(),
        }
    return BATCH_STATES[batch_id]


def load_manifest(dirs, step_name):
    """读取某步骤的 manifest.json。"""
    manifest_map = {
        "images": dirs["images"] / "manifest.json",
        "prompts": dirs["prompts"] / "manifest.json",
        "clips": dirs["clips"] / "manifest.json",
        "composed": dirs["composed"] / "manifest.json",
        "final": dirs["final"] / "manifest.json",
    }
    path = manifest_map.get(step_name)
    if path and path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


# ── 页面路由 ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


@app.route("/static/<path:filename>")
def serve_static(filename):
    return send_from_directory("static", filename)


# ── API: 批次管理 ─────────────────────────────────────────────────

@app.route("/api/batches", methods=["GET"])
def list_batches():
    """列出所有批次。"""
    batches = []
    if OUTPUT_ROOT.exists():
        for d in sorted(OUTPUT_ROOT.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("batch_"):
                date_str = d.name.replace("batch_", "")
                state_file = d / "state.json"
                state = {}
                if state_file.exists():
                    with open(state_file, encoding="utf-8") as f:
                        state = json.load(f)
                batches.append({
                    "id": d.name,
                    "date": date_str,
                    "name": state.get("name", ""),
                    "status": state.get("status", "unknown"),
                    "dish_count": len(state.get("dishes", [])),
                })
    return jsonify(batches)


@app.route("/api/batch", methods=["POST"])
def create_batch():
    """创建新批次。"""
    data = request.json
    batch_name = data.get("name", "")
    batch_date = data.get("date", datetime.now().strftime("%Y%m%d"))
    batch_id = f"batch_{batch_date}"

    # 同一天可以有多个批次，加后缀
    if (OUTPUT_ROOT / batch_id).exists():
        suffix = 2
        while (OUTPUT_ROOT / f"{batch_id}_{suffix}").exists():
            suffix += 1
        batch_id = f"{batch_id}_{suffix}"

    state = get_batch_state(batch_id)
    state["name"] = batch_name
    state["date"] = batch_date

    # 创建目录
    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)

    # 保存状态
    save_state(batch_id)

    return jsonify({"id": batch_id, "state": state})


@app.route("/api/batch/<batch_id>", methods=["GET"])
def get_batch(batch_id):
    """获取批次详情。"""
    state = load_state(batch_id)
    if not state:
        return jsonify({"error": "批次不存在"}), 404
    return jsonify(state)


@app.route("/api/batch/<batch_id>/dishes", methods=["POST"])
def update_dishes(batch_id):
    """更新菜品配置（含顺序）。"""
    state = get_batch_state(batch_id)
    dishes = request.json.get("dishes", [])
    state["dishes"] = dishes
    state["status"] = "configured"
    save_state(batch_id)
    return jsonify(state)


# ── API: 图片上传 ─────────────────────────────────────────────────

@app.route("/api/batch/<batch_id>/upload", methods=["POST"])
def upload_images(batch_id):
    """上传菜品图片。"""
    state = get_batch_state(batch_id)
    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)

    dish_name = request.form.get("dish", "")
    files = request.files.getlist("files")

    uploaded = []
    for f in files:
        ext = Path(f.filename).suffix
        filename = f"{dish_name}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = dirs["images"] / filename
        f.save(str(filepath))
        uploaded.append(str(filepath))

    return jsonify({"dish": dish_name, "images": uploaded})


# ── API: 素材库浏览 ───────────────────────────────────────────────

@app.route("/api/library/dishes", methods=["GET"])
def list_library_dishes():
    """列出素材库中可用的菜品文件夹。"""
    dishes = []
    for lib in [IMAGE_LIBRARY] + EXTRA_IMAGE_LIBS:
        if not lib.exists():
            continue
        for sub in lib.iterdir():
            if sub.is_dir():
                images = list(sub.glob("*.jpg")) + list(sub.glob("*.jpeg")) + \
                         list(sub.glob("*.png")) + list(sub.glob("*.JPG"))
                if images:
                    dishes.append({
                        "name": sub.name,
                        "library": str(lib),
                        "image_count": len(images),
                        "sample": str(images[0]),
                    })
    return jsonify(dishes)


@app.route("/api/library/preview", methods=["GET"])
def library_preview():
    """预览素材库图片。"""
    path = request.args.get("path", "")
    if Path(path).exists():
        return send_file(path)
    return "", 404


# ── API: 流水线执行 ───────────────────────────────────────────────

@app.route("/api/batch/<batch_id>/run/step1", methods=["POST"])
def run_step1(batch_id):
    """执行 Step 1: 图片预处理（如果用上传的图则跳过素材库匹配）。"""
    state = get_batch_state(batch_id)
    state["status"] = "generating"
    state["current_step"] = 1
    save_state(batch_id)

    def worker():
        try:
            from pipeline.step1_match_images import preprocess_one
            from pipeline.config import PREP_TARGET_SHORT

            batch_dir = OUTPUT_ROOT / batch_id
            dirs = batch_subdirs(batch_dir)

            results = []
            for dish in state["dishes"]:
                name = dish["name"]
                images = dish.get("images", [])

                if not images:
                    # 从素材库找图
                    from pipeline.step1_match_images import find_dish_images
                    all_dirs = [IMAGE_LIBRARY] + EXTRA_IMAGE_LIBS
                    images = find_dish_images(name, all_dirs, limit=1)

                if not images:
                    results.append({"dish": name, "status": "not_found", "images": []})
                    continue

                processed = []
                for img_path in images:
                    base = Path(img_path).stem
                    out_name = f"{name}_{base}_9x16.jpg"
                    out_path = str(dirs["images"] / out_name)
                    preprocess_one(img_path, out_path)
                    processed.append(out_path)

                results.append({
                    "dish": name,
                    "status": "ok",
                    "images": processed,
                    "category": dish.get("category", ""),
                    "highlight": dish.get("highlight", ""),
                })

            manifest_path = dirs["images"] / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            state["step_progress"]["step1"] = {"status": "done", "result": results}
            save_state(batch_id)
        except Exception as e:
            state["step_progress"]["step1"] = {"status": "error", "error": str(e)}
            save_state(batch_id)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/api/batch/<batch_id>/run/step2", methods=["POST"])
def run_step2(batch_id):
    """执行 Step 2: DeepSeek 生成提示词。"""
    state = get_batch_state(batch_id)
    state["current_step"] = 2
    save_state(batch_id)

    def worker():
        try:
            from pipeline.step2_gen_prompts import call_deepseek, build_full_prompt
            from pipeline.config import NEGATIVE_PROMPT

            batch_dir = OUTPUT_ROOT / batch_id
            dirs = batch_subdirs(batch_dir)

            all_results = []
            for dish in state["dishes"]:
                name = dish["name"]
                category = dish.get("category", "")
                highlight = dish.get("highlight", "")

                ai_result = call_deepseek(name, category, highlight)
                full_prompt = build_full_prompt(ai_result)

                prompt_path = dirs["prompts"] / f"{name}_prompt.txt"
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(full_prompt)

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

            manifest_path = dirs["prompts"] / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)

            state["step_progress"]["step2"] = {"status": "done", "result": all_results}
            save_state(batch_id)
        except Exception as e:
            state["step_progress"]["step2"] = {"status": "error", "error": str(e)}
            save_state(batch_id)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"status": "started"})


# ── API: 提示词编辑（供同事修改后保存） ──────────────────────────

@app.route("/api/batch/<batch_id>/prompts", methods=["GET"])
def get_prompts(batch_id):
    """获取当前批次的所有提示词（供前端编辑）。"""
    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    prompts_data = load_manifest(dirs, "prompts") or []

    # 读取已编辑的提示词（如果存在）
    edited_path = dirs["prompts"] / "edited_prompts.json"
    edited = {}
    if edited_path.exists():
        with open(edited_path, encoding="utf-8") as f:
            edited = json.load(f)

    result = []
    for p in prompts_data:
        dish = p["dish"]
        item = {
            "dish": dish,
            "video_prompt": edited.get(dish, {}).get("video_prompt", p["video_prompt"]),
            "negative_prompt": edited.get(dish, {}).get("negative_prompt", p.get("negative_prompt", "")),
            "subtitle": p.get("subtitle", dish),
            "caption": p.get("caption", ""),
        }
        result.append(item)

    return jsonify(result)


@app.route("/api/batch/<batch_id>/prompts", methods=["POST"])
def save_prompts(batch_id):
    """保存同事编辑后的提示词。"""
    prompts = request.json.get("prompts", [])
    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)

    edited = {}
    for p in prompts:
        dish = p["dish"]
        edited[dish] = {
            "video_prompt": p["video_prompt"],
            "negative_prompt": p.get("negative_prompt", ""),
        }

    edited_path = dirs["prompts"] / "edited_prompts.json"
    with open(edited_path, "w", encoding="utf-8") as f:
        json.dump(edited, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "saved"})


# ── API: 执行 Step 3（Kling 生成视频） ──────────────────────────

@app.route("/api/batch/<batch_id>/run/step3", methods=["POST"])
def run_step3(batch_id):
    """执行 Step 3: Kling API 批量图生视频。使用编辑后的提示词。"""
    state = get_batch_state(batch_id)
    state["current_step"] = 3
    save_state(batch_id)

    def worker():
        try:
            from pipeline.step3_gen_videos import (
                image_to_base64, create_task, wait_for_video, download_video,
                session_with_retry,
            )
            from pipeline.config import VIDEO_DURATION, ROLL_COUNT, NEGATIVE_PROMPT

            batch_dir = OUTPUT_ROOT / batch_id
            dirs = batch_subdirs(batch_dir)

            # 读取 step1 和 step2 结果
            images_data = load_manifest(dirs, "images") or []
            prompts_data = load_manifest(dirs, "prompts") or []

            # 读取同事编辑后的提示词（优先使用）
            edited_path = dirs["prompts"] / "edited_prompts.json"
            edited_prompts = {}
            if edited_path.exists():
                with open(edited_path, encoding="utf-8") as f:
                    edited_prompts = json.load(f)

            prompt_map = {}
            for p in prompts_data:
                dish = p["dish"]
                if dish in edited_prompts:
                    prompt_map[dish] = edited_prompts[dish]
                else:
                    prompt_map[dish] = {
                        "video_prompt": p["video_prompt"],
                        "negative_prompt": p.get("negative_prompt", NEGATIVE_PROMPT),
                    }

            tasks = []
            for img_info in images_data:
                if img_info["status"] != "ok":
                    continue
                dish = img_info["dish"]
                if dish not in prompt_map:
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

            state["step_progress"]["step3"] = {
                "status": "running",
                "total": len(tasks),
                "done": 0,
                "results": [],
            }
            save_state(batch_id)

            session = session_with_retry()
            results = []

            for i, task in enumerate(tasks, 1):
                try:
                    img_b64 = image_to_base64(task["image_path"])
                    task_id = create_task(
                        session, img_b64, task["prompt"],
                        task["negative_prompt"],
                        duration=VIDEO_DURATION, mode="pro", sound="off",
                    )
                    video_url, info = wait_for_video(session, task_id)

                    if video_url:
                        out_name = f"{task['dish']}_roll{task['roll']}_1080p_5s.mp4"
                        out_path = str(dirs["clips"] / out_name)
                        download_video(session, video_url, out_path)
                        results.append({**task, "status": "ok", "output": out_path})
                    else:
                        results.append({**task, "status": "failed", "error": str(info)[:200]})
                except Exception as e:
                    results.append({**task, "status": "error", "error": str(e)})

                state["step_progress"]["step3"]["done"] = i
                state["step_progress"]["step3"]["results"] = results
                save_state(batch_id)

            manifest_path = dirs["clips"] / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            state["step_progress"]["step3"]["status"] = "done"
            state["status"] = "reviewing"
            save_state(batch_id)
        except Exception as e:
            state["step_progress"]["step3"] = {"status": "error", "error": str(e)}
            save_state(batch_id)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"status": "started"})


# ── API: 审核挑选 ─────────────────────────────────────────────────

@app.route("/api/batch/<batch_id>/clips", methods=["GET"])
def get_clips(batch_id):
    """获取所有视频片段供审核。"""
    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    clips = load_manifest(dirs, "clips") or []

    # 按菜品分组
    grouped = {}
    for clip in clips:
        if clip["status"] != "ok":
            continue
        dish = clip["dish"]
        if dish not in grouped:
            grouped[dish] = []
        grouped[dish].append({
            "roll": clip["roll"],
            "filename": os.path.basename(clip["output"]),
            "path": clip["output"],
        })

    return jsonify(grouped)


@app.route("/api/batch/<batch_id>/clips/<filename>", methods=["GET"])
def serve_clip(batch_id, filename):
    """提供视频片段文件。"""
    batch_dir = OUTPUT_ROOT / batch_id
    clips_dir = batch_dir / "03_clips"
    return send_from_directory(str(clips_dir), filename)


@app.route("/api/batch/<batch_id>/select", methods=["POST"])
def select_clips(batch_id):
    """提交选用的片段。"""
    state = get_batch_state(batch_id)
    state["selected_clips"] = request.json.get("selected", {})
    state["status"] = "selected"
    save_state(batch_id)
    return jsonify(state)


# ── API: 文案编辑 ─────────────────────────────────────────────────

@app.route("/api/batch/<batch_id>/captions", methods=["GET"])
def get_captions(batch_id):
    """获取 AI 生成的文案。"""
    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    prompts = load_manifest(dirs, "prompts") or []

    captions = {}
    for p in prompts:
        dish = p["dish"]
        captions[dish] = {
            "subtitle": p.get("subtitle", dish),
            "caption": p.get("caption", ""),
        }
    return jsonify(captions)


@app.route("/api/batch/<batch_id>/captions", methods=["POST"])
def update_captions(batch_id):
    """更新文案。"""
    state = get_batch_state(batch_id)
    state["captions"] = request.json.get("captions", {})
    save_state(batch_id)
    return jsonify(state)


# ── API: 合成成片 ─────────────────────────────────────────────────

@app.route("/api/batch/<batch_id>/run/compose", methods=["POST"])
def run_compose(batch_id):
    """执行 Step 5 + Step 6: 合成 + 配音。"""
    state = get_batch_state(batch_id)
    state["status"] = "composing"
    state["current_step"] = 5
    save_state(batch_id)

    video_config = request.json.get("video_config", {})

    def worker():
        try:
            batch_dir = OUTPUT_ROOT / batch_id
            dirs = batch_subdirs(batch_dir)

            # Step 5: 合成
            from pipeline.step5_compose import trim_clip, concat_clips
            from pipeline.config import FINAL_RESOLUTION, FINAL_FPS

            selected = state.get("selected_clips", {})
            captions = state.get("captions", {})

            # 读取字幕
            subtitles = {}
            prompts = load_manifest(dirs, "prompts") or []
            for p in prompts:
                dish = p["dish"]
                if dish in captions:
                    subtitles[dish] = captions[dish].get("subtitle", dish)
                else:
                    subtitles[dish] = p.get("subtitle", dish)

            # 菜品顺序
            dish_order = video_config.get("dish_order", list(selected.keys()))
            template_key = video_config.get("template", "5_dish")
            template = TEMPLATE_5_DISH if template_key == "5_dish" else TEMPLATE_3_DISH
            segments = template["segments"]
            seg_durations = [s["duration"] for s in segments if s["role"] != "outro"]

            trimmed_paths = []
            vid_subtitles = []
            for i, dish in enumerate(dish_order):
                if dish not in selected:
                    continue
                clip_file = selected[dish]
                clip_path = str(dirs["clips"] / clip_file)
                if not os.path.exists(clip_path):
                    continue

                duration = seg_durations[i] if i < len(seg_durations) else 2.0
                trimmed_name = f"composed_{dish}_trim.mp4"
                trimmed_path = str(dirs["composed"] / trimmed_name)
                trim_clip(clip_path, trimmed_path, start=0.5, duration=duration)
                trimmed_paths.append(trimmed_path)
                vid_subtitles.append({"text": subtitles.get(dish, dish), "duration": duration})

            if not trimmed_paths:
                raise RuntimeError("无可用片段")

            out_path = str(dirs["composed"] / "final_composed.mp4")
            brand_info = video_config.get("brand", {"name": "示例品牌", "cta": "评论区领优惠券"})
            concat_clips(trimmed_paths, out_path, vid_subtitles, brand_info)

            for p in trimmed_paths:
                if os.path.exists(p):
                    os.remove(p)

            # Step 6: 配音 + BGM
            from pipeline.step6_voice_bgm import generate_caption, generate_tts, mix_audio, merge_audio_video, get_video_duration
            from pipeline.config import BGM_FILE

            duration = get_video_duration(out_path)

            # 生成配音文案
            dish_names = [subtitles.get(d, d) for d in dish_order]
            caption_text = ""
            if captions:
                # 用同事编辑的文案
                for d in dish_order:
                    if d in captions and captions[d].get("caption"):
                        caption_text = captions[d]["caption"]
                        break
            if not caption_text:
                caption_text = generate_caption(dish_names, brand_info, "final")

            voice_path = str(dirs["final"] / "voice.mp3")
            voice_result = generate_tts(caption_text, voice_path)

            audio_path = str(dirs["final"] / "audio.mp3")
            if voice_result and os.path.exists(str(BGM_FILE)):
                mix_audio(voice_path, str(BGM_FILE), audio_path,
                         bgm_volume=0.3, video_duration=duration)
            elif voice_result:
                shutil.copy(voice_path, audio_path)
            else:
                # 仅 BGM
                import subprocess
                cmd = ["ffmpeg", "-y", "-i", str(BGM_FILE), "-t", str(duration),
                       "-af", f"volume=0.3,afade=t=in:st=0:d=0.5,afade=t=out:st={duration-1}:d=1",
                       "-c:a", "aac", "-b:a", "192k", audio_path]
                subprocess.run(cmd, capture_output=True, timeout=60)

            final_path = str(dirs["final"] / "final_video.mp4")
            merge_audio_video(out_path, audio_path, final_path)

            # 清理临时文件
            for tmp in [voice_path, audio_path]:
                if os.path.exists(tmp):
                    os.remove(tmp)

            state["videos"] = [{
                "path": final_path,
                "filename": "final_video.mp4",
                "caption": caption_text,
                "duration": duration,
            }]
            state["status"] = "done"
            state["step_progress"]["compose"] = {"status": "done"}
            save_state(batch_id)

        except Exception as e:
            state["step_progress"]["compose"] = {"status": "error", "error": str(e)}
            state["status"] = "error"
            state["error"] = str(e)
            save_state(batch_id)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return jsonify({"status": "started"})


@app.route("/api/batch/<batch_id>/status", methods=["GET"])
def get_status(batch_id):
    """获取批次当前状态。"""
    state = load_state(batch_id)
    if not state:
        return jsonify({"error": "批次不存在"}), 404
    return jsonify(state)


@app.route("/api/batch/<batch_id>/final", methods=["GET"])
def download_final(batch_id):
    """下载最终视频。"""
    batch_dir = OUTPUT_ROOT / batch_id
    final_dir = batch_dir / "06_final"
    final_path = final_dir / "final_video.mp4"
    if final_path.exists():
        return send_file(str(final_path), as_attachment=True,
                        download_name=f"{batch_id}_final.mp4")
    return jsonify({"error": "视频未生成"}), 404


# ── 状态持久化 ────────────────────────────────────────────────────

def save_state(batch_id):
    """保存批次状态到文件。"""
    state = BATCH_STATES.get(batch_id)
    if not state:
        return
    state_file = OUTPUT_ROOT / batch_id / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        # 序列化时处理不可序列化的对象
        safe = {}
        for k, v in state.items():
            try:
                json.dumps(v)
                safe[k] = v
            except TypeError:
                safe[k] = str(v)
        json.dump(safe, f, ensure_ascii=False, indent=2, default=str)


def load_state(batch_id):
    """从文件加载批次状态。"""
    state_file = OUTPUT_ROOT / batch_id / "state.json"
    if state_file.exists():
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
            BATCH_STATES[batch_id] = state
            return state
    return get_batch_state(batch_id)


# ── API: 配置检查 ─────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def get_config():
    """返回当前配置状态（不暴露密钥）。"""
    return jsonify({
        "deepseek": bool(DEEPSEEK_API_KEY),
        "kling": bool(KLING_API_KEY),
        "image_library": str(IMAGE_LIBRARY),
        "image_library_exists": IMAGE_LIBRARY.exists(),
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  引流视频生产平台")
    print("  http://localhost:8080")
    print("=" * 50)
    app.run(host="127.0.0.1", port=8080, debug=True)
