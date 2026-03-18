"""
Agent 循环 - 核心 REPL 实现

Agent 就是 while True + stop_reason

流程:
    用户输入 --> [messages[]] --> LLM API --> stop_reason?
                                               /        \\
                                         "stop"      "tool_calls"
                                             |           |
                                          打印回复    执行工具(下一节)

用法:
    from coder.components.agent import AgentLoop

    loop = AgentLoop()
    loop.run()
"""

from typing import List, Dict, Any, Optional
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
)


class AgentLoop:
    """
    Agent 循环类

    管理 messages 状态和 LLM 交互循环
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ):
        """
        初始化 Agent 循环

        Args:
            model_id: 模型ID，默认从配置读取
            api_key: API密钥，默认从配置读取
            api_base_url: API基础URL，默认从配置读取
            max_tokens: 最大token数，默认从配置读取
            system_prompt: 系统提示词，默认使用组件提供
        """
        self.model_id = model_id or settings.model_id
        self.api_key = api_key or settings.api_key
        self.api_base_url = api_base_url or settings.api_base_url
        self.max_tokens = max_tokens or settings.max_tokens
        self.system_prompt = system_prompt or get_system_prompt()

        # 消息历史
        self.messages: List[Dict[str, Any]] = []

        # 配置 litellm
        if self.api_base_url:
            litellm.api_base = self.api_base_url

    def _build_messages(self) -> List[Dict[str, Any]]:
        """构建发送给 LLM 的消息列表（包含系统提示词）"""
        return [{"role": "system", "content": self.system_prompt}] + self.messages

    def _call_llm(self) -> Optional[ModelResponse]:
        """调用 LLM API"""
        try:
            response = litellm.completion(
                model=self.model_id,
                max_tokens=self.max_tokens,
                messages=self._build_messages(),
                api_key=self.api_key,
                stream=False,
            )
            return response
        except Exception as exc:
            print_error(f"API Error: {exc}")
            return None

    def _handle_stop(self, assistant_message: Any) -> None:
        """处理 finish_reason='stop' 的情况"""
        assistant_text = assistant_message.content or ""
        print_assistant(assistant_text)

        self.messages.append(
            {
                "role": "assistant",
                "content": assistant_text,
            }
        )

    def _handle_tool_calls(self, assistant_message: Any) -> None:
        """处理 finish_reason='tool_calls' 的情况（预留，s02实现）"""
        print_info("[finish_reason=tool_calls] 本节没有可用工具.")
        print_info("参见 s02_tool_use 了解工具支持.")

        self.messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",
            }
        )

    def _handle_other(self, finish_reason: str, assistant_message: Any) -> None:
        """处理其他 finish_reason 的情况"""
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

    def _process_response(self, response: ModelResponse) -> None:
        """处理 LLM 响应"""
        choice = response.choices[0]
        finish_reason = choice.finish_reason
        assistant_message = choice.message

        if finish_reason == "stop":
            self._handle_stop(assistant_message)
        elif finish_reason == "tool_calls":
            self._handle_tool_calls(assistant_message)
        else:
            self._handle_other(finish_reason, assistant_message)

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

    def run(self) -> None:
        """
        运行 Agent 循环

        主 REPL 循环:
        1. 收集用户输入
        2. 追加到 messages
        3. 调用 LLM
        4. 根据 finish_reason 分支处理
        """
        print_banner("your-claw | Section 01: Agent 循环", self.model_id)

        while True:
            # 获取用户输入
            user_input = self._get_user_input()
            if user_input is None:
                break
            if not user_input:
                continue

            # 追加到历史
            self.messages.append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            # 调用 LLM
            response = self._call_llm()
            if response is None:
                # API 错误，回滚消息
                self.messages.pop()
                continue

            # 处理响应
            self._process_response(response)


def run_agent_loop() -> None:
    """便捷函数：运行 Agent 循环"""
    loop = AgentLoop()
    loop.run()
