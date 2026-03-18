import logging
from datetime import datetime

from uvicorn import run

# 导入应用模块
from coder.application import app  # noqa: F401
from coder.common.time import ChinaTimeZone
from coder.settings import settings


_logger = logging.getLogger(__name__)


def main(cli_args=None):
    # 默认使用配置文件中的值
    cli_args = cli_args or {}

    # 当前日期，用于日志文件名
    current_date = datetime.now(tz=ChinaTimeZone).strftime("%Y-%m-%d")

    # 这部分使用配置文件
    host = settings.host
    port = settings.port
    log_level = settings.log_level
    workers = settings.workers

    run(
        app="coder.application:app",
        host=host,
        port=port,
        log_level=log_level.lower(),
        workers=workers,
        reload=False,
    )


if __name__ == "__main__":
    main()
