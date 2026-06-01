"""
EmotionCore - 情绪系统模块
管理小雫的情绪状态，根据对话内容动态调整
"""
from src.EmotionCore.manager import on_new_message, get_current_emotion

__all__ = ["on_new_message", "get_current_emotion"]
