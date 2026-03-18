"""
Agent 循环 - 核心 REPL 实现

Agent 就是 while True + stop_reason

流程:
    用户输入 --> [messages[]] --> LLM API --> stop_reason?
                                               /        \\
                                         "stop"      "tool_calls"
                                             |           |
                                          打印回复    执行工具
                                                          |
                                                     工具结果
                                                          |
                                                    回到 LLM --> 可能继续调用工具
                                                               或 "stop" --> 打印

用法:
    from coder.components.agent import AgentLoop

    # 不使用工具和会话
    loop = AgentLoop()
    loop.run()

    # 使用工具
    from coder.components.tools import TOOLS
    loop = AgentLoop(tools=TOOLS)
    loop.run()

    # 使用会话持久化 (s03)
    loop = AgentLoop(tools=TOOLS, enable_session=True)
    loop.run()
"""

from typing import List, Dict, Any, Optional, Tuple
import litellm
from litellm import ModelResponse

from coder.settings import settings
from coder.components.prompts import get_system_prompt
from coder.components.cli import (
    colored_user,
    print_assistant,
    print_info,
    print_error,
    print_banner,
    print_goodbye,
    print_session,
    print_warn,
    print_context_bar,
)
from coder.components.tools import process_tool_call


# 工具使用的系统提示词扩展
TOOL_SYSTEM_PROMPT_EXTENSION = (
    "You are a helpful AI assistant with access to tools.\n"
    "Use the tools to help the user with file operations and shell commands.\n"
    "Always read a file before editing it.\n"
    "When using edit_file, the old_string must match EXACTLY (including whitespace)."
)


class AgentLoop:
    """
    Agent 循环类

    管理 messages 状态和 LLM 交互循环
    支持工具调用 (s02)
    支持会话持久化和上下文保护 (s03)
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        enable_session: bool = False,
        agent_id: str = "default",
    ):
        """
        初始化 Agent 循环

        Args:
            model_id: 模型ID，默认从配置读取
            api_key: API密钥，默认从配置读取
            api_base_url: API基础URL，默认从配置读取
            max_tokens: 最大token数，默认从配置读取
            system_prompt: 系统提示词，默认使用组件提供
            tools: 工具schema列表，如果提供则启用工具支持
            enable_session: 是否启用会话持久化 (s03)
            agent_id: Agent 标识符，用于会话存储
        """
        self.model_id = model_id or settings.model_id
        self.api_key = api_key or settings.api_key
        self.api_base_url = api_base_url or settings.api_base_url
        self.max_tokens = max_tokens or settings.max_tokens
        self.tools = tools
        self.enable_session = enable_session
        self.agent_id = agent_id

        # 如果启用了工具，扩展系统提示词
        if self.tools:
            base_prompt = system_prompt or get_system_prompt()
            self.system_prompt = f"{TOOL_SYSTEM_PROMPT_EXTENSION}\n\n{base_prompt}"
        else:
            self.system_prompt = system_prompt or get_system_prompt()

        # 消息历史
        self.messages: List[Dict[str, Any]] = []

        # 会话存储和上下文保护 (s03)
        self._store = None
        self._guard = None

        if self.enable_session:
            from coder.components.session import SessionStore, ContextGuard

            self._store = SessionStore(agent_id=self.agent_id)
            self._guard = ContextGuard()

        # 配置 litellm
        if self.api_base_url:
            litellm.api_base = self.api_base_url

    def _build_messages(self) -> List[Dict[str, Any]]:
        """构建发送给 LLM 的消息列表（包含系统提示词）"""
        return [{"role": "system", "content": self.system_prompt}] + self.messages

    def _call_llm(self) -> Optional[ModelResponse]:
        """调用 LLM API（带上下文保护）"""
        try:
            # 如果启用会话，使用 ContextGuard 保护
            if self._guard:
                return self._guard.guard_api_call(
                    api_key=self.api_key,
                    model=self.model_id,
                    system=self.system_prompt,
                    messages=self.messages,
                    tools=self.tools,
                    max_tokens=self.max_tokens,
                    api_base_url=self.api_base_url,
                )

            # 否则直接调用
            kwargs: Dict[str, Any] = {
                "model": self.model_id,
                "max_tokens": self.max_tokens,
                "messages": self._build_messages(),
                "api_key": self.api_key,
                "stream": False,
            }

            if self.tools:
                kwargs["tools"] = self.tools

            response = litellm.completion(**kwargs)
            return response
        except Exception as exc:
            print_error(f"API Error: {exc}")
            return None

    def _handle_stop(self, assistant_message: Any) -> bool:
        """
        处理 finish_reason='stop' 的情况

        Returns:
            True 表示跳出内层循环，False 表示继续
        """
        assistant_text = assistant_message.content or ""
        print_assistant(assistant_text)

        # 将助手消息添加到历史
        assistant_msg: Dict[str, Any] = {"role": "assistant"}
        if assistant_text:
            assistant_msg["content"] = assistant_text
        if hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:
            assistant_msg["tool_calls"] = assistant_message.tool_calls
        self.messages.append(assistant_msg)

        # 保存到会话存储 (s03)
        if self._store:
            serialized_content = [{"type": "text", "text": assistant_text}] if assistant_text else []
            self._store.save_turn("assistant", serialized_content)

        return True  # 跳出内层循环

    def _handle_tool_calls(self, assistant_message: Any) -> bool:
        """
        处理 finish_reason='tool_calls' 的情况

        模型可能连续调用多个工具，执行后把结果送回模型。

        Returns:
            False 表示继续内层循环
        """
        # 将助手消息（包含 tool_calls）添加到历史
        assistant_msg: Dict[str, Any] = {"role": "assistant"}
        if assistant_message.content:
            assistant_msg["content"] = assistant_message.content
        if hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:
            assistant_msg["tool_calls"] = assistant_message.tool_calls
        self.messages.append(assistant_msg)

        # 处理每个工具调用
        tool_calls = assistant_message.tool_calls or []
        tool_results = []

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_input = tool_call.function.arguments
            tool_id = tool_call.id

            # 执行工具
            result = process_tool_call(tool_name, tool_input)

            # 保存到会话存储 (s03)
            if self._store:
                self._store.save_tool_result(tool_id, tool_name, tool_input, result)

            # 构建工具结果
            tool_results.append(
                {
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": result,
                }
            )

        # 将工具结果添加到历史
        self.messages.extend(tool_results)

        return False  # 继续内层循环

    def _handle_other(self, finish_reason: str, assistant_message: Any) -> bool:
        """
        处理其他 finish_reason 的情况

        Returns:
            True 表示跳出内层循环
        """
        print_info(f"[finish_reason={finish_reason}]")
        assistant_text = assistant_message.content or ""
        if assistant_text:
            print_assistant(assistant_text)

        self.messages.append(
            {
                "role": "assistant",
                "content": assistant_text,
            }
        )

        # 保存到会话存储 (s03)
        if self._store:
            serialized_content = [{"type": "text", "text": assistant_text}] if assistant_text else []
            self._store.save_turn("assistant", serialized_content)

        return True  # 跳出内层循环

    def _process_response(self, response: ModelResponse) -> bool:
        """
        处理 LLM 响应

        Returns:
            True 表示跳出内层循环，False 表示继续
        """
        choice = response.choices[0]
        finish_reason = choice.finish_reason
        assistant_message = choice.message

        if finish_reason == "stop":
            return self._handle_stop(assistant_message)
        elif finish_reason == "tool_calls":
            return self._handle_tool_calls(assistant_message)
        else:
            return self._handle_other(finish_reason, assistant_message)

    def _get_user_input(self) -> Optional[str]:
        """获取用户输入"""
        try:
            user_input = input(colored_user()).strip()
        except (KeyboardInterrupt, EOFError):
            print_goodbye()
            return None

        if not user_input:
            return ""

        if user_input.lower() in ("quit", "exit"):
            print_goodbye()
            return None

        return user_input

    def _handle_repl_command(self, command: str) -> Tuple[bool, bool]:
        """
        处理以 / 开头的 REPL 命令。

        Args:
            command: 用户输入的命令

        Returns:
            (是否已处理, 是否应该继续循环)
        """
        if not self._store or not self._guard:
            print_warn("  REPL commands require session support. Enable with enable_session=True")
            return True, True

        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/new":
            label = arg or ""
            sid = self._store.create_session(label)
            self.messages = []
            print_session(f"  Created new session: {sid}" + (f" ({label})" if label else ""))
            return True, True

        elif cmd == "/list":
            sessions = self._store.list_sessions()
            if not sessions:
                print_info("  No sessions found.")
                return True, True

            print_info("  Sessions:")
            for sid, meta in sessions:
                active = " <-- current" if sid == self._store.current_session_id else ""
                label = meta.get("label", "")
                label_str = f" ({label})" if label else ""
                count = meta.get("message_count", 0)
                last = meta.get("last_active", "?")[:19]
                print_info(f"    {sid}{label_str}  msgs={count}  last={last}{active}")
            return True, True

        elif cmd == "/switch":
            if not arg:
                print_warn("  Usage: /switch <session_id>")
                return True, True
            target_id = arg.strip()
            matched = [sid for sid in self._store._index if sid.startswith(target_id)]
            if len(matched) == 0:
                print_warn(f"  Session not found: {target_id}")
                return True, True
            if len(matched) > 1:
                print_warn(f"  Ambiguous prefix, matches: {', '.join(matched)}")
                return True, True

            sid = matched[0]
            self.messages = self._store.load_session(sid)
            print_session(f"  Switched to session: {sid} ({len(self.messages)} messages)")
            return True, True

        elif cmd == "/context":
            estimated = self._guard.estimate_messages_tokens(self.messages)
            print_context_bar(estimated, self._guard.max_tokens)
            print_info(f"  Messages: {len(self.messages)}")
            return True, True

        elif cmd == "/compact":
            if len(self.messages) <= 4:
                print_info("  Too few messages to compact (need > 4).")
                return True, True
            print_session("  Compacting history...")
            old_count = len(self.messages)
            self.messages = self._guard.compact_history(self.messages, self.api_key, self.model_id, self.api_base_url)
            print_session(f"  {old_count} -> {len(self.messages)} messages")
            return True, True

        elif cmd == "/help":
            print_info("  Commands:")
            print_info("    /new [label]       Create a new session")
            print_info("    /list              List all sessions")
            print_info("    /switch <id>       Switch to a session (prefix match)")
            print_info("    /context           Show context token usage")
            print_info("    /compact           Manually compact conversation history")
            print_info("    /help              Show this help")
            print_info("    quit / exit        Exit the REPL")
            return True, True

        return False, True

    def _init_session(self) -> None:
        """初始化会话：恢复最近的会话或创建新会话"""
        if not self._store:
            return

        sessions = self._store.list_sessions()
        if sessions:
            sid = sessions[0][0]
            self.messages = self._store.load_session(sid)
            print_session(f"  Resumed session: {sid} ({len(self.messages)} messages)")
        else:
            sid = self._store.create_session("initial")
            self.messages = []
            print_session(f"  Created initial session: {sid}")

    def run(self) -> None:
        """
        运行 Agent 循环

        主 REPL 循环:
        1. 收集用户输入
        2. 追加到 messages
        3. 调用 LLM（内层循环处理工具调用）
        4. 根据 finish_reason 分支处理
        """
        # 初始化会话
        if self.enable_session:
            self._init_session()

        # 打印横幅
        extra_info = ""
        if self.tools:
            from coder.components.tools import TOOL_HANDLERS

            extra_info = f"Tools: {', '.join(TOOL_HANDLERS.keys())}"

        if self.enable_session:
            section = "Section 03: 会话与上下文保护"
            if extra_info:
                extra_info = f"Session: {self._store.current_session_id} | {extra_info}"
            else:
                extra_info = f"Session: {self._store.current_session_id}"
        elif self.tools:
            section = "Section 02: 工具使用"
        else:
            section = "Section 01: Agent 循环"

        print_banner(f"your-claw | {section}", self.model_id, extra_info=extra_info)

        if self.enable_session:
            print_info("  Type /help for commands, quit/exit to leave.")
            print()

        while True:
            # 获取用户输入
            user_input = self._get_user_input()
            if user_input is None:
                break
            if not user_input:
                continue

            # REPL 命令处理 (s03)
            if user_input.startswith("/"):
                handled, _ = self._handle_repl_command(user_input)
                if handled:
                    continue

            # 追加到历史
            self.messages.append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            # 保存到会话存储 (s03)
            if self._store:
                self._store.save_turn("user", user_input)

            # 内层循环：处理工具调用
            # 模型可能连续调用多个工具才最终给出文本回复
            while True:
                # 调用 LLM
                response = self._call_llm()
                if response is None:
                    # API 错误，回滚消息到最近的 user 消息
                    while self.messages and self.messages[-1]["role"] != "user":
                        self.messages.pop()
                    if self.messages:
                        self.messages.pop()
                    break

                # 处理响应
                should_break = self._process_response(response)
                if should_break:
                    break


def run_agent_loop(
    tools: Optional[List[Dict[str, Any]]] = None,
    enable_session: bool = False,
    agent_id: str = "default",
) -> None:
    """
    便捷函数：运行 Agent 循环

    Args:
        tools: 工具schema列表，如果提供则启用工具支持
        enable_session: 是否启用会话持久化 (s03)
        agent_id: Agent 标识符，用于会话存储
    """
    loop = AgentLoop(tools=tools, enable_session=enable_session, agent_id=agent_id)
    loop.run()
