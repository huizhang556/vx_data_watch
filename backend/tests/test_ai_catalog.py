from app.ai_catalog import _merge_catalog, validate_catalog


def test_catalog_override_keeps_new_builtin_provider_fields() -> None:
    builtin = {"schema_version": 2, "providers": {"demo": {"display_name": "Demo", "models": {"chat": ["new"]}}}}
    override = {"providers": {"demo": {"models": {"chat": ["custom"]}}}}
    merged = _merge_catalog(builtin, override)
    assert merged["providers"]["demo"]["display_name"] == "Demo"
    assert merged["providers"]["demo"]["models"]["chat"] == ["custom"]
    assert merged["schema_version"] == 2


def test_catalog_validation_rejects_duplicate_protocols() -> None:
    value = {
        "schema_version": 2,
        "providers": {
            "demo": {
                "display_name": "Demo",
                "base_url": "https://example.com",
                "default_model": "demo-chat",
                "models": {"chat": ["demo-chat"], "image": [], "video": []},
                "protocols": {
                    "chat": [
                        {"id": "demo", "label": "Demo", "method": "POST", "path": "/chat", "request_format": "demo", "implemented": False},
                        {"id": "demo", "label": "Demo", "method": "POST", "path": "/chat", "request_format": "demo", "implemented": False},
                    ],
                    "image": [],
                    "video": [],
                },
            }
        },
    }
    try:
        validate_catalog(value)
    except ValueError as exc:
        assert "重复协议" in str(exc)
    else:
        raise AssertionError("duplicate protocol IDs must be rejected")


def test_catalog_validation_rejects_enabled_unknown_runtime_protocol() -> None:
    value = {
        "schema_version": 1,
        "providers": {
            "demo": {
                "display_name": "Demo",
                "base_url": "https://example.com",
                "default_model": "demo-chat",
                "models": {"chat": ["demo-chat"], "image": [], "video": []},
                "protocols": {
                    "chat": [{"id": "future_chat", "label": "Future", "method": "POST", "path": "/future", "request_format": "future", "implemented": True}],
                    "image": [],
                    "video": [],
                },
            }
        },
    }
    try:
        validate_catalog(value)
    except ValueError as exc:
        assert "implemented=false" in str(exc)
    else:
        raise AssertionError("unknown enabled protocols must be rejected")
