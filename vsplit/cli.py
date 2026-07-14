"""vsplit 命令行入口。

子命令:
  info       查看视频信息（分辨率/码率/HDR 等）
  duration   按时长切分（默认无损 -c copy，可 --transcode 转码）
  size       按目标大小切分（默认转码，可 --lossless 无损）
  moments    预设：切成多个 ≤30s、1080p、H.264 片段（发朋友圈）
  chat       预设：切成多个 ≤指定大小的 1080p H.264 片段（聊天发文件）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .capabilities import detect
from .encode import EncodeOptions
from .probe import ProbeError, format_size, probe
from .split import SplitPlan, execute, plan_duration, plan_size


def _add_encode_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("编码选项（转码时生效）")
    g.add_argument("--codec", choices=["h264", "hevc"], default="h264",
                   help="视频编码，默认 h264（微信兼容性最好）")
    g.add_argument("--encoder", choices=["auto", "hardware", "software"],
                   default="auto", help="编码器：auto 优先硬件(videotoolbox)，快")
    g.add_argument("--resolution", "-r", default=None,
                   help="目标分辨率：1080p/720p/4k 或 1920x1080，默认保持原分辨率")
    g.add_argument("--fps", type=float, default=None, help="目标帧率，默认保持")
    g.add_argument("--crf", type=int, default=None,
                   help="软件编码质量(18~28常用，越小越清晰)；指定后强制软件编码")
    g.add_argument("--bitrate", type=int, default=None,
                   help="目标视频码率 (kbps)")
    g.add_argument("--audio-bitrate", type=int, default=128,
                   help="音频码率 (kbps)，默认 128")
    g.add_argument("--audio-copy", action="store_true", help="直接复制音频流")
    g.add_argument("--hdr", choices=["auto", "sdr", "keep"], default="auto",
                   help="HDR 处理：auto/sdr(转SDR)/keep(保留HDR)")
    g.add_argument("--preset", default="medium",
                   help="x264/x265 的 -preset，默认 medium")


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("file", help="输入视频文件")
    p.add_argument("--outdir", "-o", default=None, help="输出目录")
    p.add_argument("--dry-run", action="store_true", help="只打印将执行的命令，不实际运行")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认直接执行")


def _opts_from_args(a: argparse.Namespace) -> EncodeOptions:
    return EncodeOptions(
        codec=a.codec,
        encoder=a.encoder,
        resolution=a.resolution,
        fps=a.fps,
        crf=a.crf,
        bitrate_kbps=a.bitrate,
        audio_bitrate_kbps=a.audio_bitrate,
        audio_copy=a.audio_copy,
        hdr=a.hdr,
        x26x_preset=a.preset,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vsplit",
        description="把长视频切成适合微信分享的多个小视频（可自定义质量/大小）",
    )
    parser.add_argument("--version", action="version", version=f"vsplit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="查看视频信息")
    p_info.add_argument("file", help="输入视频文件")

    p_dur = sub.add_parser("duration", help="按时长切分")
    _add_common(p_dur)
    p_dur.add_argument("--seconds", "-s", type=float, required=True,
                       help="每段时长（秒）")
    p_dur.add_argument("--transcode", action="store_true",
                       help="转码切分（默认无损 -c copy）")
    _add_encode_args(p_dur)

    p_size = sub.add_parser("size", help="按目标大小切分")
    _add_common(p_size)
    p_size.add_argument("--target-mb", "-m", type=float, required=True,
                        help="每段目标大小 (MB)")
    p_size.add_argument("--lossless", action="store_true",
                        help="无损按大小切分（-c copy，保留原画质/HDR）")
    _add_encode_args(p_size)

    p_mom = sub.add_parser("moments", help="预设：朋友圈 ≤30s 1080p H.264 片段")
    _add_common(p_mom)
    p_mom.add_argument("--seconds", "-s", type=float, default=30,
                       help="每段时长，默认 30 秒")
    _add_encode_args(p_mom)

    p_chat = sub.add_parser("chat", help="预设：聊天发文件，按大小切 1080p H.264")
    _add_common(p_chat)
    p_chat.add_argument("--target-mb", "-m", type=float, default=100,
                        help="每段目标大小 (MB)，默认 100")
    _add_encode_args(p_chat)

    return parser


def _confirm_and_run(plan: SplitPlan, *, dry_run: bool, yes: bool) -> int:
    print(plan.describe())
    for w in plan.warnings:
        print(f"  ⚠️  {w}")

    if not dry_run and not yes:
        try:
            ans = input("\n开始切分？[Y/n] ").strip().lower()
        except EOFError:
            ans = "y"
        if ans in {"n", "no"}:
            print("已取消。")
            return 1

    files = execute(plan, dry_run=dry_run)
    if dry_run:
        print("（dry-run，未实际执行）")
        return 0

    print(f"\n✅ 完成，共 {len(files)} 段：")
    total = 0
    for f in files:
        sz = f.stat().st_size
        total += sz
        print(f"  {f.name}  ({format_size(sz)})")
    print(f"  合计 {format_size(total)} -> {plan.output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "info":
            print(probe(args.file).human())
            return 0

        info = probe(args.file)
        caps = detect()

        if args.command == "duration":
            opts = _opts_from_args(args)
            plan = plan_duration(
                info, args.seconds, caps, opts,
                transcode=args.transcode, outdir=args.outdir,
            )
        elif args.command == "size":
            opts = _opts_from_args(args)
            plan = plan_size(
                info, args.target_mb, caps, opts,
                lossless=args.lossless, outdir=args.outdir,
            )
        elif args.command == "moments":
            if args.resolution is None:
                args.resolution = "1080p"
            if args.hdr == "auto":
                args.hdr = "sdr"  # 微信预设：优先兼容性
            opts = _opts_from_args(args)
            plan = plan_duration(
                info, args.seconds, caps, opts,
                transcode=True, outdir=args.outdir,
            )
        elif args.command == "chat":
            if args.resolution is None:
                args.resolution = "1080p"
            if args.hdr == "auto":
                args.hdr = "sdr"  # 微信预设：优先兼容性
            opts = _opts_from_args(args)
            plan = plan_size(
                info, args.target_mb, caps, opts,
                lossless=False, outdir=args.outdir,
            )
        else:  # pragma: no cover
            print(f"未知命令：{args.command}", file=sys.stderr)
            return 2

        return _confirm_and_run(plan, dry_run=args.dry_run, yes=args.yes)

    except (ProbeError, ValueError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("\n已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
