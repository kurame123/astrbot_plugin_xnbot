"""
情绪分析器
调用 AI 模型分析当前情绪
"""
import json
import re
from dataclasses import dataclass
from typing import Optional

from nonebot.log import logger

from src.EmotionCore.state import MessageRecord


@dataclass
class EmotionResult:
    """情绪分析结果"""
    emotion: str
    intensity: float
    comment: str


async def analyze_emotion(recent_messages: list[MessageRecord]) -> Optional[EmotionResult]:
    """
    调用 AI 模型分析情绪

    Args:
        recent_messages: 最近的消息列表

    Returns:
        EmotionResult 或 None（分析失败时）
    """
    from ai_server.client import call_model
    from ai_server.schemas import Message
    from src.bot.core.config_loader import get_emotion_config

    config = get_emotion_config()
    emotions_config = config.get("emotions", {})
    prompt_config = config.get("prompt", {})

    levels = emotions_config.get("levels", ["平静"])
    default_emotion = emotions_config.get("default", "平静")

    # 构建历史文本
    history_lines = []
    for msg in recent_messages:
        role_name = "用户" if msg.role == "user" else "小雫"
        history_lines.append(f"{role_name}：{msg.text}")
    history_text = "\n".join(history_lines)

    if not history_text.strip():
        logger.debug("[EMOTION] 无历史消息，跳过分析")
        return None

    # 构建 prompt
    levels_list = "、".join(levels)
    system_prompt = prompt_config.get("system", "").replace("{levels_list}", levels_list)
    user_prompt = prompt_config.get("user_template", "").replace("{history_text}", history_text)

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    try:
        logger.debug(f"[EMOTION] 调用情绪分析模型，消息数={len(recent_messages)}")
        response = await call_model("emotion_analyzer", messages)
        content = response.content.strip()

        # 解析 JSON
        result = _parse_emotion_response(content, levels, default_emotion)
        if result:
            logger.info(
                f"[EMOTION] 分析完成: emotion={result.emotion}, "
                f"intensity={result.intensity:.2f}, comment={result.comment}"
            )
        return result

    except Exception as e:
        logger.warning(f"[EMOTION] 分析失败: {e}")
        return None


def _parse_emotion_response(
    content: str,
    valid_levels: list[str],
    default_emotion: str,
) -> Optional[EmotionResult]:
    """
    解析模型返回的 JSON

    Args:
        content: 模型输出
        valid_levels: 有效的情绪等级列表
        default_emotion: 默认情绪

    Returns:
        EmotionResult 或 None
    """
    try:
        # 尝试提取 JSON（模型可能输出额外内容）
        json_match = re.search(r'\{[^}]+\}', content)
        if not json_match:
            logger.warning(f"[EMOTION] 无法提取 JSON: {content[:100]}")
            return None

        data = json.loads(json_match.group())

        emotion = data.get("emotion", default_emotion)
        intensity = float(data.get("intensity", 0.5))
        comment = data.get("comment", "")

        # 验证情绪是否在有效列表中
        if emotion not in valid_levels:
            logger.warning(f"[EMOTION] 无效情绪 '{emotion}'，使用默认值")
            emotion = default_emotion

        # 限制强度范围
        intensity = max(0.0, min(1.0, intensity))

        return EmotionResult(emotion=emotion, intensity=intensity, comment=comment)

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"[EMOTION] JSON 解析失败: {e}, content={content[:100]}")
        return None
