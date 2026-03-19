"""
弹性组件 - 三层重试洋葱

一次调用失败, 轮换重试。

架构:
    Profiles: [main-key, backup-key, emergency-key]
         |
    for each non-cooldown profile:          LAYER 1: Auth Rotation
         |
    create client(profile.api_key)
         |
    for compact_attempt in 0..2:            LAYER 2: Overflow Recovery
         |
    _run_attempt(client, model, ...)        LAYER 3: Tool-Use Loop
         |              |
       success       exception
         |              |
    mark_success    classify_failure()
    return result       |
                   overflow? --> compact, retry Layer 2
                   auth/rate? -> mark_failure, break to Layer 1
                   timeout?  --> mark_failure(60s), break to Layer 1
                        |
                   all profiles exhausted?
                        |
                   try fallback models

组件:
    - FailoverReason: 失败原因枚举 (rate_limit, auth, timeout, billing, overflow, unknown)
    - classify_failure: 将异常分类为 FailoverReason
    - AuthProfile: API key 及其冷却状态
    - ProfileManager: 冷却感知的 key 轮换
    - SimulatedFailure: 模拟失败工具 (用于测试)
    - ResilienceRunner: 三层重试洋葱
"""

from coder.resilience.failure import (
    FailoverReason,
    SimulatedFailure,
    classify_failure,
)
from coder.resilience.profile import (
    AuthProfile,
    ProfileManager,
)
from coder.resilience.runner import (
    BASE_RETRY,
    MAX_OVERFLOW_COMPACTION,
    PER_PROFILE,
    ResilienceRunner,
)


__all__ = [
    # Failure classification
    "FailoverReason",
    "classify_failure",
    "SimulatedFailure",
    # Profile management
    "AuthProfile",
    "ProfileManager",
    # Runner
    "ResilienceRunner",
    # Constants
    "BASE_RETRY",
    "PER_PROFILE",
    "MAX_OVERFLOW_COMPACTION",
]
