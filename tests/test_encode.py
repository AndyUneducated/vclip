import pytest

from vclip.encode import (
    _default_bitrate,
    build_plan,
    parse_resolution,
    resolve_hdr_mode,
)
from conftest import make_caps, make_info, make_opts, make_sdr_info


def test_parse_resolution_aliases():
    assert parse_resolution("1080p") == (None, 1080)
    assert parse_resolution("4k") == (None, 2160)
    assert parse_resolution("720p") == (None, 720)
    assert parse_resolution("1920x1080") == (1920, 1080)
    assert parse_resolution("1080") == (None, 1080)
    assert parse_resolution(None) == (None, None)


def test_parse_resolution_invalid():
    with pytest.raises(ValueError):
        parse_resolution("huge")


def test_default_bitrate_tiers():
    assert _default_bitrate("h264", 1080) == 8000
    assert _default_bitrate("hevc", 2160) == 25000
    assert _default_bitrate("h264", 99999) == _default_bitrate("h264", 2160)


def test_resolve_hdr_sdr_source_is_none():
    mode, warns = resolve_hdr_mode(make_sdr_info(), make_opts(), make_caps())
    assert mode == "none"
    assert warns == []


def test_resolve_hdr_auto_keeps_when_cannot_tonemap():
    caps = make_caps(zscale=False, tonemap=False, libplacebo=False)
    mode, warns = resolve_hdr_mode(make_info(), make_opts(hdr="auto"), caps)
    assert mode == "keep"
    assert warns  # 应有降级提醒


def test_resolve_hdr_auto_prefers_sdr_when_capable():
    mode, _ = resolve_hdr_mode(make_info(), make_opts(hdr="auto"), make_caps())
    assert mode == "sdr"


def test_build_plan_software_h264():
    plan = build_plan(make_sdr_info(), make_opts(encoder="software"), make_caps())
    assert plan.encoder_name == "libx264"
    assert "-c:v" in plan.video_args and "libx264" in plan.video_args


def test_build_plan_hardware_selection():
    caps = make_caps(vt_h264=True)
    plan = build_plan(make_sdr_info(), make_opts(encoder="hardware"), caps)
    assert plan.encoder_name == "h264_videotoolbox"


def test_build_plan_hardware_falls_back_to_software():
    caps = make_caps(vt_h264=False, nvenc_h264=False)
    plan = build_plan(make_sdr_info(), make_opts(encoder="hardware"), caps)
    assert plan.encoder_name == "libx264"
    assert any("回退" in w for w in plan.warnings)


def test_hdr_keep_forces_hevc():
    # auto+可 tonemap 会转 sdr，这里显式 keep
    plan = build_plan(make_info(), make_opts(codec="h264", hdr="keep",
                                             encoder="software"), make_caps())
    assert plan.encoder_name == "libx265"
    assert plan.hdr_mode == "keep"


def test_force_bitrate_drops_crf():
    plan = build_plan(
        make_sdr_info(),
        make_opts(crf=20, encoder="software"),
        make_caps(),
        force_bitrate=True,
    )
    # force_bitrate 时忽略 CRF，改用码率
    assert "-crf" not in plan.video_args
    assert plan.total_bitrate_kbps is not None


def test_crf_implies_software_even_if_hw_available():
    caps = make_caps(vt_h264=True)
    plan = build_plan(make_sdr_info(), make_opts(crf=22), caps)
    assert plan.encoder_name == "libx264"
    assert "-crf" in plan.video_args


def test_audio_copy_and_no_audio():
    plan = build_plan(make_sdr_info(), make_opts(audio_copy=True, encoder="software"),
                      make_caps())
    assert plan.audio_args == ["-c:a", "copy"]
    plan2 = build_plan(make_sdr_info(has_audio=False),
                       make_opts(encoder="software"), make_caps())
    assert plan2.audio_args == ["-an"]
