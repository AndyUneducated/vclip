# vsplit —— 微信视频切分工具

把长视频（尤其是 iPhone 17 Pro Max 录制的 **4K60 / HEVC / 杜比视界 HDR**）切成
适合微信分享的多个小视频，支持**自定义画质、分辨率、码率、目标大小**，并针对
微信的限制内置了预设。底层调用 `ffmpeg` / `ffprobe`，本体零 Python 第三方依赖。

## 微信相关限制（切分目标的由来）

| 场景 | 限制 | 建议做法 |
| --- | --- | --- |
| 朋友圈直接发视频 | 时长约 **≤30 秒**，会被压缩 | `moments` 预设：切 ≤30s、1080p、H.264 |
| 聊天里发「视频」 | 会被**大幅二次压缩**降质 | 先转 1080p H.264 再发，画质更可控 |
| 聊天里发「文件」 | 有单文件大小上限（近期约 200MB，随版本变化） | `size` / `chat` 预设：切到每段 ≤ 目标大小，原画质可选 |

> iPhone 的 4K60 是 HEVC + 杜比视界（PQ）HDR，码率约 400–500MB/分钟，且
> HEVC/HDR 在部分安卓机、微信里兼容性差、颜色发灰。发微信通常建议转成
> **1080p + H.264 + SDR**。

## 安装

```bash
# 1. 安装 ffmpeg（必须）
brew install ffmpeg

# 2. 安装本工具（可选，装完可直接用 vsplit 命令）
cd wechat-video-splitter
pip install -e .
```

不安装也可以直接用模块方式运行：

```bash
python3 -m vsplit <子命令> ...
```

## 快速开始

```bash
# 查看视频信息（分辨率/码率/是否 HDR）
vsplit info movie.mov

# 朋友圈：切成多个 ≤30s、1080p、H.264 片段
vsplit moments movie.mov

# 聊天发文件：切成每段 ≤100MB 的 1080p H.264 片段
vsplit chat movie.mov -m 100

# 无损按时长切（不重编码，保留 4K/HDR，极快）
vsplit duration movie.mov -s 60

# 无损按大小切（每段约 ≤190MB，保留原画质）
vsplit size movie.mov -m 190 --lossless

# 自定义：切成 720p、码率 4Mbps、每段 20 秒
vsplit duration movie.mov -s 20 --transcode -r 720p --bitrate 4000

# 自定义画质：用 CRF 20 软件编码（越小越清晰）
vsplit duration movie.mov -s 30 --transcode --crf 20
```

所有会写文件的命令，执行前都会打印计划并让你确认；加 `--dry-run` 只看命令不执行，
加 `-y` 跳过确认。

## 子命令

| 命令 | 作用 | 默认行为 |
| --- | --- | --- |
| `info` | 查看视频信息 | — |
| `duration` | 按时长切分 | **无损** `-c copy`；加 `--transcode` 转码 |
| `size` | 按目标大小切分 | **转码**（大小可控）；加 `--lossless` 无损 |
| `moments` | 朋友圈预设 | 转码：≤30s、1080p、H.264、SDR |
| `chat` | 聊天发文件预设 | 转码：每段 ≤100MB、1080p、H.264、SDR |

### 常用编码选项（转码时生效）

| 选项 | 说明 |
| --- | --- |
| `-r, --resolution` | `1080p` / `720p` / `4k` / `1920x1080`，默认保持（只缩小不放大） |
| `--codec` | `h264`（默认，兼容最好）/ `hevc` |
| `--encoder` | `auto`（默认，优先硬件 videotoolbox，快）/ `hardware` / `software` |
| `--bitrate` | 目标视频码率（kbps） |
| `--crf` | 软件编码质量（18–28 常用，越小越清晰；指定后强制软件编码） |
| `--fps` | 目标帧率（如把 60fps 降到 30fps 省体积） |
| `--hdr` | `auto` / `sdr`（转 SDR）/ `keep`（保留 HDR） |
| `--audio-bitrate` / `--audio-copy` | 音频码率 / 直接复制音频 |
| `-o, --outdir` | 输出目录（默认在源文件旁 `<名字>_clips/`） |

## 无损 vs 转码，怎么选

- **无损（`-c copy`）**：不重编码，秒级完成，画质/HDR 完全保留。
  代价是切点只能落在关键帧上，**单段实际时长/大小会有波动**，且文件仍然很大。
- **转码**：逐段用 `-ss/-t` 精确编码，段数/时长/大小可预测，可降分辨率/码率大幅缩小体积，
  兼容性更好。代价是需要编码时间、有画质损失。

## HDR 处理说明（重要）

- `--hdr keep`：保留 HDR，会自动改用 **HEVC 10-bit**，并写入 HDR10 元数据
  （`bt2020` / `smpte2084`）。此模式默认用**软件 x265**，因为硬件
  videotoolbox 常常不写入 transfer/primaries 标签，导致输出不被识别为 HDR。
  杜比视界的**动态元数据无法保留**（ffmpeg 限制），会退化为 HDR10 静态元数据。
- `--hdr sdr`：把 HDR 转成 SDR（bt709），适合微信。**高质量 tone-mapping 需要
  ffmpeg 带 `zscale`(libzimg) 或 `libplacebo`**；若缺失，会退化为粗略转换（高光/
  颜色可能不准），运行时会有明确警告。检查是否具备：

```bash
ffmpeg -filters | grep -E 'zscale|libplacebo'
```

  若为空且你需要高质量 SDR，请安装带 libzimg 的 ffmpeg 版本。
- `--hdr auto`（默认）：能高质量 tone-map 就转 SDR，否则保留 HDR 以免毁色彩。
  `moments` / `chat` 两个微信预设为了兼容性，默认按 `sdr` 处理。

## 目录结构

```
wechat-video-splitter/
├── pyproject.toml
├── requirements.txt
├── README.md
└── vsplit/
    ├── __init__.py
    ├── __main__.py      # python -m vsplit 入口
    ├── cli.py           # 命令行与子命令
    ├── probe.py         # ffprobe 探测视频信息
    ├── capabilities.py  # 检测 ffmpeg 支持的编码器/滤镜
    ├── encode.py        # 构建编码/滤镜参数
    └── split.py         # 切分核心逻辑
```

## 许可证

MIT
