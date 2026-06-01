"""
表情检索模块
向量相似度计算和匹配
"""
import numpy as np
from typing import Optional

from nonebot.log import logger

from src.emojiCore.schemas import EmojiMatch


def compute_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    计算两个归一化向量的余弦相似度（即内积）

    Args:
        vec1: 归一化向量1
        vec2: 归一化向量2

    Returns:
        相似度分数 [-1, 1]
    """
    return float(np.dot(vec1, vec2))


def find_best_match(
    query_vec: np.ndarray,
    candidates: list[tuple[int, np.ndarray, str, str, str]],
    threshold: float = 0.65,
) -> Optional[EmojiMatch]:
    """
    从候选表情中找出最匹配的一个

    Args:
        query_vec: 查询向量（已归一化）
        candidates: 候选列表，每项为 (id, vector, file_path, desc, hash)
        threshold: 相似度阈值

    Returns:
        最佳匹配结果，或 None（无满足阈值的匹配）
    """
    if not candidates:
        return None

    best_match: Optional[EmojiMatch] = None
    best_sim = -1.0

    for emoji_id, vec, file_path, desc, hash_str in candidates:
        sim = compute_similarity(query_vec, vec)
        if sim > best_sim:
            best_sim = sim
            best_match = EmojiMatch(
                id=emoji_id,
                file_path=file_path,
                desc=desc,
                similarity=sim,
                hash=hash_str,
            )

    if best_match and best_match.similarity >= threshold:
        logger.debug(
            f"[EMOJI_RETRIEVER] 最佳匹配: sim={best_match.similarity:.3f}, "
            f"desc={best_match.desc[:30]}..."
        )
        return best_match

    logger.debug(
        f"[EMOJI_RETRIEVER] 无满足阈值的匹配, best_sim={best_sim:.3f}, "
        f"threshold={threshold}"
    )
    return None
