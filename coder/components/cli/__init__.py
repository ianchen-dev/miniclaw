"""
CLI 组件 - 终端交互工具

提供命令行界面的颜色输出、输入提示等功能。
"""

# ANSI 颜色代码
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


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


def print_banner(title: str, model: str) -> None:
    """打印启动横幅"""
    print_info("=" * 60)
    print_info(f"  {title}")
    print_info(f"  Model: {model}")
    print_info("  输入 'quit' 或 'exit' 退出. Ctrl+C 同样有效.")
    print_info("=" * 60)
    print()


def print_goodbye() -> None:
    """打印再见消息"""
    print(f"{DIM}再见.{RESET}")


__all__ = [
    "CYAN",
    "GREEN",
    "YELLOW",
    "DIM",
    "RESET",
    "BOLD",
    "colored_user",
    "print_assistant",
    "print_info",
    "print_error",
    "print_banner",
    "print_goodbye",
]
