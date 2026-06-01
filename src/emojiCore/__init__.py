"""
表情管理系统
负责表情的入库、描述生成、向量化和检索
"""
from src.emojiCore.manager import (
    init_emoji_system,
    handle_incoming_emoji,
    find_best_emoji_for_text,
)
from src.emojiCore.schemas import EmojiRecord, EmojiMatch

__all__ = [
    "init_emoji_system",
    "handle_incoming_emoji",
    "find_best_emoji_for_text",
    "EmojiRecord",
    "EmojiMatch",
]
