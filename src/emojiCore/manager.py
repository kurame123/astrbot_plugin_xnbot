"""
表情管理核心模块
对外提供初始化、入库、检索接口
"""
import hashlib
import time
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from nonebot.log import logger

from src.emojiCore.schemas import EmojiMatch, EmojiRecord
from src.emojiCore.store import EmojiStore

# 全局存储实例
_emoji_store: Optional[EmojiStore] = None
_emoji_dir: Optional[Path] = None
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """获取 HTTP 客户端"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


def get_emoji_store() -> EmojiStore:
    """获取表情存储实例"""
    if _emoji_store is None:
        raise RuntimeError("表情系统未初始化，请先调用 init_emoji_system()")
    return _emoji_store


def init_emoji_system() -> bool:
    """
    初始化表情管理系统

    Returns:
        是否初始化成功
    """
    global _emoji_store, _emoji_dir

    try:
        from src.bot.core.config_loader import get_emoji_config

        emoji_config = get_emoji_config()
        storage_config = emoji_config.get("storage", {})

        # 获取项目根目录
        root_dir = Path(__file__).parent.parent.parent

        # 初始化表情目录
        emoji_dir_name = storage_config.get("emoji_dir", "emoji")
        _emoji_dir = root_dir / emoji_dir_name
        _emoji_dir.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        db_path_str = storage_config.get("db_path", "data/emoji.db")
        db_path = root_dir / db_path_str

        _emoji_store = EmojiStore(db_path)
        _emoji_store.init_db()

        count = _emoji_store.get_emoji_count()
        logger.info(
            f"[EMOJI_INIT] 表情系统初始化完成, "
            f"目录={_emoji_dir}, 数据库={db_path}, 表情数={count}"
        )
        return True

    except Exception as e:
        logger.error(f"[EMOJI_INIT] 初始化失败: {e}")
        return False


async def handle_incoming_emoji(
    user_id: str,
    session_id: str,
    image_url: str,
    is_animated_emoji: bool = True,
) -> Optional[EmojiRecord]:
    """
    处理收到的表情图片，入库

    Args:
        user_id: 用户 ID
        session_id: 会话 ID
        image_url: 图片 URL
        is_animated_emoji: 是否为动画表情

    Returns:
        表情记录（新建或已存在）
    """
    store = get_emoji_store()

    try:
        # 1. 下载图片
        client = _get_http_client()
        response = await client.get(image_url)
        response.raise_for_status()
        content = response.content

        # 2. 计算 MD5
        hash_str = hashlib.md5(content).hexdigest()

        # 3. 查重
        existing = store.get_emoji_by_hash(hash_str)
        if existing:
            logger.debug(f"[EMOJI_INCOMING] 表情已存在: hash={hash_str[:8]}...")
            store.update_usage_count(existing.id)
            return existing

        # 4. 确定文件扩展名并保存
        content_type = response.headers.get("content-type", "")
        if "gif" in content_type or image_url.endswith(".gif"):
            ext = ".gif"
        elif "png" in content_type or image_url.endswith(".png"):
            ext = ".png"
        elif "webp" in content_type or image_url.endswith(".webp"):
            ext = ".webp"
        else:
            ext = ".jpg"

        file_path = _emoji_dir / f"{hash_str}{ext}"
        with open(file_path, "wb") as f:
            f.write(content)

        # 5. 视觉描述
        from src.emojiCore.vision import describe_emoji_image
        desc = await describe_emoji_image(str(file_path))
        if not desc:
            desc = "未知表情"

        # 6. 生成向量
        from src.emojiCore.embedder import embed_emoji_text
        vector = await embed_emoji_text(desc)
        if not vector:
            logger.warning(f"[EMOJI_INCOMING] 向量生成失败: hash={hash_str[:8]}")
            return None

        # 7. 写入数据库
        source = "qq_animated_emoji" if is_animated_emoji else "qq_image"
        created_at = time.time()
        emoji_id = store.insert_emoji(
            hash_str=hash_str,
            file_path=str(file_path),
            desc=desc,
            vector=vector,
            created_at=created_at,
            source=source,
        )

        logger.info(
            f"[EMOJI_INCOMING] 新表情入库: id={emoji_id}, hash={hash_str[:8]}, "
            f"desc={desc[:30]}..."
        )

        return EmojiRecord(
            id=emoji_id,
            hash=hash_str,
            file_path=str(file_path),
            desc=desc,
            created_at=created_at,
            source=source,
            usage_count=0,
        )

    except Exception as e:
        logger.error(f"[EMOJI_INCOMING] 处理失败: {e}")
        return None


async def find_best_emoji_for_text(reply_text: str) -> Optional[EmojiMatch]:
    """
    根据回复文本查找最合适的表情

    Args:
        reply_text: 回复文本

    Returns:
        最佳匹配的表情，或 None
    """
    store = get_emoji_store()

    try:
        from src.bot.core.config_loader import get_emoji_config
        from src.emojiCore.embedder import embed_emoji_text
        from src.emojiCore.retriever import find_best_match

        emoji_config = get_emoji_config()
        retrieval_config = emoji_config.get("retrieval", {})
        threshold = retrieval_config.get("similarity_threshold", 0.65)
        max_candidates = retrieval_config.get("max_candidates", 100)

        # 1. 对回复文本生成向量
        query_vec = await embed_emoji_text(reply_text)
        if not query_vec:
            logger.warning("[EMOJI_FIND] 查询向量生成失败")
            return None

        query_vec = np.array(query_vec, dtype=np.float32)

        # 2. 加载候选表情向量
        candidates = store.load_all_vectors(limit=max_candidates)
        if not candidates:
            logger.debug("[EMOJI_FIND] 无可用表情")
            return None

        # 3. 查找最佳匹配
        match = find_best_match(query_vec, candidates, threshold)

        if match:
            # 更新使用次数
            store.update_usage_count(match.id)
            logger.info(
                f"[EMOJI_FIND] 匹配成功: sim={match.similarity:.3f}, "
                f"desc={match.desc[:30]}..., text={reply_text[:30]}..."
            )

        return match

    except Exception as e:
        logger.error(f"[EMOJI_FIND] 检索失败: {e}")
        return None


def close_emoji_system() -> None:
    """关闭表情系统"""
    global _emoji_store, _http_client

    if _emoji_store:
        _emoji_store.close()
        _emoji_store = None

    if _http_client:
        # 注意：这是同步关闭，异步场景需要 await
        pass

    logger.info("[EMOJI] 表情系统已关闭")
