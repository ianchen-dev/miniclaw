import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from coder.common.path import LOG_FOLDER
from coder.settings import settings


# 日志级别映射字典
LEVEL_DICT: dict[str, str] = {
    "debug": "DEBUG",
    "DEBUG": "DEBUG",
    "info": "INFO",
    "INFO": "INFO",
    "warn": "WARNING",
    "WARN": "WARNING",
    "warning": "WARNING",
    "WARNING": "WARNING",
    "error": "ERROR",
    "ERROR": "ERROR",
    "critical": "CRITICAL",
    "CRITICAL": "CRITICAL",
}


def setup_logger(
    log_file: Optional[str] = LOG_FOLDER / "coder.log",
    log_level: str = settings.log_level,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 30,
) -> None:
    """
    设置全局logging配置，所有通过logging.getLogger()获取的logger都会继承此配置

    Args:
        log_file: 日志文件路径，默认为 logs/coder.log
        log_level: 日志级别
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的日志文件数量
    """

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 获取根logger
    root_logger = logging.getLogger()

    # 清除已有的handlers，避免重复添加
    root_logger.handlers.clear()

    # 设置根logger级别
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # 创建格式器
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)

    # 文件处理器（支持轮转）
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, log_level.upper()))
    file_handler.setFormatter(formatter)

    # 添加处理器到根logger
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
