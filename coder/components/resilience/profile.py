"""
配置管理 - API key 轮换和冷却追踪

AuthProfile 表示一个可轮换使用的 API key。
ProfileManager 管理配置池, 支持冷却感知的选择。
"""

import time
from dataclasses import dataclass
from typing import Any

from coder.components.resilience.failure import FailoverReason


@dataclass
class AuthProfile:
    """
    表示一个可轮换使用的 API key。

    Attributes:
        name: 可读标签
        provider: LLM 提供商 (如 "anthropic")
        api_key: 实际的 API key 字符串
        cooldown_until: unix 时间戳; 在此之前跳过该配置
        failure_reason: 上次失败原因字符串, 健康时为 None
        last_good_at: 上次成功调用的 unix 时间戳
    """

    name: str
    provider: str
    api_key: str
    cooldown_until: float = 0.0
    failure_reason: str | None = None
    last_good_at: float = 0.0


class ProfileManager:
    """
    管理 AuthProfile 池, 支持冷却感知的选择。

    按顺序检查配置。当冷却过期时配置可用。
    失败后配置进入冷却; 成功后清除失败状态。
    """

    def __init__(self, profiles: list[AuthProfile]) -> None:
        """
        初始化 ProfileManager。

        Args:
            profiles: 配置列表
        """
        self.profiles = profiles

    def select_profile(self) -> AuthProfile | None:
        """
        返回第一个冷却已过期的配置。

        按顺序检查配置。当 time.time() >= cooldown_until 时可用。
        所有配置都在冷却中则返回 None。

        Returns:
            AuthProfile | None: 可用的配置, 或 None
        """
        now = time.time()
        for profile in self.profiles:
            if now >= profile.cooldown_until:
                return profile
        return None

    def select_all_available(self) -> list[AuthProfile]:
        """
        按顺序返回所有未冷却的配置。

        Returns:
            list[AuthProfile]: 可用的配置列表
        """
        now = time.time()
        return [p for p in self.profiles if now >= p.cooldown_until]

    def mark_failure(
        self,
        profile: AuthProfile,
        reason: FailoverReason,
        cooldown_seconds: float = 300.0,
    ) -> None:
        """
        在失败后将配置置入冷却。

        默认冷却 5 分钟。超时失败使用更短的冷却
        (调用方传入 cooldown_seconds=60)。

        Args:
            profile: 要标记的配置
            reason: 失败原因
            cooldown_seconds: 冷却时长 (秒)
        """
        from coder.components.cli import print_resilience

        profile.cooldown_until = time.time() + cooldown_seconds
        profile.failure_reason = reason.value
        print_resilience(f"Profile '{profile.name}' -> cooldown {cooldown_seconds:.0f}s (reason: {reason.value})")

    def mark_success(self, profile: AuthProfile) -> None:
        """
        清除失败状态并记录上次成功时间。

        Args:
            profile: 要标记的配置
        """
        profile.failure_reason = None
        profile.last_good_at = time.time()

    def list_profiles(self) -> list[dict[str, Any]]:
        """
        返回所有配置的状态用于展示。

        Returns:
            list[dict]: 配置状态列表
        """
        result = []
        now = time.time()
        for p in self.profiles:
            remaining = max(0, p.cooldown_until - now)
            status = "available" if remaining == 0 else f"cooldown ({remaining:.0f}s)"
            result.append(
                {
                    "name": p.name,
                    "provider": p.provider,
                    "status": status,
                    "failure_reason": p.failure_reason,
                    "last_good": (
                        time.strftime("%H:%M:%S", time.localtime(p.last_good_at)) if p.last_good_at > 0 else "never"
                    ),
                }
            )
        return result

    def reset_rate_limit_cooldowns(self) -> int:
        """
        重置所有 rate_limit 和 timeout 相关的冷却。

        用于 fallback 模型尝试时。

        Returns:
            int: 重置的配置数量
        """
        count = 0
        for p in self.profiles:
            if p.failure_reason in (
                FailoverReason.rate_limit.value,
                FailoverReason.timeout.value,
            ):
                p.cooldown_until = 0.0
                count += 1
        return count


__all__ = [
    "AuthProfile",
    "ProfileManager",
]
