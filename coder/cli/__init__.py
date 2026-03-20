"""
CLI 组件 - 终端交互工具

提供命令行界面的颜色输出、输入提示等功能。
"""

# ANSI 颜色代码
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
ORANGE = "\033[38;5;208m"

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

    if pct < 50:
        color = GREEN
    elif pct < 80:
        color = YELLOW
    else:
        color = RED

    print_info(f"  Context usage: ~{estimated:,} / {max_tokens:,} tokens")
    print(f"  {color}[{bar}] {pct:.1f}%{RESET}")


def print_heartbeat(text: str) -> None:
    """打印心跳相关文本（蓝色）"""
    print(f"{BLUE}{BOLD}[heartbeat]{RESET} {text}")


def print_cron(text: str) -> None:
    """打印 Cron 相关文本（紫色）"""
    print(f"{MAGENTA}{BOLD}[cron]{RESET} {text}")


def print_delivery(text: str) -> None:
    """打印消息投递相关文本（蓝色）"""
    print(f"{BLUE}[delivery]{RESET} {text}")


def print_resilience(text: str) -> None:
    """打印弹性相关文本（紫色）"""
    print(f"  {MAGENTA}[resilience]{RESET} {text}")


def print_lane(lane_name: str, text: str) -> None:
    """
    打印 lane 相关文本

    根据不同的 lane 名称使用不同的颜色:
    - main: 青色
    - cron: 紫色
    - heartbeat: 蓝色
    - 其他: 黄色

    Args:
        lane_name: Lane 名称
        text: 要打印的文本
    """
    color = {
        "main": CYAN,
        "cron": MAGENTA,
        "heartbeat": BLUE,
    }.get(lane_name, YELLOW)
    print(f"{color}{BOLD}[{lane_name}]{RESET} {text}")


def print_lanes_stats(stats: dict) -> None:
    """
    打印所有 lanes 的统计信息

    Args:
        stats: CommandQueue.stats() 返回的统计字典
    """
    if not stats:
        print_info("  No lanes.")
        return

    for name, st in stats.items():
        active = st["active"]
        max_c = st["max_concurrency"]
        active_bar = "*" * active + "." * (max_c - active)
        print_info(f"  {name:12s}  active=[{active_bar}]  queued={st['queue_depth']}  max={max_c}  gen={st['generation']}")


def print_queue_status(stats: dict) -> None:
    """
    打印队列状态

    Args:
        stats: CommandQueue.stats() 返回的统计字典
    """
    total = sum(st["queue_depth"] for st in stats.values())

    if total == 0:
        print_info("  All lanes empty.")
        return

    for name, st in stats.items():
        if st["queue_depth"] > 0 or st["active"] > 0:
            print_info(f"  {name}: {st['queue_depth']} queued, {st['active']} active")


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
    "ORANGE",
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
    "print_heartbeat",
    "print_cron",
    "print_delivery",
    "print_resilience",
    "print_lane",
    "print_lanes_stats",
    "print_queue_status",
]
