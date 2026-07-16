from vclip.verify import StreamCheck, VerifyReport, compare_sequences


def test_compare_identical():
    ok, first = compare_sequences(["a", "b", "c"], ["a", "b", "c"])
    assert ok is True
    assert first is None


def test_compare_length_mismatch_prefix_matches():
    ok, first = compare_sequences(["a", "b", "c"], ["a", "b"])
    assert ok is False
    assert first is None  # 前缀一致，仅长度不同


def test_compare_pixel_mismatch_index():
    ok, first = compare_sequences(["a", "b", "c", "d"], ["a", "b", "X", "d"])
    assert ok is False
    assert first == 2


def test_compare_empty():
    ok, first = compare_sequences([], [])
    assert ok is True
    assert first is None


def _video_check(ok, expected, actual, first=None):
    return StreamCheck("视频", "逐帧像素", ok, expected, actual, first)


def test_report_ok_when_all_checks_ok():
    r = VerifyReport(checks=[
        _video_check(True, 600, 600),
        StreamCheck("音频#0", "包计数", True, 518, 518),
    ])
    assert r.ok is True
    assert "通过" in r.human()
    assert "600 帧" in r.human()


def test_report_fails_if_any_check_fails():
    r = VerifyReport(
        checks=[
            _video_check(False, 600, 594, first=237),
            StreamCheck("音频#0", "包计数", True, 518, 518),
        ],
        part_frame_counts=[237, 189, 168],
    )
    assert r.ok is False
    h = r.human()
    assert "未通过" in h
    assert "594" in h and "237" in h
    assert "--transcode" in h


def test_report_audio_packet_mismatch_fails():
    r = VerifyReport(checks=[
        _video_check(True, 600, 600),
        StreamCheck("音频#0", "包计数", False, 518, 500),
    ])
    assert r.ok is False
    assert "包数不一致" in r.human()


def test_report_empty_checks_not_ok():
    assert VerifyReport(checks=[]).ok is False
