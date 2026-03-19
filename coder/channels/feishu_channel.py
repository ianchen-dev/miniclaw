"""
飞书/Lark 通道实现

基于 webhook 实现的飞书机器人通道。

特性:
    - Webhook 事件回调
    - Token 认证
    - @提及检测
    - 多类型消息解析（文本、富文本、图片）
"""

import json
import time
from typing import Any, Dict, List

from coder.channels.base import Channel
from coder.channels.schema import ChannelAccount, InboundMessage
from coder.cli import RED, RESET, print_info


# 检查 httpx 是否可用
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class FeishuChannel(Channel):
    """
    飞书/Lark 通道。

    使用 webhook 接收消息事件，支持飞书和 Lark（国际版）。

    Attributes:
        name: 通道名称，固定为 "feishu"
    """

    name = "feishu"

    def __init__(self, account: ChannelAccount) -> None:
        """
        初始化飞书通道。

        Args:
            account: 通道账号配置

        Raises:
            RuntimeError: 如果 httpx 未安装
        """
        if not HAS_HTTPX:
            raise RuntimeError("FeishuChannel requires httpx: pip install httpx")

        self.account_id = account.account_id
        self.app_id = account.config.get("app_id", "")
        self.app_secret = account.config.get("app_secret", "")
        self._encrypt_key = account.config.get("encrypt_key", "")
        self._bot_open_id = account.config.get("bot_open_id", "")

        # 根据是否为 Lark 选择 API 域名
        is_lark = account.config.get("is_lark", False)
        self.api_base = "https://open.larksuite.com/open-apis" if is_lark else "https://open.feishu.cn/open-apis"

        # Token 缓存
        self._tenant_token: str = ""
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=15.0)

    def _refresh_token(self) -> str:
        """
        刷新 tenant_access_token。

        Returns:
            有效的 token，失败时返回空字符串
        """
        if self._tenant_token and time.time() < self._token_expires_at:
            return self._tenant_token

        try:
            resp = self._http.post(
                f"{self.api_base}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = resp.json()

            if data.get("code") != 0:
                print(f"  {RED}[feishu] Token error: {data.get('msg', '?')}{RESET}")
                return ""

            self._tenant_token = data.get("tenant_access_token", "")
            self._token_expires_at = time.time() + data.get("expire", 7200) - 300
            return self._tenant_token

        except Exception as exc:
            print(f"  {RED}[feishu] Token error: {exc}{RESET}")
            return ""

    def _bot_mentioned(self, event: Dict[str, Any]) -> bool:
        """
        检查机器人是否在消息中被 @提及。

        Args:
            event: 事件对象

        Returns:
            True 如果机器人被提及
        """
        for m in event.get("message", {}).get("mentions", []):
            mid = m.get("id", {})
            if isinstance(mid, dict) and mid.get("open_id") == self._bot_open_id:
                return True
            if isinstance(mid, str) and mid == self._bot_open_id:
                return True
            if m.get("key") == self._bot_open_id:
                return True
        return False

    def _parse_content(self, message: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
        """
        解析飞书消息内容。

        支持:
            - text: 纯文本
            - post: 富文本
            - image: 图片

        Args:
            message: 消息对象

        Returns:
            (文本内容, 媒体列表)
        """
        msg_type = message.get("msg_type", "text")
        raw = message.get("content", "{}")

        try:
            content = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return "", []

        media: List[Dict[str, Any]] = []

        if msg_type == "text":
            return content.get("text", ""), media

        if msg_type == "post":
            texts: List[str] = []
            for lc in content.values():
                if not isinstance(lc, dict):
                    continue
                title = lc.get("title", "")
                if title:
                    texts.append(title)
                for para in lc.get("content", []):
                    for node in para:
                        tag = node.get("tag")
                        if tag == "text":
                            texts.append(node.get("text", ""))
                        elif tag == "a":
                            texts.append(node.get("text", "") + " " + node.get("href", ""))
            return "\n".join(texts), media

        if msg_type == "image":
            key = content.get("image_key", "")
            if key:
                media.append({"type": "image", "key": key})
            return "[image]", media

        return "", media

    def parse_event(self, payload: Dict[str, Any], token: str = "") -> InboundMessage | None:
        """
        解析飞书事件回调。

        用于处理 webhook 推送的事件。使用简单的 token 校验进行验证。

        Args:
            payload: 事件载荷
            token: 验证 token

        Returns:
            InboundMessage，如果事件无效则返回 None
        """
        # Token 验证
        if self._encrypt_key and token and token != self._encrypt_key:
            print(f"  {RED}[feishu] Token verification failed{RESET}")
            return None

        # 处理 challenge 响应
        if "challenge" in payload:
            print_info(f"[feishu] Challenge: {payload['challenge']}")
            return None

        event = payload.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})
        user_id = sender.get("open_id", sender.get("user_id", ""))
        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "")
        is_group = chat_type == "group"

        # 群聊中检查是否被 @提及
        if is_group and self._bot_open_id and not self._bot_mentioned(event):
            return None

        text, media = self._parse_content(message)
        if not text:
            return None

        return InboundMessage(
            text=text,
            sender_id=user_id,
            channel="feishu",
            account_id=self.account_id,
            peer_id=user_id if chat_type == "p2p" else chat_id,
            media=media,
            is_group=is_group,
            raw=payload,
        )

    def receive(self) -> InboundMessage | None:
        """
        接收消息。

        飞书通道通过 webhook 接收消息，此方法始终返回 None。
        实际使用时应该通过 parse_event() 处理 webhook 回调。

        Returns:
            始终返回 None
        """
        return None

    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        """
        发送消息到指定聊天。

        Args:
            to: 目标 chat_id
            text: 消息文本
            **kwargs: 额外参数

        Returns:
            True 表示发送成功，False 表示发送失败
        """
        token = self._refresh_token()
        if not token:
            return False

        try:
            resp = self._http.post(
                f"{self.api_base}/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={"receive_id": to, "msg_type": "text", "content": json.dumps({"text": text})},
            )
            data = resp.json()

            if data.get("code") != 0:
                print(f"  {RED}[feishu] Send: {data.get('msg', '?')}{RESET}")
                return False

            return True

        except Exception as exc:
            print(f"  {RED}[feishu] Send: {exc}{RESET}")
            return False

    def close(self) -> None:
        """关闭 HTTP 客户端。"""
        self._http.close()


__all__ = [
    "FeishuChannel",
]
