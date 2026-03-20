"""
Bootstrap 文件加载器

在 agent 启动时加载工作区的 Bootstrap 文件。
不同加载模式 (full/minimal/none) 适用于不同场景:
    - full = 主 agent
    - minimal = 子 agent / cron
    - none = 最小化

Bootstrap 文件定义 agent 的基础配置和行为指南。
"""

from pathlib import Path
from typing import Dict, Optional

from coder.settings import settings

# Bootstrap 文件名 -- 每个 agent 启动时加载这 8 个文件
BOOTSTRAP_FILES = [
    "SOUL.md",
    "IDENTITY.md",
    "TOOLS.md",
    "USER.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "AGENTS.md",
    "MEMORY.md",
]


class BootstrapLoader:
    """
    Bootstrap 文件加载器

    从工作区加载 markdown 文件, 支持截断和总量上限。

    用法:
        loader = BootstrapLoader()
        bootstrap = loader.load_all(mode="full")
        soul = bootstrap.get("SOUL.md", "")
    """

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        """
        初始化 Bootstrap 加载器

        Args:
            workspace_dir: 工作区目录, 默认从配置读取
        """
        self.workspace_dir = Path(workspace_dir or settings.workspace_dir)
        self.max_file_chars = settings.max_file_chars
        self.max_total_chars = settings.max_total_chars

    def load_file(self, name: str) -> str:
        """
        加载单个文件

        Args:
            name: 文件名

        Returns:
            文件内容, 如果文件不存在或读取失败则返回空字符串
        """
        path = self.workspace_dir / name
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def truncate_file(self, content: str, max_chars: Optional[int] = None) -> str:
        """
        截断超长文件内容

        仅保留头部, 在行边界处截断。

        Args:
            content: 原始内容
            max_chars: 最大字符数, 默认使用配置值

        Returns:
            截断后的内容
        """
        if max_chars is None:
            max_chars = self.max_file_chars

        if len(content) <= max_chars:
            return content

        # 在行边界处截断
        cut = content.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars

        return content[:cut] + f"\n\n[... truncated ({len(content)} chars total, showing first {cut}) ...]"

    def load_all(self, mode: str = "full") -> Dict[str, str]:
        """
        加载所有 Bootstrap 文件

        Args:
            mode: 加载模式
                - "full": 加载所有 8 个文件
                - "minimal": 只加载 AGENTS.md 和 TOOLS.md
                - "none": 不加载任何文件

        Returns:
            文件名到内容的映射
        """
        if mode == "none":
            return {}

        names = ["AGENTS.md", "TOOLS.md"] if mode == "minimal" else list(BOOTSTRAP_FILES)

        result: Dict[str, str] = {}
        total = 0

        for name in names:
            raw = self.load_file(name)
            if not raw:
                continue

            truncated = self.truncate_file(raw)

            # 检查总量上限
            remaining = self.max_total_chars - total
            if remaining <= 0:
                break
            if len(truncated) > remaining:
                truncated = self.truncate_file(raw, remaining)

            result[name] = truncated
            total += len(truncated)

        return result


__all__ = [
    "BOOTSTRAP_FILES",
    "BootstrapLoader",
]
