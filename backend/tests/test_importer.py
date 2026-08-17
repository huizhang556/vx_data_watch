from __future__ import annotations

import pytest
from app.importers import ImportValidationError, parse_account_csv

CSV_SAMPLE = """视频号视频详情数据,,,,,\n由于服务器缓存，数据可能存在微小误差。,,,,,\n\"时间\",\"播放\",\"推荐\",\"喜欢\",\"评论\",\"分享\",\"关注\"\n\"2026/08/16\",1200,12,60,8,20,10\n\"2026/08/15\",800,8,40,4,12,6\n""".encode()


def test_parse_real_header_shape() -> None:
    rows = parse_account_csv(b"\xef\xbb\xbf" + CSV_SAMPLE)
    assert len(rows) == 2
    assert rows[0].metric_date.isoformat() == "2026-08-16"
    assert rows[0].plays == 1200
    assert rows[0].likes == 60


def test_rejects_negative_or_invalid_values() -> None:
    invalid = CSV_SAMPLE.replace(b"1200", b"-1")
    with pytest.raises(ImportValidationError, match="非负整数"):
        parse_account_csv(invalid)
