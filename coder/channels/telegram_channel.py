"""
Telegram 通道实现

基于 Bot API 长轮询实现。

特性:
    - 长轮询 (long-poll, 30s)
    - offset 持久化 (磁盘)
    - 媒体组缓冲 (500ms 窗口)
    - 文本合并 (1s 窗口)
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from coder.channels.base import Channel
from coder.channels.schema import ChannelAccount, InboundMessage
from coder.cli import RED, RESET


# 检查 httpx 是否可用
try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


def _save_offset(path: Path, offset: int) -> None:
    """
    保存 Telegram 更新偏移量到文件。

    Args:
        path: 偏移量文件路径
        offset: 更新偏移量
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset))


def _load_offset(path: Path) -> int:
    """
    从文件加载 Telegram 更新偏移量。

    Args:
        path: 偏移量文件路径

    Returns:
        更新偏移量，如果文件不存在则返回 0
    """
    try:
        return int(path.read_text().strip())
    except Exception:
        return 0


class TelegramChannel(Channel):
    """
    Telegram 通道。

    使用 Bot API 长轮询接收消息，支持群组、私聊和话题。

    Attributes:
        name: 通道名称，固定为 "telegram"
        MAX_MSG_LEN: 单条消息最大长度 (4096)
    """

    name = "telegram"
    MAX_MSG_LEN = 4096

    def __init__(self, account: ChannelAccount, state_dir: Path | None = None) -> None:
        """
        初始化 Telegram 通道。

        Args:
            account: 通道账号配置
            state_dir: 状态存储目录，默认为 workspace/.state

        Raises:
            RuntimeError: 如果 httpx 未安装
        """
        if not HAS_HTTPX:
            raise RuntimeError("TelegramChannel requires httpx: pip install httpx")

        self.account_id = account.account_id
        self.base_url = f"https://api.telegram.org/bot{account.token}"
        self._http = httpx.Client(timeout=35.0)

        # 解析白名单
        raw = account.config.get("allowed_chats", "")
        self.allowed_chats: Set[str] = {c.strip() for c in raw.split(",") if c.strip()} if raw else set()

        # 偏移量持久化
        if state_dir is None:
            from coder.settings import settings

            workspace = Path(settings.session_workspace).parent
            state_dir = workspace / ".state"
        self._offset_path = state_dir / "telegram" / f"offset-{self.account_id}.txt"
        self._offset = _load_offset(self._offset_path)

        # 消息缓冲
        self._seen: Set[int] = set()
        self._media_groups: Dict[str, Dict[str, Any]] = {}
        self._text_buf: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _api(self, method: str, **params: Any) -> Dict[str, Any]:
        """
        调用 Telegram Bot API。

        Args:
            method: API 方法名
            **params: API 参数

        Returns:
            API 响应结果，失败时返回空字典
        """
        filtered = {k: v for k, v in params.items() if v is not None}
        try:
            resp = self._http.post(f"{self.base_url}/{method}", json=filtered)
            data = resp.json()
            if not data.get("ok"):
                print(f"  {RED}[telegram] {method}: {data.get('description', '?')}{RESET}")
                return {}
            return data.get("result", {})
        except Exception as exc:
            print(f"  {RED}[telegram] {method}: {exc}{RESET}")
            return {}

    def send_typing(self, chat_id: str) -> None:
        """
        发送输入指示器。

        Args:
            chat_id: 聊天ID
        """
        self._api("sendChatAction", chat_id=chat_id, action="typing")

    def poll(self) -> List[InboundMessage]:
        """
        轮询获取新消息。

        使用长轮询 (30s timeout)，处理媒体组缓冲和文本合并。

        Returns:
            准备好的消息列表
        """
        result = self._api("getUpdates", offset=self._offset, timeout=30, allowed_updates=["message"])
        if not result or not isinstance(result, list):
            return self._flush_all()

        for update in result:
            uid = update.get("update_id", 0)
            if uid >= self._offset:
                self._offset = uid + 1
                _save_offset(self._offset_path, self._offset)
            if uid in self._seen:
                continue
            self._seen.add(uid)
            if len(self._seen) > 5000:
                self._seen.clear()

            msg = update.get("message")
            if not msg:
                continue
            if msg.get("media_group_id"):
                self._buf_media(msg, update)
                continue
            inbound = self._parse(msg, update)
            if not inbound:
                continue
            if self.allowed_chats and inbound.peer_id not in self.allowed_chats:
                continue
            self._buf_text(inbound)

        return self._flush_all()

    def _flush_all(self) -> List[InboundMessage]:
        """刷新所有缓冲区，返回准备好的消息。"""
        ready = self._flush_media()
        ready.extend(self._flush_text())
        return ready

    def _buf_media(self, msg: Dict[str, Any], update: Dict[str, Any]) -> None:
        """
        缓冲媒体组消息。

        Telegram 会将相册拆分成多条消息，需要缓冲后合并。

        Args:
            msg: 消息对象
            update: 原始更新对象
        """
        mgid = msg["media_group_id"]
        if mgid not in self._media_groups:
            self._media_groups[mgid] = {"ts": time.monotonic(), "entries": []}
        self._media_groups[mgid]["entries"].append((msg, update))

    def _flush_media(self) -> List[InboundMessage]:
        """
        刷新过期的媒体组缓冲。

        媒体组在 500ms 静默后被认为是完整的。

        Returns:
            合并后的媒体组消息列表
        """
        now = time.monotonic()
        ready: List[InboundMessage] = []
        expired = [k for k, g in self._media_groups.items() if (now - g["ts"]) >= 0.5]

        for mgid in expired:
            entries = self._media_groups.pop(mgid)["entries"]
            captions: List[str] = []
            media_items: List[Dict[str, Any]] = []

            for m, _ in entries:
                if m.get("caption"):
                    captions.append(m["caption"])
                for mt in ("photo", "video", "document", "audio"):
                    if mt in m:
                        raw_m = m[mt]
                        if isinstance(raw_m, list) and raw_m:
                            fid = raw_m[-1].get("file_id", "")
                        elif isinstance(raw_m, dict):
                            fid = raw_m.get("file_id", "")
                        else:
                            fid = ""
                        if fid:
                            media_items.append({"type": mt, "file_id": fid})

            inbound = self._parse(entries[0][0], entries[0][1])
            if inbound:
                inbound.text = "\n".join(captions) if captions else "[media group]"
                inbound.media = media_items
                if not self.allowed_chats or inbound.peer_id in self.allowed_chats:
                    ready.append(inbound)

        return ready

    def _buf_text(self, inbound: InboundMessage) -> None:
        """
        缓冲文本消息。

        Telegram 会将长粘贴拆分成多个片段，缓冲后在 1s 静默后发出。

        Args:
            inbound: 入站消息
        """
        key = (inbound.peer_id, inbound.sender_id)
        now = time.monotonic()

        if key in self._text_buf:
            self._text_buf[key]["text"] += "\n" + inbound.text
            self._text_buf[key]["ts"] = now
        else:
            self._text_buf[key] = {"text": inbound.text, "msg": inbound, "ts": now}

    def _flush_text(self) -> List[InboundMessage]:
        """
        刷新过期的文本缓冲。

        文本在 1s 静默后被认为是完整的。

        Returns:
            合并后的文本消息列表
        """
        now = time.monotonic()
        ready: List[InboundMessage] = []
        expired = [k for k, b in self._text_buf.items() if (now - b["ts"]) >= 1.0]

        for key in expired:
            buf = self._text_buf.pop(key)
            buf["msg"].text = buf["text"]
            ready.append(buf["msg"])

        return ready

    def _parse(self, msg: Dict[str, Any], raw_update: Dict[str, Any]) -> InboundMessage | None:
        """
        解析 Telegram 消息为 InboundMessage。

        Args:
            msg: 消息对象
            raw_update: 原始更新对象

        Returns:
            InboundMessage，如果消息不包含文本则返回 None
        """
        chat = msg.get("chat", {})
        chat_type = chat.get("type", "")
        chat_id = str(chat.get("id", ""))
        user_id = str(msg.get("from", {}).get("id", ""))
        text = msg.get("text", "") or msg.get("caption", "")

        if not text:
            return None

        thread_id = msg.get("message_thread_id")
        is_forum = chat.get("is_forum", False)
        is_group = chat_type in ("group", "supergroup")

        # 确定 peer_id
        if chat_type == "private":
            peer_id = user_id
        elif is_group and is_forum and thread_id is not None:
            peer_id = f"{chat_id}:topic:{thread_id}"
        else:
            peer_id = chat_id

        return InboundMessage(
            text=text,
            sender_id=user_id,
            channel="telegram",
            account_id=self.account_id,
            peer_id=peer_id,
            is_group=is_group,
            raw=raw_update,
        )

    def receive(self) -> InboundMessage | None:
        """
        接收一条消息。

        Returns:
            InboundMessage 如果有消息，None 如果没有消息
        """
        msgs = self.poll()
        return msgs[0] if msgs else None

    def send(self, to: str, text: str, **kwargs: Any) -> bool:
        """
        发送消息到指定聊天。

        自动处理长消息分块和话题消息。

        Args:
            to: 目标ID，可以是 chat_id 或 chat_id:topic:thread_id
            text: 消息文本
            **kwargs: 额外参数

        Returns:
            True 表示全部发送成功，False 表示有失败
        """
        chat_id, thread_id = to, None
        if ":topic:" in to:
            parts = to.split(":topic:")
            chat_id = parts[0]
            if len(parts) > 1:
                thread_id = int(parts[1])

        ok = True
        for chunk in self._chunk(text):
            if not self._api("sendMessage", chat_id=chat_id, text=chunk, message_thread_id=thread_id):
                ok = False

        return ok

    def _chunk(self, text: str) -> List[str]:
        """
        将长消息分块。

        优先在换行符处分割。

        Args:
            text: 原始文本

        Returns:
            分块后的文本列表
        """
        if len(text) <= self.MAX_MSG_LEN:
            return [text]

        chunks: List[str] = []
        while text:
            if len(text) <= self.MAX_MSG_LEN:
                chunks.append(text)
                break
            cut = text.rfind("\n", 0, self.MAX_MSG_LEN)
            if cut <= 0:
                cut = self.MAX_MSG_LEN
            chunks.append(text[:cut])
            text = text[cut:].lstrip("\n")

        return chunks

    def close(self) -> None:
        """关闭 HTTP 客户端。"""
        self._http.close()


__all__ = [
    "TelegramChannel",
]
