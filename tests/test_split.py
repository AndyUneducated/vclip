import pytest

from vclip.split import (
    _copy_cmd,
    _encode_seg_cmd,
    plan_duration,
    plan_size,
    plan_trim,
)
from vclip.encode import build_plan
from conftest import make_caps, make_info, make_opts, make_sdr_info


def test_copy_cmd_preserves_all_streams(tmp_path):
    info = make_sdr_info()
    cmd = _copy_cmd(info, 10.0, tmp_path / "out_%03d.mp4")
    # -map 0 保留全部流
    assert "-map" in cmd
    assert cmd[cmd.index("-map") + 1] == "0"
    assert "copy" in cmd
    assert "segment" in cmd


def test_encode_seg_maps_all_audio(tmp_path):
    info = make_sdr_info()
    plan = build_plan(info, make_opts(encoder="software"), make_caps())
    cmd = _encode_seg_cmd(info, plan, 0.0, 10.0, tmp_path / "p.mp4")
    assert "0:v:0" in cmd
    assert "0:a?" in cmd


def test_plan_duration_copy():
    plan = plan_duration(make_sdr_info(duration=120), 30, make_caps(),
                         make_opts(), transcode=False)
    assert plan.mode == "duration-copy"
    assert plan.estimated_parts == 4
    assert len(plan.commands) == 1
    assert plan.encode_plan is None


def test_plan_duration_encode_parts_and_jobs():
    plan = plan_duration(make_sdr_info(duration=100), 30, make_caps(),
                         make_opts(encoder="software"), transcode=True, jobs=4)
    assert plan.mode == "duration-encode"
    assert plan.estimated_parts == 4  # ceil(100/30)
    assert len(plan.commands) == 4
    assert plan.jobs == 4


def test_plan_duration_rejects_nonpositive():
    with pytest.raises(ValueError):
        plan_duration(make_sdr_info(), 0, make_caps(), make_opts(), transcode=False)


def test_plan_size_copy_requires_bitrate():
    with pytest.raises(ValueError):
        plan_size(make_sdr_info(duration=0, size_bytes=0, stream_bitrate=0),
                  100, make_caps(), make_opts(), lossless=True)


def test_plan_size_copy_segments():
    info = make_sdr_info(size_bytes=1000 * 1024 * 1024, duration=100)
    plan = plan_size(info, 200, make_caps(), make_opts(), lossless=True)
    assert plan.mode == "size-copy"
    assert plan.estimated_parts >= 1


def test_plan_size_rejects_nonpositive():
    with pytest.raises(ValueError):
        plan_size(make_sdr_info(), 0, make_caps(), make_opts(), lossless=False)


def test_plan_trim_copy_basic(tmp_path):
    info = make_sdr_info(duration=100)
    plan = plan_trim(info, 10, 40, make_caps(), make_opts(),
                     transcode=False, outdir=tmp_path)
    assert plan.mode == "trim-copy"
    assert plan.estimated_parts == 1
    cmd = plan.commands[0]
    assert "-ss" in cmd and cmd[cmd.index("-ss") + 1] == "10.000"
    assert "-t" in cmd


def test_plan_trim_to_end_omits_t(tmp_path):
    info = make_sdr_info(duration=100)
    plan = plan_trim(info, 90, None, make_caps(), make_opts(),
                     transcode=False, outdir=tmp_path)
    assert "-t" not in plan.commands[0]


def test_plan_trim_validation():
    info = make_sdr_info(duration=100)
    with pytest.raises(ValueError):
        plan_trim(info, -1, 10, make_caps(), make_opts(), transcode=False)
    with pytest.raises(ValueError):
        plan_trim(info, 200, None, make_caps(), make_opts(), transcode=False)
    with pytest.raises(ValueError):
        plan_trim(info, 30, 20, make_caps(), make_opts(), transcode=False)


def test_plan_trim_encode(tmp_path):
    info = make_sdr_info(duration=100)
    plan = plan_trim(info, 10, 40, make_caps(),
                     make_opts(encoder="software"), transcode=True, outdir=tmp_path)
    assert plan.mode == "trim-encode"
    assert plan.encode_plan is not None
