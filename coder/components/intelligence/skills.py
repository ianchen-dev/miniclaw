"""
技能发现与注入

一个技能 = 一个包含 SKILL.md (带 frontmatter) 的目录。
按优先级顺序扫描; 同名技能会被后发现的覆盖。

技能目录扫描顺序:
    1. extra_dirs (自定义目录)
    2. workspace/skills (内置技能)
    3. workspace/.skills (托管技能)
    4. workspace/.agents/skills (个人 agent 技能)
    5. cwd/.agents/skills (项目 agent 技能)
    6. cwd/skills (工作区技能)
"""

from pathlib import Path
from typing import Dict, List, Optional

from coder.settings import settings


class SkillsManager:
    """
    技能管理器

    扫描多个目录查找带 YAML frontmatter 的 SKILL.md 文件。

    用法:
        mgr = SkillsManager()
        mgr.discover()
        skills_block = mgr.format_prompt_block()
    """

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        """
        初始化技能管理器

        Args:
            workspace_dir: 工作区目录, 默认从配置读取
        """
        if workspace_dir is None:
            self.workspace_dir = Path(settings.workspace_dir)
        else:
            self.workspace_dir = workspace_dir

        self.skills: List[Dict[str, str]] = []

        # 从配置读取限制
        self.max_skills = settings.max_skills
        self.max_skills_prompt = settings.max_skills_prompt

    def _parse_frontmatter(self, text: str) -> Dict[str, str]:
        """
        解析简单的 YAML frontmatter

        不依赖 pyyaml, 只解析简单的 key: value 格式。

        Args:
            text: 文件内容

        Returns:
            解析出的元数据字典
        """
        meta: Dict[str, str] = {}
        if not text.startswith("---"):
            return meta

        parts = text.split("---", 2)
        if len(parts) < 3:
            return meta

        for line in parts[1].strip().splitlines():
            if ":" not in line:
                continue
            key, _, value = line.strip().partition(":")
            meta[key.strip()] = value.strip()

        return meta

    def _scan_dir(self, base: Path) -> List[Dict[str, str]]:
        """
        扫描单个目录下的技能

        Args:
            base: 要扫描的目录

        Returns:
            发现的技能列表
        """
        found: List[Dict[str, str]] = []
        if not base.is_dir():
            return found

        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue

            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue

            meta = self._parse_frontmatter(content)
            if not meta.get("name"):
                continue

            # 提取 body (frontmatter 之后的内容)
            body = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()

            found.append(
                {
                    "name": meta.get("name", ""),
                    "description": meta.get("description", ""),
                    "invocation": meta.get("invocation", ""),
                    "body": body,
                    "path": str(child),
                }
            )

        return found

    def discover(self, extra_dirs: Optional[List[Path]] = None) -> None:
        """
        按优先级扫描技能目录

        同名技能后者覆盖前者。

        Args:
            extra_dirs: 额外的扫描目录列表
        """
        scan_order: List[Path] = []

        # 添加额外目录
        if extra_dirs:
            scan_order.extend(extra_dirs)

        # 添加标准扫描目录
        scan_order.append(self.workspace_dir / "skills")  # 内置技能
        scan_order.append(self.workspace_dir / ".skills")  # 托管技能
        scan_order.append(self.workspace_dir / ".agents" / "skills")  # 个人 agent 技能
        scan_order.append(Path.cwd() / ".agents" / "skills")  # 项目 agent 技能
        scan_order.append(Path.cwd() / "skills")  # 工作区技能

        # 使用字典去重 (后者覆盖前者)
        seen: Dict[str, Dict[str, str]] = {}
        for d in scan_order:
            for skill in self._scan_dir(d):
                seen[skill["name"]] = skill

        # 限制数量
        self.skills = list(seen.values())[: self.max_skills]

    def format_prompt_block(self) -> str:
        """
        将技能格式化为提示词块

        Returns:
            格式化后的技能块字符串
        """
        if not self.skills:
            return ""

        lines = ["## Available Skills", ""]
        total = 0

        for skill in self.skills:
            block = (
                f"### Skill: {skill['name']}\n"
                f"Description: {skill['description']}\n"
                f"Invocation: {skill['invocation']}\n"
            )
            if skill.get("body"):
                block += f"\n{skill['body']}\n"
            block += "\n"

            # 检查长度限制
            if total + len(block) > self.max_skills_prompt:
                lines.append("(... more skills truncated)")
                break

            lines.append(block)
            total += len(block)

        return "\n".join(lines)

    def get_skill_names(self) -> List[str]:
        """
        获取所有技能名称列表

        Returns:
            技能名称列表
        """
        return [s["name"] for s in self.skills]

    def get_skill_by_name(self, name: str) -> Optional[Dict[str, str]]:
        """
        按名称获取技能

        Args:
            name: 技能名称

        Returns:
            技能字典, 如果未找到则返回 None
        """
        for skill in self.skills:
            if skill["name"] == name:
                return skill
        return None


__all__ = [
    "SkillsManager",
]
