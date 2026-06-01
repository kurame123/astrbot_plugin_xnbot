"""
XN_Memory.store - SQLite 数据库操作层
负责表定义、增删改查
"""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from nonebot.log import logger

# 默认数据库路径
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "xn_memory.db"


class MemoryStore:
    """SQLite 记忆存储"""

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")   # 提升并发写入性能
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ========================
    # 表初始化
    # ========================
    def init_db(self) -> None:
        """创建所有表（幂等）"""
        conn = self._connect()
        try:
            # 第一步：建表和基础索引（不含 note_type 索引，因为旧库可能还没有这列）
            conn.executescript("""
                -- 主记忆表：每条记录 = 一问一答 或 Agent 笔记
                CREATE TABLE IF NOT EXISTS memories (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         TEXT    NOT NULL,
                    session_id      TEXT,
                    nickname        TEXT    DEFAULT '',   -- 用户昵称
                    user_text       TEXT    NOT NULL,
                    bot_text        TEXT    NOT NULL,
                    keywords        TEXT    DEFAULT '',
                    importance      REAL    DEFAULT 0.5,
                    created_at      REAL    NOT NULL,
                    last_accessed_at REAL   DEFAULT 0.0,
                    note_type       TEXT    DEFAULT 'conversation'  -- conversation / agent_note
                );

                -- 按用户和时间查询的索引
                CREATE INDEX IF NOT EXISTS idx_memories_user_id
                    ON memories(user_id);
                CREATE INDEX IF NOT EXISTS idx_memories_created_at
                    ON memories(created_at);
                CREATE INDEX IF NOT EXISTS idx_memories_importance
                    ON memories(importance);

                -- 待写入队列表：异步写入时暂存
                CREATE TABLE IF NOT EXISTS memory_write_queue (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     TEXT    NOT NULL,
                    session_id  TEXT,
                    user_text   TEXT    NOT NULL,
                    bot_text    TEXT    NOT NULL,
                    created_at  REAL    NOT NULL,
                    status      TEXT    DEFAULT 'pending',  -- pending / done / failed
                    retry_count INTEGER DEFAULT 0,
                    queued_at   REAL    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_queue_status
                    ON memory_write_queue(status);
            """)
            conn.commit()

            # 第二步：兼容旧数据库——先补列，再建依赖该列的索引
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN note_type TEXT DEFAULT 'conversation'")
                conn.commit()
                logger.info("[XN_Memory] 已为旧数据库添加 note_type 字段")
            except sqlite3.OperationalError:
                pass  # 列已存在，忽略

            # 第三步：建 note_type 索引（此时列一定存在）
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_note_type ON memories(note_type)"
            )
            conn.commit()

            # XN_Core 表
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT    NOT NULL,
                    summary      TEXT    NOT NULL,
                    health_score REAL    DEFAULT 0,
                    sleep_start  REAL    NOT NULL,
                    sleep_end    REAL    NOT NULL,
                    created_at   REAL    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reflections_user
                    ON reflections(user_id);

                CREATE TABLE IF NOT EXISTS heartbeat_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      TEXT    NOT NULL,
                    trigger_time REAL    NOT NULL,
                    decision     TEXT    NOT NULL,
                    message      TEXT,
                    created_at   REAL    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_heartbeat_user
                    ON heartbeat_log(user_id);
            """)
            conn.commit()

            for col, ddl in (
                ("feeling", "TEXT DEFAULT ''"),
                ("highlights", "TEXT DEFAULT '[]'"),
            ):
                try:
                    conn.execute(f"ALTER TABLE reflections ADD COLUMN {col} {ddl}")
                    conn.commit()
                except sqlite3.OperationalError:
                    pass

            logger.info("[XN_Memory] 数据库初始化完成")
        finally:
            conn.close()

    # ========================
    # 写入
    # ========================
    def insert_memory(
        self,
        user_id: str,
        user_text: str,
        bot_text: str,
        keywords: list[str],
        importance: float,
        session_id: str | None = None,
        nickname: str = "",
        created_at: float | None = None,
        note_type: str = "conversation",
    ) -> int:
        """插入一条记忆记录，返回新记录的 id

        Args:
            note_type: 记录类型，'conversation'=对话记忆，'agent_note'=Agent 主动笔记
        """
        conn = self._connect()
        try:
            now = created_at or time.time()
            keywords_str = ",".join(keywords) if isinstance(keywords, list) else keywords
            cursor = conn.execute(
                """
                INSERT INTO memories
                    (user_id, session_id, nickname, user_text, bot_text, keywords, importance, created_at, last_accessed_at, note_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?)
                """,
                (user_id, session_id, nickname, user_text, bot_text, keywords_str, importance, now, note_type),
            )
            conn.commit()
            new_id = cursor.lastrowid
            logger.debug(f"[XN_Memory] 写入记忆 id={new_id} user={user_id}({nickname}) importance={importance:.2f} type={note_type}")
            return new_id
        finally:
            conn.close()

    def enqueue_write(
        self,
        user_id: str,
        user_text: str,
        bot_text: str,
        session_id: str | None = None,
        nickname: str = "",
        created_at: float | None = None,
    ) -> int:
        """将待写入记录加入队列（异步写入的第一步）"""
        conn = self._connect()
        try:
            now = time.time()
            cursor = conn.execute(
                """
                INSERT INTO memory_write_queue
                    (user_id, session_id, user_text, bot_text, created_at, status, retry_count, queued_at)
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?)
                """,
                (user_id, session_id, user_text, bot_text, created_at or now, now),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def mark_queue_done(self, queue_id: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE memory_write_queue SET status='done' WHERE id=?",
                (queue_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_queue_failed(self, queue_id: int) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE memory_write_queue SET status='failed', retry_count=retry_count+1 WHERE id=?",
                (queue_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def get_pending_queue(self, limit: int = 20) -> list[dict]:
        """获取待处理的队列记录"""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM memory_write_queue
                WHERE status='pending' AND retry_count < 3
                ORDER BY queued_at ASC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ========================
    # 查询
    # ========================
    def get_by_ids(self, ids: list[int]) -> list[dict]:
        """按 id 列表批量查询记忆（供 Agent 检索后取完整文本）"""
        if not ids:
            return []
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(ids))
            cursor = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})",
                ids,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_by_id(self, memory_id: int) -> dict | None:
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_recent(self, user_id: str, limit: int = 20) -> list[dict]:
        """获取某用户最近的记忆记录"""
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM memories
                WHERE user_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_recent_conversations(
        self,
        user_id: str,
        count: int = 20,
        before_timestamp: float | None = None,
    ) -> list[dict]:
        """
        读取用户的对话历史，返回拆分后的消息列表。

        和 get_recent 的区别：
        - 只返回 note_type='conversation' 的记录（排除 Agent 笔记）
        - 每条记忆拆成两条消息（user + assistant），格式与 history_for_agent 一致
        - 支持 before_timestamp 翻页（读更早的历史）

        Args:
            user_id: 用户 id
            count: 返回的记忆对数量（每对 = 1 user + 1 assistant，实际消息数 = count * 2）
            before_timestamp: 只返回这个时间戳之前的记录（用于翻页）

        Returns:
            [{"role": "user"|"assistant", "content": str, "timestamp": float}, ...]
            按时间升序排列（最早的在前）
        """
        conn = self._connect()
        try:
            if before_timestamp is not None:
                cursor = conn.execute(
                    """
                    SELECT user_text, bot_text, created_at FROM memories
                    WHERE user_id=? AND note_type='conversation' AND created_at < ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, before_timestamp, count),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT user_text, bot_text, created_at FROM memories
                    WHERE user_id=? AND note_type='conversation'
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, count),
                )
            rows = cursor.fetchall()
        finally:
            conn.close()

        # 倒序取出后翻转为升序，再拆成两条
        messages = []
        for row in reversed(rows):
            messages.append({
                "role": "user",
                "content": row["user_text"],
                "timestamp": row["created_at"],
            })
            messages.append({
                "role": "assistant",
                "content": row["bot_text"],
                "timestamp": row["created_at"],
            })
        return messages

    # ========================
    # 唤醒更新
    # ========================
    def touch_memory(self, memory_id: int) -> None:
        """
        记忆被检索命中时调用：
        - 更新 last_accessed_at
        - 根据距上次访问的间隔动态提升 importance（上限 1.0）

        间隔效应：间隔越长，boost 越大（最大 0.15）
        边际效应：短时间内反复命中，boost 趋近于 0
        公式：boost = 0.15 × (1 - e^(-interval_days / 7))
          - 间隔 0 天 → boost ≈ 0.00
          - 间隔 1 天 → boost ≈ 0.02
          - 间隔 3 天 → boost ≈ 0.06
          - 间隔 7 天 → boost ≈ 0.09
          - 间隔 30 天 → boost ≈ 0.14
          - 间隔 ∞   → boost → 0.15
        """
        import math
        conn = self._connect()
        try:
            now = time.time()
            # 先读取上次访问时间
            cursor = conn.execute(
                "SELECT last_accessed_at FROM memories WHERE id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return

            last_accessed_at = row[0] or 0.0
            interval_days = (now - last_accessed_at) / 86400.0

            # 间隔效应公式：boost = MAX_BOOST × (1 - e^(-interval / SCALE))
            MAX_BOOST = 0.15
            SCALE = 7.0  # 时间尺度（天），7天时达到约63%的最大boost
            boost = MAX_BOOST * (1.0 - math.exp(-interval_days / SCALE))

            conn.execute(
                """
                UPDATE memories
                SET last_accessed_at = ?,
                    importance = MIN(1.0, importance + ?)
                WHERE id = ?
                """,
                (now, boost, memory_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ========================
    # 统计
    # ========================
    def count_by_user(self, user_id: str) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE user_id=?", (user_id,)
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    # ========================
    # 时间范围查询（XN_Core 用）
    # ========================
    def get_conversations_in_range(
        self,
        user_id: str,
        since: float | None = None,
        before: float | None = None,
        count: int = 200,
    ) -> list[dict]:
        """
        按时间范围查询对话记录，返回拆分后的消息列表。

        比 get_recent_conversations 更灵活：支持 since + before 双向过滤。
        供 XN_Core 反思/打分/心跳使用。

        Args:
            user_id: 用户 id
            since: 只返回 >= 这个时间戳的记录
            before: 只返回 < 这个时间戳的记录
            count: 最大返回记忆对数量

        Returns:
            [{"role": "user"|"assistant", "content": str, "timestamp": float}, ...]
            按时间升序
        """
        conn = self._connect()
        try:
            conditions = ["user_id=?", "note_type='conversation'"]
            params: list = [user_id]
            if since is not None:
                conditions.append("created_at >= ?")
                params.append(since)
            if before is not None:
                conditions.append("created_at < ?")
                params.append(before)
            where = " AND ".join(conditions)
            params.append(count)
            cursor = conn.execute(
                f"SELECT user_text, bot_text, created_at FROM memories "
                f"WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params,
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        messages = []
        for row in reversed(rows):
            messages.append({"role": "user", "content": row["user_text"], "timestamp": row["created_at"]})
            messages.append({"role": "assistant", "content": row["bot_text"], "timestamp": row["created_at"]})
        return messages

    # ========================
    # XN_Core: 反思
    # ========================
    def insert_reflection(
        self,
        user_id: str,
        summary: str,
        sleep_start: float,
        sleep_end: float,
        health_score: float = 0.0,
        feeling: str = "",
        highlights: list | None = None,
    ) -> int:
        hl = json.dumps(highlights or [], ensure_ascii=False)
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO reflections (user_id, summary, feeling, highlights, "
                "health_score, sleep_start, sleep_end, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id, summary, feeling, hl, health_score,
                    sleep_start, sleep_end, time.time(),
                ),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def count_sleep_period_user_messages(
        self, user_id: str, since: float,
    ) -> int:
        """统计睡眠期间用户侧消息条数（含未回复落库）"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE user_id=? AND note_type='conversation' "
                "AND created_at >= ? AND user_text NOT LIKE '[睡眠期间未读%'",
                (user_id, since),
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def count_heartbeat_today(self, user_id: str | None = None) -> dict:
        """今日心跳 skip/send 统计"""
        from datetime import datetime as dt
        conn = self._connect()
        try:
            today_start = dt.now().replace(
                hour=0, minute=0, second=0, microsecond=0,
            ).timestamp()
            base = "FROM heartbeat_log WHERE created_at >= ?"
            params: list = [today_start]
            if user_id:
                base += " AND user_id = ?"
                params.append(user_id)
            send = conn.execute(
                f"SELECT COUNT(*) {base} AND decision='send'", params,
            ).fetchone()[0]
            skip = conn.execute(
                f"SELECT COUNT(*) {base} AND decision='skip'", params,
            ).fetchone()[0]
            return {"send": send, "skip": skip}
        finally:
            conn.close()

    def update_reflection_score(self, ref_id: int, health_score: float) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE reflections SET health_score=? WHERE id=?",
                (health_score, ref_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_reflections(self, user_id: str, limit: int = 3) -> list[dict]:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM reflections WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ========================
    # XN_Core: 心跳日志
    # ========================
    def insert_heartbeat_log(
        self,
        user_id: str,
        trigger_time: float,
        decision: str,
        message: str | None = None,
    ) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO heartbeat_log (user_id, trigger_time, decision, message, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, trigger_time, decision, message, time.time()),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
