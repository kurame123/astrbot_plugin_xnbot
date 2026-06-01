"""
XN_Memory.faiss_manager - FAISS 索引管理
每个用户独立一个 index 文件
使用 IndexIDMap 支持按 SQLite id 映射
"""
import math
from pathlib import Path
from typing import Optional

import numpy as np
from nonebot.log import logger

# bge-m3 向量维度
VECTOR_DIM = 1024

# 默认索引目录
DEFAULT_INDEX_DIR = Path(__file__).parent.parent.parent / "data" / "vector_index"


class FaissManager:
    """
    管理多用户的 FAISS 索引
    每个用户对应 {index_dir}/{user_id}.index
    """

    def __init__(self, index_dir: str | None = None):
        self.index_dir = Path(index_dir) if index_dir else DEFAULT_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        # 内存缓存：user_id -> faiss.Index
        self._cache: dict[str, object] = {}

    def _index_path(self, user_id: str) -> Path:
        # 对 user_id 做简单清洗，避免路径注入
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
        return self.index_dir / f"{safe_id}.index"

    def _load_index(self, user_id: str):
        """加载或创建用户的 FAISS 索引"""
        import faiss

        if user_id in self._cache:
            return self._cache[user_id]

        path = self._index_path(user_id)
        if path.exists():
            index = faiss.read_index(str(path))
            logger.debug(f"[FaissManager] 加载索引 user={user_id} ntotal={index.ntotal}")
        else:
            # 新建：使用 IndexFlatIP（内积，配合归一化向量等价于余弦相似度）
            # 用 IndexIDMap 包装，支持自定义 id（对应 SQLite 的 memory.id）
            flat = faiss.IndexFlatIP(VECTOR_DIM)
            index = faiss.IndexIDMap(flat)
            logger.debug(f"[FaissManager] 新建索引 user={user_id}")

        self._cache[user_id] = index
        return index

    def _save_index(self, user_id: str) -> None:
        import faiss

        index = self._cache.get(user_id)
        if index is None:
            return
        path = self._index_path(user_id)
        faiss.write_index(index, str(path))
        logger.debug(f"[FaissManager] 保存索引 user={user_id} ntotal={index.ntotal}")

    # ========================
    # 写入
    # ========================
    def add_vector(self, user_id: str, memory_id: int, vector: list[float]) -> None:
        """
        添加一条向量记录
        vector 会被归一化（L2），确保内积 = 余弦相似度
        """
        index = self._load_index(user_id)

        vec = np.array([vector], dtype=np.float32)
        # L2 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        ids = np.array([memory_id], dtype=np.int64)
        index.add_with_ids(vec, ids)
        self._save_index(user_id)

    # ========================
    # 检索
    # ========================
    def search(
        self,
        user_id: str,
        query_vector: list[float],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """
        检索最相似的 top_k 条记录
        返回 [(memory_id, similarity_score), ...]，按相似度降序
        """
        index = self._load_index(user_id)

        if index.ntotal == 0:
            return []

        vec = np.array([query_vector], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        actual_k = min(top_k, index.ntotal)
        scores, ids = index.search(vec, actual_k)

        results = []
        for score, mid in zip(scores[0], ids[0]):
            if mid == -1:  # FAISS 无效结果
                continue
            results.append((int(mid), float(score)))

        return results

    # ========================
    # 综合评分排序
    # ========================
    @staticmethod
    def compute_final_score(
        similarity: float,
        importance: float,
        created_at: float,
        current_time: float,
    ) -> float:
        """
        综合分数 = similarity × importance × e^(-λt)
        λ 根据 importance 动态取值：
          importance < 0.3  → λ=0.3（遗忘快）
          importance < 0.6  → λ=0.1
          importance >= 0.6 → λ=0.02（遗忘慢）
        """
        days_elapsed = (current_time - created_at) / 86400.0
        if importance < 0.3:
            lam = 0.3
        elif importance < 0.6:
            lam = 0.1
        else:
            lam = 0.02

        decay = math.exp(-lam * days_elapsed)
        return similarity * importance * decay

    def search_with_score(
        self,
        user_id: str,
        query_vector: list[float],
        memories: list[dict],   # 从 SQLite 取出的记忆列表，含 id/importance/created_at
        top_k: int = 5,
        current_time: float | None = None,
    ) -> list[dict]:
        """
        检索并按综合分数排序，返回 top_k 条
        memories 是 FAISS 召回后从 SQLite 取出的完整记录
        """
        import time as _time

        now = current_time or _time.time()

        # 先做 FAISS 检索，取更多候选再重排
        raw_results = self.search(user_id, query_vector, top_k=top_k * 3)
        if not raw_results:
            return []

        # 建立 id -> similarity 映射
        sim_map = {mid: score for mid, score in raw_results}

        # 建立 id -> memory 映射
        mem_map = {m["id"]: m for m in memories}

        scored = []
        for mid, sim in sim_map.items():
            mem = mem_map.get(mid)
            if mem is None:
                continue
            final = self.compute_final_score(
                similarity=sim,
                importance=mem.get("importance", 0.5),
                created_at=mem.get("created_at", now),
                current_time=now,
            )
            scored.append({**mem, "_similarity": sim, "_final_score": final})

        scored.sort(key=lambda x: x["_final_score"], reverse=True)
        return scored[:top_k]

    # ========================
    # 统计
    # ========================
    def count(self, user_id: str) -> int:
        index = self._load_index(user_id)
        return index.ntotal

    def flush_cache(self) -> None:
        """将所有缓存中的索引写入磁盘"""
        for user_id in list(self._cache.keys()):
            self._save_index(user_id)
        self._cache.clear()
