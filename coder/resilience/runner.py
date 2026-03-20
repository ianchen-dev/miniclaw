"""
ResilienceRunner - 三层重试洋葱

执行 agent 回合, 带自动故障转移、压缩和重试。

三层嵌套的重试包裹每次 agent 执行:
    Layer 1 (最外层): 遍历 API key 配置, 跳过冷却中的配置。
            如果配置因 auth/rate/timeout 失败, 标记后尝试下一个。
    Layer 2 (中间层): 上下文溢出错误时, 压缩消息历史并重试,
            最多 MAX_OVERFLOW_COMPACTION 次。
    Layer 3 (最内层): 标准的工具调用循环 (while True + stop_reason)。
"""

import json
from typing import Any

import litellm

from coder.resilience.failure import FailoverReason, SimulatedFailure, classify_failure
from coder.resilience.profile import AuthProfile, ProfileManager


# Retry limits
BASE_RETRY = 24
PER_PROFILE = 8
MAX_OVERFLOW_COMPACTION = 3


class ResilienceRunner:
    """
    执行 agent 回合, 带自动故障转移、压缩和重试。

    三层重试洋葱:
        Layer 1: Auth Rotation - 在 API key 配置之间轮转
        Layer 2: Overflow Recovery - 上下文溢出时压缩消息
        Layer 3: Tool-Use Loop - 标准的 while True + stop_reason 分发
    """

    def __init__(
        self,
        profile_manager: ProfileManager,
        model_id: str,
        fallback_models: list[str] | None = None,
        simulated_failure: SimulatedFailure | None = None,
        max_tokens: int = 8096,
        api_base_url: str | None = None,
        context_safe_limit: int = 180000,
    ) -> None:
        """
        初始化 ResilienceRunner。

        Args:
            profile_manager: 配置管理器
            model_id: 主模型 ID
            fallback_models: 备选模型列表
            simulated_failure: 模拟失败器 (用于测试)
            max_tokens: 最大 token 数
            api_base_url: API 基础 URL
            context_safe_limit: 上下文安全限制
        """
        self.profile_manager = profile_manager
        self.model_id = model_id
        self.fallback_models = fallback_models or []
        self.simulated_failure = simulated_failure
        self.max_tokens = max_tokens
        self.api_base_url = api_base_url
        self.context_safe_limit = context_safe_limit

        num_profiles = len(profile_manager.profiles)
        self.max_iterations = min(
            max(BASE_RETRY + PER_PROFILE * num_profiles, 32),
            160,
        )

        # Stats
        self.total_attempts = 0
        self.total_successes = 0
        self.total_failures = 0
        self.total_compactions = 0
        self.total_rotations = 0

    def run(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        """
        执行三层重试洋葱。

        Args:
            system: 系统提示词
            messages: 消息列表
            tools: 工具列表

        Returns:
            tuple[Any, list[dict]]: (final_response, updated_messages)

        Raises:
            RuntimeError: 所有配置和备选模型都耗尽时
        """
        from coder.cli import print_error, print_resilience, print_warn

        current_messages = list(messages)
        profiles_tried: set[str] = set()

        # Configuration: failure reason -> (cooldown_seconds, should_break)
        FAILURE_CONFIG: dict[FailoverReason, tuple[float, bool]] = {
            FailoverReason.auth: (300, True),
            FailoverReason.billing: (300, True),
            FailoverReason.rate_limit: (120, True),
            FailoverReason.timeout: (60, True),
            FailoverReason.unknown: (120, True),
            FailoverReason.overflow: (600, False),  # Special case: handled separately
        }

        # ---- LAYER 1: Auth Rotation ----
        # Iterate through available profiles. On auth/rate/timeout failures,
        # mark the profile and try the next one.
        for _rotation in range(len(self.profile_manager.profiles)):
            profile = self.profile_manager.select_profile()
            if profile is None:
                print_warn("All profiles on cooldown")
                break
            if profile.name in profiles_tried:
                break
            profiles_tried.add(profile.name)

            if len(profiles_tried) > 1:
                self.total_rotations += 1
                print_resilience(f"Rotating to profile '{profile.name}'")

            # ---- LAYER 2: Overflow Recovery ----
            # On context overflow, compact messages and retry.
            layer2_messages = list(current_messages)
            for compact_attempt in range(MAX_OVERFLOW_COMPACTION):
                try:
                    self.total_attempts += 1

                    # Check simulated failure before real API call
                    if self.simulated_failure:
                        self.simulated_failure.check_and_fire()

                    # ---- LAYER 3: Tool-Use Loop ----
                    result, layer2_messages = self._run_attempt(
                        profile=profile,
                        model=self.model_id,
                        system=system,
                        messages=layer2_messages,
                        tools=tools,
                    )
                    self.profile_manager.mark_success(profile)
                    self.total_successes += 1
                    return result, layer2_messages

                except Exception as exc:
                    reason = classify_failure(exc)
                    self.total_failures += 1

                    if reason == FailoverReason.overflow:
                        if compact_attempt < MAX_OVERFLOW_COMPACTION - 1:
                            self.total_compactions += 1
                            print_resilience(
                                f"Context overflow (attempt {compact_attempt + 1}/"
                                f"{MAX_OVERFLOW_COMPACTION}), compacting..."
                            )
                            # Stage 1: truncate tool results
                            layer2_messages = self._truncate_tool_results(layer2_messages)
                            # Stage 2: compact history via LLM summary
                            layer2_messages = self._compact_history(layer2_messages, profile.api_key, self.model_id)
                            continue
                        else:
                            print_error(f"Overflow not resolved after {MAX_OVERFLOW_COMPACTION} compaction attempts")
                            self.profile_manager.mark_failure(profile, reason, cooldown_seconds=600)
                            break

                    # Handle other failures using configuration
                    cooldown, should_break = FAILURE_CONFIG.get(reason, (120, True))
                    self.profile_manager.mark_failure(profile, reason, cooldown_seconds=cooldown)
                    if should_break:
                        break

        # ---- Fallback models ----
        # All primary profiles exhausted. Try fallback models with any
        # available profile (cooldowns may have expired during retries).
        if self.fallback_models:
            print_resilience("Primary profiles exhausted, trying fallback models...")
            for fallback_model in self.fallback_models:
                profile = self.profile_manager.select_profile()
                if profile is None:
                    # Try resetting cooldowns for fallback attempt
                    self.profile_manager.reset_rate_limit_cooldowns()
                    profile = self.profile_manager.select_profile()
                if profile is None:
                    continue

                print_resilience(f"Fallback: model='{fallback_model}', profile='{profile.name}'")

                try:
                    self.total_attempts += 1
                    if self.simulated_failure:
                        self.simulated_failure.check_and_fire()

                    result, updated = self._run_attempt(
                        profile=profile,
                        model=fallback_model,
                        system=system,
                        messages=current_messages,
                        tools=tools,
                    )
                    self.profile_manager.mark_success(profile)
                    self.total_successes += 1
                    return result, updated

                except Exception as exc:
                    reason = classify_failure(exc)
                    self.total_failures += 1
                    print_warn(f"Fallback model '{fallback_model}' failed: {reason.value} -- {exc}")
                    continue

        raise RuntimeError(
            "All profiles and fallback models exhausted. "
            f"Tried {len(profiles_tried)} profiles, "
            f"{len(self.fallback_models)} fallback models."
        )

    def _run_attempt(
        self,
        profile: AuthProfile,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        """
        Layer 3: 标准工具调用循环。

        运行 while True + stop_reason 模式。
        end_turn 时返回 (final_response, updated_messages)。
        任何 API 异常都向外层传播。

        Args:
            profile: 当前使用的配置
            model: 模型 ID
            system: 系统提示词
            messages: 消息列表
            tools: 工具列表

        Returns:
            tuple[Any, list[dict]]: (response, updated_messages)

        Raises:
            RuntimeError: 工具调用循环超过最大迭代次数
        """
        from coder.cli import print_tool
        from coder.tools import process_tool_call

        current_messages = list(messages)
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1

            # Build API call kwargs
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system}] + current_messages,
                "api_key": profile.api_key,
            }
            if self.api_base_url:
                kwargs["api_base"] = self.api_base_url
            if tools:
                kwargs["tools"] = tools

            response = litellm.completion(**kwargs)

            # Extract response content and finish_reason
            response_content = []
            finish_reason = None

            for choice in response.choices:
                if not hasattr(choice, "message"):
                    continue
                msg = choice.message
                if not finish_reason and hasattr(choice, "finish_reason"):
                    finish_reason = choice.finish_reason

                if hasattr(msg, "content") and msg.content:
                    response_content.append({"type": "text", "text": msg.content})
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if hasattr(tc, "function"):
                            response_content.append(
                                {
                                    "type": "tool_use",
                                    "id": tc.id,
                                    "name": tc.function.name,
                                    "input": json.loads(tc.function.arguments)
                                    if isinstance(tc.function.arguments, str)
                                    else tc.function.arguments,
                                }
                            )

            current_messages.append({"role": "assistant", "content": response_content})

            # Check if we have tool calls
            has_tool_calls = any(block.get("type") == "tool_use" for block in response_content)

            if has_tool_calls:
                # Process tool calls
                tool_results = []
                for block in response_content:
                    if block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name", "?")
                    tool_input = block.get("input", {})
                    print_tool(tool_name, str(tool_input)[:100])
                    result = process_tool_call(tool_name, tool_input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.get("id", ""),
                            "content": result,
                        }
                    )
                current_messages.append({"role": "user", "content": tool_results})
                continue

            # No tool calls - treat as end_turn
            return response, current_messages

        raise RuntimeError(f"Tool-use loop exceeded {self.max_iterations} iterations")

    def _truncate_tool_results(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        截断过大的 tool_result 块以减少上下文占用。

        Args:
            messages: 消息列表

        Returns:
            list[dict]: 处理后的消息列表
        """
        max_chars = int(self.context_safe_limit * 4 * 0.3)

        def truncate_block(block: dict[str, Any]) -> dict[str, Any]:
            """Truncate a single tool_result block if needed."""
            if (
                block.get("type") != "tool_result"
                or not isinstance(block.get("content"), str)
                or len(block["content"]) <= max_chars
            ):
                return block
            truncated = dict(block)
            original_len = len(truncated["content"])
            truncated["content"] = (
                truncated["content"][:max_chars]
                + f"\n\n[... truncated ({original_len} chars total, showing first {max_chars}) ...]"
            )
            return truncated

        result = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                new_blocks = [truncate_block(b) if isinstance(b, dict) else b for b in content]
                result.append({"role": msg["role"], "content": new_blocks})
            else:
                result.append(msg)
        return result

    def _compact_history(
        self,
        messages: list[dict[str, Any]],
        api_key: str,
        model: str,
    ) -> list[dict[str, Any]]:
        """
        将前 50% 的消息压缩为 LLM 生成的摘要。

        保留最后 20% (至少 4 条) 的消息不变, 以保持近期上下文。

        Args:
            messages: 消息列表
            api_key: API 密钥
            model: 模型 ID

        Returns:
            list[dict]: 压缩后的消息列表
        """
        from coder.cli import print_resilience, print_warn

        total = len(messages)
        if total <= 4:
            return messages

        keep_count = max(4, int(total * 0.2))
        compress_count = max(2, int(total * 0.5))
        compress_count = min(compress_count, total - keep_count)

        if compress_count < 2:
            return messages

        old_messages = messages[:compress_count]
        recent_messages = messages[compress_count:]

        # Flatten old messages to plain text for summarization
        def flatten_message(msg: dict[str, Any]) -> str:
            """Flatten a single message to text representation."""
            role = msg["role"]
            content = msg.get("content", "")
            if isinstance(content, str):
                return f"[{role}]: {content}"
            if not isinstance(content, list):
                return ""

            parts = []
            for block in content:
                if not isinstance(block, dict):
                    if hasattr(block, "text"):
                        parts.append(f"[{role}]: {block.text}")
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    parts.append(f"[{role}]: {block['text']}")
                elif block_type == "tool_use":
                    parts.append(
                        f"[{role} called {block.get('name', '?')}]: "
                        f"{json.dumps(block.get('input', {}), ensure_ascii=False)}"
                    )
                elif block_type == "tool_result":
                    rc = block.get("content", "")
                    preview = rc[:500] if isinstance(rc, str) else str(rc)[:500]
                    parts.append(f"[tool_result]: {preview}")
            return "\n".join(parts)

        old_text = "\n".join(filter(None, (flatten_message(msg) for msg in old_messages)))

        summary_prompt = (
            "Summarize the following conversation concisely, "
            "preserving key facts and decisions. "
            "Output only the summary, no preamble.\n\n"
            f"{old_text}"
        )

        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": summary_prompt}],
                "api_key": api_key,
            }
            if self.api_base_url:
                kwargs["api_base"] = self.api_base_url

            summary_resp = litellm.completion(**kwargs)

            # Extract summary text from response
            summary_text = "".join(
                choice.message.content or ""
                for choice in summary_resp.choices
                if hasattr(choice, "message") and hasattr(choice.message, "content")
            )

            print_resilience(f"Compacted {len(old_messages)} messages -> summary ({len(summary_text)} chars)")
        except Exception as exc:
            print_warn(f"Summary failed ({exc}), dropping old messages")
            return recent_messages

        return [
            {"role": "user", "content": f"[Previous conversation summary]\n{summary_text}"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Understood, I have the context from our previous conversation."}],
            },
            *recent_messages,
        ]

    def get_stats(self) -> dict[str, Any]:
        """
        返回弹性运行器的统计数据。

        Returns:
            dict: 统计数据
        """
        return {
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_compactions": self.total_compactions,
            "total_rotations": self.total_rotations,
            "max_iterations": self.max_iterations,
        }


__all__ = [
    "ResilienceRunner",
    "BASE_RETRY",
    "PER_PROFILE",
    "MAX_OVERFLOW_COMPACTION",
]
