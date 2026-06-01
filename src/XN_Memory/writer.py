"""
XN_Memory.writer - 异步写入层
回复发出后触发，负责：
1. 调用关键词提取 LLM 生成关键词 + importance
2. 调用嵌入模型生成向量
3. 写入 SQLite + FAISS
"""
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Optional

from nonebot.log import logger

from src.XN_Memory.store import MemoryStore
from src.XN_Memory.faiss_manager import FaissManager


# 关键词提取的 prompt 模板
_KEYWORD_EXTRACT_PROMPT = """你是一个记忆索引助手。请分析以下对话，完成两件事：

1. 提取 5 个关键词，结构如下：
   - 第1个：主题词（这段对话属于什么场景，如：表白、吵架、约定、日常闲聊）
   - 第2个：概念词（对话涉及的核心情感或关系概念，如：思念、信任、亲密、愧疚）
   - 第3个：原文关键词（直接出现在对话中的具体词语）
   - 第4个：自由选择（地名、人名、事物名、情绪词均可，选对检索最有帮助的）
   - 第5个：自由选择（地名、人名、事物名、情绪词均可，选对检索最有帮助的）

2. 评估这段对话的重要性分数（0.0~1.0）

重要性评分标准：
- 0.7~1.0：涉及强烈情绪（争吵、哭泣、非常开心、受伤）、重要约定、承诺、重大决定或事件
- 0.3~0.6：普通聊天、分享日常、轻松话题
- 0.0~0.2：无意义闲聊、天气、打招呼

对话内容：
用户：{user_text}
小雫：{bot_text}

请严格按以下 JSON 格式输出，不要有任何其他内容：
{{"keywords": ["主题词", "概念词", "原文词", "自由词1", "自由词2"], "importance": 0.5}}"""


class MemoryWriter:
    """异步记忆写入器"""

    def __init__(
        self,
        store: MemoryStore,
        faiss: FaissManager | None = None,
        index_dir: str | None = None,
    ):
        self.store = store
        self.faiss = faiss or FaissManager(index_dir=index_dir)
        # 写入任务队列（asyncio.Queue 保证线程安全）
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start_worker(self) -> None:
        """启动后台写入 worker（在 bot 启动后调用）"""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("[XN_Memory] 写入 worker 已启动")

    async def stop_worker(self, timeout: float = 5.0) -> None:
        """停止 worker，等待队列清空（带超时）"""
        if self._worker_task and not self._worker_task.done():
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"[XN_Memory] 队列清空超时（{timeout}s），强制取消")
            self._worker_task.cancel()
            logger.info("[XN_Memory] 写入 worker 已停止")

    # ========================
    # 对外接口：提交写入任务
    # ========================
    def submit(
        self,
        user_id: str,
        user_text: str,
        bot_text: str,
        session_id: str | None = None,
        nickname: str = "",
        created_at: float | None = None,
    ) -> None:
        """提交一条写入任务（非阻塞）"""
        task = {
            "user_id": user_id,
            "user_text": user_text,
            "bot_text": bot_text,
            "session_id": session_id,
            "nickname": nickname,
            "created_at": created_at or time.time(),
        }
        try:
            self._queue.put_nowait(task)
        except asyncio.QueueFull:
            logger.warning("[XN_Memory] 写入队列已满，丢弃本次写入任务")

    # ========================
    # 后台 worker
    # ========================
    async def _worker_loop(self) -> None:
        """持续消费写入队列"""
        while True:
            try:
                task = await self._queue.get()
                try:
                    await self._process_task(task)
                except Exception as e:
                    logger.error(f"[XN_Memory] 写入任务失败: {e}")
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[XN_Memory] worker 异常: {e}")
                await asyncio.sleep(1)

    async def _process_task(self, task: dict) -> None:
        """处理单条写入任务"""
        user_id = task["user_id"]
        user_text = task["user_text"]
        bot_text = task["bot_text"]
        session_id = task.get("session_id")
        nickname = task.get("nickname", "")
        created_at = task.get("created_at", time.time())

        keywords, importance = await self._extract_keywords(user_text, bot_text)
        if not keywords:
            logger.warning(f"[XN_Memory] 关键词提取失败，跳过写入 user={user_id}")
            return

        keyword_text = " ".join(keywords)
        vector = await self._embed(keyword_text)
        if not vector:
            logger.warning(f"[XN_Memory] 向量生成失败，跳过写入 user={user_id}")
            return

        memory_id = self.store.insert_memory(
            user_id=user_id,
            user_text=user_text,
            bot_text=bot_text,
            keywords=keywords,
            importance=importance,
            session_id=session_id,
            nickname=nickname,
            created_at=created_at,
        )

        self.faiss.add_vector(user_id=user_id, memory_id=memory_id, vector=vector)

        logger.info(
            f"[XN_Memory] 写入完成 id={memory_id} user={user_id}({nickname}) "
            f"keywords={keywords} importance={importance:.2f}"
        )

    # ========================
    # 关键词提取
    # ========================
    async def _extract_keywords(
        self, user_text: str, bot_text: str
    ) -> tuple[list[str], float]:
        """
        调用关键词提取 LLM，返回 (keywords, importance)
        失败时返回 ([], 0.5)
        """
        from ai_server.client import call_model
        from ai_server.schemas import Message

        prompt = _KEYWORD_EXTRACT_PROMPT.format(
            user_text=user_text[:500],  # 截断避免超长
            bot_text=bot_text[:500],
        )

        try:
            response = await call_model(
                model_name="keyword_extractor",
                messages=[Message(role="user", content=prompt)],
            )
            return self._parse_keyword_response(response.content)
        except Exception as e:
            logger.error(f"[XN_Memory] 关键词提取 LLM 调用失败: {e}")
            return [], 0.5

    @staticmethod
    def _parse_keyword_response(content: str) -> tuple[list[str], float]:
        """解析 LLM 返回的 JSON，容错处理"""
        # 剥掉思考模型的 <think> 块
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        try:
            # 尝试直接解析
            data = json.loads(content.strip())
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON 块
            match = re.search(r"\{.*?\}", content, re.DOTALL)
            if not match:
                logger.warning(f"[XN_Memory] 无法解析关键词响应: {content[:200]}")
                return [], 0.5
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return [], 0.5

        keywords = data.get("keywords", [])
        importance = float(data.get("importance", 0.5))

        # 校验
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if k][:5]  # 最多5个
        importance = max(0.0, min(1.0, importance))

        return keywords, importance

    # ========================
    # 嵌入
    # ========================
    @staticmethod
    async def _embed(text: str) -> list[float]:
        """调用嵌入模型生成向量"""
        try:
            from ai_server.embedding import embed_text
            return await embed_text(text)
        except Exception as e:
            logger.error(f"[XN_Memory] 嵌入模型调用失败: {e}")
            return []
