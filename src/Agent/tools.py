"""
Agent.tools - Agent 可调用的工具函数
检索工具：生成关键词向量 → FAISS 搜索 → 取 SQLite 完整文本 → 综合评分排序
"""
import json
import time
from typing import Optional

from nonebot.log import logger


async def get_character_info() -> str:
    """
    工具：读取小雫的角色设定和性格信息。

    用途：
    - 需要判断小雫在当前情境下会有什么反应时调用
    - 给 hint 时参考小雫的说话风格和性格特点
    - 不确定小雫对某类话题的态度时调用

    Returns:
        小雫的角色设定文本（short_desc + profile + speaking_style）
    """
    from src.bot.core.config_loader import get_bot_config, get_character_config
    try:
        bot_config = get_bot_config()
        char = bot_config.get("character", {})
        personality = bot_config.get("personality", {})

        short_desc = char.get("short_desc", "")
        profile = char.get("profile", "")
        speaking_style = personality.get("speaking_style", "")
        traits = personality.get("traits", [])

        parts = []
        if short_desc:
            parts.append(f"【基本介绍】{short_desc}")
        if profile:
            parts.append(f"【性格详情】{profile}")
        if traits:
            parts.append(f"【性格关键词】{'、'.join(traits)}")
        if speaking_style:
            parts.append(f"【说话风格】{speaking_style}")

        result = "\n".join(parts)
        logger.debug(f"[Agent.tools] get_character_info 返回 {len(result)} 字")
        return result or "（未找到角色设定）"
    except Exception as e:
        logger.warning(f"[Agent.tools] get_character_info 失败: {e}")
        return "（角色设定读取失败）"


async def think(content: str) -> str:
    """
    工具：纯思考步骤，不调用任何外部工具。

    用途：
    - 分析用户消息的深层意图
    - 总结已检索到的信息，决定是否继续搜索
    - 在多工具调用之间做推理衔接

    Args:
        content: 思考内容

    Returns:
        思考记录的确认字符串（供 Agent 继续推理）
    """
    logger.debug(f"[Agent.tools] think: {content[:100]}")
    return f"[思考记录] {content}"


async def save_note(
    user_id: str,
    content: str,
    tags: list[str],
    importance: float = 0.8,
) -> str:
    """
    工具：Agent 主动记录重要信息。

    用于记录 Agent 在检索过程中发现的高价值信息，
    例如"用户提到生日是3月15日"、"用户下周要去成都出差"。
    这类信息比普通对话记忆更重要，会被优先检索。

    Args:
        user_id: 用户 id
        content: 笔记内容（一句话描述重要信息）
        tags: 标签列表（用于向量检索，如 ["生日", "个人信息"]）
        importance: 重要性分数（默认 0.8，高于普通对话记忆的 0.5）

    Returns:
        操作结果字符串
    """
    from src.XN_Memory import get_store, get_faiss

    store = get_store()

    # 先写入 SQLite（不依赖向量，保证笔记一定能保存）
    memory_id = store.insert_memory(
        user_id=user_id,
        user_text=content,
        bot_text="",
        keywords=tags,
        importance=importance,
        note_type="agent_note",
    )

    # 向量生成失败不影响笔记保存（降级处理）
    try:
        from ai_server.embedding import embed_text
        embed_input = " ".join(tags) + " " + content
        vector = await embed_text(embed_input)
        if vector:
            faiss_mgr = get_faiss()
            faiss_mgr.add_vector(user_id=user_id, memory_id=memory_id, vector=vector)
            logger.info(f"[Agent.tools] save_note 完成 id={memory_id} user={user_id} tags={tags}")
        else:
            logger.warning(f"[Agent.tools] save_note 向量为空，仅保存文本 id={memory_id}")
    except Exception as e:
        logger.warning(f"[Agent.tools] save_note 向量写入失败（笔记已保存）: {e}")

    return f"已记录：{content}"


async def read_conversation(
    user_id: str,
    count: int = 20,
    before_timestamp: float | None = None,
) -> list[dict]:
    """
    工具：读取用户的历史对话记录。

    和 search_memory 的区别：
    - 不做向量检索，直接按时间顺序读取
    - 适合"上个月我们聊了什么"、"最近几次对话"这类时序性查询
    - 返回格式与 history_for_agent 一致，Agent 可直接使用

    Args:
        user_id: 用户 id
        count: 读取的对话对数量（每对 = 1 user + 1 assistant）
        before_timestamp: 只读取这个时间戳之前的记录（用于翻页读更早的历史）

    Returns:
        [{"role": "user"|"assistant", "content": str, "timestamp": float}, ...]
        按时间升序排列
    """
    from src.XN_Memory import get_store

    store = get_store()
    messages = store.get_recent_conversations(
        user_id=user_id,
        count=count,
        before_timestamp=before_timestamp,
    )
    logger.debug(f"[Agent.tools] read_conversation user={user_id} count={count} got={len(messages)} messages")
    return messages


async def search_memory(
    user_id: str,
    keywords: list[str],
    top_k: int = 5,
    time_range: tuple[float, float] | None = None,
) -> list[dict]:
    """
    工具：根据关键词检索记忆

    Args:
        user_id: 用户 id
        keywords: 关键词列表，用于生成查询向量
        top_k: 返回结果数量
        time_range: 可选时间范围过滤 (start_timestamp, end_timestamp)，
                    例如 (time.time() - 7*86400, time.time()) 表示最近7天
    """
    from ai_server.embedding import embed_text
    from src.XN_Memory import get_store, get_faiss
    from src.XN_Memory.faiss_manager import FaissManager

    if not keywords:
        return []

    keyword_text = " ".join(keywords)

    try:
        query_vector = await embed_text(keyword_text)
    except Exception as e:
        logger.error(f"[Agent.tools] 嵌入模型调用失败: {e}")
        return []

    if not query_vector:
        return []

    store = get_store()
    faiss_mgr = get_faiss()

    raw_results = faiss_mgr.search(user_id=user_id, query_vector=query_vector, top_k=top_k * 3)
    if not raw_results:
        return []

    candidate_ids = [mid for mid, _ in raw_results]
    memories = store.get_by_ids(candidate_ids)
    if not memories:
        return []

    # 时间范围过滤
    if time_range is not None:
        start_ts, end_ts = time_range
        memories = [
            m for m in memories
            if start_ts <= m.get("created_at", 0) <= end_ts
        ]
        if not memories:
            return []

    sim_map = {mid: score for mid, score in raw_results}
    now = time.time()
    scored = []
    for mem in memories:
        sim = sim_map.get(mem["id"], 0.0)
        # agent_note 的重要性权重额外加成（精心提取的信息优先）
        importance = mem.get("importance", 0.5)
        if mem.get("note_type") == "agent_note":
            importance = min(1.0, importance + 0.1)
        final = FaissManager.compute_final_score(
            similarity=sim,
            importance=importance,
            created_at=mem.get("created_at", now),
            current_time=now,
        )
        scored.append({**mem, "_similarity": sim, "_final_score": final})

    scored.sort(key=lambda x: x["_final_score"], reverse=True)
    return scored[:top_k]


async def search_image_desc(
    user_id: str,
    keywords: list[str],
    top_k: int = 5,
) -> list[dict]:
    """
    工具：根据关键词检索用户发送过的图片描述
    返回 [{"id", "nickname", "description", "created_at", "_similarity"}, ...]
    """
    from ai_server.embedding import embed_text
    from src.bot.img.store import get_image_store

    if not keywords:
        return []

    keyword_text = " ".join(keywords)

    try:
        query_vector = await embed_text(keyword_text)
    except Exception as e:
        logger.error(f"[Agent.tools] 图片检索嵌入失败: {e}")
        return []

    if not query_vector:
        return []

    store = get_image_store()
    raw_results = store.search(user_id=user_id, query_vector=query_vector, top_k=top_k * 2)
    if not raw_results:
        return []

    candidate_ids = [mid for mid, _ in raw_results]
    records = store.get_by_ids(candidate_ids)
    sim_map = {mid: score for mid, score in raw_results}

    scored = []
    for rec in records:
        sim = sim_map.get(rec["id"], 0.0)
        scored.append({**rec, "_similarity": sim})

    scored.sort(key=lambda x: x["_similarity"], reverse=True)
    return scored[:top_k]


async def search_web(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """
    工具：联网搜索现实信息（歌曲、新闻、人物、事件等）
    返回 [{"title", "snippet", "link"}, ...]
    """
    import httpx
    from src.bot.core.config_loader import get_bot_config

    config = get_bot_config()
    api_key = config.get("search", {}).get("serper_api_key", "")
    if not api_key or api_key == "your_serper_api_key_here":
        logger.warning("[Agent.tools] Serper API key 未配置")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": top_k, "hl": "zh-cn", "gl": "cn"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        # 知识卡片（歌曲/人物/地点等结构化信息）
        if kg := data.get("knowledgeGraph"):
            snippet_parts = [kg.get("description", "")]
            for attr in kg.get("attributes", {}).items():
                snippet_parts.append(f"{attr[0]}：{attr[1]}")
            results.append({
                "title": kg.get("title", ""),
                "snippet": " | ".join(p for p in snippet_parts if p),
                "link": kg.get("website", ""),
            })
        # 普通搜索结果
        for item in data.get("organic", [])[:top_k]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
            })
        return results[:top_k]

    except Exception as e:
        logger.error(f"[Agent.tools] 联网搜索失败: {e}")
        return []


async def search_graph(
    query: str,
    user_id: str,
    depth: int = 1,
    top_k: int = 3,
) -> dict:
    """
    工具：在图记忆中检索实体，并沿关系边扩散

    Args:
        query: 检索查询（实体名、事件描述等）
        user_id: 用户 id
        depth: 扩散深度（1=直接邻居，2=二跳邻居）
        top_k: 向量检索返回的种子实体数量

    Returns:
        {"entities": [...], "relations": [...]}
    """
    from ai_server.embedding import embed_text
    from src.XN_Memory import get_graph_store

    try:
        graph_store = get_graph_store()
    except RuntimeError:
        logger.warning("[Agent.tools] 图记忆系统未初始化")
        return {"entities": [], "relations": []}

    try:
        query_vector = await embed_text(query)
    except Exception as e:
        logger.error(f"[Agent.tools] 图检索嵌入失败: {e}")
        return {"entities": [], "relations": []}

    if not query_vector:
        return {"entities": [], "relations": []}

    # 向量检索种子实体
    seed_entities = graph_store.search_entities_by_vector(
        query_vector=query_vector,
        user_id=user_id,
        top_k=top_k,
        threshold=0.55,
    )

    if not seed_entities:
        logger.debug(f"[Agent.tools] 图检索未命中: query={query}")
        return {"entities": [], "relations": []}

    seed_ids = [e["id"] for e in seed_entities]
    logger.info(f"[Agent.tools] 图检索命中 {len(seed_ids)} 个种子实体，扩散深度={depth}")

    # 沿边扩散
    subgraph = graph_store.expand_from_entities(
        entity_ids=seed_ids,
        user_id=user_id,
        depth=depth,
    )

    return subgraph


async def touch_memories(memory_ids: list[int]) -> None:
    """
    工具：标记记忆被命中（唤醒）
    更新 last_accessed_at，小幅提升 importance
    """
    from src.XN_Memory import get_store
    store = get_store()
    for mid in memory_ids:
        store.touch_memory(mid)
    logger.debug(f"[Agent.tools] 唤醒记忆 ids={memory_ids}")


async def query_conversations(
    user_id: str,
    since: float | None = None,
    before: float | None = None,
    count: int = 50,
) -> str:
    """
    工具：按时间范围直接查询对话记录（不做语义检索）。

    和 search_memory 的区别：
    - search_memory 是语义检索（FAISS 向量），找"相关的"
    - query_conversations 是按时间范围直接查 SQLite，找"那个时间段的"
    - 适合"今天聊了什么"、"最近3小时的对话"、"某段时间内的所有对话"

    Args:
        user_id: 用户 id
        since: 起始时间戳（包含），如今天凌晨的时间戳
        before: 结束时间戳（不包含），如当前时间
        count: 最大返回记忆对数量

    Returns:
        格式化的对话文本
    """
    from src.XN_Memory import get_store
    from datetime import datetime as dt

    store = get_store()
    messages = store.get_conversations_in_range(
        user_id=user_id, since=since, before=before, count=count,
    )
    if not messages:
        return "该时间段内无对话记录"

    lines = []
    for msg in messages:
        ts = dt.fromtimestamp(msg["timestamp"]).strftime("%m-%d %H:%M")
        role = "用户" if msg["role"] == "user" else "小雫"
        lines.append(f"[{ts}] {role}: {msg['content'][:300]}")
    result = "\n".join(lines)
    logger.info(f"[Agent.tools] query_conversations user={user_id} since={since} before={before} got={len(messages)} msgs")
    return result


async def search_reflections(user_id: str, limit: int = 3) -> str:
    """
    工具：读取小雫的反思日记（每天睡前生成）。

    反思日记包含：
    - 小雫对当天对话的总结（≤500字）
    - 对话质量打分
    - 睡眠时间段

    Args:
        user_id: 用户 id
        limit: 返回最近几条

    Returns:
        格式化的反思日记文本
    """
    from src.XN_Memory import get_store
    from datetime import datetime as dt

    store = get_store()
    reflections = store.get_recent_reflections(user_id=user_id, limit=limit)
    if not reflections:
        return "暂无反思日记"

    lines = []
    for r in reflections:
        date = dt.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d")
        score = r.get("health_score", 0)
        feeling = r.get("feeling") or ""
        hl_raw = r.get("highlights") or "[]"
        try:
            hl = json.loads(hl_raw) if isinstance(hl_raw, str) else hl_raw
        except json.JSONDecodeError:
            hl = []
        hl_str = "；".join(str(x) for x in hl[:3]) if hl else ""
        block = f"【{date}】对话质量:{score:.1f}分\n事实:{r['summary']}"
        if feeling:
            block += f"\n感受:{feeling}"
        if hl_str:
            block += f"\n细节:{hl_str}"
        lines.append(block)
    result = "\n\n".join(lines)
    logger.info(f"[Agent.tools] search_reflections user={user_id} got={len(reflections)} entries")
    return result


async def list_graph(
    user_id: str,
    page: int = 1,
    page_size: int = 30,
) -> str:
    """
    工具：列出图数据库中的所有实体（分页），并显示总数统计。

    用途：
    - 查看图数据库里一共有多少实体和关系
    - 浏览所有已记录的实体，不需要关键词
    - 调试时确认图数据库内容是否正确写入

    Args:
        user_id: 用户 id
        page: 页码（从 1 开始）
        page_size: 每页数量（默认 30，最大 50）

    Returns:
        格式化的实体列表文本，包含总数统计
    """
    from src.XN_Memory import get_graph_store

    try:
        gs = get_graph_store()
    except RuntimeError:
        return "图记忆系统未初始化"

    page_size = min(page_size, 50)
    offset = (page - 1) * page_size

    total, entities = gs.list_entities(user_id=user_id, limit=page_size, offset=offset)
    relation_count = gs.count_relations(user_id=user_id)

    if total == 0:
        return f"图数据库中暂无实体（user_id={user_id}）"

    total_pages = (total + page_size - 1) // page_size
    lines = [f"【图数据库概览】实体总数={total}，关系总数={relation_count}，第{page}/{total_pages}页"]
    lines.append("")

    for e in entities:
        summary = f"：{e['summary'][:40]}" if e.get("summary") else ""
        lines.append(f"  [{e['entity_type']}] {e['name']}{summary}")

    if total > page * page_size:
        lines.append(f"\n（还有 {total - page * page_size} 个实体，可用 page={page+1} 查看下一页）")

    logger.info(f"[Agent.tools] list_graph user={user_id} total={total} relations={relation_count} page={page}")
    return "\n".join(lines)

