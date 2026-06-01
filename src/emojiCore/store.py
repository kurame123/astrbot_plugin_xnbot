"""
表情数据库存储层
SQLite 操作封装
"""
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from nonebot.log import logger

from src.emojiCore.schemas import EmojiRecord

# 向量维度
VECTOR_DIM = 1024


class EmojiStore:
    """表情存储管理器"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def init_db(self) -> None:
        """初始化数据库和表结构"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emojis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                desc TEXT NOT NULL,
                vector BLOB,
                created_at REAL NOT NULL,
                source TEXT DEFAULT 'unknown',
                usage_count INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hash ON emojis(hash)")
        self._conn.commit()
        logger.info(f"[EMOJI_STORE] 数据库初始化完成: {self.db_path}")

    def get_emoji_by_hash(self, hash_str: str) -> Optional[EmojiRecord]:
        """根据 MD5 哈希查询表情"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT id, hash, file_path, desc, created_at, source, usage_count "
                "FROM emojis WHERE hash = ?",
                (hash_str,)
            )
            row = cursor.fetchone()
            if row:
                return EmojiRecord(
                    id=row["id"],
                    hash=row["hash"],
                    file_path=row["file_path"],
                    desc=row["desc"],
                    created_at=row["created_at"],
                    source=row["source"],
                    usage_count=row["usage_count"],
                )
            return None


    def insert_emoji(
        self,
        hash_str: str,
        file_path: str,
        desc: str,
        vector: list[float],
        created_at: float,
        source: str = "unknown",
    ) -> int:
        """
        插入新表情记录

        Args:
            hash_str: MD5 哈希
            file_path: 文件路径
            desc: 文本描述
            vector: 1024 维向量
            created_at: 创建时间戳
            source: 来源

        Returns:
            新记录的 ID
        """
        # 将向量转为二进制（float32）
        vector_blob = struct.pack(f"{len(vector)}f", *vector)

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO emojis (hash, file_path, desc, vector, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (hash_str, file_path, desc, vector_blob, created_at, source),
            )
            self._conn.commit()
            return cursor.lastrowid

    def update_usage_count(self, emoji_id: int) -> None:
        """增加表情使用次数"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE emojis SET usage_count = usage_count + 1 WHERE id = ?",
                (emoji_id,),
            )
            self._conn.commit()

    def load_all_vectors(
        self, limit: int = 100
    ) -> list[tuple[int, np.ndarray, str, str, str]]:
        """
        加载所有表情的向量数据

        Args:
            limit: 最大加载数量

        Returns:
            列表，每项为 (id, vector, file_path, desc, hash)
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT id, vector, file_path, desc, hash FROM emojis "
                "ORDER BY usage_count DESC, created_at DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()

        results = []
        for row in rows:
            vector_blob = row["vector"]
            if vector_blob:
                # 从二进制解析向量
                vector = np.array(
                    struct.unpack(f"{VECTOR_DIM}f", vector_blob),
                    dtype=np.float32,
                )
                results.append((
                    row["id"],
                    vector,
                    row["file_path"],
                    row["desc"],
                    row["hash"],
                ))

        return results

    def get_emoji_count(self) -> int:
        """获取表情总数"""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM emojis")
            return cursor.fetchone()[0]

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
