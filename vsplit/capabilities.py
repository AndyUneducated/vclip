"""检测本机 ffmpeg 支持哪些编码器 / 滤镜。

不同的 ffmpeg 编译版本能力差异很大（尤其是 HDR->SDR 需要的 zscale /
libplacebo），所以运行时探测一次并缓存，据此选择安全的默认行为。
"""
from __future__ import annotations

import functools
import shutil
import subprocess
from dataclasses import dataclass


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("找不到 `ffmpeg`，请先安装：brew install ffmpeg")
    return path


def _run(args: list[str]) -> str:
    return subprocess.run(
        args, capture_output=True, text=True, check=False
    ).stdout


@dataclass(frozen=True)
class Capabilities:
    libx264: bool
    libx265: bool
    vt_h264: bool          # h264_videotoolbox (Apple 硬件编码)
    vt_hevc: bool          # hevc_videotoolbox
    zscale: bool
    libplacebo: bool
    tonemap: bool
    colorspace: bool

    @property
    def has_hardware(self) -> bool:
        return self.vt_h264 or self.vt_hevc

    @property
    def can_tonemap_hdr(self) -> bool:
        """是否具备高质量 HDR->SDR 色调映射能力。"""
        return self.libplacebo or (self.zscale and self.tonemap)


@functools.lru_cache(maxsize=1)
def detect() -> Capabilities:
    ffmpeg = _require_ffmpeg()
    encoders = _run([ffmpeg, "-hide_banner", "-encoders"])
    filters = _run([ffmpeg, "-hide_banner", "-filters"])

    def enc(name: str) -> bool:
        return name in encoders

    def flt(name: str) -> bool:
        return name in filters

    return Capabilities(
        libx264=enc("libx264"),
        libx265=enc("libx265"),
        vt_h264=enc("h264_videotoolbox"),
        vt_hevc=enc("hevc_videotoolbox"),
        zscale=flt("zscale"),
        libplacebo=flt("libplacebo"),
        tonemap=flt("tonemap"),
        colorspace=flt("colorspace"),
    )
