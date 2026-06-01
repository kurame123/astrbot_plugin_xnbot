"""
src/bot/img/store.py - 图片描述数据库
独立 SQLite，存储用户发送的图片描述、时间戳、昵称
同时维护 FAISS 向量索引用于 Agent 检索
"""
import sqlite3
import time
from pathlib import Path
from typing import Optional

import numpy as np
from nonebot.log import logger

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "image_desc.db"
DEFAULT_INDEX_DIR = Path(__file__).parent.parent.parent.parent / "data" / "vector_index"
VECTOR_DIM = 1024


class ImageDescStore:
    """图片描述存储"""

    def __init__(
        self,
        db_path: str | None = None,
        index_dir: str | None = None,
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_dir = Path(index_dir) if index_dir else DEFAULT_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._faiss_cache: dict = {}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_db(self) -> None:
        """建表（幂等）"""
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS image_descriptions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT    NOT NULL,
                    nickname    TEXT    DEFAULT '',
                    session_id  TEXT,
                    image_url   TEXT,
                    description TEXT    NOT NULL,
                    created_at  REAL    NOT NULL   -- 精确时间戳
                );

                CREATE INDEX IF NOT EXISTS idx_imgdesc_user
                    ON image_descriptions(user_id);
                CREATE INDEX IF NOT EXISTS idx_imgdesc_time
                    ON image_descriptions(created_at);
            """)
            conn.commit()
            logger.info("[ImgStore] 数据库初始化完成")
        finally:
            conn.close()

    # ========================
    # 写入
    # ========================
    def insert(
        self,
        user_id: str,
        description: str,
        nickname: str = "",
        session_id: str | None = None,
        image_url: str | None = None,
        created_at: float | None = None,
    ) -> int:
        conn = self._connect()
        try:
            now = created_at or time.time()
            cursor = conn.execute(
                """
                INSERT INTO image_descriptions
                    (user_id, nickname, session_id, image_url, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, nickname, session_id, image_url, description, now),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    # ========================
    # FAISS
    # ========================
    def _index_path(self, user_id: str) -> Path:
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
        return self.index_dir / f"img_{safe_id}.index"

    def _load_index(self, user_id: str):
        import faiss
        if user_id in self._faiss_cache:
            return self._faiss_cache[user_id]
        path = self._index_path(user_id)
        if path.exists():
            index = faiss.read_index(str(path))
        else:
            flat = faiss.IndexFlatIP(VECTOR_DIM)
            index = faiss.IndexIDMap(flat)
        self._faiss_cache[user_id] = index
        return index

    def _save_index(self, user_id: str) -> None:
        import faiss
        index = self._faiss_cache.get(user_id)
        if index:
            faiss.write_index(index, str(self._index_path(user_id)))

    def add_vector(self, user_id: str, record_id: int, vector: list[float]) -> None:
        index = self._load_index(user_id)
        vec = np.array([vector], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        index.add_with_ids(vec, np.array([record_id], dtype=np.int64))
        self._save_index(user_id)

    def search(
        self,
        user_id: str,
        query_vector: list[float],
        top_k: int = 5,
    ) -> list[tuple[int, float]]:
        index = self._load_index(user_id)
        if index.ntotal == 0:
            return []
        vec = np.array([query_vector], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        k = min(top_k, index.ntotal)
        scores, ids = index.search(vec, k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    # ========================
    # 查询
    # ========================
    def get_by_ids(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(
                f"SELECT * FROM image_descriptions WHERE id IN ({placeholders})",
                ids,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_recent(self, user_id: str, limit: int = 10) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM image_descriptions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


# 全局单例
_store: ImageDescStore | None = None


def get_image_store() -> ImageDescStore:
    global _store
    if _store is None:
        _store = ImageDescStore()
        _store.init_db()
    return _store
