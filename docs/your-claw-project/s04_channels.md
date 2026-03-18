# 第 04 节: 通道 - 工程化实现

> 每个平台都不同，但它们都产生相同的 InboundMessage。

## 架构

```
    Telegram ----.                          .---- sendMessage API
    Feishu -------+-- InboundMessage ---+---- im/v1/messages
    CLI (stdin) --'    Agent Loop        '---- print(stdout)
                       (same brain)

    Telegram detail:
    getUpdates (long-poll, 30s)
        |
    offset persist (disk)
        |
    media_group_id? --yes--> buffer 500ms --> merge captions
        |no
    text buffer (1s silence) --> flush
        |
    InboundMessage --> allowed_chats filter --> agent turn
```

## 工程化架构

教程中的单文件代码被拆分为模块化组件:

```
coder/components/
├── cli/                        # CLI 工具组件 (扩展)
│   └── __init__.py             # 新增 BLUE 颜色常量
├── channels/                   # 通道组件 (新增)
│   ├── __init__.py             # 导出
│   ├── schema.py               # InboundMessage, ChannelAccount
│   ├── base.py                 # Channel ABC
│   ├── manager.py              # ChannelManager
│   ├── cli_channel.py          # CLIChannel 实现
│   ├── telegram_channel.py     # TelegramChannel 实现
│   └── feishu_channel.py       # FeishuChannel 实现
└── agent/                      # Agent 核心组件 (s05 更新)
    ├── __init__.py
    └── loop.py
```

## 核心文件说明

### 1. 配置扩展 (coder/settings.py)

添加了通道相关配置:

```python
class Settings(BaseSettings):
    # ... 原有配置 ...

    # 通道配置 (s04)
    telegram_bot_token: Optional[str] = None
    telegram_allowed_chats: str = ""  # 逗号分隔的聊天ID白名单
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_encrypt_key: str = ""  # 飞书事件订阅加密key
    feishu_bot_open_id: str = ""  # 飞书机器人 open_id，用于@检测
    feishu_is_lark: bool = False  # 是否使用 Lark (国际版飞书)
```

### 2. 数据结构 (coder/components/channels/schema.py)

#### InboundMessage

统一的消息格式，所有通道都归一化为此结构:

```python
@dataclass
class InboundMessage:
    text: str                    # 消息文本内容
    sender_id: str               # 发送者ID
    channel: str = ""            # 通道类型 ("cli", "telegram", "feishu")
    account_id: str = ""         # 接收消息的 bot 账号ID
    peer_id: str = ""            # 会话ID
    is_group: bool = False       # 是否是群组消息
    media: list = field(default_factory=list)  # 媒体附件
    raw: dict = field(default_factory=dict)    # 原始平台消息
```

`peer_id` 编码了会话范围:

| 上下文            | peer_id 格式              |
|-------------------|---------------------------|
| Telegram 私聊     | `user_id`                 |
| Telegram 群组     | `chat_id`                 |
| Telegram 话题     | `chat_id:topic:thread_id` |
| 飞书单聊          | `user_id`                 |
| 飞书群组          | `chat_id`                 |

#### ChannelAccount

每个 bot 的配置，同一通道类型可以运行多个 bot:

```python
@dataclass
class ChannelAccount:
    channel: str                  # 通道类型
    account_id: str               # bot 账号唯一标识
    token: str = ""               # 认证令牌
    config: dict = field(default_factory=dict)  # 额外配置
```

### 3. Channel 抽象基类 (coder/components/channels/base.py)

添加新平台只需实现两个方法:

```python
class Channel(ABC):
    name: str = "unknown"

    @abstractmethod
    def receive(self) -> InboundMessage | None: ...

    @abstractmethod
    def send(self, to: str, text: str, **kwargs: Any) -> bool: ...

    def close(self) -> None:
        pass
```

### 4. CLIChannel (coder/components/channels/cli_channel.py)

最简单的通道实现:

```python
class CLIChannel(Channel):
    name = "cli"

    def receive(self) -> InboundMessage | None:
        text = input(colored_user()).strip()
        if not text:
            return None
        return InboundMessage(
            text=text, sender_id="cli-user", channel="cli",
            account_id=self.account_id, peer_id="cli-user",
        )

    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        print_assistant(text)
        return True
```

### 5. TelegramChannel (coder/components/channels/telegram_channel.py)

完整的 Telegram Bot API 实现:

```python
class TelegramChannel(Channel):
    name = "telegram"
    MAX_MSG_LEN = 4096

    def __init__(self, account: ChannelAccount, state_dir: Path | None = None):
        # 初始化 HTTP 客户端
        # 解析白名单
        # 加载 offset

    def poll(self) -> List[InboundMessage]:
        # 长轮询获取更新
        # 处理媒体组缓冲
        # 处理文本合并

    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        # 自动分块
        # 支持话题消息
```

#### Telegram 特性

| 特性 | 实现方式 |
|------|---------|
| 长轮询 | getUpdates (30s timeout) |
| Offset 持久化 | 磁盘文件 |
| 媒体组缓冲 | 500ms 窗口合并 |
| 文本合并 | 1s 窗口合并 |
| 白名单过滤 | allowed_chats 配置 |
| 话题支持 | chat_id:topic:thread_id 格式 |
| 长消息分块 | 优先在换行符处分割 |

### 6. FeishuChannel (coder/components/channels/feishu_channel.py)

飞书/Lark webhook 实现:

```python
class FeishuChannel(Channel):
    name = "feishu"

    def __init__(self, account: ChannelAccount):
        # 初始化 HTTP 客户端
        # 选择 API 域名 (飞书/Lark)

    def parse_event(self, payload: dict, token: str = "") -> InboundMessage | None:
        # 解析 webhook 事件
        # Token 验证
        # @提及检测
        # 多类型消息解析

    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        # 刷新 token
        # 发送消息
```

#### 飞书特性

| 特性 | 实现方式 |
|------|---------|
| 消息接收 | Webhook 事件回调 |
| 认证 | tenant_access_token |
| Token 缓存 | 自动刷新 (提前 5 分钟) |
| @提及检测 | bot_open_id 匹配 |
| 消息类型 | text, post, image |
| 多域名 | 飞书/Lark 国际版 |

### 7. ChannelManager (coder/components/channels/manager.py)

通道注册和管理:

```python
class ChannelManager:
    def __init__(self):
        self.channels: Dict[str, Channel] = {}
        self.accounts: List[ChannelAccount] = []

    def register(self, channel: Channel) -> None: ...
    def unregister(self, name: str) -> bool: ...
    def list_channels(self) -> List[str]: ...
    def get(self, name: str) -> Channel | None: ...
    def close_all(self) -> None: ...
```

## 使用方法

### 1. 配置环境变量

```bash
# .env

# Agent 基础配置
API_KEY=your-api-key-here
MODEL_ID=claude-sonnet-4-20250514

# Telegram Bot 配置 (可选)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_CHATS=12345,67890

# 飞书配置 (可选)
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
FEISHU_BOT_OPEN_ID=ou_xxxxx
```

### 2. 基本使用

```python
from coder.components.channels import (
    ChannelManager,
    CLIChannel,
    TelegramChannel,
    FeishuChannel,
    ChannelAccount,
)
from coder.settings import settings

# 创建通道管理器
mgr = ChannelManager()

# 注册 CLI 通道
cli = CLIChannel()
mgr.register(cli)

# 注册 Telegram 通道
if settings.telegram_bot_token:
    tg_acc = ChannelAccount(
        channel="telegram",
        account_id="tg-primary",
        token=settings.telegram_bot_token,
        config={"allowed_chats": settings.telegram_allowed_chats},
    )
    mgr.accounts.append(tg_acc)
    tg_channel = TelegramChannel(tg_acc)
    mgr.register(tg_channel)

# 注册飞书通道
if settings.feishu_app_id and settings.feishu_app_secret:
    fs_acc = ChannelAccount(
        channel="feishu",
        account_id="feishu-primary",
        config={
            "app_id": settings.feishu_app_id,
            "app_secret": settings.feishu_app_secret,
            "encrypt_key": settings.feishu_encrypt_key,
            "bot_open_id": settings.feishu_bot_open_id,
            "is_lark": settings.feishu_is_lark,
        },
    )
    mgr.accounts.append(fs_acc)
    mgr.register(FeishuChannel(fs_acc))

# 列出已注册的通道
print(mgr.list_channels())  # ['cli', 'telegram', 'feishu']

# 接收和发送消息
if msg := cli.receive():
    print(f"收到消息: {msg.text}")
    mgr.get(msg.channel).send(msg.peer_id, "Hello!")

# 关闭所有通道
mgr.close_all()
```

### 3. 直接使用单个通道

```python
from coder.components.channels import CLIChannel, InboundMessage

# CLI 通道
cli = CLIChannel()
if msg := cli.receive():
    cli.send(msg.peer_id, f"你说: {msg.text}")
```

```python
from coder.components.channels import TelegramChannel, ChannelAccount

# Telegram 通道
acc = ChannelAccount(
    channel="telegram",
    account_id="my-bot",
    token="123456:ABC-DEF...",
    config={"allowed_chats": "12345"},
)
tg = TelegramChannel(acc)

# 轮询消息
if msg := tg.receive():
    tg.send(msg.peer_id, "收到!")

# 发送输入指示器
tg.send_typing(msg.peer_id)

# 发送到话题
tg.send("chat_id:topic:thread_id", "话题消息")

tg.close()
```

```python
from coder.components.channels import FeishuChannel, ChannelAccount

# 飞书通道
acc = ChannelAccount(
    channel="feishu",
    account_id="my-bot",
    config={
        "app_id": "cli_xxxxx",
        "app_secret": "xxxxx",
        "bot_open_id": "ou_xxxxx",
    },
)
fs = FeishuChannel(acc)

# 解析 webhook 事件
@app.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    payload = await request.json()
    token = request.headers.get("X-Lark-Token", "")
    if msg := fs.parse_event(payload, token):
        # 处理消息
        fs.send(msg.peer_id, "收到!")

# 发送消息
fs.send("oc_xxxxx", "Hello!")

fs.close()
```

## REPL 命令

| 命令 | 功能 |
|------|------|
| `/channels` | 列出已注册的通道 |
| `/accounts` | 显示 bot 账号配置 |

## 与教程代码的对比

| 方面 | 教程 (s04_channels.py) | 工程化实现 |
|------|------------------------|-----------|
| 通道实现 | 单文件内联 | 独立模块文件 |
| 数据结构 | 内联 dataclass | 独立 schema.py |
| 抽象基类 | 内联定义 | 独立 base.py |
| 配置管理 | 直接读取环境变量 | Pydantic Settings |
| 错误处理 | 简单 print | 统一颜色输出 |
| 依赖检查 | try/except 内联 | 条件导入 |

## 依赖

- **必需**: 无额外依赖 (CLI 通道可用)
- **可选**: `httpx` (Telegram/飞书通道需要)

```bash
pip install httpx
# 或
uv add httpx
```

## 试一试

```bash
# 仅 CLI (除了 API key 外不需要其他环境变量)
python -c "from coder.components.channels import CLIChannel; cli = CLIChannel(); msg = cli.receive(); cli.send('', f'Echo: {msg.text}' if msg else 'No input')"

# 启用 Telegram -- 在 .env 中添加:
# TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# TELEGRAM_ALLOWED_CHATS=12345,67890

# 启用飞书 -- 在 .env 中添加:
# FEISHU_APP_ID=cli_xxxxx
# FEISHU_APP_SECRET=xxxxx
```

## 后续扩展

- **s05**: 添加 AgentManager 多 agent 支持
- **s05**: 添加 WebSocket 网关
- **s05**: 添加 BindingTable 5层路由
