from typing import Any, List, Optional, Type

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field
from starlette.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from extended.fastapi.responses import ORJSONResponse


class Success(ORJSONResponse):
    """成功响应"""

    def __init__(
        self,
        code: int = HTTP_200_OK,
        msg: Optional[str] = "OK",
        data: Optional[Any] = None,
        **kwargs,
    ) -> None:
        content: dict[str, Any] = {
            "code": code,
            "msg": msg,
            "data": data,
        }
        # 添加额外的参数，如conversation_id, has_more, limit等
        content.update(kwargs)
        super().__init__(content=content, status_code=code)


class SuccessExtra(ORJSONResponse):
    """分页成功响应"""

    def __init__(
        self,
        code: int = HTTP_200_OK,
        msg: Optional[str] = None,
        data: Optional[Any] = None,
        total: int = 0,
        page: int = 1,
        page_size: int = 20,
        **kwargs,
    ) -> None:
        content: dict[str, Any] = {
            "code": code,
            "msg": msg,
            "data": data,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
        content.update(kwargs)
        super().__init__(
            content=content,
            status_code=code,
        )


class Fail(ORJSONResponse):
    """失败响应"""

    def __init__(
        self,
        code: int = HTTP_400_BAD_REQUEST,
        msg: Optional[str] = None,
        data: Optional[Any] = None,
        **kwargs,
    ) -> None:
        content: dict[str, Any] = {
            "code": code,
            "msg": msg,
            "data": data,
        }
        content.update(kwargs)
        super().__init__(content=content, status_code=code)


##################################################################################################


class BaseModel(PydanticBaseModel):
    """拓展Pydantic基础模型类"""

    model_config = ConfigDict(
        # 推荐添加的配置
        # 时间序列化格式
        ser_json_timedelta="iso8601",
        # 从属性中获取模型数据，方便ORM模型转换
        from_attributes=True,
        # 允许通过字段名称和别名(alias)来填充数据
        populate_by_name=True,
        # 使用枚举值而非枚举对象，使序列化更直观
        use_enum_values=True,
        # 验证默认值，确保默认值也符合字段约束
        validate_default=True,
        # JSON输出时处理无穷大和NaN值
        ser_json_inf_nan="null",
        # 严格模式设置，根据项目需要可选
        # strict=False,  # 默认为宽松模式，允许类型转换
        # 字符串处理选项
        str_strip_whitespace=True,  # 自动去除字符串首尾空白
        # 错误消息隐藏输入值，提高安全性
        # hide_input_in_errors=True,  # 在错误信息中隐藏输入值
        # 字符串缓存，提高性能
        cache_strings=True,
        # 支持中文注释文档
        use_attribute_docstrings=True,
        # 处理额外字段的策略
        extra="ignore",  # 忽略模型定义外的字段
    )


##################################################################################################


class BaseQueryParams(BaseModel):
    """基础查询参数Schema"""

    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=20, description="每页条数")


##################################################################################################


# 成功响应
class SuccessRespModel(BaseModel):
    code: int = Field(default=HTTP_200_OK, description="状态码")
    msg: str = Field(default="OK", description="状态描述")
    data: Optional[Any] = Field(default=None, description="响应数据")


class SuccessExtraRespModel(BaseModel):
    """分页成功响应"""

    code: int = Field(default=HTTP_200_OK, description="状态码")
    msg: str = Field(default="OK", description="状态描述")
    data: Optional[Any] = Field(default=None, description="响应数据")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=20, description="每页大小")


class RequestValidationRespModel(BaseModel):
    """请求参数错误响应"""

    code: int = Field(default=HTTP_422_UNPROCESSABLE_ENTITY, description="状态码")
    msg: str = Field(
        default="请求参数错误",
        description="状态描述",
        examples=["请求参数验证错误: 字段 'name' 太短，最小长度为 1"],
    )
    errors: Optional[List[Any]] = Field(
        default=None,
        description="错误详情",
        examples=[
            {
                "type": "string_too_short",
                "loc": ["body", "name"],
                "msg": "String should have at least 1 character",
                "input": "",
                "ctx": {"min_length": 1},
            }
        ],
    )


class RequestUnauthorizedRespModel(BaseModel):
    """请求未授权响应"""

    code: int = Field(default=HTTP_401_UNAUTHORIZED, description="状态码")
    msg: str = Field(
        default="请求未授权",
        description="状态描述",
        examples=["请求未授权，请先登录"],
    )


class RequestForbiddenRespModel(BaseModel):
    """请求被禁止响应"""

    code: int = Field(default=HTTP_403_FORBIDDEN, description="状态码")
    msg: str = Field(
        default="请求被禁止",
        description="状态描述",
        examples=["请求被禁止，请检查您的权限"],
    )


class RequestRateLimitRespModel(BaseModel):
    """请求频率过高响应"""

    code: int = Field(default=HTTP_429_TOO_MANY_REQUESTS, description="状态码")
    msg: str = Field(
        default="请求频率过高",
        description="状态描述",
        examples=["请求频率过高，请稍后再试。10秒后重试"],
    )


class NotFoundRespModel(BaseModel):
    """未找到响应"""

    code: int = Field(default=HTTP_404_NOT_FOUND, description="状态码")
    msg: str = Field(
        default="未找到",
        description="状态描述",
        examples=["未找到数据"],
    )


class RequestEntityTooLargeRespModel(BaseModel):
    """请求实体过大响应"""

    code: int = Field(default=HTTP_413_REQUEST_ENTITY_TOO_LARGE, description="状态码")
    msg: str = Field(
        default="请求实体过大",
        description="状态描述",
        examples=["上传的文件超出了服务器允许的最大大小"],
    )


class UnsupportedMediaTypeRespModel(BaseModel):
    """不支持的媒体类型响应"""

    code: int = Field(default=HTTP_415_UNSUPPORTED_MEDIA_TYPE, description="状态码")
    msg: str = Field(
        default="不支持的媒体类型",
        description="状态描述",
        examples=["服务器不支持此类型的文件或数据格式"],
    )


class BadRequestRespModel(BaseModel):
    """错误响应"""

    code: int = Field(default=HTTP_400_BAD_REQUEST, description="状态码")
    msg: str = Field(default="请求错误", description="状态描述")
    data: Optional[Any] = Field(default=None, description="响应数据")


class ServerErrorRespModel(BaseModel):
    """服务器错误响应"""

    code: int = Field(default=HTTP_500_INTERNAL_SERVER_ERROR, description="状态码")
    msg: str = Field(default="服务器错误", description="状态描述")
    details: Optional[Any] = Field(
        default=None,
        description="错误总结",
        examples=["服务器错误，请稍后再试"],
    )
    errors: Optional[Any] = Field(
        default=None,
        description="错误条目",
        examples=[],
    )


class ServiceUnavailableRespModel(BaseModel):
    """服务不可用响应"""

    code: int = Field(default=HTTP_503_SERVICE_UNAVAILABLE, description="状态码")
    msg: str = Field(
        default="服务暂时不可用",
        description="状态描述",
        examples=["服务器正在维护或过载，请稍后再试"],
    )
    details: Optional[Any] = Field(
        default=None,
        description="错误总结",
        examples=["预计服务恢复时间：XX分钟后"],
    )


class VoMixin(BaseModel):
    """VO模型基类"""

    @classmethod
    def get_model_class(cls, target_cls: Optional[Type["VoMixin"]] = None) -> Type["VoMixin"]:
        """获取模型类"""
        if target_cls is not None:
            return target_cls
        return cls
