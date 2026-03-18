"""
ContextGuard - 上下文溢出保护

三阶段溢出重试:
    1. 正常调用
    2. 截断过大的工具结果
    3. 压缩历史 (LLM 摘要)
    4. 仍然溢出则抛出异常
"""

import json
from typing import Any, Dict, List, Optional

import litellm

from coder.settings import settings


def _serialize_messages_for_summary(messages: List[Dict[str, Any]]) -> str:
    """
    将消息列表扁平化为纯文本，用于 LLM 摘要。

    Args:
        messages: 消息列表

    Returns:
        序列化后的文本
    """
    parts: List[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        parts.append(f"[{role}]: {block['text']}")
                    elif btype == "tool_use":
                        parts.append(
                            f"[{role} called {block.get('name', '?')}]: "
                            f"{json.dumps(block.get('input', {}), ensure_ascii=False)}"
                        )
                    elif btype == "tool_result":
                        rc = block.get("content", "")
                        preview = rc[:500] if isinstance(rc, str) else str(rc)[:500]
                        parts.append(f"[tool_result]: {preview}")
                elif hasattr(block, "text"):
                    parts.append(f"[{role}]: {block.text}")
    return "\n".join(parts)


class ContextGuard:
    """
    保护 agent 免受上下文窗口溢出。

    三阶段重试策略:
        1. 正常调用
        2. 截断过大的工具结果 (在换行边界处只保留头部)
        3. 将旧消息压缩为 LLM 生成的摘要 (固定 50% 比例)
        4. 仍然溢出则抛出异常
    """

    def __init__(self, max_tokens: Optional[int] = None):
        """
        初始化 ContextGuard。

        Args:
            max_tokens: 上下文安全限制，默认从配置读取
        """
        self.max_tokens = max_tokens or settings.context_safe_limit

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        估算文本的 token 数量。

        使用简单的启发式方法: len(text) // 4

        Args:
            text: 文本内容

        Returns:
            估算的 token 数量
        """
        return len(text) // 4

    def estimate_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        估算消息列表的 token 数量。

        Args:
            messages: 消息列表

        Returns:
            估算的 token 数量
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if "text" in block:
                            total += self.estimate_tokens(block["text"])
                        elif block.get("type") == "tool_result":
                            rc = block.get("content", "")
                            if isinstance(rc, str):
                                total += self.estimate_tokens(rc)
                        elif block.get("type") == "tool_use":
                            total += self.estimate_tokens(json.dumps(block.get("input", {})))
                    else:
                        if hasattr(block, "text"):
                            total += self.estimate_tokens(block.text)
                        elif hasattr(block, "input"):
                            total += self.estimate_tokens(json.dumps(block.input))
        return total

    def truncate_tool_result(self, result: str, max_fraction: float = 0.3) -> str:
        """
        在换行边界处只保留头部进行截断。

        Args:
            result: 工具结果
            max_fraction: 最大占上下文的比例

        Returns:
            截断后的结果
        """
        max_chars = int(self.max_tokens * 4 * max_fraction)
        if len(result) <= max_chars:
            return result
        cut = result.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        head = result[:cut]
        return head + f"\n\n[... truncated ({len(result)} chars total, showing first {len(head)}) ...]"

    def compact_history(
        self,
        messages: List[Dict[str, Any]],
        api_key: str,
        model: str,
        api_base_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        将前 50% 的消息压缩为 LLM 生成的摘要。
        保留最后 N 条消息 (N = max(4, 总数的 20%)) 不变。

        Args:
            messages: 消息列表
            api_key: API 密钥
            model: 模型ID
            api_base_url: API 基础 URL

        Returns:
            压缩后的消息列表
        """
        from coder.components.cli import print_session, print_warn

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

        old_text = _serialize_messages_for_summary(old_messages)

        summary_prompt = (
            "Summarize the following conversation concisely, "
            "preserving key facts and decisions. "
            "Output only the summary, no preamble.\n\n"
            f"{old_text}"
        )

        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": summary_prompt}],
                "api_key": api_key,
            }
            if api_base_url:
                kwargs["api_base"] = api_base_url

            summary_resp = litellm.completion(**kwargs)

            summary_text = ""
            for choice in summary_resp.choices:
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    summary_text += choice.message.content or ""

            print_session(f"  [compact] {len(old_messages)} messages -> summary ({len(summary_text)} chars)")
        except Exception as exc:
            print_warn(f"  [compact] Summary failed ({exc}), dropping old messages")
            return recent_messages

        compacted = [
            {
                "role": "user",
                "content": "[Previous conversation summary]\n" + summary_text,
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Understood, I have the context from our previous conversation."}],
            },
        ]
        compacted.extend(recent_messages)
        return compacted

    def _truncate_large_tool_results(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        遍历消息列表，截断过大的 tool_result 块。

        Args:
            messages: 消息列表

        Returns:
            处理后的消息列表
        """
        result = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                new_blocks = []
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_result"
                        and isinstance(block.get("content"), str)
                    ):
                        block = dict(block)
                        block["content"] = self.truncate_tool_result(block["content"])
                    new_blocks.append(block)
                result.append({"role": msg["role"], "content": new_blocks})
            else:
                result.append(msg)
        return result

    def guard_api_call(
        self,
        api_key: str,
        model: str,
        system: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 8096,
        api_base_url: Optional[str] = None,
        max_retries: int = 2,
    ) -> Any:
        """
        三阶段重试:
            第0次尝试: 正常调用
            第1次尝试: 截断过大的工具结果
            第2次尝试: 通过 LLM 摘要压缩历史

        Args:
            api_key: API 密钥
            model: 模型ID
            system: 系统提示词
            messages: 消息列表
            tools: 工具列表
            max_tokens: 最大 token 数
            api_base_url: API 基础 URL
            max_retries: 最大重试次数

        Returns:
            LLM 响应

        Raises:
            Exception: 重试耗尽后抛出最后一次异常
        """
        from coder.components.cli import print_warn

        current_messages = messages

        for attempt in range(max_retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "system", "content": system}] + current_messages,
                    "api_key": api_key,
                }
                if api_base_url:
                    kwargs["api_base"] = api_base_url
                if tools:
                    kwargs["tools"] = tools

                result = litellm.completion(**kwargs)

                if current_messages is not messages:
                    messages.clear()
                    messages.extend(current_messages)
                return result

            except Exception as exc:
                error_str = str(exc).lower()
                is_overflow = "context" in error_str or "token" in error_str or "length" in error_str

                if not is_overflow or attempt >= max_retries:
                    raise

                if attempt == 0:
                    print_warn("  [guard] Context overflow detected, truncating large tool results...")
                    current_messages = self._truncate_large_tool_results(current_messages)
                elif attempt == 1:
                    print_warn("  [guard] Still overflowing, compacting conversation history...")
                    current_messages = self.compact_history(current_messages, api_key, model, api_base_url)

        raise RuntimeError("guard_api_call: exhausted retries")


__all__ = ["ContextGuard", "_serialize_messages_for_summary"]
