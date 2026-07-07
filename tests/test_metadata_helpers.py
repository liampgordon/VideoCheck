import pytest

from videocheck_qt import parse_frame_rate, format_bitrate, parse_int


def test_parses_ntsc_fractional_rate():
    assert parse_frame_rate("30000/1001") == pytest.approx(29.97, abs=0.01)


def test_parses_whole_number_rate():
    assert parse_frame_rate("25/1") == pytest.approx(25.0)


def test_zero_rate_returns_zero():
    assert parse_frame_rate("0/0") == 0


def test_missing_rate_returns_zero():
    assert parse_frame_rate(None) == 0
    assert parse_frame_rate("") == 0


def test_garbage_is_not_executed():
    assert parse_frame_rate("__import__('os').getpid()") == 0


def test_format_bitrate_scales_units():
    assert format_bitrate(5_000_000) == "5.0 Mbps"
    assert format_bitrate(140_000) == "140 kbps"
    assert format_bitrate(None) == "N/A"


def test_parse_int_handles_bad_input():
    assert parse_int("139572") == 139572
    assert parse_int(None) is None
    assert parse_int("not a number") is None


def test_get_metadata_on_real_clip(test_clip):
    from videocheck_qt import get_metadata

    meta = get_metadata(test_clip)
    assert meta["Resolution"] == "320 x 240"
    assert meta["FPS"] == "25.00"
    assert meta["Video Codec"] == "h264"
    assert meta["Audio Codec"] == "aac"
    assert meta["Bit Rate"].endswith(("kbps", "Mbps"))
    sort = meta["_sort"]
    assert sort["FPS"] == 25.0
    assert sort["Size"] > 0
    assert sort["Bit Rate"] > 0
    assert 0.5 < sort["Duration"] < 2.0
    assert sort["Channels"] == 1
