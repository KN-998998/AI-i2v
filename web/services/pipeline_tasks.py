# -*- coding: utf-8 -*-
"""Background pipeline task orchestration for the web app."""
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from pipeline.config import IMAGE_LIBRARY, EXTRA_IMAGE_LIBS, OUTPUT_ROOT, batch_subdirs
from web.core.logging import get_logger
from web.services.planning import build_video_plan, get_video_template
from web.services.state import get_batch_state, load_manifest, save_state, summarize_clip_results

logger = get_logger(__name__)


def start_thread(name: str, target) -> None:
    thread = threading.Thread(name=name, target=target, daemon=True)
    thread.start()


def run_step1(batch_id: str) -> dict[str, Any]:
    state = get_batch_state(batch_id)
    state["status"] = "generating"
    state["current_step"] = 1
    save_state(batch_id, state)

    def worker() -> None:
        logger.info("Step1 started batch=%s", batch_id)
        try:
            from pipeline.step1_match_images import find_dish_images, preprocess_one

            batch_dir = OUTPUT_ROOT / batch_id
            dirs = batch_subdirs(batch_dir)
            results = []
            for dish in state.get("dishes", []):
                name = dish["name"]
                images = dish.get("images", [])
                if not images:
                    images = find_dish_images(name, [IMAGE_LIBRARY] + EXTRA_IMAGE_LIBS, limit=0)
                if not images:
                    results.append({"dish": name, "status": "not_found", "images": []})
                    continue

                processed = []
                for img_path in images:
                    base = Path(img_path).stem
                    out_path = str(dirs["images"] / f"{name}_{base}_9x16.jpg")
                    preprocess_one(img_path, out_path)
                    processed.append(out_path)
                results.append({
                    "dish": name,
                    "status": "ok",
                    "images": processed,
                    "category": dish.get("category", ""),
                    "highlight": dish.get("highlight", ""),
                })

            with open(dirs["images"] / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            state["step_progress"]["step1"] = {"status": "done", "result": results}
            logger.info("Step1 done batch=%s count=%s", batch_id, len(results))
        except Exception as exc:
            logger.exception("Step1 failed batch=%s", batch_id)
            state["step_progress"]["step1"] = {"status": "error", "error": str(exc)}
        save_state(batch_id, state)

    start_thread(f"step1-{batch_id}", worker)
    return {"status": "started"}


def run_step2(batch_id: str, force: bool = False) -> dict[str, Any]:
    from pipeline.step2_gen_prompts import PROMPT_VARIANTS

    state = get_batch_state(batch_id)
    dish_count = len(state.get("dishes", []))
    total_variants = dish_count * len(PROMPT_VARIANTS)
    state["status"] = "generating"
    state["current_step"] = 2
    state["error"] = None
    state["step_progress"]["step2"] = {
        "status": "running",
        "total": total_variants,
        "done": 0,
        "results": [],
    }
    save_state(batch_id, state)

    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    if not force:
        existing = load_manifest(dirs, "prompts") or []
        expected_keys = {
            f"{dish['name']}|{variant['id']}"
            for dish in state.get("dishes", [])
            for variant in PROMPT_VARIANTS
        }
        existing_keys = {
            f"{p.get('dish')}|{p.get('variant_id')}"
            for p in existing
            if p.get("dish") and p.get("variant_id") and p.get("video_prompt")
        }
        if expected_keys and expected_keys.issubset(existing_keys):
            state["step_progress"]["step2"] = {
                "status": "done",
                "total": len(expected_keys),
                "done": len(existing_keys),
                "result": existing,
                "reused": True,
            }
            save_state(batch_id, state)
            return {"status": "reused", "count": len(existing), "message": "???????????"}

    def worker() -> None:
        logger.info("Step2 started batch=%s force=%s", batch_id, force)
        try:
            from pipeline.config import NEGATIVE_PROMPT
            from pipeline.step2_gen_prompts import build_full_prompt, call_deepseek

            if not state.get("dishes"):
                raise RuntimeError("???????????????????????????????")

            results = []
            done = 0
            for dish in state["dishes"]:
                name = dish["name"]
                category = dish.get("category", "")
                highlight = dish.get("highlight", "")
                for variant in PROMPT_VARIANTS:
                    ai_result = call_deepseek(name, category, highlight, variant)
                    full_prompt = build_full_prompt(ai_result, name, category, highlight, variant)
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
                    with open(dirs["prompts"] / f"{name}_{variant['id']}_prompt.txt", "w", encoding="utf-8") as f:
                        f.write(full_prompt)
                    with open(dirs["prompts"] / f"{name}_{variant['id']}_meta.json", "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                    results.append(result)
                    done += 1
                    state["step_progress"]["step2"] = {
                        "status": "running",
                        "total": total_variants,
                        "done": done,
                        "results": results,
                    }
                    save_state(batch_id, state)

            with open(dirs["prompts"] / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            state["step_progress"]["step2"] = {
                "status": "done",
                "total": total_variants,
                "done": len(results),
                "result": results,
            }
            logger.info("Step2 done batch=%s count=%s", batch_id, len(results))
        except Exception as exc:
            logger.exception("Step2 failed batch=%s", batch_id)
            state["step_progress"]["step2"] = {"status": "error", "error": str(exc)}
        save_state(batch_id, state)

    start_thread(f"step2-{batch_id}", worker)
    return {"status": "started", "total": total_variants}


def _build_step3_tasks(dirs: dict[str, Path], state: dict[str, Any] | None = None,
                       use_tail_frame: bool = True) -> list[dict[str, Any]]:
    """构建 Step3 任务。尾帧图以用户在 Step2 显式上传的为准（tail_images），
    仅环绕方案(v2)且开启首尾帧时使用；v1/v3 始终单图。
    """
    images_data = load_manifest(dirs, "images") or []
    prompts_data = load_manifest(dirs, "prompts") or []
    edited_path = dirs["prompts"] / "edited_prompts.json"
    edited_prompts = {}
    if edited_path.exists():
        with open(edited_path, encoding="utf-8") as f:
            edited_prompts = json.load(f)

    # 每道菜显式上传的尾帧图（Step2 用户上传，非自动猜测）
    tail_map: dict[str, str] = {}
    for dish_cfg in (state or {}).get("dishes", []):
        tails = dish_cfg.get("tail_images") or []
        if tails:
            tail_map[dish_cfg.get("name", "")] = tails[0]

    prompt_map: dict[str, list[dict[str, Any]]] = {}
    for p in prompts_data:
        dish = p["dish"]
        variant_id = p.get("variant_id", "v1")
        key = f"{dish}|{variant_id}"
        merged = {
            **p,
            **edited_prompts.get(key, {}),
        }
        if merged.get("selected", p.get("selected", False)):
            prompt_map.setdefault(dish, []).append(merged)

    tasks = []
    for img_info in images_data:
        if img_info.get("status") != "ok":
            continue
        dish = img_info["dish"]
        if dish not in prompt_map:
            continue
        images = img_info.get("images", [])
        if not images:
            continue
        for idx, prompt in enumerate(prompt_map[dish], 1):
            selection = img_info.get("selected_by_variant", {}).get(prompt.get("variant_id", "v1"), {})
            image_path = selection.get("path") if isinstance(selection, dict) else selection
            image_path = image_path or images[0]
            # 尾帧：仅环绕方案(v2) + 开启首尾帧 + 用户已上传尾帧图
            tail_image = None
            if use_tail_frame and prompt.get("variant_id") == "v2":
                tail_image = tail_map.get(dish)
            tasks.append({
                "dish": dish,
                "image_path": image_path,
                "tail_image": tail_image,
                "asset_selection": selection,
                "prompt": prompt["video_prompt"],
                "negative_prompt": prompt.get("negative_prompt", ""),
                "variant_id": prompt.get("variant_id", f"v{idx}"),
                "variant_label": prompt.get("variant_label", f"??{idx}"),
                "roll": idx,
            })
    return tasks


def run_step3(batch_id: str, force: bool = False) -> dict[str, Any]:
    state = get_batch_state(batch_id)
    state["status"] = "generating"
    state["current_step"] = 3
    state["error"] = None
    save_state(batch_id, state)

    batch_dir = OUTPUT_ROOT / batch_id
    dirs = batch_subdirs(batch_dir)
    use_tail_frame = bool(state.get("use_tail_frame", True))
    tasks = _build_step3_tasks(dirs, state=state, use_tail_frame=use_tail_frame)
    if not tasks:
        raise ValueError("请至少选择一条提示词后再生成视频")

    pending = tasks

    if not force:
        existing_clips = load_manifest(dirs, "clips") or []
        task_map = {
            f"{task['dish']}|{task.get('variant_id', task['roll'])}": task
            for task in tasks
        }
        success_map = {
            f"{c['dish']}|{c.get('variant_id', c.get('roll'))}": c["prompt"]
            for c in existing_clips
            if (
                c.get("status") == "ok"
                and c.get("prompt")
                and f"{c.get('dish')}|{c.get('variant_id', c.get('roll'))}" in task_map
            )
        }
        pending = []
        reused = []
        for task in tasks:
            key = f"{task['dish']}|{task.get('variant_id', task['roll'])}"
            if key in success_map and success_map[key] == task["prompt"]:
                reused.append(task)
            else:
                pending.append(task)

        initial_results = [
            clip
            for clip in existing_clips
            if (
                clip.get("status") == "ok"
                and (task := task_map.get(f"{clip.get('dish')}|{clip.get('variant_id', clip.get('roll'))}"))
                and clip.get("prompt") == task["prompt"]
            )
        ]

        if not pending:
            state["step_progress"]["step3"] = {
                "status": "done", "total": len(tasks), "done": len(tasks),
                "results": initial_results, "reused": True,
            }
            save_state(batch_id, state)
            return {
                "status": "reused", "total": len(tasks), "pending": 0,
                "message": f"所有片段已生成且提示词未变（{len(tasks)} 条复用），未调用 Kling API",
            }

        state["step_progress"]["step3"] = {
            "status": "running", "total": len(tasks), "done": len(initial_results),
            "results": initial_results, "reused_count": len(reused), "pending": len(pending),
        }
        save_state(batch_id, state)

    def worker() -> None:
        logger.info("Step3 started batch=%s total=%s pending=%s force=%s", batch_id, len(tasks), len(pending), force)
        try:
            from pipeline.config import VIDEO_DURATION
            from pipeline.step3_gen_videos import (
                create_task,
                download_video,
                image_to_base64,
                session_with_retry,
                wait_for_video,
            )

            session = session_with_retry()
            results = list(state["step_progress"]["step3"].get("results", []))
            done = state["step_progress"]["step3"].get("done", 0)

            for task in pending:
                try:
                    img_b64 = image_to_base64(task["image_path"])
                    tail_b64 = None
                    if task.get("tail_image"):
                        try:
                            tail_b64 = image_to_base64(task["tail_image"])
                        except Exception:
                            logger.warning("Step3 tail image read failed, fallback single-frame dish=%s", task["dish"])
                    task_id = create_task(
                        session,
                        img_b64,
                        task["prompt"],
                        task["negative_prompt"],
                        duration=VIDEO_DURATION,
                        mode="pro",
                        sound="off",
                        image_tail_base64=tail_b64,
                    )
                    video_url, info = wait_for_video(session, task_id)
                    if video_url:
                        variant_name = task.get("variant_id") or f"roll{task['roll']}"
                        out_name = f"{task['dish']}_{variant_name}_1080p_{VIDEO_DURATION}s.mp4"
                        out_path = str(dirs["clips"] / out_name)
                        download_video(session, video_url, out_path)
                        results.append({**task, "status": "ok", "output": out_path, "prompt": task["prompt"]})
                    else:
                        results.append({**task, "status": "failed", "error": str(info)[:200]})
                except Exception as exc:
                    logger.exception("Step3 item failed batch=%s dish=%s variant=%s", batch_id, task.get("dish"), task.get("variant_id", task.get("roll")))
                    results.append({**task, "status": "error", "error": str(exc)})

                done += 1
                state["step_progress"]["step3"]["done"] = done
                state["step_progress"]["step3"]["results"] = results
                save_state(batch_id, state)

            with open(dirs["clips"] / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            ok, _failed, first_error = summarize_clip_results(results)
            state["step_progress"]["step3"]["done"] = len(results)
            state["step_progress"]["step3"]["results"] = results
            if ok:
                state["step_progress"]["step3"]["status"] = "done"
                state["status"] = "reviewing"
                state["error"] = None
            else:
                state["step_progress"]["step3"]["status"] = "error"
                state["step_progress"]["step3"]["error"] = first_error or "Kling 片段生成全部失败"
                state["status"] = "error"
                state["error"] = f"Kling 片段生成失败：{state['step_progress']['step3']['error']}"
            logger.info("Step3 finished batch=%s ok=%s total=%s", batch_id, ok, len(results))
        except Exception as exc:
            logger.exception("Step3 failed batch=%s", batch_id)
            state["step_progress"]["step3"] = {"status": "error", "error": str(exc)}
        save_state(batch_id, state)

    if pending == tasks:
        state["step_progress"]["step3"] = {"status": "running", "total": len(tasks), "done": 0, "results": []}
        save_state(batch_id, state)

    start_thread(f"step3-{batch_id}", worker)
    return {"status": "started", "total": len(tasks), "pending": len(pending)}


def run_compose(batch_id: str, video_config: dict[str, Any]) -> dict[str, Any]:
    state = get_batch_state(batch_id)
    selected = state.get("selected_clips", {})
    try:
        min_dishes = int(video_config.get("min_dishes") or 5)
    except (TypeError, ValueError):
        min_dishes = 5
    min_dishes = max(1, min(min_dishes, 20))
    selected_count = sum(1 for filename in selected.values() if filename)
    if selected_count < min_dishes:
        raise ValueError(f"当前已选择 {selected_count} 道菜，至少需要选择 {min_dishes} 道菜才能合成")

    state["status"] = "composing"
    state["current_step"] = 5
    video_plan = build_video_plan(state, selected, video_config)
    if not video_plan:
        raise ValueError("请先选择可合成的片段")

    state["step_progress"]["compose"] = {"status": "running", "total": len(video_plan), "done": 0, "results": []}
    state["video_plan"] = video_plan
    save_state(batch_id, state)

    def worker() -> None:
        logger.info("Compose started batch=%s videos=%s", batch_id, len(video_plan))
        try:
            from pipeline.config import BGM_FILE
            from pipeline.step5_compose import concat_clips, trim_clip
            from pipeline.step6_voice_bgm import generate_caption, generate_tts, get_video_duration, merge_audio_video, mix_audio

            batch_dir = OUTPUT_ROOT / batch_id
            dirs = batch_subdirs(batch_dir)
            captions = state.get("captions", {})
            brand_info = video_config.get("brand", {"name": "示例品牌", "cta": "评论区领优惠券"})
            bgm_volume = video_config.get("bgm_volume", 0.3)

            subtitles = {}
            prompts = load_manifest(dirs, "prompts") or []
            for prompt in prompts:
                dish = prompt["dish"]
                subtitles[dish] = captions.get(dish, {}).get("subtitle") or prompt.get("subtitle", dish)

            results = []
            for video in video_plan:
                vid = video["id"]
                dish_order = list(video["dishes"])
                hook_dish = video.get("hook_dish", dish_order[0])
                if hook_dish in dish_order:
                    dish_order.remove(hook_dish)
                    dish_order.insert(0, hook_dish)

                template = get_video_template(len(dish_order))
                seg_durations = [s["duration"] for s in template["segments"] if s["role"] != "outro"]
                trimmed_paths = []
                vid_subtitles = []
                for i, dish in enumerate(dish_order):
                    clip_file = selected.get(dish)
                    if not clip_file:
                        continue
                    clip_path = str(dirs["clips"] / clip_file)
                    if not os.path.exists(clip_path):
                        continue
                    duration = seg_durations[i] if i < len(seg_durations) else 2.0
                    trimmed_path = str(dirs["composed"] / f"{vid}_{dish}_trim.mp4")
                    trim_clip(clip_path, trimmed_path, start=0.5, duration=duration)
                    trimmed_paths.append(trimmed_path)
                    vid_subtitles.append({"text": subtitles.get(dish, dish), "duration": duration})

                if not trimmed_paths:
                    results.append({"id": vid, "status": "failed", "error": "无可用片段"})
                    continue

                composed_path = str(dirs["composed"] / f"{vid}_composed.mp4")
                concat_clips(trimmed_paths, composed_path, vid_subtitles, brand_info)
                for path in trimmed_paths:
                    if os.path.exists(path):
                        os.remove(path)

                duration = get_video_duration(composed_path)
                caption_text = ""
                for dish in dish_order:
                    if dish in captions and captions[dish].get("caption"):
                        caption_text = captions[dish]["caption"]
                        break
                if not caption_text:
                    caption_text = generate_caption([subtitles.get(d, d) for d in dish_order], brand_info, vid)

                voice_path = str(dirs["final"] / f"{vid}_voice.mp3")
                audio_path = str(dirs["final"] / f"{vid}_audio.mp3")
                final_path = str(dirs["final"] / f"{vid}_final.mp4")
                voice_result = generate_tts(caption_text, voice_path)
                bgm_exists = os.path.exists(str(BGM_FILE))

                if voice_result and bgm_exists:
                    mix_audio(voice_path, str(BGM_FILE), audio_path, bgm_volume=bgm_volume, video_duration=duration)
                    merge_audio_video(composed_path, audio_path, final_path)
                elif voice_result:
                    merge_audio_video(composed_path, voice_path, final_path)
                elif bgm_exists:
                    cmd = [
                        "ffmpeg", "-y", "-i", str(BGM_FILE), "-t", str(duration),
                        "-af", f"volume={bgm_volume},afade=t=in:st=0:d=0.5,afade=t=out:st={duration-1}:d=1",
                        "-c:a", "aac", "-b:a", "192k", audio_path,
                    ]
                    subprocess.run(cmd, capture_output=True, timeout=60)
                    merge_audio_video(composed_path, audio_path, final_path)
                else:
                    shutil.copy(composed_path, final_path)

                for tmp in [voice_path, audio_path]:
                    if os.path.exists(tmp):
                        os.remove(tmp)

                item = {
                    "id": vid,
                    "status": "ok" if os.path.exists(final_path) else "failed",
                    "path": final_path,
                    "filename": os.path.basename(final_path),
                    "caption": caption_text,
                    "duration": duration,
                    "dishes": dish_order,
                }
                results.append(item)
                state["step_progress"]["compose"]["done"] = len(results)
                state["step_progress"]["compose"]["results"] = results
                save_state(batch_id, state)

            with open(dirs["final"] / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            state["status"] = "done"
            state["videos"] = results
            state["step_progress"]["compose"]["status"] = "done"
            logger.info("Compose done batch=%s videos=%s", batch_id, len(results))
        except Exception as exc:
            logger.exception("Compose failed batch=%s", batch_id)
            state["step_progress"]["compose"] = {"status": "error", "error": str(exc)}
            state["status"] = "error"
            state["error"] = str(exc)
        save_state(batch_id, state)

    start_thread(f"compose-{batch_id}", worker)
    return {"status": "started"}
