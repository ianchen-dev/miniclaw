from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """配置类"""

    # 日志配置
    log_level: str = "INFO"

    # 接口文档配置
    api_docs_enabled: bool = False

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # CORS配置
    cors_allowed_origin_patterns: List[str] = ["*"]
    cors_allowed_methods: List[str] = ["*"]
    cors_allowed_headers: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_max_age: int = 86400
    cors_expose_headers: List[str] = []

    # Agent 配置 (s01)
    api_key: Optional[str] = None
    model_id: str = "claude-sonnet-4-20250514"
    api_base_url: Optional[str] = None
    max_tokens: int = 8096

    # 工具配置 (s02)
    max_tool_output: int = 50000  # 工具输出最大字符数

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # 支持环境变量前缀
        env_prefix = ""


settings = Settings()
