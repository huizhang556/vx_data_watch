from __future__ import annotations

import io
from datetime import date

from app import ocr
from PIL import Image


def _box(x: int, y: int, width: int = 70) -> list[list[int]]:
    return [[x, y - 5], [x + width, y - 5], [x + width, y + 5], [x, y + 5]]


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (400, 500), "white").save(output, format="PNG")
    return output.getvalue()


def test_extracts_candidate_from_ocr_coordinates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    entries = [
        [_box(5, 105), "缩略图干扰文字", 0.99],
        [_box(90, 100, 220), "一条用于测试的视频", 0.96],
        [_box(90, 150, 220), "2026年8月14日 21:49", 0.98],
        [_box(80, 220), "1.3万", 0.97],
        [_box(145, 200), "30", 0.97],
        [_box(215, 240), "8", 0.97],
        [_box(290, 210), "15", 0.97],
        [_box(100, 320, 220), "昨日新增 600 次播放", 0.99],
    ]
    def fake_engine(image):  # type: ignore[no-untyped-def]
        return (entries, 0.01) if image.width == 400 else (None, 0.01)

    monkeypatch.setattr(ocr, "_engine", lambda: fake_engine)

    rows = ocr.extract_screenshot_candidates(_image_bytes(), date(2026, 8, 16), "sample.png")

    assert len(rows) == 1
    assert rows[0] == {
        "source_image": "sample.png",
        "title": "一条用于测试的视频",
        "published_at": "2026-08-14T21:49:00",
        "metric_date": "2026-08-16",
        "plays": 600,
        "cumulative_plays": 13000,
        "cumulative_plays_approximate": True,
        "likes": 30,
        "comments": 8,
        "shares": 15,
        "confidence": 0.96,
    }


def test_deduplicates_overlapping_screenshots_by_confidence() -> None:
    common = {
        "title": "同一条 视频",
        "published_at": "2026-08-14T21:49:00",
        "metric_date": "2026-08-16",
        "plays": 600,
    }
    low = {**common, "source_image": "first.png", "confidence": 0.72}
    high = {**common, "title": "同一条视频", "source_image": "second.png", "confidence": 0.95}

    assert ocr.deduplicate_candidates([low, high]) == [high]


def test_resizes_high_resolution_images_before_ocr() -> None:
    image = Image.new("RGB", (5000, 4000), "white")
    resized = ocr._resize_for_ocr(image)
    assert max(resized.size) == 2000
    assert resized.size == (2000, 1600)
