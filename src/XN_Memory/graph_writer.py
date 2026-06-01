"""
XN_Memory.graph_writer - 聊天流监听 + 图记忆写入

触发逻辑：
  每条消息进来时记录到缓冲区
  5分钟内无新消息 → 触发 LLM 提取实体和关系 → 写入图数据库

LLM 提取格式：
  输入：一段聊天记录
  输出：实体列表 + 关系列表（JSON）
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from nonebot.log import logger


# ========================
# 数据结构
# ========================

@dataclass
class ChatMessage:
    role: str        # "user" 或 "assistant"
    content: str
    nickname: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str   # 人物/地点/时间/事件/事物
    summary: str


@dataclass
class ExtractedRelation:
    from_entity: str
    to_entity: str
    rel_type: str
    description: str


# ========================
# LLM 提取 Prompt
# ========================

_EXTRACT_PROMPT = """你是一个知识图谱构建助手。请分析以下聊天记录，提取其中的实体和关系。

【实体类型说明】
- 人物：真实或虚构的人，包括昵称、角色名
- 地点：城市、地址、场所、店铺等
- 时间：具体日期、时间段、节日等
- 事件：发生的事情、活动、经历
- 事物：物品、作品、歌曲、电影、食物等

【提取要求】
1. 实体名称使用简称/常用称呼（如"成都"而非"成都市"，"米菲"而非"米菲小姐"）
2. 每个实体写一句话摘要，说明它在这段对话中的角色或相关信息
3. 关系描述要简洁，说明两个实体之间发生了什么
4. 只提取对话中明确出现或强烈暗示的内容，不要推断

【聊天记录】
{chat_text}

请严格按以下 JSON 格式输出，不要有任何其他内容：
{{
  "entities": [
    {{"name": "实体名", "type": "人物|地点|时间|事件|事物", "summary": "一句话摘要"}},
    ...
  ],
  "relations": [
    {{"from": "实体A", "to": "实体B", "rel_type": "关系类型", "description": "关系描述"}},
    ...
  ]
}}

关系类型示例：在场、提及、发生于、属于、喜欢、参与、位于、时间为"""


# ========================
# 图写入器
# ========================

class GraphWriter:
    """
    监听聊天流，定时触发图记忆提取和写入
    每个 user_id 独立维护一个消息缓冲区
    """

    IDLE_TIMEOUT = 300  # 5分钟无新消息触发提取
    MIN_MESSAGES = 4    # 至少积累这么多条消息才触发

    def __init__(self, graph_store=None):
        # user_id -> 消息缓冲区
        self._buffers: dict[str, list[ChatMessage]] = {}
        # user_id -> 上次收到消息的时间
        self._last_message_time: dict[str, float] = {}
        # 后台检查任务
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
        self._graph_store = graph_store

    def set_graph_store(self, graph_store):
        self._graph_store = graph_store

    def start(self):
        """启动后台定时检查"""
        if self._running:
            return
        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("[GraphWriter] 后台检查任务已启动")

    async def stop(self, timeout: float = 5.0):
        """停止后台任务，处理剩余缓冲区（带超时）"""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
        # 处理所有剩余缓冲区（带总超时）
        try:
            await asyncio.wait_for(self._flush_all(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"[GraphWriter] 缓冲区刷写超时（{timeout}s），丢弃剩余数据")

    async def _flush_all(self):
        for user_id in list(self._buffers.keys()):
            await self._flush(user_id)

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        nickname: str,
        timestamp: float | None = None,
    ):
        """添加一条消息到缓冲区"""
        if user_id not in self._buffers:
            self._buffers[user_id] = []

        self._buffers[user_id].append(ChatMessage(
            role=role,
            content=content,
            nickname=nickname,
            timestamp=timestamp or time.time(),
        ))
        self._last_message_time[user_id] = time.time()

    async def _check_loop(self):
        """每30秒检查一次是否有超时的缓冲区需要处理"""
        while self._running:
            try:
                await asyncio.sleep(30)
                now = time.time()
                for user_id in list(self._buffers.keys()):
                    last_time = self._last_message_time.get(user_id, 0)
                    buf = self._buffers.get(user_id, [])
                    if (
                        buf
                        and len(buf) >= self.MIN_MESSAGES
                        and now - last_time >= self.IDLE_TIMEOUT
                    ):
                        logger.info(f"[GraphWriter] user={user_id} 触发图记忆提取，消息数={len(buf)}")
                        await self._flush(user_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[GraphWriter] 检查循环异常: {e}")

    async def _flush(self, user_id: str):
        """处理指定用户的缓冲区，提取图记忆并写入"""
        buf = self._buffers.pop(user_id, [])
        self._last_message_time.pop(user_id, None)

        if not buf or len(buf) < self.MIN_MESSAGES:
            return

        try:
            entities, relations = await self._extract_graph(buf)
            if not entities:
                logger.debug(f"[GraphWriter] user={user_id} 未提取到实体，跳过写入")
                return

            await self._write_to_graph(user_id, entities, relations)
            logger.info(
                f"[GraphWriter] user={user_id} 写入完成: "
                f"{len(entities)}个实体, {len(relations)}条关系"
            )
        except Exception as e:
            logger.error(f"[GraphWriter] user={user_id} 图记忆写入失败: {e}")

    async def _extract_graph(
        self,
        messages: list[ChatMessage],
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        """调用 LLM 从聊天记录中提取实体和关系"""
        from ai_server.client import call_model
        from ai_server.schemas import Message

        # 格式化聊天记录
        lines = []
        for msg in messages:
            name = msg.nickname if msg.role == "user" else "小雫"
            lines.append(f"{name}：{msg.content}")
        chat_text = "\n".join(lines)

        prompt = _EXTRACT_PROMPT.replace("{chat_text}", chat_text)

        try:
            response = await call_model(
                model_name="tools",
                messages=[Message(role="user", content=prompt)],
            )
            return self._parse_extract_response(response.content)
        except Exception as e:
            logger.error(f"[GraphWriter] LLM 提取失败: {e}")
            return [], []

    @staticmethod
    def _parse_extract_response(
        content: str,
    ) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
        """解析 LLM 返回的 JSON"""
        # 剥掉 markdown 代码块
        content = re.sub(r'```(?:json)?\s*', '', content).strip()

        try:
            # 尝试提取 JSON 对象
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"[GraphWriter] JSON 解析失败: {e}, content={content[:200]}")
            return [], []

        entities = []
        for item in data.get("entities", []):
            name = str(item.get("name", "")).strip()
            etype = str(item.get("type", "事物")).strip()
            summary = str(item.get("summary", "")).strip()
            if name:
                entities.append(ExtractedEntity(
                    name=name,
                    entity_type=etype,
                    summary=summary,
                ))

        relations = []
        for item in data.get("relations", []):
            from_e = str(item.get("from", "")).strip()
            to_e = str(item.get("to", "")).strip()
            rel_type = str(item.get("rel_type", "相关")).strip()
            desc = str(item.get("description", "")).strip()
            if from_e and to_e:
                relations.append(ExtractedRelation(
                    from_entity=from_e,
                    to_entity=to_e,
                    rel_type=rel_type,
                    description=desc,
                ))

        return entities, relations

    async def _write_to_graph(
        self,
        user_id: str,
        entities: list[ExtractedEntity],
        relations: list[ExtractedRelation],
    ):
        """将提取结果写入图数据库"""
        if self._graph_store is None:
            logger.warning("[GraphWriter] graph_store 未设置，跳过写入")
            return

        from ai_server.embedding import embed_text

        # 写入实体（带向量）
        for entity in entities:
            try:
                embed_input = f"{entity.entity_type} {entity.name} {entity.summary}"
                vector = await embed_text(embed_input)
                self._graph_store.upsert_entity(
                    name=entity.name,
                    entity_type=entity.entity_type,
                    summary=entity.summary,
                    user_id=user_id,
                    vector=vector if vector else None,
                )
            except Exception as e:
                logger.error(f"[GraphWriter] 写入实体 {entity.name} 失败: {e}")

        # 写入关系
        for rel in relations:
            try:
                self._graph_store.add_relation(
                    from_name=rel.from_entity,
                    to_name=rel.to_entity,
                    rel_type=rel.rel_type,
                    description=rel.description,
                    user_id=user_id,
                )
            except Exception as e:
                logger.error(f"[GraphWriter] 写入关系 {rel.from_entity}->{rel.to_entity} 失败: {e}")


# ========================
# 全局单例
# ========================

_graph_writer: Optional[GraphWriter] = None


def get_graph_writer() -> GraphWriter:
    global _graph_writer
    if _graph_writer is None:
        _graph_writer = GraphWriter()
    return _graph_writer
