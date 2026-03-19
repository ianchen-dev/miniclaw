"""
智能层组件 - 系统提示词组装与记忆管理

提供 8 层提示词组装、技能发现、记忆存储和搜索功能。

核心组件:
    - BootstrapLoader: 加载工作区的 Bootstrap 文件
    - SkillsManager: 发现和解析技能
    - MemoryStore: 记忆存储和 TF-IDF + MMR 搜索
    - build_system_prompt: 8 层提示词组装

用法:
    from coder.intelligence import (
        BootstrapLoader,
        SkillsManager,
        MemoryStore,
        build_system_prompt,
        auto_recall,
    )

    # 加载引导文件
    loader = BootstrapLoader()
    bootstrap = loader.load_all(mode="full")

    # 发现技能
    skills_mgr = SkillsManager()
    skills_mgr.discover()
    skills_block = skills_mgr.format_prompt_block()

    # 记忆搜索
    memory_store = MemoryStore()
    results = memory_store.hybrid_search("python")

    # 组装系统提示词
    prompt = build_system_prompt(
        mode="full",
        bootstrap=bootstrap,
        skills_block=skills_block,
        memory_context="...",
    )
"""

from coder.intelligence.bootstrap import BOOTSTRAP_FILES, BootstrapLoader
from coder.intelligence.memory import MemoryStore
from coder.intelligence.prompt_builder import auto_recall, build_system_prompt
from coder.intelligence.skills import SkillsManager


__all__ = [
    "BootstrapLoader",
    "BOOTSTRAP_FILES",
    "SkillsManager",
    "MemoryStore",
    "build_system_prompt",
    "auto_recall",
]
