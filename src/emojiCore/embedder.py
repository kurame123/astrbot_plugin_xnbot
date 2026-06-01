"""
表情文本嵌入模块
将表情描述转换为向量
"""
import numpy as np
from nonebot.log import logger


async def embed_emoji_text(desc: str) -> list[float]:
    """
    将表情描述文本转换为归一化向量

    Args:
        desc: 表情的文本描述

    Returns:
        归一化后的 1024 维向量
    """
    # 延迟导入
    from ai_server.embedding import embed_text
    from src.bot.core.config_loader import get_emoji_config

    emoji_config = get_emoji_config()
    model_name = emoji_config.get("models", {}).get(
        "embedding_model", "embedding_bge_m3"
    )

    vector = await embed_text(desc, model_name)

    if vector:
        # 归一化向量（使余弦相似度 = 内积）
        vec_array = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(vec_array)
        if norm > 0:
            vec_array = vec_array / norm
        vector = vec_array.tolist()
        logger.debug(f"[EMOJI_EMBED] 向量生成完成，维度={len(vector)}")

    return vector
