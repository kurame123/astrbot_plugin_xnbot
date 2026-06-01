"""
日志工具
支持按配置开关 debug
"""
import json
from datetime import datetime
from pathlib import Path

from nonebot.log import logger

# 直接导出 nonebot 的 logger
__all__ = [
    "logger",
    "log_context_debug",
    "log_reply_debug",
    "truncate_log",
    "log_flow",
    "log_llm_call",
    "log_progress",
]

# LLM 日志文件路径
LLM_LOG_PATH = Path(__file__).parent.parent / "data" / "logs" / "LLM_LOG.log"


def _get_debug_config() -> dict:
    """获取调试配置（延迟导入避免循环依赖）"""
    try:
        from src.bot.core.config_loader import get_debug_config

        return get_debug_config()
    except Exception:
        return {}


def _get_max_log_chars() -> int:
    """获取日志最大字符数"""
    config = _get_debug_config()
    return config.get("max_log_chars", 800)


def truncate_log(text: str, max_chars: int | None = None) -> str:
    """
    截断日志文本

    Args:
        text: 原始文本
        max_chars: 最大字符数，None 则使用配置值

    Returns:
        截断后的文本
    """
    if max_chars is None:
        max_chars = _get_max_log_chars()

    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...[truncated]"


def log_progress(step: int, total: int, message: str) -> None:
    """
    打印处理进度日志

    Args:
        step: 当前步骤
        total: 总步骤数
        message: 进度描述
    """
    logger.info(f"[{step}/{total}] {message}")


def log_context_debug(
    stage: str,
    session_id: str,
    message: str,
    **kwargs,
) -> None:
    """
    打印场景模型相关的调试日志

    Args:
        stage: 阶段标签（如 CONTEXT_PROMPT_BUILT, CONTEXT_MODEL_RESPONSE）
        session_id: 会话 ID
        message: 日志内容
        **kwargs: 额外的键值对信息
    """
    config = _get_debug_config()
    if not config.get("enable_context_debug", False):
        return

    extra_info = (
        " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    )
    log_msg = f"[{stage}] session={session_id} | {truncate_log(message)}"
    if extra_info:
        log_msg += f" | {extra_info}"

    logger.debug(log_msg)


def log_reply_debug(
    stage: str,
    session_id: str,
    message: str,
    **kwargs,
) -> None:
    """
    打印回复模型相关的调试日志

    Args:
        stage: 阶段标签（如 REPLY_PROMPT_BUILT, REPLY_MODEL_RESPONSE）
        session_id: 会话 ID
        message: 日志内容
        **kwargs: 额外的键值对信息
    """
    config = _get_debug_config()
    if not config.get("enable_reply_debug", False):
        return

    extra_info = (
        " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    )
    log_msg = f"[{stage}] session={session_id} | {truncate_log(message)}"
    if extra_info:
        log_msg += f" | {extra_info}"

    logger.debug(log_msg)


def log_flow(stage: str, session_id: str, message: str) -> None:
    """
    打印流程节点日志（INFO 级别，始终打印）

    Args:
        stage: 阶段标签
        session_id: 会话 ID
        message: 日志内容
    """
    logger.info(f"[{stage}] session={session_id} | {message}")


def log_llm_call(
    model_name: str,
    session_id: str,
    messages: list,
    response: str,
    usage: dict | None = None,
    reasoning_content: str | None = None,
) -> None:
    """
    记录 LLM 调用到文件

    Args:
        model_name: 模型名称
        session_id: 会话 ID
        messages: 输入的消息列表
        response: 模型输出
        usage: token 使用情况
        reasoning_content: 推理模型的思考过程（DeepSeek-R1 等）
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 格式化消息
    formatted_messages = []
    for msg in messages:
        if hasattr(msg, "role") and hasattr(msg, "content"):
            formatted_messages.append({"role": msg.role, "content": msg.content})
        elif isinstance(msg, dict):
            formatted_messages.append(msg)

    log_entry = {
        "timestamp": timestamp,
        "model": model_name,
        "session_id": session_id,
        "input": formatted_messages,
        "output": response,
        "reasoning": reasoning_content,
        "usage": usage,
    }

    # 确保目录存在
    LLM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 追加写入文件
    with open(LLM_LOG_PATH, "a", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"[{timestamp}] Model: {model_name} | Session: {session_id}\n")
        f.write("-" * 40 + " INPUT " + "-" * 40 + "\n")
        for msg in formatted_messages:
            f.write(f"[{msg['role']}]\n{msg['content']}\n\n")
        # 如果有思考过程，记录它
        if reasoning_content:
            f.write("-" * 38 + " REASONING " + "-" * 38 + "\n")
            f.write(f"{reasoning_content}\n\n")
        f.write("-" * 40 + " OUTPUT " + "-" * 39 + "\n")
        f.write(f"{response}\n")
        if usage:
            f.write(f"\nUsage: {json.dumps(usage)}\n")
        f.write("\n")
