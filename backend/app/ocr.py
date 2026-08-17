from __future__ import annotations

import io
import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from PIL import Image, UnidentifiedImageError

from .importers import normalize_title


class OCRUnavailableError(RuntimeError):
    pass


@lru_cache
def _engine():  # type: ignore[no-untyped-def]
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise OCRUnavailableError("OCR 组件未安装，请安装项目的 ocr 依赖") from exc
    return RapidOCR()


def _center_y(box: Any) -> float:
    return sum(float(point[1]) for point in box) / len(box)


def _center_x(box: Any) -> float:
    return sum(float(point[0]) for point in box) / len(box)


def _parse_compact_number(text: str) -> tuple[int | None, bool]:
    cleaned = text.strip().replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)万", cleaned)
    if match:
        return int(float(match.group(1)) * 10000), True
    match = re.search(r"\d+", cleaned.replace(",", ""))
    return (int(match.group()), False) if match else (None, False)


def _line(box: Any, text: Any, score: Any) -> dict[str, Any]:
    return {
        "box": box,
        "text": str(text).strip(),
        "score": float(score),
        "x": _center_x(box),
        "left": min(float(point[0]) for point in box),
        "y": _center_y(box),
    }


def _merge_line(lines: list[dict[str, Any]], incoming: dict[str, Any]) -> None:
    for index, existing in enumerate(lines):
        if abs(existing["x"] - incoming["x"]) < 20 and abs(existing["y"] - incoming["y"]) < 8:
            if incoming["score"] > existing["score"]:
                lines[index] = incoming
            return
    lines.append(incoming)


def _assign_metric_values(
    lines: list[dict[str, Any]],
    anchors: tuple[float, ...],
    width: float,
    values: dict[int, tuple[int, bool, float]],
) -> None:
    for line in lines:
        value, approximate = _parse_compact_number(line["text"])
        if value is None:
            continue
        position = line["x"] / width
        metric_index = min(range(len(anchors)), key=lambda index: abs(anchors[index] - position))
        if abs(anchors[metric_index] - position) > 0.1:
            continue
        previous = values.get(metric_index)
        if not previous or line["score"] > previous[2]:
            values[metric_index] = (value, approximate, line["score"])


def extract_screenshot_candidates(
    content: bytes, metric_date: date, image_name: str
) -> list[dict[str, Any]]:
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
        image.verify() if hasattr(image, "verify") else None
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("无法读取截图") from exc
    if image.width * image.height > 30_000_000:
        raise ValueError("截图像素过大")

    result, _elapsed = _engine()(image)
    lines: list[dict[str, Any]] = []
    for entry in result or []:
        box, text, score = entry
        _merge_line(lines, _line(box, text, score))

    crop_left = int(image.width * 0.19)
    crop_right = int(image.width * 0.93)
    crop_top = int(image.height * 0.09)
    crop_bottom = int(image.height * 0.96)
    content = image.crop((crop_left, crop_top, crop_right, crop_bottom)).resize(
        ((crop_right - crop_left) * 2, (crop_bottom - crop_top) * 2),
        Image.Resampling.LANCZOS,
    )
    detailed_result, _elapsed = _engine()(content)
    for box, text, score in detailed_result or []:
        mapped_box = [
            [crop_left + float(point[0]) / 2, crop_top + float(point[1]) / 2] for point in box
        ]
        _merge_line(lines, _line(mapped_box, text, score))
    lines.sort(key=lambda item: item["y"])

    candidates: list[dict[str, Any]] = []
    increment_pattern = re.compile(r"昨日新增\s*(\d+)\s*次?播放")
    published_pattern = re.compile(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[：:](\d{2})"
    )
    for increment_line in lines:
        match = increment_pattern.search(increment_line["text"].replace(" ", ""))
        if not match:
            continue
        card_height = max(300.0, image.height * 0.22)
        window = [
            line
            for line in lines
            if increment_line["y"] - card_height <= line["y"] < increment_line["y"]
        ]
        published_at = None
        date_line = None
        for line in reversed(window):
            date_match = published_pattern.search(line["text"])
            if date_match:
                published_at = datetime(*(int(value) for value in date_match.groups()))
                date_line = line
                break
        title_lines = []
        if date_line:
            title_height = max(90.0, image.height * 0.06)
            title_lines = [
                line
                for line in window
                if date_line["y"] - title_height <= line["y"] < date_line["y"]
                and line["left"] >= image.width * 0.2
                and len(line["text"]) >= 3
                and not re.search(r"昨日新增|数据中心|单篇数据", line["text"])
            ]
        title = " ".join(line["text"] for line in title_lines).strip() or "待确认视频"
        numeric_lines = [
            line
            for line in window
            if date_line and date_line["y"] < line["y"] < increment_line["y"] - 15
        ]
        metric_anchors = (0.286, 0.448, 0.617, 0.813)
        metric_values: dict[int, tuple[int, bool, float]] = {}
        _assign_metric_values(numeric_lines, metric_anchors, image.width, metric_values)
        if date_line and len(metric_values) < 4:
            band_left = int(image.width * 0.19)
            band_right = int(image.width * 0.93)
            band_top = max(0, int(date_line["y"] - image.height * 0.02))
            band_bottom = min(image.height, int(increment_line["y"] - image.height * 0.02))
            band = image.crop((band_left, band_top, band_right, band_bottom)).resize(
                ((band_right - band_left) * 2, (band_bottom - band_top) * 2),
                Image.Resampling.LANCZOS,
            )
            band_result, _elapsed = _engine()(band)
            band_lines = [
                _line(box, text, score)
                for box, text, score in band_result or []
                if _center_y(box) > band.height * 0.45
            ]
            band_anchors = tuple(
                (anchor * image.width - band_left) / (band_right - band_left)
                for anchor in metric_anchors
            )
            _assign_metric_values(band_lines, band_anchors, band.width, metric_values)
        cumulative_entry = metric_values.get(0)
        cumulative = cumulative_entry[0] if cumulative_entry else None
        approximate = cumulative_entry[1] if cumulative_entry else False
        candidates.append(
            {
                "source_image": image_name,
                "title": title,
                "published_at": published_at.isoformat() if published_at else None,
                "metric_date": metric_date.isoformat(),
                "plays": int(match.group(1)),
                "cumulative_plays": cumulative,
                "cumulative_plays_approximate": approximate,
                "likes": metric_values.get(1, (None, False, 0.0))[0],
                "comments": metric_values.get(2, (None, False, 0.0))[0],
                "shares": metric_values.get(3, (None, False, 0.0))[0],
                "confidence": round(
                    min([increment_line["score"], *(line["score"] for line in title_lines)]), 3
                )
                if title_lines
                else round(increment_line["score"], 3),
            }
        )
    return deduplicate_candidates(candidates)


def deduplicate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for candidate in candidates:
        published_at = candidate.get("published_at")
        key = (
            ("published", published_at, candidate.get("plays"))
            if published_at
            else ("title", normalize_title(candidate.get("title", "")), candidate.get("plays"))
        )
        existing = unique.get(key)
        if not existing or candidate.get("confidence", 0) > existing.get("confidence", 0):
            unique[key] = candidate
    return list(unique.values())
