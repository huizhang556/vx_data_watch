from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings
from .ai_protocol_registry import RUNTIME_PROTOCOLS

BUILTIN_CATALOG_PATH = Path(__file__).with_name("ai_protocols.json")
OVERRIDE_FILENAME = "ai_protocols.override.json"
HISTORY_DIRNAME = "ai-protocol-history"
MAX_HISTORY_FILES = 20
MAX_CATALOG_BYTES = 2 * 1024 * 1024
PROTOCOL_CATEGORIES = {"chat", "image", "video"}


class CatalogValidationError(ValueError):
    pass


def override_path() -> Path:
    return get_settings().data_dir / OVERRIDE_FILENAME


def history_dir() -> Path:
    return get_settings().data_dir / HISTORY_DIRNAME


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_CATALOG_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_builtin_catalog() -> dict[str, Any]:
    value = _read_json(BUILTIN_CATALOG_PATH)
    return value or {"schema_version": 1, "providers": {}}


def load_catalog() -> tuple[dict[str, Any], str, str | None]:
    builtin = load_builtin_catalog()
    path = override_path()
    override = _read_json(path)
    if override and isinstance(override.get("providers"), dict):
        timestamp: str | None = None
        try:
            timestamp = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
        except OSError:
            pass
        return _merge_catalog(builtin, override), "custom", timestamp
    return builtin, "builtin", None


def _merge_catalog(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge admin overrides onto the bundled catalog so new release fields survive."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = copy.deepcopy(base)
        for key, value in override.items():
            result[key] = _merge_catalog(result[key], value) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(override)


def validate_catalog(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogValidationError("协议目录必须是 JSON 对象")
    providers = value.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise CatalogValidationError("协议目录至少需要一个厂商")
    normalized = copy.deepcopy(value)
    normalized["schema_version"] = int(value.get("schema_version", 1))
    for key, provider in providers.items():
        if not isinstance(key, str) or not key or not isinstance(provider, dict):
            raise CatalogValidationError("厂商键和厂商配置格式无效")
        for field in ("display_name", "base_url", "default_model"):
            if not isinstance(provider.get(field), str) or not provider[field].strip():
                raise CatalogValidationError(f"厂商 {key} 缺少有效的 {field}")
        models = provider.get("models", {})
        protocols = provider.get("protocols", {})
        if not isinstance(models, dict) or not isinstance(protocols, dict):
            raise CatalogValidationError(f"厂商 {key} 的 models 或 protocols 格式无效")
        for category in PROTOCOL_CATEGORIES:
            model_values = models.get(category, [])
            protocol_values = protocols.get(category, [])
            if not isinstance(model_values, list) or any(not isinstance(item, str) or not item.strip() for item in model_values):
                raise CatalogValidationError(f"厂商 {key} 的 {category} 模型列表无效")
            if not isinstance(protocol_values, list):
                raise CatalogValidationError(f"厂商 {key} 的 {category} 协议列表无效")
            seen: set[str] = set()
            for item in protocol_values:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
                    raise CatalogValidationError(f"厂商 {key} 的 {category} 协议缺少 id")
                if item["id"] in seen:
                    raise CatalogValidationError(f"厂商 {key} 的 {category} 存在重复协议 id")
                seen.add(item["id"])
                if item.get("implemented", True) and item["id"] not in RUNTIME_PROTOCOLS[category]:
                    raise CatalogValidationError(f"厂商 {key} 的 {category} 协议 {item['id']} 尚未注册运行时处理器，请标记 implemented=false")
                for field in ("label", "method", "path", "request_format"):
                    if not isinstance(item.get(field), str) or not item[field].strip():
                        raise CatalogValidationError(f"协议 {item['id']} 缺少有效的 {field}")
    return normalized


def save_catalog(value: Any) -> dict[str, Any]:
    catalog = validate_catalog(value)
    path = override_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        history_dir().mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path.replace(history_dir() / f"{stamp}.json")
        history = sorted(history_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in history[MAX_HISTORY_FILES:]:
            old.unlink(missing_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return catalog


def reset_catalog() -> None:
    try:
        override_path().unlink()
    except FileNotFoundError:
        pass


def list_history() -> list[dict[str, str]]:
    rows = []
    for path in sorted(history_dir().glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        rows.append({"filename": path.name, "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()})
    return rows


def restore_history(filename: str) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise CatalogValidationError("历史文件名无效")
    path = history_dir() / filename
    value = _read_json(path)
    if value is None:
        raise CatalogValidationError("历史协议目录不存在或格式无效")
    return save_catalog(value)
