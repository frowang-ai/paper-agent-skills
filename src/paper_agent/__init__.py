"""Paper Agent shared runtime."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("paper-agent-skills")
except PackageNotFoundError:  # 源码目录直接运行(未安装)时的回退
    __version__ = "0.0.0+local"
