"""vclip —— 通用视频切分 / 重组工具。

把长视频切成多个小片段（按大小或按时长），或把切好的片段无损拼回一个视频。
底层调用 ffmpeg / ffprobe，本体零 Python 第三方依赖。

模块结构:
  runner       —— 统一定位 / 调用 ffmpeg / ffprobe
  probe        —— ffprobe 探测视频信息 (VideoInfo)
  capabilities —— 检测本机 ffmpeg 支持的编码器/滤镜（含跨平台硬件编码）
  encode       —— 根据 EncodeOptions 构建 ffmpeg 编码参数
  split        —— 按大小 / 按时长切分、裁剪子片段的核心逻辑
  merge        —— 无损重组（-c copy 拼接）
  verify       —— 逐帧像素级无损校验（合并 / 切分通用）
  cli          —— 命令行入口
"""

__version__ = "0.4.0"
