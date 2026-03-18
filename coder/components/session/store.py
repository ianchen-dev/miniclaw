"""
SessionStore - JSONL 持久化存储

会话就是 JSONL 文件。追加写入，读取时重放。

文件布局:
    workspace/.sessions/agents/{agent_id}/sessions/{session_id}.jsonl
    workspace/.sessions/agents/{agent_id}/sessions.json  (index)

JSONL 记录类型:
    {"type": "user", "content": "Hello", "ts": 1234567890}
    {"type": "assistant", "content": [...], "ts": ...}
    {"type": "tool_use", "tool_use_id": "...", "name": "...", "input": {...}, "ts": ...}
    {"type": "tool_result", "tool_use_id": "...", "content": "...", "ts": ...}
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from coder.settings import settings


class SessionStore:
    """
    管理 agent 会话的持久化存储。

    核心功能:
        - JSONL 追加写入
        - 从 JSONL 重建 API 格式的 messages[]
        - 会话索引管理
    """

    def __init__(self, agent_id: str = "default", workspace: Optional[Path] = None):
        """
        初始化 SessionStore。

        Args:
            agent_id: Agent 标识符，用于区分不同 agent 的会话
            workspace: 工作目录，默认从配置读取
        """
        self.agent_id = agent_id
        if workspace is None:
            workspace = Path(settings.session_workspace)
        self.base_dir = workspace / "agents" / agent_id / "sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir.parent / "sessions.json"
        self._index: Dict[str, Dict[str, Any]] = self._load_index()
        self.current_session_id: Optional[str] = None

    def _load_index(self) -> Dict[str, Dict[str, Any]]:
        """加载会话索引。"""
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self) -> None:
        """保存会话索引。"""
        self.index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _session_path(self, session_id: str) -> Path:
        """获取会话文件路径。"""
        return self.base_dir / f"{session_id}.jsonl"

    def create_session(self, label: str = "") -> str:
        """
        创建新会话。

        Args:
            label: 会话标签（可选）

        Returns:
            新创建的会话ID
        """
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self._index[session_id] = {
            "label": label,
            "created_at": now,
            "last_active": now,
            "message_count": 0,
        }
        self._save_index()
        self._session_path(session_id).touch()
        self.current_session_id = session_id
        return session_id

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        从 JSONL 重建 API 格式的 messages[]。

        Args:
            session_id: 会话ID

        Returns:
            重建的消息列表
        """
        path = self._session_path(session_id)
        if not path.exists():
            return []
        self.current_session_id = session_id
        return self._rebuild_history(path)

    def save_turn(self, role: str, content: Any) -> None:
        """
        保存一轮对话。

        Args:
            role: 角色 (user/assistant)
            content: 消息内容
        """
        if not self.current_session_id:
            return
        self.append_transcript(
            self.current_session_id,
            {
                "type": role,
                "content": content,
                "ts": time.time(),
            },
        )

    def save_tool_result(
        self,
        tool_use_id: str,
        name: str,
        tool_input: Dict[str, Any],
        result: str,
    ) -> None:
        """
        保存工具调用和结果。

        Args:
            tool_use_id: 工具调用ID
            name: 工具名称
            tool_input: 工具输入参数
            result: 工具执行结果
        """
        if not self.current_session_id:
            return
        ts = time.time()
        self.append_transcript(
            self.current_session_id,
            {
                "type": "tool_use",
                "tool_use_id": tool_use_id,
                "name": name,
                "input": tool_input,
                "ts": ts,
            },
        )
        self.append_transcript(
            self.current_session_id,
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result,
                "ts": ts,
            },
        )

    def append_transcript(self, session_id: str, record: Dict[str, Any]) -> None:
        """
        追加记录到 JSONL 文件。

        Args:
            session_id: 会话ID
            record: 记录字典
        """
        path = self._session_path(session_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if session_id in self._index:
            self._index[session_id]["last_active"] = datetime.now(timezone.utc).isoformat()
            self._index[session_id]["message_count"] += 1
            self._save_index()

    def _rebuild_history(self, path: Path) -> List[Dict[str, Any]]:
        """
        从 JSONL 行重建 API 格式的消息列表。

        Anthropic API 规则决定了这种重建方式:
            - 消息必须 user/assistant 交替
            - tool_use 块属于 assistant 消息
            - tool_result 块属于 user 消息

        Args:
            path: JSONL 文件路径

        Returns:
            重建的消息列表
        """
        messages: List[Dict[str, Any]] = []
        lines = path.read_text(encoding="utf-8").strip().split("\n")

        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type")

            if rtype == "user":
                messages.append(
                    {
                        "role": "user",
                        "content": record["content"],
                    }
                )

            elif rtype == "assistant":
                content = record["content"]
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )

            elif rtype == "tool_use":
                block = {
                    "type": "tool_use",
                    "id": record["tool_use_id"],
                    "name": record["name"],
                    "input": record["input"],
                }
                if messages and messages[-1]["role"] == "assistant":
                    content = messages[-1]["content"]
                    if isinstance(content, list):
                        content.append(block)
                    else:
                        messages[-1]["content"] = [
                            {"type": "text", "text": str(content)},
                            block,
                        ]
                else:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": [block],
                        }
                    )

            elif rtype == "tool_result":
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": record["tool_use_id"],
                    "content": record["content"],
                }
                # 将连续的 tool_result 合并到同一个 user 消息中
                if (
                    messages
                    and messages[-1]["role"] == "user"
                    and isinstance(messages[-1]["content"], list)
                    and messages[-1]["content"]
                    and isinstance(messages[-1]["content"][0], dict)
                    and messages[-1]["content"][0].get("type") == "tool_result"
                ):
                    messages[-1]["content"].append(result_block)
                else:
                    messages.append(
                        {
                            "role": "user",
                            "content": [result_block],
                        }
                    )

        return messages

    def list_sessions(self) -> List[Tuple[str, Dict[str, Any]]]:
        """
        列出所有会话，按最后活跃时间倒序。

        Returns:
            [(session_id, metadata), ...]
        """
        items = list(self._index.items())
        items.sort(key=lambda x: x[1].get("last_active", ""), reverse=True)
        return items


__all__ = ["SessionStore"]
