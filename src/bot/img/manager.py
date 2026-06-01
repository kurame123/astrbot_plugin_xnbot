"""
src/bot/img/manager.py - 图片处理对外接口
收到图片 → 视觉模型描述 → 存库 + 向量化 → 返回格式化文本
"""
import asyncio
import time
from datetime import datetime

from nonebot.log import logger

from src.bot.img.store import get_image_store
from src.bot.img.vision import describe_image


async def handle_image(
    user_id: str,
    nickname: str,
    image_url: str,
    session_id: str | None = None,
    original_text: str | None = None,
) -> str:
    """
    处理用户发送的图片：
    1. 调用视觉模型生成描述
    2. 异步存库 + 向量化
    3. 返回格式化的消息文本，供拼入对话历史

    返回格式：
    [图片]这个图片展示了xxxxxxxxx
    """
    if not image_url:
        return original_text or ""

    # 生成描述
    description = await describe_image(image_url)
    if not description:
        description = "（图片内容无法识别）"

    now = time.time()

    # 异步写入数据库 + 向量化（不阻塞回复流程）
    asyncio.create_task(
        _save_image_desc(
            user_id=user_id,
            nickname=nickname,
            description=description,
            session_id=session_id,
            image_url=image_url,
            created_at=now,
        )
    )

    # 格式化消息文本
    image_text = f"[图片]{description}"
    if original_text:
        return f"{original_text} {image_text}"
    return image_text


async def _save_image_desc(
    user_id: str,
    nickname: str,
    description: str,
    session_id: str | None,
    image_url: str | None,
    created_at: float,
) -> None:
    """异步存库 + 向量化"""
    try:
        store = get_image_store()

        # 写入 SQLite
        record_id = store.insert(
            user_id=user_id,
            nickname=nickname,
            description=description,
            session_id=session_id,
            image_url=image_url,
            created_at=created_at,
        )

        # 生成向量
        from ai_server.embedding import embed_text
        vector = await embed_text(description)
        if vector:
            store.add_vector(user_id=user_id, record_id=record_id, vector=vector)

        ts = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
        logger.info(f"[ImgStore] 图片描述已存储 id={record_id} user={nickname}({user_id}) time={ts}")

    except Exception as e:
        logger.error(f"[ImgStore] 存储失败: {type(e).__name__}: {e}")


def format_image_in_history(
    nickname: str,
    description: str,
    created_at: float,
) -> str:
    """
    格式化图片记录用于对话历史显示
    格式：Sakuraba Rorin: [图片]这个图片展示了xxxxxxxxx
    """
    return f"[图片]{description}"
