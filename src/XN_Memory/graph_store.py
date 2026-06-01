"""
XN_Memory.graph_store - 基于 Kùzu 的图数据库操作层

图结构：
  节点（Entity）：人物、地点、时间、事件、事物等
  边（Relation）：实体之间的关系，带描述和时间戳

向量检索：
  每个实体有一个向量（由实体名+摘要嵌入生成）
  检索时先向量召回候选实体，再沿边扩散
"""
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
from nonebot.log import logger

# Kùzu 图数据库
try:
    import kuzu
    KUZU_AVAILABLE = True
except ImportError:
    KUZU_AVAILABLE = False
    logger.warning("[GraphStore] kuzu 未安装，图记忆功能不可用。运行 pip install kuzu 安装。")

# FAISS 向量索引
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

DEFAULT_GRAPH_DIR = Path(__file__).parent.parent.parent / "data" / "graph_index"
VECTOR_DIM = 1024  # bge-m3 维度


class GraphStore:
    """
    Kùzu 图数据库 + FAISS 向量索引

    节点表：Entity(id, name, entity_type, summary, user_id, created_at, updated_at)
    边表：Relation(from, to, rel_type, description, user_id, created_at)
    """

    def __init__(self, graph_dir: str | None = None):
        self.graph_dir = Path(graph_dir) if graph_dir else DEFAULT_GRAPH_DIR
        self.graph_dir.mkdir(parents=True, exist_ok=True)

        self._db = None
        self._conn = None
        self._faiss_index = None
        # id -> entity_id 映射（FAISS 内部用整数 id）
        self._faiss_id_map: dict[int, int] = {}   # faiss_int_id -> entity_id
        self._entity_id_map: dict[int, int] = {}  # entity_id -> faiss_int_id
        self._next_faiss_id = 0

        if KUZU_AVAILABLE:
            try:
                self._init_db()
            except Exception as e:
                logger.warning(f"[GraphStore] Kùzu 初始化失败（图功能不可用）: {e}")
                self._conn = None
        if FAISS_AVAILABLE:
            self._init_faiss()

    # ========================
    # 初始化
    # ========================

    def _init_db(self):
        """初始化 Kùzu 数据库和表结构"""
        db_path = str(self.graph_dir / "graph.db")
        self._db = kuzu.Database(db_path)
        self._conn = kuzu.Connection(self._db)

        # 创建节点表
        self._conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Entity (
                id SERIAL,
                name STRING,
                entity_type STRING,
                summary STRING,
                user_id STRING,
                created_at DOUBLE,
                updated_at DOUBLE,
                PRIMARY KEY (id)
            )
        """)

        # 创建边表
        self._conn.execute("""
            CREATE REL TABLE IF NOT EXISTS Relation (
                FROM Entity TO Entity,
                rel_type STRING,
                description STRING,
                user_id STRING,
                created_at DOUBLE
            )
        """)

        logger.info(f"[GraphStore] Kùzu 图数据库初始化完成: {db_path}")

    def _init_faiss(self):
        """初始化或加载 FAISS 向量索引"""
        index_path = self.graph_dir / "entity_vectors.index"
        map_path = self.graph_dir / "entity_id_map.json"

        if index_path.exists():
            self._faiss_index = faiss.read_index(str(index_path))
            if map_path.exists():
                with open(map_path, "r") as f:
                    data = json.load(f)
                    self._faiss_id_map = {int(k): v for k, v in data["faiss_to_entity"].items()}
                    self._entity_id_map = {v: int(k) for k, v in self._faiss_id_map.items()}
                    self._next_faiss_id = data.get("next_id", len(self._faiss_id_map))
            logger.debug(f"[GraphStore] 加载 FAISS 索引，实体数={self._faiss_index.ntotal}")
        else:
            flat = faiss.IndexFlatIP(VECTOR_DIM)
            self._faiss_index = faiss.IndexIDMap(flat)
            logger.debug("[GraphStore] 新建 FAISS 实体向量索引")

    def _save_faiss(self):
        """持久化 FAISS 索引和 id 映射"""
        if not FAISS_AVAILABLE or self._faiss_index is None:
            return
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.graph_dir / "entity_vectors.index"
        map_path = self.graph_dir / "entity_id_map.json"
        faiss.write_index(self._faiss_index, str(index_path))
        with open(map_path, "w") as f:
            json.dump({
                "faiss_to_entity": self._faiss_id_map,
                "next_id": self._next_faiss_id,
            }, f)

    # ========================
    # 实体操作
    # ========================

    def get_entity_by_name(self, name: str, user_id: str) -> Optional[dict]:
        """按名称查找实体"""
        if not self._conn:
            return None
        result = self._conn.execute(
            "MATCH (e:Entity) WHERE e.name = $name AND e.user_id = $uid RETURN e.*",
            {"name": name, "uid": user_id}
        )
        rows = result.get_as_df()
        if rows.empty:
            return None
        row = rows.iloc[0]
        return {
            "id": int(row["e.id"]),
            "name": row["e.name"],
            "entity_type": row["e.entity_type"],
            "summary": row["e.summary"],
            "user_id": row["e.user_id"],
            "created_at": float(row["e.created_at"]),
            "updated_at": float(row["e.updated_at"]),
        }

    def upsert_entity(
        self,
        name: str,
        entity_type: str,
        summary: str,
        user_id: str,
        vector: list[float] | None = None,
    ) -> int:
        """
        插入或更新实体，返回实体 id。
        如果同名实体已存在，合并 summary 并更新向量。
        """
        if not self._conn:
            return -1

        now = time.time()
        existing = self.get_entity_by_name(name, user_id)

        if existing:
            entity_id = existing["id"]
            # 合并 summary（追加新信息，避免重复）
            old_summary = existing["summary"] or ""
            new_summary = old_summary if summary in old_summary else f"{old_summary}；{summary}".strip("；")
            self._conn.execute(
                "MATCH (e:Entity) WHERE e.id = $id SET e.summary = $summary, e.updated_at = $ts",
                {"id": entity_id, "summary": new_summary, "ts": now}
            )
            logger.debug(f"[GraphStore] 更新实体: {name}(id={entity_id})")
        else:
            self._conn.execute(
                """
                CREATE (e:Entity {
                    name: $name,
                    entity_type: $type,
                    summary: $summary,
                    user_id: $uid,
                    created_at: $ts,
                    updated_at: $ts
                })
                """,
                {"name": name, "type": entity_type, "summary": summary, "uid": user_id, "ts": now}
            )
            # 重新查询获取自增 id
            result = self._conn.execute(
                "MATCH (e:Entity) WHERE e.name = $name AND e.user_id = $uid RETURN e.id ORDER BY e.created_at DESC LIMIT 1",
                {"name": name, "uid": user_id}
            )
            rows = result.get_as_df()
            entity_id = int(rows.iloc[0]["e.id"])
            logger.debug(f"[GraphStore] 新建实体: {name}(id={entity_id}, type={entity_type})")

        # 更新向量索引
        if vector and FAISS_AVAILABLE and self._faiss_index is not None:
            self._upsert_vector(entity_id, vector)

        return entity_id

    def _upsert_vector(self, entity_id: int, vector: list[float]):
        """更新实体的向量（先删旧的再插新的）"""
        vec = np.array([vector], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        # 如果已有向量，先删除
        if entity_id in self._entity_id_map:
            old_faiss_id = self._entity_id_map[entity_id]
            self._faiss_index.remove_ids(np.array([old_faiss_id], dtype=np.int64))

        faiss_id = self._next_faiss_id
        self._next_faiss_id += 1
        self._faiss_index.add_with_ids(vec, np.array([faiss_id], dtype=np.int64))
        self._faiss_id_map[faiss_id] = entity_id
        self._entity_id_map[entity_id] = faiss_id
        self._save_faiss()

    # ========================
    # 关系操作
    # ========================

    def add_relation(
        self,
        from_name: str,
        to_name: str,
        rel_type: str,
        description: str,
        user_id: str,
    ) -> bool:
        """添加两个实体之间的关系边"""
        if not self._conn:
            return False

        now = time.time()
        try:
            # 先分别查出两个节点的 id（Kùzu 不支持 MATCH (a),(b) WHERE name 混合建边）
            r_a = self._conn.execute(
                "MATCH (a:Entity) WHERE a.name = $name AND a.user_id = $uid RETURN a.id LIMIT 1",
                {"name": from_name, "uid": user_id}
            )
            df_a = r_a.get_as_df()
            if df_a.empty:
                logger.debug(f"[GraphStore] 源节点不存在: {from_name}")
                return False

            r_b = self._conn.execute(
                "MATCH (b:Entity) WHERE b.name = $name AND b.user_id = $uid RETURN b.id LIMIT 1",
                {"name": to_name, "uid": user_id}
            )
            df_b = r_b.get_as_df()
            if df_b.empty:
                logger.debug(f"[GraphStore] 目标节点不存在: {to_name}")
                return False

            id_a = int(df_a.iloc[0]["a.id"])
            id_b = int(df_b.iloc[0]["b.id"])

            # 直接把整数 id 拼入查询（Kùzu 对 MATCH+CREATE 的参数绑定有兼容问题）
            # description 做转义避免注入
            safe_rel_type = rel_type.replace("'", "\\'")
            safe_desc = description.replace("'", "\\'")
            safe_uid = user_id.replace("'", "\\'")
            self._conn.execute(
                f"MATCH (a:Entity), (b:Entity) WHERE a.id = {id_a} AND b.id = {id_b} "
                f"CREATE (a)-[:Relation {{rel_type: '{safe_rel_type}', description: '{safe_desc}', "
                f"user_id: '{safe_uid}', created_at: {now}}}]->(b)"
            )
            logger.debug(f"[GraphStore] 添加关系: {from_name} -[{rel_type}]-> {to_name}")
            return True
        except Exception as e:
            logger.error(f"[GraphStore] 添加关系失败: {e}")
            return False

    # ========================
    # 检索
    # ========================

    def search_entities_by_vector(
        self,
        query_vector: list[float],
        user_id: str,
        top_k: int = 5,
        threshold: float = 0.55,
    ) -> list[dict]:
        """
        向量检索实体，返回相似度高于阈值的实体列表
        """
        if not FAISS_AVAILABLE or self._faiss_index is None or self._faiss_index.ntotal == 0:
            return []

        vec = np.array([query_vector], dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm

        actual_k = min(top_k * 3, self._faiss_index.ntotal)
        scores, ids = self._faiss_index.search(vec, actual_k)

        results = []
        for score, faiss_id in zip(scores[0], ids[0]):
            if faiss_id == -1 or float(score) < threshold:
                continue
            entity_id = self._faiss_id_map.get(int(faiss_id))
            if entity_id is None:
                continue
            entity = self._get_entity_by_id(entity_id, user_id)
            if entity:
                entity["_similarity"] = float(score)
                results.append(entity)
            if len(results) >= top_k:
                break

        return results

    def _get_entity_by_id(self, entity_id: int, user_id: str) -> Optional[dict]:
        """按 id 查询实体"""
        if not self._conn:
            return None
        result = self._conn.execute(
            "MATCH (e:Entity) WHERE e.id = $id AND e.user_id = $uid RETURN e.*",
            {"id": entity_id, "uid": user_id}
        )
        rows = result.get_as_df()
        if rows.empty:
            return None
        row = rows.iloc[0]
        return {
            "id": int(row["e.id"]),
            "name": row["e.name"],
            "entity_type": row["e.entity_type"],
            "summary": row["e.summary"],
            "user_id": row["e.user_id"],
        }

    def expand_from_entities(
        self,
        entity_ids: list[int],
        user_id: str,
        depth: int = 1,
    ) -> dict:
        """
        从种子实体出发，沿关系边扩散 depth 跳，返回子图

        返回格式：
        {
            "entities": [{"id", "name", "entity_type", "summary"}, ...],
            "relations": [{"from", "to", "rel_type", "description"}, ...]
        }
        """
        if not self._conn or not entity_ids:
            return {"entities": [], "relations": []}

        visited_ids = set(entity_ids)
        all_entities = []
        all_relations = []

        # 先拉种子实体
        for eid in entity_ids:
            e = self._get_entity_by_id(eid, user_id)
            if e:
                all_entities.append(e)

        current_frontier = set(entity_ids)

        for _ in range(depth):
            if not current_frontier:
                break
            next_frontier = set()

            for eid in current_frontier:
                # 查出边
                result = self._conn.execute(
                    """
                    MATCH (a:Entity)-[r:Relation]->(b:Entity)
                    WHERE a.id = $id AND a.user_id = $uid
                    RETURN b.id, b.name, b.entity_type, b.summary,
                           r.rel_type, r.description
                    """,
                    {"id": eid, "uid": user_id}
                )
                rows = result.get_as_df()
                for _, row in rows.iterrows():
                    bid = int(row["b.id"])
                    all_relations.append({
                        "from": self._get_entity_name(eid, user_id),
                        "to": row["b.name"],
                        "rel_type": row["r.rel_type"],
                        "description": row["r.description"],
                    })
                    if bid not in visited_ids:
                        visited_ids.add(bid)
                        next_frontier.add(bid)
                        all_entities.append({
                            "id": bid,
                            "name": row["b.name"],
                            "entity_type": row["b.entity_type"],
                            "summary": row["b.summary"],
                        })

                # 查入边
                result = self._conn.execute(
                    """
                    MATCH (a:Entity)-[r:Relation]->(b:Entity)
                    WHERE b.id = $id AND b.user_id = $uid
                    RETURN a.id, a.name, a.entity_type, a.summary,
                           r.rel_type, r.description
                    """,
                    {"id": eid, "uid": user_id}
                )
                rows = result.get_as_df()
                for _, row in rows.iterrows():
                    aid = int(row["a.id"])
                    all_relations.append({
                        "from": row["a.name"],
                        "to": self._get_entity_name(eid, user_id),
                        "rel_type": row["r.rel_type"],
                        "description": row["r.description"],
                    })
                    if aid not in visited_ids:
                        visited_ids.add(aid)
                        next_frontier.add(aid)
                        all_entities.append({
                            "id": aid,
                            "name": row["a.name"],
                            "entity_type": row["a.entity_type"],
                            "summary": row["a.summary"],
                        })

            current_frontier = next_frontier

        # 去重
        seen_entities = {}
        for e in all_entities:
            seen_entities[e["id"]] = e

        seen_relations = set()
        unique_relations = []
        for r in all_relations:
            key = (r["from"], r["to"], r["rel_type"])
            if key not in seen_relations:
                seen_relations.add(key)
                unique_relations.append(r)

        return {
            "entities": list(seen_entities.values()),
            "relations": unique_relations,
        }

    def _get_entity_name(self, entity_id: int, user_id: str) -> str:
        e = self._get_entity_by_id(entity_id, user_id)
        return e["name"] if e else str(entity_id)

    def list_entities(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """
        列出指定用户的所有实体（分页）。
        返回 (total_count, entities)
        """
        if not self._conn:
            return 0, []
        try:
            r_total = self._conn.execute(
                "MATCH (e:Entity) WHERE e.user_id = $uid RETURN COUNT(e) AS cnt",
                {"uid": user_id},
            )
            total = int(r_total.get_as_df().iloc[0]["cnt"])

            r = self._conn.execute(
                f"MATCH (e:Entity) WHERE e.user_id = $uid "
                f"RETURN e.id, e.name, e.entity_type, e.summary "
                f"ORDER BY e.created_at DESC SKIP {offset} LIMIT {limit}",
                {"uid": user_id},
            )
            df = r.get_as_df()
            entities = []
            for _, row in df.iterrows():
                entities.append({
                    "id": int(row["e.id"]),
                    "name": row["e.name"],
                    "entity_type": row["e.entity_type"],
                    "summary": row["e.summary"] or "",
                })
            return total, entities
        except Exception as e:
            logger.error(f"[GraphStore] list_entities 失败: {e}")
            return 0, []

    def count_relations(self, user_id: str) -> int:
        """统计指定用户的关系总数"""
        if not self._conn:
            return 0
        try:
            r = self._conn.execute(
                "MATCH ()-[r:Relation]->() WHERE r.user_id = $uid RETURN COUNT(r) AS cnt",
                {"uid": user_id},
            )
            return int(r.get_as_df().iloc[0]["cnt"])
        except Exception as e:
            logger.error(f"[GraphStore] count_relations 失败: {e}")
            return 0


        """将子图格式化为 Agent 可读的文本"""
        if not subgraph["entities"] and not subgraph["relations"]:
            return ""

        lines = []
        if subgraph["entities"]:
            lines.append("【相关实体】")
            for e in subgraph["entities"]:
                summary = f"：{e['summary']}" if e.get("summary") else ""
                lines.append(f"  {e['entity_type']} · {e['name']}{summary}")

        if subgraph["relations"]:
            lines.append("【关系】")
            for r in subgraph["relations"]:
                lines.append(f"  {r['from']} -[{r['rel_type']}]-> {r['to']}：{r['description']}")

        return "\n".join(lines)
