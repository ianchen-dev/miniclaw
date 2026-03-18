from datetime import datetime
from typing import Any

import orjson
from fastapi.responses import ORJSONResponse as RawORJSONResponse
from typing_extensions import override


class ORJSONResponse(RawORJSONResponse):
    @override
    def render(self, content: Any) -> bytes:
        # 自定义序列化选项
        return orjson.dumps(
            content,
            default=self.custom_encoder,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_SERIALIZE_DATACLASS,
        )

    def custom_encoder(self, obj: Any) -> Any:
        # 处理datetime
        if isinstance(obj, datetime):
            return obj.isoformat()

        # 处理Pydantic模型
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")

        # 处理列表和其他可迭代对象，递归处理其中的元素
        if isinstance(obj, list | tuple):
            return [self.custom_encoder(item) for item in obj]

        # 处理集合
        if isinstance(obj, set):
            return [self.custom_encoder(item) for item in obj]

        # 处理字典，递归处理键值
        if isinstance(obj, dict):
            return {k: self.custom_encoder(v) for k, v in obj.items()}

        # 处理其他类型
        raise TypeError(f"Type is not JSON serializable: {type(obj).__name__}")
