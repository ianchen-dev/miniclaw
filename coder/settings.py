from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """配置类"""

    # 日志配置
    log_level: str = "INFO"

    # Agent 配置 (s01)
    api_key: Optional[str] = None
    model_id: str = "claude-sonnet-4-20250514"
    api_base_url: Optional[str] = None
    max_tokens: int = 8096

    # 工具配置 (s02)
    max_tool_output: int = 50000  # 工具输出最大字符数

    # 会话配置 (s03)
    context_safe_limit: int = 180000  # 上下文安全限制 (tokens)
    session_workspace: str = "workspace/.sessions"  # 会话存储目录

    # 通道配置 (s04)
    telegram_bot_token: Optional[str] = None
    telegram_allowed_chats: str = ""  # 逗号分隔的聊天ID白名单
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_encrypt_key: str = ""  # 飞书事件订阅加密key
    feishu_bot_open_id: str = ""  # 飞书机器人 open_id，用于@检测
    feishu_is_lark: bool = False  # 是否使用 Lark (国际版飞书)

    # 网关配置 (s05)
    gateway_enabled: bool = False  # 是否启用 WebSocket 网关
    gateway_host: str = "localhost"  # 网关监听地址
    gateway_port: int = 8765  # 网关监听端口
    agents_base_dir: str = "workspace/.agents"  # Agent 配置目录
    max_concurrent_agents: int = 4  # 最大并发 agent 数量

    # 智能层配置 (s06)
    workspace_dir: str = "workspace"  # 工作区目录
    max_file_chars: int = 20000  # 单个 Bootstrap 文件最大字符数
    max_total_chars: int = 150000  # Bootstrap 文件总字符数上限
    max_skills: int = 150  # 最大技能数量
    max_skills_prompt: int = 30000  # 技能提示词块最大字符数
    memory_top_k: int = 5  # 记忆搜索默认返回数量
    memory_decay_rate: float = 0.01  # 记忆时间衰减率
    mmr_lambda: float = 0.7  # MMR 重排序的 lambda 参数

    # 心跳与 Cron 配置 (s07)
    heartbeat_interval: float = 1800.0  # 心跳间隔 (秒)
    heartbeat_active_start: int = 9  # 心跳活跃开始时间 (小时, 0-23)
    heartbeat_active_end: int = 22  # 心跳活跃结束时间 (小时, 0-23)
    heartbeat_max_queue_size: int = 10  # 心跳输出队列最大大小
    cron_auto_disable_threshold: int = 5  # Cron 任务连续错误自动禁用阈值

    # 消息投递配置 (s08)
    delivery_queue_dir: str = ""  # 投递队列目录，空则使用 workspace/.delivery-queue
    delivery_max_retries: int = 5  # 最大重试次数
    delivery_verbose: bool = True  # 是否打印投递详细信息

    # 弹性配置 (s09)
    resilience_fallback_models: str = ""  # 备选模型链，逗号分隔 (如: "claude-haiku-4-20250514,gpt-4o-mini")
    resilience_max_overflow_compaction: int = 3  # 最大溢出压缩尝试次数

    # 并发配置 (s10)
    lane_main_max_concurrency: int = 1  # main lane 最大并发数
    lane_cron_max_concurrency: int = 1  # cron lane 最大并发数
    lane_heartbeat_max_concurrency: int = 1  # heartbeat lane 最大并发数

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # 支持环境变量前缀
        env_prefix = ""


settings = Settings()
