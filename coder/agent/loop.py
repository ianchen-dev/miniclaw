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
    from coder.agent import AgentLoop

    # 不使用工具和会话
    loop = AgentLoop()
    loop.run()

    # 使用工具
    from coder.tools import TOOLS
    loop = AgentLoop(tools=TOOLS)
    loop.run()

    # 使用会话持久化 (s03)
    loop = AgentLoop(tools=TOOLS, enable_session=True)
    loop.run()

    # 使用智能层 (s06)
    loop = AgentLoop(tools=TOOLS, enable_session=True, enable_intelligence=True)
    loop.run()

    # 使用心跳和 Cron (s07)
    loop = AgentLoop(tools=TOOLS, enable_scheduler=True)
    loop.run()
"""

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import litellm
from litellm import ModelResponse

from coder.cli import (
    BLUE,
    RESET,
    colored_user,
    print_assistant,
    print_banner,
    print_context_bar,
    print_cron,
    print_error,
    print_goodbye,
    print_heartbeat,
    print_info,
    print_session,
    print_warn,
)
from coder.settings import settings
from coder.tools import process_tool_call


class AgentLoop:
    """
    Agent 循环类

    管理 messages 状态和 LLM 交互循环
    支持工具调用 (s02)
    支持会话持久化和上下文保护 (s03)
    支持智能层 8 层提示词组装 (s06)
    支持心跳和 Cron 调度 (s07)
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
        enable_intelligence: bool = False,
        enable_scheduler: bool = False,
        workspace: Optional[Path] = None,
        channel: str = "terminal",
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
            enable_intelligence: 是否启用智能层 (s06)
            enable_scheduler: 是否启用调度器 (s07)
            workspace: 工作区目录，默认从配置读取
            channel: 通道类型 (terminal/telegram/discord/slack)
        """
        self.model_id = model_id or settings.model_id
        self.api_key = api_key or settings.api_key
        self.api_base_url = api_base_url or settings.api_base_url
        self.max_tokens = max_tokens or settings.max_tokens
        self.tools = tools
        self.enable_session = enable_session
        self.agent_id = agent_id
        self.enable_intelligence = enable_intelligence
        self.enable_scheduler = enable_scheduler
        self.channel = channel
        self._custom_system_prompt = system_prompt

        # 工作区
        self._workspace = workspace or Path(settings.workspace_dir)

        # 消息历史
        self.messages: List[Dict[str, Any]] = []

        # 会话存储和上下文保护 (s03)
        self._store = None
        self._guard = None

        # 智能层组件 (s06)
        self._bootstrap_loader = None
        self._skills_manager = None
        self._memory_store = None
        self._bootstrap_data: Dict[str, str] = {}
        self._skills_block = ""

        # 调度器组件 (s07)
        self._lane_lock: Optional[threading.Lock] = None
        self._heartbeat = None
        self._cron_service = None
        self._cron_stop_event: Optional[threading.Event] = None
        self._cron_thread: Optional[threading.Thread] = None

        if self.enable_session:
            from coder.session import ContextGuard, SessionStore

            self._store = SessionStore(agent_id=self.agent_id)
            self._guard = ContextGuard()

        if self.enable_intelligence:
            self._init_intelligence()

        if self.enable_scheduler:
            self._init_scheduler()

        # 配置 litellm
        if self.api_base_url:
            litellm.api_base = self.api_base_url

    def _init_intelligence(self) -> None:
        """初始化智能层组件"""
        from coder.intelligence import (
            BootstrapLoader,
            MemoryStore,
            SkillsManager,
        )

        self._bootstrap_loader = BootstrapLoader()
        self._bootstrap_data = self._bootstrap_loader.load_all(mode="full")

        self._skills_manager = SkillsManager()
        self._skills_manager.discover()
        self._skills_block = self._skills_manager.format_prompt_block()

        self._memory_store = MemoryStore()

    def _init_scheduler(self) -> None:
        """初始化调度器组件 (s07)"""
        from coder.scheduler import CronService, HeartbeatRunner

        # Lane 互斥锁
        self._lane_lock = threading.Lock()

        # 心跳运行器
        self._heartbeat = HeartbeatRunner(
            workspace=self._workspace,
            lane_lock=self._lane_lock,
        )

        # Cron 服务
        cron_file = self._workspace / "CRON.json"
        self._cron_service = CronService(cron_file, workspace=self._workspace)

        # 启动心跳
        self._heartbeat.start()

        # 启动 Cron 后台线程
        self._cron_stop_event = threading.Event()

        def cron_loop() -> None:
            while not self._cron_stop_event.is_set():
                try:
                    self._cron_service.tick()
                except Exception:
                    pass
                self._cron_stop_event.wait(timeout=1.0)

        self._cron_thread = threading.Thread(
            target=cron_loop,
            daemon=True,
            name="cron-tick",
        )
        self._cron_thread.start()

    def _stop_scheduler(self) -> None:
        """停止调度器组件"""
        if self._heartbeat:
            self._heartbeat.stop()

        if self._cron_stop_event:
            self._cron_stop_event.set()

        if self._cron_thread:
            self._cron_thread.join(timeout=3.0)

    def _drain_scheduler_output(self) -> None:
        """获取并打印调度器输出"""
        if self._heartbeat:
            for msg in self._heartbeat.drain_output():
                print_heartbeat(msg)

        if self._cron_service:
            for msg in self._cron_service.drain_output():
                print_cron(msg)

    def _build_system_prompt(self, user_input: str = "") -> str:
        """
        构建系统提示词

        如果启用了智能层，使用 8 层组装；否则使用简单模式。

        Args:
            user_input: 用户输入，用于自动记忆召回

        Returns:
            系统提示词
        """
        if self._custom_system_prompt:
            return self._custom_system_prompt

        if not self.enable_intelligence:
            # 简单模式
            from coder.prompts import get_system_prompt

            return get_system_prompt(mode="simple")

        # 智能层模式: 8 层组装
        from coder.intelligence import auto_recall, build_system_prompt

        memory_context = ""
        if user_input and self._memory_store:
            memory_context = auto_recall(user_input, self._memory_store)

        return build_system_prompt(
            mode="full",
            bootstrap=self._bootstrap_data,
            skills_block=self._skills_block,
            memory_context=memory_context,
            agent_id=self.agent_id,
            channel=self.channel,
            model_id=self.model_id,
        )

    def _build_messages(self, system_prompt: str) -> List[Dict[str, Any]]:
        """构建发送给 LLM 的消息列表（包含系统提示词）"""
        return [{"role": "system", "content": system_prompt}] + self.messages

    def _call_llm(self, system_prompt: str) -> Optional[ModelResponse]:
        """调用 LLM API（带上下文保护）"""
        try:
            # 如果启用会话，使用 ContextGuard 保护
            if self._guard:
                return self._guard.guard_api_call(
                    api_key=self.api_key,
                    model=self.model_id,
                    system=system_prompt,
                    messages=self.messages,
                    tools=self.tools,
                    max_tokens=self.max_tokens,
                    api_base_url=self.api_base_url,
                )

            # 否则直接调用
            kwargs: Dict[str, Any] = {
                "model": self.model_id,
                "max_tokens": self.max_tokens,
                "messages": self._build_messages(system_prompt),
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

    def _handle_scheduler_command(self, command: str) -> Tuple[bool, bool]:
        """
        处理调度器相关的 REPL 命令 (s07)

        Args:
            command: 用户输入的命令

        Returns:
            (是否已处理, 是否应该继续循环)
        """
        if not self.enable_scheduler:
            return False, True

        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/heartbeat":
            print_info("--- Heartbeat Status ---")
            if self._heartbeat:
                for k, v in self._heartbeat.status().items():
                    print_info(f"  {k}: {v}")
            else:
                print_info("  (heartbeat not initialized)")
            return True, True

        elif cmd == "/trigger":
            print_info("--- Trigger Heartbeat ---")
            if self._heartbeat:
                result = self._heartbeat.trigger()
                print_info(f"  {result}")
                # 打印触发生成的输出
                for msg in self._heartbeat.drain_output():
                    print_heartbeat(msg)
            else:
                print_info("  (heartbeat not initialized)")
            return True, True

        elif cmd == "/cron":
            print_info("--- Cron Jobs ---")
            if self._cron_service:
                jobs = self._cron_service.list_jobs()
                if not jobs:
                    print_info("  No cron jobs.")
                else:
                    for j in jobs:
                        tag = f"{BLUE}ON{RESET}" if j["enabled"] else f"\033[31mOFF{RESET}"
                        err = f" \033[33merr:{j['errors']}{RESET}" if j["errors"] else ""
                        nxt = f" in {j['next_in']}s" if j["next_in"] is not None else ""
                        print(f"  [{tag}] {j['id']} - {j['name']}{err}{nxt}")
            else:
                print_info("  (cron service not initialized)")
            return True, True

        elif cmd == "/cron-trigger":
            if not arg:
                print_warn("  Usage: /cron-trigger <job_id>")
                return True, True
            if self._cron_service:
                result = self._cron_service.trigger_job(arg.strip())
                print_info(f"  {result}")
                # 打印触发生成的输出
                for msg in self._cron_service.drain_output():
                    print_cron(msg)
            else:
                print_info("  (cron service not initialized)")
            return True, True

        elif cmd == "/lanes":
            print_info("--- Lane Status ---")
            if self._lane_lock and self._heartbeat:
                # 尝试非阻塞获取锁来检测状态
                locked = not self._lane_lock.acquire(blocking=False)
                if not locked:
                    self._lane_lock.release()
                print_info(f"  main_locked: {locked}  heartbeat_running: {self._heartbeat.running}")
            else:
                print_info("  (scheduler not initialized)")
            return True, True

        return False, True

    def _handle_intelligence_command(self, command: str) -> Tuple[bool, bool]:
        """
        处理智能层相关的 REPL 命令 (s06)

        Args:
            command: 用户输入的命令

        Returns:
            (是否已处理, 是否应该继续循环)
        """
        if not self.enable_intelligence:
            return False, True

        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/soul":
            print_info("--- SOUL.md ---")
            soul = self._bootstrap_data.get("SOUL.md", "")
            print(soul if soul else "(未找到 SOUL.md)")
            return True, True

        elif cmd == "/skills":
            print_info("--- 已发现的技能 ---")
            if not self._skills_manager or not self._skills_manager.skills:
                print_info("(未找到技能)")
            else:
                for s in self._skills_manager.skills:
                    print(f"  {BLUE}{s['invocation']}{RESET}  {s['name']} - {s['description']}")
                    print_info(f"    path: {s['path']}")
            return True, True

        elif cmd == "/memory":
            print_info("--- 记忆统计 ---")
            if self._memory_store:
                stats = self._memory_store.get_stats()
                print_info(f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符")
                print_info(f"  每日文件: {stats['daily_files']}")
                print_info(f"  每日条目: {stats['daily_entries']}")
            else:
                print_info("(记忆存储未初始化)")
            return True, True

        elif cmd == "/search":
            if not arg:
                print_warn("  用法: /search <query>")
                return True, True
            print_info(f"--- 记忆搜索: {arg} ---")
            if self._memory_store:
                results = self._memory_store.hybrid_search(arg)
                if not results:
                    print_info("(无结果)")
                else:
                    for r in results:
                        print_info(f"  [{r['score']:.4f}] {r['path']}")
                        print_info(f"    {r['snippet']}")
            else:
                print_info("(记忆存储未初始化)")
            return True, True

        elif cmd == "/prompt":
            print_info("--- 完整系统提示词 ---")
            prompt = self._build_system_prompt("show prompt")
            if len(prompt) > 3000:
                print(prompt[:3000])
                print_info(f"\n... ({len(prompt) - 3000} more chars, total {len(prompt)})")
            else:
                print(prompt)
            print_info(f"\n提示词总长度: {len(prompt)} 字符")
            return True, True

        elif cmd == "/bootstrap":
            print_info("--- Bootstrap 文件 ---")
            if not self._bootstrap_data:
                print_info("(未加载 Bootstrap 文件)")
            else:
                for name, content in self._bootstrap_data.items():
                    print(f"  {BLUE}{name}{RESET}: {len(content)} chars")
            total = sum(len(v) for v in self._bootstrap_data.values())
            print_info(f"\n  总计: {total} 字符 (上限: {settings.max_total_chars})")
            return True, True

        return False, True

    def _handle_session_command(self, command: str) -> Tuple[bool, bool]:
        """
        处理会话相关的 REPL 命令 (s03)

        Args:
            command: 用户输入的命令

        Returns:
            (是否已处理, 是否应该继续循环)
        """
        if not self._store or not self._guard:
            return False, True

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

        return False, True

    def _handle_repl_command(self, command: str) -> Tuple[bool, bool]:
        """
        处理以 / 开头的 REPL 命令。

        Args:
            command: 用户输入的命令

        Returns:
            (是否已处理, 是否应该继续循环)
        """
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()

        # 帮助命令
        if cmd == "/help":
            print_info("  Commands:")
            if self.enable_session:
                print_info("    /new [label]       Create a new session")
                print_info("    /list              List all sessions")
                print_info("    /switch <id>       Switch to a session (prefix match)")
                print_info("    /context           Show context token usage")
                print_info("    /compact           Manually compact conversation history")
            if self.enable_intelligence:
                print_info("    /soul              Show SOUL.md content")
                print_info("    /skills            List discovered skills")
                print_info("    /memory            Show memory statistics")
                print_info("    /search <query>    Search memories")
                print_info("    /prompt            Show full system prompt")
                print_info("    /bootstrap         Show loaded bootstrap files")
            if self.enable_scheduler:
                print_info("    /heartbeat         Heartbeat status")
                print_info("    /trigger           Force heartbeat now")
                print_info("    /cron              List cron jobs")
                print_info("    /cron-trigger <id> Trigger a cron job")
                print_info("    /lanes             Lane lock status")
            print_info("    /help              Show this help")
            print_info("    quit / exit        Exit the REPL")
            return True, True

        # 先尝试调度器命令 (s07)
        handled, should_continue = self._handle_scheduler_command(command)
        if handled:
            return handled, should_continue

        # 再尝试智能层命令 (s06)
        handled, should_continue = self._handle_intelligence_command(command)
        if handled:
            return handled, should_continue

        # 再尝试会话命令 (s03)
        handled, should_continue = self._handle_session_command(command)
        if handled:
            return handled, should_continue

        # 未知命令
        print_warn(f"  Unknown command: {cmd}")
        return True, True

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
            from coder.tools import TOOL_HANDLERS

            extra_info = f"Tools: {', '.join(TOOL_HANDLERS.keys())}"

        # 确定章节标题
        if self.enable_scheduler:
            section = "Section 07: 心跳与 Cron"
            if self._heartbeat and self._cron_service:
                hb_status = "on" if self._heartbeat.heartbeat_path.exists() else "off"
                cron_count = len(self._cron_service.jobs)
                extra_info = f"Heartbeat: {hb_status} ({self._heartbeat.interval}s) | Cron jobs: {cron_count}"
                if self.tools:
                    from coder.tools import TOOL_HANDLERS

                    extra_info += f" | Tools: {len(TOOL_HANDLERS)}"
        elif self.enable_intelligence:
            section = "Section 06: 智能层"
            if self._skills_manager:
                extra_info = f"Skills: {len(self._skills_manager.skills)}" + (f" | {extra_info}" if extra_info else "")
            if self._memory_store:
                stats = self._memory_store.get_stats()
                mem_info = f"Memory: {stats['daily_entries']} entries"
                extra_info = f"{mem_info}" + (f" | {extra_info}" if extra_info else "")
        elif self.enable_session:
            section = "Section 03: 会话与上下文保护"
            if extra_info:
                extra_info = f"Session: {self._store.current_session_id} | {extra_info}"
            else:
                extra_info = f"Session: {self._store.current_session_id}"
        elif self.tools:
            section = "Section 02: 工具使用"
        else:
            section = "Section 01: Agent 循环"

        print_banner(f"Miniclaw | {section}", self.model_id, extra_info=extra_info)

        if self.enable_session or self.enable_intelligence or self.enable_scheduler:
            print_info("  Type /help for commands, quit/exit to leave.")
            print()

        try:
            while True:
                # 获取调度器输出 (s07)
                if self.enable_scheduler:
                    self._drain_scheduler_output()

                # 获取用户输入
                user_input = self._get_user_input()
                if user_input is None:
                    break
                if not user_input:
                    continue

                # REPL 命令处理
                if user_input.startswith("/"):
                    handled, _ = self._handle_repl_command(user_input)
                    if handled:
                        continue

                # Lane 互斥: 用户消息始终优先 (s07)
                if self._lane_lock:
                    self._lane_lock.acquire()

                try:
                    # 自动记忆召回 (s06)
                    memory_context = ""
                    if self.enable_intelligence and self._memory_store:
                        from coder.intelligence import auto_recall

                        memory_context = auto_recall(user_input, self._memory_store)
                        if memory_context:
                            print_info("  [自动召回] 找到相关记忆")

                    # 构建系统提示词 (每轮重建，因为记忆可能被更新)
                    system_prompt = self._build_system_prompt(user_input)

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
                        response = self._call_llm(system_prompt)
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

                finally:
                    # 释放 Lane 锁 (s07)
                    if self._lane_lock:
                        self._lane_lock.release()

        finally:
            # 停止调度器 (s07)
            if self.enable_scheduler:
                self._stop_scheduler()


def run_agent_loop(
    tools: Optional[List[Dict[str, Any]]] = None,
    enable_session: bool = False,
    agent_id: str = "default",
    enable_intelligence: bool = False,
    enable_scheduler: bool = False,
) -> None:
    """
    便捷函数：运行 Agent 循环

    Args:
        tools: 工具schema列表，如果提供则启用工具支持
        enable_session: 是否启用会话持久化 (s03)
        agent_id: Agent 标识符，用于会话存储
        enable_intelligence: 是否启用智能层 (s06)
        enable_scheduler: 是否启用调度器 (s07)
    """
    loop = AgentLoop(
        tools=tools,
        enable_session=enable_session,
        agent_id=agent_id,
        enable_intelligence=enable_intelligence,
        enable_scheduler=enable_scheduler,
    )
    loop.run()
