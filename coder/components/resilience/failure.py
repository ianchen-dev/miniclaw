"""
失败分类 - 将 API 调用失败原因进行分类

每种原因对应不同的重试策略:
    - overflow   -> 压缩消息后用相同配置重试
    - auth       -> 跳过此配置, 尝试下一个
    - rate_limit -> 带冷却跳过此配置, 尝试下一个
    - timeout    -> 短冷却后尝试下一个配置
    - billing    -> 跳过此配置, 尝试下一个
    - unknown    -> 跳过此配置, 尝试下一个
"""

from enum import Enum


class FailoverReason(Enum):
    """
    API 调用失败原因分类。

    每种原因对应不同的重试策略和冷却时长。
    """

    rate_limit = "rate_limit"
    auth = "auth"
    timeout = "timeout"
    billing = "billing"
    overflow = "overflow"
    unknown = "unknown"


def classify_failure(exc: Exception) -> FailoverReason:
    """
    检查异常字符串以确定失败类别。

    分类驱动重试行为:
        - overflow   -> 压缩消息后用相同配置重试
        - auth       -> 跳过此配置, 尝试下一个
        - rate_limit -> 带冷却跳过此配置, 尝试下一个
        - timeout    -> 短冷却后尝试下一个配置
        - billing    -> 跳过此配置, 尝试下一个
        - unknown    -> 跳过此配置, 尝试下一个

    Args:
        exc: 捕获的异常

    Returns:
        FailoverReason: 失败原因枚举值
    """
    msg = str(exc).lower()

    if "rate" in msg or "429" in msg:
        return FailoverReason.rate_limit
    if "auth" in msg or "401" in msg or "key" in msg:
        return FailoverReason.auth
    if "timeout" in msg or "timed out" in msg:
        return FailoverReason.timeout
    if "billing" in msg or "quota" in msg or "402" in msg:
        return FailoverReason.billing
    if "context" in msg or "token" in msg or "overflow" in msg:
        return FailoverReason.overflow

    return FailoverReason.unknown


class SimulatedFailure:
    """
    持有一个待触发的模拟失败, 在下次 API 调用时触发。

    用于测试三层重试洋葱的各类失败处理。
    """

    TEMPLATES: dict[str, str] = {
        "rate_limit": "Error code: 429 -- rate limit exceeded",
        "auth": "Error code: 401 -- authentication failed, invalid API key",
        "timeout": "Request timed out after 30s",
        "billing": "Error code: 402 -- billing quota exceeded",
        "overflow": "Error: context window token overflow, too many tokens",
        "unknown": "Error: unexpected internal server error",
    }

    def __init__(self) -> None:
        """初始化模拟失败器。"""
        self._pending: str | None = None

    def arm(self, reason: str) -> str:
        """
        为下次 API 调用装备一个失败。

        Args:
            reason: 失败原因 (rate_limit, auth, timeout, billing, overflow, unknown)

        Returns:
            确认消息
        """
        if reason not in self.TEMPLATES:
            return f"Unknown reason '{reason}'. Valid: {', '.join(self.TEMPLATES.keys())}"
        self._pending = reason
        return f"Armed: next API call will fail with '{reason}'"

    def check_and_fire(self) -> None:
        """
        如果已装备, 抛出模拟错误并解除装备。

        Raises:
            RuntimeError: 模拟的错误
        """
        if self._pending is not None:
            reason = self._pending
            self._pending = None
            raise RuntimeError(self.TEMPLATES[reason])

    @property
    def is_armed(self) -> bool:
        """返回是否已装备模拟失败。"""
        return self._pending is not None

    @property
    def pending_reason(self) -> str | None:
        """返回待触发的失败原因。"""
        return self._pending


__all__ = [
    "FailoverReason",
    "classify_failure",
    "SimulatedFailure",
]
