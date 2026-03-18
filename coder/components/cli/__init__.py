"""
CLI 组件 - 终端交互工具

提供命令行界面的颜色输出、输入提示等功能。
"""

# ANSI 颜色代码
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"


def colored_user() -> str:
    """返回带颜色的用户输入提示符"""
    return f"{CYAN}{BOLD}You > {RESET}"


def print_assistant(text: str) -> None:
    """打印助手回复"""
    print(f"\n{GREEN}{BOLD}Assistant:{RESET} {text}\n")


def print_info(text: str) -> None:
    """打印信息文本（灰色）"""
    print(f"{DIM}{text}{RESET}")


def print_error(text: str) -> None:
    """打印错误文本"""
    print(f"\n{YELLOW}Error: {text}{RESET}\n")


def print_banner(title: str, model: str, extra_info: str = "") -> None:
    """打印启动横幅"""
    print_info("=" * 60)
    print_info(f"  {title}")
    print_info(f"  Model: {model}")
    if extra_info:
        print_info(f"  {extra_info}")
    print_info("  输入 'quit' 或 'exit' 退出. Ctrl+C 同样有效.")
    print_info("=" * 60)
    print()


def print_goodbye() -> None:
    """打印再见消息"""
    print(f"{DIM}再见.{RESET}")


def print_tool(name: str, detail: str) -> None:
    """打印工具调用信息"""
    print(f"  {DIM}[tool: {name}] {detail}{RESET}")


def print_warn(text: str) -> None:
    """打印警告文本（黄色）"""
    print(f"{YELLOW}{text}{RESET}")


def print_session(text: str) -> None:
    """打印会话相关文本（紫色）"""
    print(f"{MAGENTA}{text}{RESET}")


def print_context_bar(estimated: int, max_tokens: int) -> None:
    """
    打印上下文使用进度条。

    Args:
        estimated: 估算的 token 数
        max_tokens: 最大 token 数
    """
    pct = (estimated / max_tokens) * 100
    bar_len = 30
    filled = int(bar_len * min(pct, 100) / 100)
    bar = "#" * filled + "-" * (bar_len - filled)
    color = GREEN if pct < 50 else (YELLOW if pct < 80 else RED)
    print_info(f"  Context usage: ~{estimated:,} / {max_tokens:,} tokens")
    print(f"  {color}[{bar}] {pct:.1f}%{RESET}")


__all__ = [
    "CYAN",
    "GREEN",
    "YELLOW",
    "RED",
    "DIM",
    "RESET",
    "BOLD",
    "MAGENTA",
    "BLUE",
    "colored_user",
    "print_assistant",
    "print_info",
    "print_error",
    "print_banner",
    "print_goodbye",
    "print_tool",
    "print_warn",
    "print_session",
    "print_context_bar",
]
