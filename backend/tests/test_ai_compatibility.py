from __future__ import annotations

from app.ai_catalog import load_builtin_catalog
from app.ai_service import (
    SUPPORTED_CHAT_PROTOCOLS,
    SUPPORTED_IMAGE_PROTOCOLS,
    SUPPORTED_VIDEO_PROTOCOLS,
    _request_path,
)
from app.ai_catalog import RUNTIME_PROTOCOLS
from app.ai_protocol_registry import RUNTIME_PROTOCOLS as REGISTRY_PROTOCOLS


def test_catalog_and_request_runtime_use_one_protocol_registry() -> None:
    assert RUNTIME_PROTOCOLS is REGISTRY_PROTOCOLS


def test_catalog_implemented_protocols_have_runtime_handlers() -> None:
    catalog = load_builtin_catalog()
    supported = {
        "chat": SUPPORTED_CHAT_PROTOCOLS,
        "image": SUPPORTED_IMAGE_PROTOCOLS,
        "video": SUPPORTED_VIDEO_PROTOCOLS,
    }
    for provider_key, provider in catalog["providers"].items():
        models = provider["models"]
        for category, entries in provider["protocols"].items():
            for entry in entries:
                if not entry.get("implemented", True):
                    continue
                assert entry["id"] in supported[category], f"{provider_key}/{category}/{entry['id']} has no handler"
                assert entry["path"].startswith("/"), f"{provider_key}/{entry['id']} path must be absolute"
                assert entry["request_format"], f"{provider_key}/{entry['id']} request format is missing"
                assert models.get(category), f"{provider_key}/{category} has an implemented protocol but no model"


def test_builtin_protocol_paths_resolve_without_duplicate_version_prefix() -> None:
    assert _request_path("https://api.openai.com", "openai_images", "gpt-image-1", "image") == "/v1/images/generations"
    assert _request_path("https://api.openai.com/v1", "openai_images", "gpt-image-1", "image") == "/images/generations"
    assert _request_path("https://api.openai.com", "openai_videos", "sora-2", "video") == "/v1/videos"
    assert _request_path("https://api.openai.com/v1", "openai_videos", "sora-2", "video") == "/videos"
    assert _request_path("https://generativelanguage.googleapis.com", "gemini", "gemini-2.5-flash") == "/v1beta/models/gemini-2.5-flash:generateContent"


def test_unimplemented_generation_protocols_are_not_runtime_supported() -> None:
    catalog = load_builtin_catalog()
    for provider in catalog["providers"].values():
        for category in ("image", "video"):
            for entry in provider["protocols"].get(category, []):
                if not entry.get("implemented", True):
                    assert entry["id"] not in (SUPPORTED_IMAGE_PROTOCOLS | SUPPORTED_VIDEO_PROTOCOLS)
