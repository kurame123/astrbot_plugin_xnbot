"""
情绪系统管理器
对外主接口，处理情绪更新和获取
"""
import time

from nonebot.log import logger

from src.EmotionCore.state import EmotionStateView, get_emotion_state


async def on_new_message(role: str, text: str, timestamp: float | None = None) -> None:
    """
    收到新消息时调用，触发情绪更新（带限流）

    Args:
        role: "user" 或 "assistant"
        text: 消息文本
        timestamp: 时间戳，默认当前时间
    """
    from src.bot.core.config_loader import get_emotion_config
    from src.EmotionCore.analyzer import analyze_emotion

    if timestamp is None:
        timestamp = time.time()

    config = get_emotion_config()
    runtime_config = config.get("runtime", {})
    update_interval = runtime_config.get("update_interval_seconds", 60)
    history_limit = runtime_config.get("history_message_limit", 20)

    state = get_emotion_state()
    state.set_max_messages(history_limit)

    # 添加消息到缓存
    state.add_message(role, text, timestamp)

    # 判断是否需要调用情绪模型
    time_since_update = timestamp - state.updated_at

    if time_since_update < update_interval:
        logger.debug(
            f"[EMOTION] 距上次更新 {time_since_update:.0f}s < {update_interval}s，跳过分析"
        )
        return

    # 调用情绪分析模型
    logger.info(f"[EMOTION] 触发情绪分析，距上次更新 {time_since_update:.0f}s")
    result = await analyze_emotion(state.recent_messages)

    if result:
        state.set_emotion(
            emotion=result.emotion,
            intensity=result.intensity,
            comment=result.comment,
            timestamp=timestamp,
        )
    else:
        # 分析失败，保持当前情绪但更新时间戳（避免频繁重试）
        state.updated_at = timestamp
        logger.warning("[EMOTION] 分析失败，保持当前情绪")


def get_current_emotion(timestamp: float | None = None) -> EmotionStateView:
    """
    获取当前情绪状态（用于构造 prompt）

    如果超过 update_interval 没有新消息，自动回归默认情绪（不调用模型）

    Args:
        timestamp: 当前时间戳，默认当前时间

    Returns:
        EmotionStateView
    """
    from src.bot.core.config_loader import get_emotion_config

    if timestamp is None:
        timestamp = time.time()

    config = get_emotion_config()
    runtime_config = config.get("runtime", {})
    emotions_config = config.get("emotions", {})

    update_interval = runtime_config.get("update_interval_seconds", 60)
    default_emotion = emotions_config.get("default", "平静")

    state = get_emotion_state()

    # 如果超过 update_interval 没有新消息，回归默认情绪
    if state.last_message_at > 0:
        time_since_message = timestamp - state.last_message_at
        if time_since_message > update_interval:
            logger.debug(
                f"[EMOTION] 无消息 {time_since_message:.0f}s > {update_interval}s，回归默认情绪"
            )
            state.reset_to_default(default_emotion, timestamp)

    return state.get_view()


def get_emotion_text(timestamp: float | None = None) -> str:
    """
    获取用于 prompt 的情绪描述文本

    Args:
        timestamp: 当前时间戳

    Returns:
        情绪描述字符串
    """
    # 先调用 get_current_emotion 确保状态是最新的
    get_current_emotion(timestamp)

    state = get_emotion_state()
    return state.get_emotion_text()
