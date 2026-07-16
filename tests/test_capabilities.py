from conftest import make_caps


def test_hw_encoder_prefers_videotoolbox():
    caps = make_caps(vt_h264=True, nvenc_h264=True)
    assert caps.hw_encoder("h264") == "h264_videotoolbox"


def test_hw_encoder_nvenc_when_no_apple():
    caps = make_caps(nvenc_hevc=True)
    assert caps.hw_encoder("hevc") == "hevc_nvenc"


def test_hw_encoder_qsv_then_amf_order():
    caps = make_caps(qsv_h264=True, amf_h264=True)
    assert caps.hw_encoder("h264") == "h264_qsv"
    caps2 = make_caps(amf_h264=True)
    assert caps2.hw_encoder("h264") == "h264_amf"


def test_hw_encoder_none_when_only_vaapi():
    # vaapi 需要显式设备，不参与自动选择
    caps = make_caps(vaapi_h264=True, vaapi_hevc=True)
    assert caps.hw_encoder("h264") is None
    assert caps.hw_encoder("hevc") is None


def test_has_hardware():
    assert make_caps().has_hardware is False
    assert make_caps(nvenc_h264=True).has_hardware is True


def test_can_tonemap_hdr():
    assert make_caps(zscale=True, tonemap=True).can_tonemap_hdr is True
    assert make_caps(zscale=False, tonemap=True, libplacebo=False).can_tonemap_hdr is False
    assert make_caps(zscale=False, tonemap=False, libplacebo=True).can_tonemap_hdr is True
