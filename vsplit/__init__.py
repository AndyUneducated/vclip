"""vsplit —— 把长视频切成适合微信分享的多个小视频。

模块结构:
  probe        —— ffprobe 探测视频信息 (VideoInfo)
  capabilities —— 检测本机 ffmpeg 支持的编码器/滤镜
  encode       —— 根据 EncodeOptions 构建 ffmpeg 编码参数
  split        —— 按时长 / 按大小切分的核心逻辑
  cli          —— 命令行入口
"""

__version__ = "0.1.0"
