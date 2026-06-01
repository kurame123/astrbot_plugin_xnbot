"""
会话管理模块
为每个用户维护最近 N 条对话记录 + 场景摘要
历史消息从 Napcat 获取，仅内存缓存
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from ai_server.schemas import Message
from src.bot.core.config_loader import get_behavior_config


@dataclass
class TimestampedMessage:
    """带时间戳的消息记录"""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SessionData:
    """单个会话的数据结构"""

    history: list[Message] = field(default_factory=list)
    timestamped_history: list[TimestampedMessage] = field(default_factory=list)
    scene_summary: Optional[str] = None


class SessionManager:
    """会话管理器（纯内存）"""

    def __init__(self, default_max_length: int = 20):
        self._sessions: dict[str, SessionData] = {}
        self._default_max_length = default_max_length

    @staticmethod
    def make_session_id(user_id: str, group_id: Optional[str] = None) -> str:
        """生成会话 ID"""
        if group_id:
            return f"group:{group_id}:user:{user_id}"
        return f"user:{user_id}"

    def _get_or_create_session(self, session_id: str) -> SessionData:
        """获取或创建会话数据"""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionData()
        return self._sessions[session_id]

    def _get_max_length(self) -> int:
        """获取最大记忆长度"""
        try:
            behavior = get_behavior_config()
            return behavior.get("remember_length", self._default_max_length)
        except Exception:
            return self._default_max_length

    def _get_history_load_limit(self) -> int:
        """获取历史记录加载限制"""
        try:
            behavior = get_behavior_config()
            return behavior.get("history_load_limit", 12)
        except Exception:
            return 12

    def append_message(self, session_id: str, role: str, content: str, timestamp: float | None = None) -> None:
        """追加一条消息到会话"""
        session = self._get_or_create_session(session_id)
        ts = timestamp or time.time()
        message = Message(role=role, content=content)  # type: ignore
        session.history.append(message)
        session.timestamped_history.append(TimestampedMessage(role=role, content=content, timestamp=ts))

        # 超出长度限制时，从前面删除
        max_length = self._get_max_length()
        while len(session.history) > max_length:
            session.history.pop(0)
        while len(session.timestamped_history) > max_length:
            session.timestamped_history.pop(0)

    def get_history(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[Message]:
        """获取会话历史"""
        session = self._sessions.get(session_id)
        if session is None:
            return []

        if limit is None:
            limit = self._get_history_load_limit()

        history = session.history
        if limit > 0:
            return list(history[-limit:])

        return list(history)

    def get_timestamped_history(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[TimestampedMessage]:
        """获取带时间戳的会话历史"""
        session = self._sessions.get(session_id)
        if session is None:
            return []

        if limit is None:
            limit = self._get_history_load_limit()

        history = session.timestamped_history
        if limit > 0:
            return list(history[-limit:])

        return list(history)

    def set_scene_summary(self, session_id: str, summary: str) -> None:
        """设置会话的场景摘要"""
        session = self._get_or_create_session(session_id)
        session.scene_summary = summary

    def get_scene_summary(self, session_id: str) -> Optional[str]:
        """获取会话的场景摘要"""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return session.scene_summary

    def clear_session(self, session_id: str) -> None:
        """清空指定会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def clear_all(self) -> None:
        """清空所有会话"""
        self._sessions.clear()

    def get_session_count(self) -> int:
        """获取当前会话数量"""
        return len(self._sessions)

    def get_message_count(self, session_id: str) -> int:
        """获取指定会话的消息数量"""
        session = self._sessions.get(session_id)
        if session is None:
            return 0
        return len(session.history)

    def format_history_for_prompt(
        self, session_id: str, bot_name: str = "小雫", user_name: str = "用户"
    ) -> str:
        """格式化历史记录为 prompt 可用的文本"""
        history = self.get_history(session_id)
        if not history:
            return "（暂无聊天记录）"

        lines = []
        for msg in history:
            if msg.role == "user":
                lines.append(f"{user_name}: {msg.content}")
            elif msg.role == "assistant":
                lines.append(f"{bot_name}: {msg.content}")

        return "\n".join(lines)


# 全局单例
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
