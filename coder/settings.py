from typing import List

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # 支持环境变量前缀
        env_prefix = ""


settings = Settings()
