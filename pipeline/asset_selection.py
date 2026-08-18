# -*- coding: utf-8 -*-
"""Local image quality and source-image selection for video variants."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat


VARIANT_HINTS = {
    "v1": ("front", "close", "45", "\u6b63\u9762", "\u8fd1\u666f", "\u4fa7\u524d"),
    "v2": ("side", "profile", "angle", "\u4fa7\u9762", "\u659c\u4fa7", "\u7acb\u4f53"),
    "v3": ("wide", "horizontal", "\u6a2a", "\u80cc\u666f", "\u89c6\u5dee"),
}


def _scale(value: float, values: list[float]) -> float:
    low = min(values)
    high = max(values)
    if high <= low:
        return 1.0
    return (value - low) / (high - low)


def _exposure_score(brightness: float) -> float:
    target = 145.0
    return max(0.0, 1.0 - abs(brightness - target) / target)


def _contrast_score(contrast: float) -> float:
    return min(1.0, max(0.0, (contrast - 5.0) / 60.0))


def _filename_hint(source: str, variant_id: str) -> bool:
    name = Path(source).stem.lower()
    return any(keyword.lower() in name for keyword in VARIANT_HINTS.get(variant_id, ()))


def _analyze_image(path: str) -> dict[str, Any]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        brightness = float(ImageStat.Stat(gray).mean[0])
        contrast = float(ImageStat.Stat(gray).stddev[0])
        edges = gray.filter(ImageFilter.FIND_EDGES)
        sharpness = float(ImageStat.Stat(edges).stddev[0])
        width, height = rgb.size

    return {
        "path": path,
        "width": width,
        "height": height,
        "file_size": Path(path).stat().st_size,
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "sharpness": round(sharpness, 2),
    }


def build_asset_manifest(dish: str, assets: list[dict[str, str]]) -> dict[str, Any]:
    """Score all processed images and recommend one source per prompt variant."""
    profiles = []
    for asset in assets:
        profile = _analyze_image(asset["processed"])
        profile["dish"] = dish
        profile["source"] = asset["source"]
        profiles.append(profile)

    sharpness_values = [profile["sharpness"] for profile in profiles]
    for profile in profiles:
        quality = (
            0.55 * _scale(profile["sharpness"], sharpness_values)
            + 0.30 * _exposure_score(profile["brightness"])
            + 0.15 * _contrast_score(profile["contrast"])
        )
        profile["quality_score"] = round(quality * 100, 1)

    selected_by_variant: dict[str, dict[str, Any]] = {}
    for variant_id in VARIANT_HINTS:
        ranked = sorted(
            profiles,
            key=lambda profile: profile["quality_score"] + (
                18.0 if _filename_hint(profile["source"], variant_id) else 0.0
            ),
            reverse=True,
        )
        selected = ranked[0]
        has_hint = _filename_hint(selected["source"], variant_id)
        selected_by_variant[variant_id] = {
            "path": selected["path"],
            "source": selected["source"],
            "quality_score": selected["quality_score"],
            "reason": "filename angle hint + quality score" if has_hint else "quality score fallback",
        }

    return {
        "dish": dish,
        "assets": profiles,
        "selected_by_variant": selected_by_variant,
    }