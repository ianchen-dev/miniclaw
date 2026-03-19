from pathlib import Path

from coder.settings import settings


# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent

# 项目源码目录
SRC_DIR = Path(__file__).parent.parent

# 日志目录
LOG_FOLDER = ROOT_DIR / "logs"

# 工作区目录
WORKSPACE_DIR = ROOT_DIR / settings.workspace_dir

# 记忆存储目录
MEMORY_DIR = WORKSPACE_DIR / "memory" / "daily"

# 长期记忆文件
EVERGREEN_MEMORY_PATH = WORKSPACE_DIR / "MEMORY.md"
