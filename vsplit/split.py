"""切分核心逻辑：按时长切、按大小切（无损或转码）。

- 无损(copy)：用 ffmpeg segment 复用器一次切好；切点只能落在关键帧上，
  单段时长/大小会有波动（这是 -c copy 的固有限制）。
- 转码(encode)：逐段用 -ss/-t 精确编码，段数/时长可预测，且对任意编码器都可靠。
"""
from __future__ import annotations

import math
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .capabilities import Capabilities
from .encode import EncodeOptions, EncodePlan, build_plan
from .probe import VideoInfo, format_duration, format_size


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("找不到 `ffmpeg`，请先安装：brew install ffmpeg")
    return path


@dataclass
class SplitPlan:
    """一次切分任务的完整描述（可在真正执行前打印确认）。"""
    mode: str                       # duration-copy | duration-encode | size-copy | size-encode
    segment_seconds: float
    estimated_parts: int
    estimated_part_size: int        # bytes
    commands: list[list[str]]       # 需要执行的一条或多条 ffmpeg 命令
    output_dir: Path
    output_files: list[Path] | None  # 转码模式：明确的输出文件；copy 模式为 None
    output_glob: str                 # copy 模式：执行后用于收集文件的 glob
    encode_plan: EncodePlan | None
    warnings: list[str] = field(default_factory=list)

    def describe(self) -> str:
        lines = [
            f"  切分模式  : {self.mode}",
            f"  每段时长  : {format_duration(self.segment_seconds)}",
            f"  预计段数  : {self.estimated_parts} 段",
            f"  单段大小  : ~{format_size(self.estimated_part_size)}",
            f"  输出目录  : {self.output_dir}",
        ]
        if self.encode_plan:
            lines.append(f"  编码器    : {self.encode_plan.encoder_name}")
            lines.append(f"  HDR 处理  : {self.encode_plan.hdr_mode}")
            if self.encode_plan.vf:
                lines.append(f"  滤镜      : {self.encode_plan.vf}")
        return "\n".join(lines)


def _output_dir(info: VideoInfo, outdir: str | Path | None) -> Path:
    if outdir:
        return Path(outdir)
    return info.path.parent / f"{info.path.stem}_clips"


def _part_path(info: VideoInfo, out_dir: Path, idx: int, ext: str) -> Path:
    return out_dir / f"{info.path.stem}_part{idx:03d}{ext}"


def _pattern(info: VideoInfo, out_dir: Path, ext: str) -> Path:
    return out_dir / f"{info.path.stem}_part%03d{ext}"


def _copy_cmd(info: VideoInfo, seconds: float, pattern: Path) -> list[str]:
    return [
        _ffmpeg(), "-y", "-hide_banner", "-i", str(info.path),
        "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy",
        "-f", "segment",
        "-segment_time", f"{seconds:.3f}",
        "-reset_timestamps", "1",
        "-segment_start_number", "1",
        str(pattern),
    ]


def _encode_seg_cmd(
    info: VideoInfo, plan: EncodePlan, start: float, dur: float, outfile: Path
) -> list[str]:
    cmd = [
        _ffmpeg(), "-y", "-hide_banner",
        "-ss", f"{start:.3f}", "-i", str(info.path), "-t", f"{dur:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?",
    ]
    if plan.vf:
        cmd += ["-vf", plan.vf]
    cmd += plan.video_args + plan.audio_args
    cmd += ["-movflags", "+faststart", str(outfile)]
    return cmd


def _encode_commands(
    info: VideoInfo, plan: EncodePlan, seconds: float, out_dir: Path
) -> tuple[list[list[str]], list[Path]]:
    n = max(1, math.ceil(info.duration / seconds))
    cmds: list[list[str]] = []
    files: list[Path] = []
    for i in range(n):
        start = i * seconds
        dur = min(seconds, info.duration - start)
        if dur <= 0:
            break
        out = _part_path(info, out_dir, i + 1, plan.output_ext)
        cmds.append(_encode_seg_cmd(info, plan, start, dur, out))
        files.append(out)
    return cmds, files


def plan_duration(
    info: VideoInfo,
    seconds: float,
    caps: Capabilities,
    opts: EncodeOptions,
    *,
    transcode: bool,
    outdir: str | Path | None = None,
) -> SplitPlan:
    if seconds <= 0:
        raise ValueError("每段时长必须大于 0")
    out_dir = _output_dir(info, outdir)
    est_parts = max(1, math.ceil(info.duration / seconds))

    if not transcode:
        pattern = _pattern(info, out_dir, ".mp4")
        est_size = int(info.overall_bitrate_bps * seconds / 8)
        return SplitPlan(
            mode="duration-copy",
            segment_seconds=seconds,
            estimated_parts=est_parts,
            estimated_part_size=est_size,
            commands=[_copy_cmd(info, seconds, pattern)],
            output_dir=out_dir,
            output_files=None,
            output_glob=f"{info.path.stem}_part*.mp4",
            encode_plan=None,
            warnings=[
                "无损切分：切点只能落在关键帧上，单段实际时长会略有出入。"
            ],
        )

    plan = build_plan(info, opts, caps)
    cmds, files = _encode_commands(info, plan, seconds, out_dir)
    total_kbps = plan.total_bitrate_kbps or info.overall_bitrate_bps // 1000
    est_size = int(total_kbps * 1000 * seconds / 8)
    return SplitPlan(
        mode="duration-encode",
        segment_seconds=seconds,
        estimated_parts=len(files),
        estimated_part_size=est_size,
        commands=cmds,
        output_dir=out_dir,
        output_files=files,
        output_glob=f"{info.path.stem}_part*{plan.output_ext}",
        encode_plan=plan,
        warnings=plan.warnings,
    )


def plan_size(
    info: VideoInfo,
    target_mb: float,
    caps: Capabilities,
    opts: EncodeOptions,
    *,
    lossless: bool,
    safety: float = 0.95,
    outdir: str | Path | None = None,
) -> SplitPlan:
    out_dir = _output_dir(info, outdir)
    target_bytes = int(target_mb * 1024 * 1024)
    if target_bytes <= 0:
        raise ValueError("目标大小必须大于 0")

    if lossless:
        bps = info.overall_bitrate_bps
        if bps <= 0:
            raise ValueError("无法估算源码率，无法按大小无损切分")
        seconds = target_bytes * 8 / bps * safety
        pattern = _pattern(info, out_dir, ".mp4")
        est_parts = max(1, math.ceil(info.duration / seconds))
        est_size = int(bps * seconds / 8)
        return SplitPlan(
            mode="size-copy",
            segment_seconds=seconds,
            estimated_parts=est_parts,
            estimated_part_size=est_size,
            commands=[_copy_cmd(info, seconds, pattern)],
            output_dir=out_dir,
            output_files=None,
            output_glob=f"{info.path.stem}_part*.mp4",
            encode_plan=None,
            warnings=[
                "无损按大小切分：切点受关键帧限制，单段大小会有波动（已留余量）。"
            ],
        )

    plan = build_plan(info, opts, caps, force_bitrate=True)
    total_kbps = plan.total_bitrate_kbps
    if not total_kbps:
        raise RuntimeError("无法确定目标码率")
    seconds = target_bytes * 8 / (total_kbps * 1000) * safety
    cmds, files = _encode_commands(info, plan, seconds, out_dir)
    est_size = int(total_kbps * 1000 * seconds / 8)
    return SplitPlan(
        mode="size-encode",
        segment_seconds=seconds,
        estimated_parts=len(files),
        estimated_part_size=est_size,
        commands=cmds,
        output_dir=out_dir,
        output_files=files,
        output_glob=f"{info.path.stem}_part*{plan.output_ext}",
        encode_plan=plan,
        warnings=plan.warnings,
    )


def execute(plan: SplitPlan, *, dry_run: bool = False) -> list[Path]:
    """执行切分。返回生成的文件列表。"""
    multi = len(plan.commands) > 1
    for i, cmd in enumerate(plan.commands, 1):
        prefix = f"[{i}/{len(plan.commands)}] " if multi else ""
        print(f"\n{prefix}$ " + " ".join(shlex.quote(c) for c in cmd))
    print()
    if dry_run:
        return []

    plan.output_dir.mkdir(parents=True, exist_ok=True)
    for i, cmd in enumerate(plan.commands, 1):
        if len(plan.commands) > 1:
            print(f"\n── 第 {i}/{len(plan.commands)} 段 ──")
        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 执行失败 (exit={proc.returncode})")

    if plan.output_files is not None:
        return [f for f in plan.output_files if f.exists()]
    return sorted(plan.output_dir.glob(plan.output_glob))
