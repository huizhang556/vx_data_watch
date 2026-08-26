from unittest.mock import patch

import pytest

from app.download_service import DownloadControl, _check_proxy, _format_selector


def test_format_selector_supports_download_modes():
    assert _format_selector({"quality": "720", "download_type": "audio"}) == "bestaudio/best"
    assert "height<=1080" in _format_selector({"quality": "1080", "download_type": "video"})
    assert "+bestaudio/best" in _format_selector({"quality": "best", "download_type": "video_audio"})


def test_download_control_status_is_preserved():
    assert DownloadControl("paused").status == "paused"
    assert DownloadControl("cancelled").status == "cancelled"


def test_check_proxy_reports_connection_failure():
    with patch("app.download_service.urllib.request.ProxyHandler", side_effect=ValueError("bad proxy")):
        with pytest.raises(ValueError, match="bad proxy"):
            _check_proxy("http://127.0.0.1:1")
