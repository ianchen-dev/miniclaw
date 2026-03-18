import logging

from fastapi import FastAPI
from fastapi.exceptions import (
    HTTPException,
)
from fastapi.requests import Request
from fastapi.responses import ORJSONResponse


_logger = logging.getLogger(__name__)


async def httpexc_handler(
    req: Request,
    exc: HTTPException,
) -> ORJSONResponse:
    content = {
        "code": exc.status_code,
        "msg": exc.detail,
    }
    return ORJSONResponse(
        content=content,
        status_code=exc.status_code,
    )


def register_exception_handlers(server: FastAPI):
    """
    统一注册自定义错误处理器
    """

    server.add_exception_handler(HTTPException, httpexc_handler)
