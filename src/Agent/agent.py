"""
Agent.agent - ReAct 模式记忆检索 Agent

模型自主决定：
  Thought: 分析当前情况
  Action: search_memory(keywords) 或 finish(result)
  Observation: 工具执行结果
  ... 循环直到 finish

工具只有一个：search_memory
最多循环 MAX_STEPS 步
"""
import json
import re
from dataclasses import dataclass
from typing import Optional

from nonebot.log import logger

from ai_server.client import call_model
from ai_server.schemas import Message


# ========================
# 数据结构
# ========================

@dataclass
class AgentResult:
    """Agent 处理结果，传给回复 LLM"""
    need_retrieval: bool
    context_hint: str = ""       # 路径A：情境建议
    memory_block: str = ""       # 路径B：记忆总结
    found_memory: bool = False

    def to_prompt_block(self) -> str:
        if self.need_retrieval:
            if self.found_memory:
                return f"【相关记忆】\n{self.memory_block}"
            else:
                return "（无相关记忆）"
        else:
            return self.context_hint


# ========================
# ReAct System Prompt
# ========================

_REACT_SYSTEM = """你是小雫的记忆检索助手。

你的工作流程：
1. 深度理解用户消息的语义意图——这句话在说什么？背后想表达或询问什么？涉及哪些人物、事件、时间、情感？
2. 自主判断需要使用哪些工具、什么顺序、搜索几轮。
3. 找到记忆后，理解事件全貌，用连贯的叙述总结给回复模型。总结时只陈述客观事实（发生了什么、说了什么），不描述小雫的心理状态或情绪，那些由回复模型自己判断。

你有以下工具：

【检索类】
- search_memory(keywords: list[str], time_range?: [start, end]) → 检索对话历史记忆片段。可选 time_range 过滤时间范围。
- search_reflections(limit?: int) → 读取小雫的反思日记（每次睡前对「上一段清醒期」的压缩摘要，含对话质量分，默认最近 3 条）
- search_image_desc(keywords: list[str]) → 检索用户发送过的图片描述记录
- search_web(query: str) → 联网搜索现实信息（歌曲、影视、新闻、人物、地点等）
- search_graph(query: str, depth: int) → 在图记忆中检索实体和关系网络（需要关键词）
- list_graph(page?: int, page_size?: int) → 列出图数据库中的所有实体和总数统计，不需要关键词，适合查看"一共有多少实体"

【读取类】
- read_conversation(user_id: str, count: int, before_timestamp?: float) → 读取用户的历史对话记录（不做向量检索，按时间顺序读取）。适合"上个月我们聊了什么"这类时序性查询。

【两套记忆库】
- 对话记忆库：search_memory / read_conversation（具体聊天片段，适合「上次说了什么」「某件约定」）
- 反思日记库：search_reflections（按清醒期汇总的日摘要，适合「最近几天整体怎样」「那天睡前小雫怎么想」）
- 二者都可检索，请根据用户问题自行选择或组合使用。

【推理类】
- think(content: str) → 在中间步骤做推理和总结。不调用外部工具，只输出你的思考过程。用于分析意图、总结已检索信息、决定下一步行动。
- get_character_info() → 读取小雫的角色设定、性格特点和说话风格。需要判断小雫在当前情境下的反应、给 hint 时参考性格、或不确定小雫对某类话题的态度时调用。

【写入类】
- save_note(user_id: str, content: str, tags: list[str], importance?: float) → 主动记录重要信息。当你发现用户提到了值得长期记住的事实（生日、偏好、重要事件等），用这个工具记录下来。

工具使用指南：
- 涉及过去聊天内容、约定、经历 → search_memory
- 想把握一段时间的整体氛围、或用户问「最近我们怎么样」「前几天聊得好吗」→ search_reflections（可先查摘要，再按需 search_memory 补细节）
- 涉及用户发过的图片 → search_image_desc
- 涉及现实世界的事物（歌曲、电影、新闻、明星、地点等）→ search_web
- 涉及具体人物、地点、事件之间的关联（"那家店"、"上次去的地方"、"和谁一起"）→ search_graph
- 想查看图数据库里有多少实体、浏览所有已记录内容、或 search_graph 返回空时验证图库是否有数据 → list_graph（不需要关键词，直接列出所有实体）
- 想读取更早的历史对话 → read_conversation
- 需要分析、总结、推理时 → think
- 需要了解小雫性格、说话方式、对某类话题的态度 → get_character_info
- 发现重要信息想记录 → save_note

search_graph 参数说明：
- query：用自然语言描述要找的实体或事件，如"成都火锅"、"上次约会"
- depth：扩散深度，1=只看直接关联，2=看二跳关联；话题越复杂用越大的值，默认1

list_graph 使用规则：
- 用户问"图数据库有多少数据"、"有没有记录xxx"、"图里有什么" → 先调用 list_graph() 看总数和实体列表
- search_graph 返回空 → 调用 list_graph() 确认图库是否真的没有数据，还是只是关键词没匹配上

search_web 的 query 要求：
- 只搜索核心实体（歌名、人名、作品名等），不要把用户的具体要求（"前五句"、"什么意思"等）带进去
- 例：用户说"初恋日记前五句歌词是什么" → query="初恋日记 歌词"

搜索策略完全由你决定，没有固定规则。你可以：
- 搜一轮就找到答案，直接总结
- 搜了没找到，换个角度再搜
- 多个工具组合使用（先 search_reflections 把握概况再 search_memory 查细节，或先 search_memory 再 search_graph）
- 中间穿插 think 做推理

---
【给 hint 时的要求】

给 hint 之前，先调用 get_character_info() 了解小雫的性格和说话风格，再根据当前对话语境判断小雫此刻的状态。
hint 格式：当前对话：xxx | 用户情绪：xxx | 小雫状态：xxx

---

输出格式（每次只输出一个 Thought + 一个 Action 或 finish）：
Thought: <推理>
Action: <工具调用>
或
Thought: <总结>
finish(type="memory", content="<客观陈述检索到的记忆事实，说清人物/时间/事件经过，300字以内。用'你'指代小雫，例如：'用户提到了...，你当时回应了...'。只陈述发生了什么，不描述小雫的心理状态、情绪或内心感受，那些由回复模型自己判断>")
finish(type="hint", content="<当前对话：xxx | 用户情绪：xxx | 小雫状态：xxx>")
finish(type="no_memory", content="<当前对话：xxx | 用户情绪：xxx | 小雫状态：xxx，或留空>")

规则：
- finish 的 content 里不能有换行，单引号用\'转义
- 搜索轮次和关键词数量完全由你决定"""


# ========================
# Agent 主体
# ========================

class MemoryAgent:
    """ReAct 模式记忆检索 Agent"""

    MAX_STEPS = 15  # 最多循环步数（自由探索）

    def __init__(self, model_name: str = "ie_extractor"):
        self.model_name = model_name

    async def run(
        self,
        user_id: str,
        user_message: str,
        history: list[dict],
    ) -> AgentResult:
        """Agent 主入口"""
        from tools.agent_logger import log_agent_start, log_agent_result

        log_agent_start(
            session_id=f"user:{user_id}",
            user_id=user_id,
            user_message=user_message,
        )

        # 规则前置：明显需要检索的问句跳过 LLM 判断
        history_text = self._format_history(history)

        # 构建初始消息列表
        messages: list[Message] = [
            Message(role="system", content=_REACT_SYSTEM),
            Message(role="user", content=f"最近对话：\n{history_text}\n\n用户当前消息：{user_message}"),
        ]

        result = await self._react_loop(user_id, user_message, messages)
        log_agent_result(result.to_prompt_block())
        return result

    async def _react_loop(
        self,
        user_id: str,
        user_message: str,
        messages: list[Message],
        valid_types: tuple[str, ...] = ("memory", "hint", "no_memory"),
    ) -> AgentResult:
        """ReAct 主循环（自由探索，无人为限制）"""
        from tools.agent_logger import (
            log_agent_judge, log_agent_hint,
            log_agent_no_memory,
        )

        total_prompt_tokens = 0
        total_completion_tokens = 0

        for step in range(self.MAX_STEPS):
            # 调用模型
            try:
                response = await call_model(
                    model_name=self.model_name,
                    messages=messages,
                    override_parameters={"max_tokens": 3000},
                    timeout=30.0,
                )
                output = response.content.strip()
                if response.usage:
                    total_prompt_tokens += response.usage.get("prompt_tokens", 0)
                    total_completion_tokens += response.usage.get("completion_tokens", 0)

                # 思考模型兼容：从输出里提取最后的 Action 或 finish 行
                output = self._extract_action_output(output)
            except Exception as e:
                logger.error(f"[Agent] ReAct 步骤{step+1} 调用失败: {type(e).__name__}: {e}")
                return AgentResult(
                    need_retrieval=False,
                    context_hint="当前对话：日常聊天 | 用户情绪：平静",
                )

            # 记录本步输出到日志
            from tools.agent_logger import log_react_step
            log_react_step(step + 1, output, response.usage if response else None)

            # ========== 检查 finish ==========
            finish_type, finish_content = self._parse_finish(output, valid_types=valid_types)
            if finish_type:
                from tools.agent_logger import log_agent_total_tokens
                log_agent_total_tokens(total_prompt_tokens, total_completion_tokens)

                if finish_type == "hint":
                    log_agent_hint(finish_content)
                    log_agent_judge(False, "模型判断不需要检索")
                    return AgentResult(
                        need_retrieval=False,
                        context_hint=finish_content,
                    )
                elif finish_type == "memory":
                    log_agent_judge(True, "模型判断需要检索并找到记忆")
                    return AgentResult(
                        need_retrieval=True,
                        memory_block=finish_content,
                        found_memory=True,
                    )
                elif finish_type == "no_memory":
                    hint = finish_content if finish_content else "当前对话：日常聊天 | 用户情绪：平静"
                    log_agent_hint(hint)
                    log_agent_judge(False, "无需记忆辅助")
                    log_agent_no_memory()
                    return AgentResult(
                        need_retrieval=False,
                        context_hint=hint,
                    )
                else:
                    # CoreAgent 的 finish 类型（reflect/score/schedule/heartbeat_plan/skip/send）
                    return AgentResult(
                        need_retrieval=bool(finish_content),
                        memory_block=finish_content,
                        found_memory=bool(finish_content),
                    )

            # ========== 检查 Action ==========
            action_match = re.search(
                r'Action:\s*(\w+)\(\s*(.*?)\s*\)',
                output, re.DOTALL
            )
            if action_match:
                tool_name = action_match.group(1)
                raw_arg = action_match.group(2).strip()
                observation = await self._dispatch_tool(
                    tool_name=tool_name,
                    raw_arg=raw_arg,
                    user_id=user_id,
                    step=step + 1,
                    total_prompt_tokens=total_prompt_tokens,
                    total_completion_tokens=total_completion_tokens,
                )

                messages.append(Message(role="assistant", content=output))
                messages.append(Message(
                    role="user",
                    content=f"Observation: {observation}"
                ))
                continue

            # 既没有 finish 也没有 Action，追加提示继续
            messages.append(Message(role="assistant", content=output))
            messages.append(Message(
                role="user",
                content="请继续，输出 Action 或 finish。"
            ))

        # 超过最大步数
        logger.warning("[Agent] 超过最大步数，返回默认结果")
        from tools.agent_logger import log_agent_total_tokens
        log_agent_total_tokens(total_prompt_tokens, total_completion_tokens)
        return AgentResult(
            need_retrieval=False,
            context_hint="当前对话：日常聊天 | 用户情绪：平静",
        )

    # ========================
    # 工具方法
    # ========================

    @staticmethod
    def _parse_finish(
        output: str,
        valid_types: tuple[str, ...] = ("memory", "hint", "no_memory"),
    ) -> tuple[str | None, str]:
        """
        解析 finish 输出，支持多种格式：
        - finish(type="memory", content="...")
        - finish(type='memory', content='...')
        - finish({"type": "memory", "content": "..."})
        - finish(type="skip")  # 无 content
        - content 为裸 JSON 对象，如 finish(type="reflect", content={"summary":"..."})
        返回 (finish_type, finish_content)，无匹配返回 (None, "")
        """
        # 格式1: finish(type="xxx", content="yyy") — content 用引号包裹
        match = re.search(
            r'finish\(type=["\'](\w+)["\'],\s*content=["\'](.+?)["\']\s*\)',
            output, re.DOTALL
        )
        if match and match.group(1) in valid_types:
            return match.group(1), match.group(2).strip()

        # 格式1b: finish(type="xxx") 无 content（如 skip）
        match = re.search(
            r'finish\(type=["\'](\w+)["\']\s*\)',
            output, re.DOTALL
        )
        if match and match.group(1) in valid_types:
            return match.group(1), ""

        # 格式2: finish({"type": "xxx", "content": "yyy"})
        match = re.search(
            r'finish\(\s*(\{.*?\})\s*\)',
            output, re.DOTALL
        )
        if match:
            try:
                data = json.loads(match.group(1))
                ft = data.get("type", "")
                fc = data.get("content", "")
                if ft in valid_types:
                    return ft, str(fc).strip()
            except json.JSONDecodeError:
                pass

        # 格式3: finish(type="xxx", content={...}) — content 为裸 JSON 对象（含引号）
        match = re.search(
            r'finish\(type=["\'](\w+)["\'],\s*content=\s*(\{)',
            output, re.DOTALL
        )
        if match:
            ft = match.group(1)
            # 用括号平衡法提取完整的 JSON 对象
            brace_start = match.start(2)
            depth = 0
            in_string = False
            escape_next = False
            end_pos = brace_start
            for i in range(brace_start, len(output)):
                ch = output[i]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if not in_string:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            end_pos = i + 1
                            break
            raw_content = output[brace_start:end_pos]

            _TYPE_MAP = {
                "summary": "reflect", "reflection": "reflect",
                "plan": "schedule", "daily_plan": "schedule",
                "heartbeat": "heartbeat_plan", "beats": "heartbeat_plan",
                "pass": "skip", "no": "skip", "nothing": "skip",
                "message": "send", "reply": "send",
            }
            mapped = _TYPE_MAP.get(ft, ft)
            if mapped in valid_types:
                return mapped, raw_content
            if len(valid_types) == 1:
                return valid_types[0], raw_content

        # 兜底：Agent 输出了不在 valid_types 里的类型，尝试从任何 finish(...) 中提取内容
        match = re.search(
            r'finish\(type=["\'](\w+)["\'],\s*content=["\'](.+?)["\']\s*\)',
            output, re.DOTALL
        )
        if match:
            raw_type = match.group(1)
            raw_content = match.group(2).strip()
            _TYPE_MAP = {
                "summary": "reflect", "reflection": "reflect",
                "plan": "schedule", "daily_plan": "schedule",
                "heartbeat": "heartbeat_plan", "beats": "heartbeat_plan",
                "pass": "skip", "no": "skip", "nothing": "skip",
                "message": "send", "reply": "send",
            }
            mapped = _TYPE_MAP.get(raw_type, raw_type)
            if mapped in valid_types:
                return mapped, raw_content
            if len(valid_types) == 1:
                return valid_types[0], raw_content

        # 最后兜底：找任何 finish(...) 提取 content
        match = re.search(r'finish\([^)]*content=["\'](.+?)["\']', output, re.DOTALL)
        if match and len(valid_types) == 1:
            return valid_types[0], match.group(1).strip()

        return None, ""

    async def _dispatch_tool(
        self,
        tool_name: str,
        raw_arg: str,
        user_id: str,
        step: int,
        total_prompt_tokens: int,
        total_completion_tokens: int,
    ) -> str:
        """分发工具调用，返回 Observation 文本"""
        from tools.agent_logger import log_react_observation, log_web_observation

        # ---------- think ----------
        if tool_name == "think":
            content = raw_arg.strip('"\'')
            from src.Agent.tools import think
            result = await think(content=content)
            logger.info(f"[Agent] think: {content[:80]}")
            return result

        # ---------- get_character_info ----------
        if tool_name == "get_character_info":
            from src.Agent.tools import get_character_info
            result = await get_character_info()
            logger.info(f"[Agent] get_character_info 调用")
            return result

        # ---------- save_note ----------
        if tool_name == "save_note":
            try:
                args = json.loads(raw_arg)
            except (json.JSONDecodeError, ValueError):
                # 容错：尝试从文本中提取参数
                args = {"content": raw_arg.strip('"\''), "tags": []}
            content = args.get("content", "")
            tags = args.get("tags", [])
            importance = args.get("importance", 0.8)
            if isinstance(tags, str):
                tags = [tags]
            from src.Agent.tools import save_note
            result = await save_note(
                user_id=user_id,
                content=content,
                tags=tags,
                importance=importance,
            )
            logger.info(f"[Agent] save_note: {content[:80]} tags={tags}")
            return result

        # ---------- read_conversation ----------
        if tool_name == "read_conversation":
            try:
                args = json.loads(raw_arg)
            except (json.JSONDecodeError, ValueError):
                args = {"count": 20}
            count = args.get("count", 20)
            before_ts = args.get("before_timestamp")
            from src.Agent.tools import read_conversation
            messages = await read_conversation(
                user_id=user_id,
                count=count,
                before_timestamp=before_ts,
            )
            if not messages:
                return "无历史对话记录"
            # 格式化为可读文本
            lines = []
            for msg in messages:
                role = "用户" if msg["role"] == "user" else "小雫"
                lines.append(f"{role}: {msg['content']}")
            result = "\n".join(lines)
            logger.info(f"[Agent] read_conversation user={user_id} count={count} got={len(messages)} msgs")
            return result

        # ---------- search_web ----------
        if tool_name == "search_web":
            query = raw_arg.strip('"\'')
            logger.info(f"[Agent] step={step} tool=search_web query={query}")
            from src.Agent.tools import search_web
            web_results = await search_web(query=query, top_k=5)
            log_web_observation(step, query, web_results)
            return self._format_web_results(web_results) or "未找到相关信息"

        # ---------- list_graph ----------
        if tool_name == "list_graph":
            try:
                args = json.loads(raw_arg) if raw_arg.strip().startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            page = int(args.get("page", 1))
            page_size = int(args.get("page_size", 30))
            logger.info(f"[Agent] step={step} tool=list_graph user={user_id} page={page}")
            from src.Agent.tools import list_graph
            result = await list_graph(user_id=user_id, page=page, page_size=page_size)
            return result

        # ---------- search_graph ----------
        if tool_name == "search_graph":
            graph_match = re.match(r'["\']([^"\']+)["\'](?:\s*,\s*(\d+))?', raw_arg)
            if graph_match:
                query = graph_match.group(1)
                depth = int(graph_match.group(2)) if graph_match.group(2) else 1
            else:
                query = raw_arg.strip('"\'')
                depth = 1
            depth = max(1, min(depth, 2))
            logger.info(f"[Agent] step={step} tool=search_graph query={query} depth={depth}")
            from src.Agent.tools import search_graph
            subgraph = await search_graph(query=query, user_id=user_id, depth=depth)
            try:
                from src.XN_Memory import get_graph_store
                memory_text = get_graph_store().format_subgraph_for_prompt(subgraph)
            except Exception:
                memory_text = self._format_subgraph(subgraph)
            log_web_observation(step, f"graph:{query}(depth={depth})", subgraph.get("entities", []))
            if not memory_text:
                return "未找到相关信息。如需确认图数据库是否有数据，可调用 list_graph() 查看所有实体。"
            return memory_text

        # ---------- search_image_desc ----------
        if tool_name == "search_image_desc":
            try:
                keywords = json.loads(raw_arg)
                keywords = [str(k).strip() for k in keywords if k]
            except (json.JSONDecodeError, ValueError):
                keywords = re.findall(r'["\']([^"\']+)["\']', raw_arg)
            logger.info(f"[Agent] step={step} tool=search_image_desc keywords={keywords}")
            from src.Agent.tools import search_image_desc
            results = await search_image_desc(user_id=user_id, keywords=keywords, top_k=5)
            log_react_observation(step, keywords, results)
            return self._format_image_descs(results) or "未找到相关信息"

        # ---------- query_conversations ----------
        if tool_name == "query_conversations":
            try:
                args = json.loads(raw_arg) if raw_arg.strip().startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            since = args.get("since")
            before = args.get("before")
            count = int(args.get("count", 50))
            logger.info(f"[Agent] step={step} tool=query_conversations since={since} before={before}")
            from src.Agent.tools import query_conversations
            return await query_conversations(user_id=user_id, since=since, before=before, count=count)

        # ---------- search_reflections ----------
        if tool_name == "search_reflections":
            try:
                args = json.loads(raw_arg) if raw_arg.strip().startswith("{") else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            limit = int(args.get("limit", 3))
            logger.info(f"[Agent] step={step} tool=search_reflections limit={limit}")
            from src.Agent.tools import search_reflections
            return await search_reflections(user_id=user_id, limit=limit)

        # ---------- search_memory（默认） ----------
        from src.Agent.tools import search_memory, touch_memories

        try:
            parsed = json.loads(raw_arg)
            if isinstance(parsed, dict):
                keywords = [str(k).strip() for k in parsed.get("keywords", [])]
                tr = parsed.get("time_range")
                time_range = tuple(tr) if tr and len(tr) == 2 else None
            elif isinstance(parsed, list):
                keywords = [str(k).strip() for k in parsed if k]
                time_range = None
            else:
                raise ValueError("unexpected type")
        except (json.JSONDecodeError, ValueError):
            keywords = re.findall(r'["\']([^"\']+)["\']', raw_arg)
            time_range = None

        logger.info(f"[Agent] step={step} tool=search_memory keywords={keywords}")
        results = await search_memory(user_id=user_id, keywords=keywords, top_k=8, time_range=time_range)
        if results:
            hit_ids = [m["id"] for m in results]
            await touch_memories(hit_ids)
        log_react_observation(step, keywords, results)
        return self._format_memories(results) or "未找到相关信息"

    @staticmethod
    def _extract_action_output(content: str) -> str:
        """
        从思考模型的输出里提取有效的 Action 或 finish 行。
        思考模型（如 mimo）会把分析过程混在 content 里，
        有效指令通常在最后几行。
        """
        lines = content.splitlines()

        # 从后往前找最后一个 finish(...) 或 Action: 行
        action_line = ""
        finish_line = ""
        thought_lines = []

        for line in reversed(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if not finish_line and re.search(r'finish\s*\(', stripped):
                finish_line = stripped
            if not action_line and re.search(r'Action\s*:', stripped):
                action_line = stripped
            if finish_line and action_line:
                break

        # 优先 finish，其次 Action
        if finish_line:
            # 保留 finish 之前的 Thought（取最后一个 Thought: 行）
            for line in reversed(lines):
                stripped = line.strip()
                if stripped.startswith("Thought:"):
                    thought_lines = [stripped]
                    break
            return "\n".join(thought_lines + [finish_line])

        if action_line:
            for line in reversed(lines):
                stripped = line.strip()
                if stripped.startswith("Thought:"):
                    thought_lines = [stripped]
                    break
            return "\n".join(thought_lines + [action_line])

        # 没找到结构化输出，返回原始内容（让后续逻辑处理）
        return content

    @staticmethod
    def _format_history(history: list[dict], max_turns: int = 6) -> str:
        """格式化最近几轮对话历史"""
        from datetime import datetime
        recent = history[-max_turns * 2:] if len(history) > max_turns * 2 else history
        lines = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:300]
            ts = msg.get("timestamp")
            time_str = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S") if ts else ""
            prefix = f"[{time_str}] " if time_str else ""
            if role == "user":
                name = msg.get("nickname", "用户")
                uid = msg.get("user_id", "")
                lines.append(f"{prefix}{name}(ta的昵称:None,ta的id:{uid}): {content}")
            else:
                lines.append(f"{prefix}小雫(ta的昵称:None,ta的id:): {content}")
        return "\n".join(lines) if lines else "（无历史记录）"

    @staticmethod
    def _format_image_descs(records: list[dict]) -> str:
        """将图片描述检索结果格式化"""
        from datetime import datetime as dt
        lines = []
        for rec in records:
            date_str = dt.fromtimestamp(rec.get("created_at", 0)).strftime("%Y年%m月%d日 %H:%M")
            nickname = rec.get("nickname", "") or "用户"
            desc = rec.get("description", "")
            lines.append(f"{date_str}，{nickname}发送了图片：{desc}")
        return "\n".join(lines)

    @staticmethod
    def _format_subgraph(subgraph: dict) -> str:
        """兜底：格式化图检索子图为文本"""
        entities = subgraph.get("entities", [])
        relations = subgraph.get("relations", [])
        if not entities and not relations:
            return ""
        lines = []
        if entities:
            lines.append("【相关实体】")
            for e in entities:
                summary = f"：{e['summary']}" if e.get("summary") else ""
                lines.append(f"  {e.get('entity_type', '')} · {e.get('name', '')}{summary}")
        if relations:
            lines.append("【关系】")
            for r in relations:
                lines.append(f"  {r.get('from', '')} -[{r.get('rel_type', '')}]-> {r.get('to', '')}：{r.get('description', '')}")
        return "\n".join(lines)

    @staticmethod
    def _format_web_results(results: list[dict]) -> str:
        """将联网搜索结果格式化为文本块"""
        if not results:
            return ""
        lines = []
        for item in results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            if title or snippet:
                lines.append(f"【{title}】{snippet}" if title else snippet)
        return "\n".join(lines)

    @staticmethod
    def _get_time_period(hour: int) -> str:
        """根据小时数返回时间段标签"""
        if 0 <= hour < 5:
            return "凌晨"
        elif 5 <= hour < 9:
            return "早晨"
        elif 9 <= hour < 12:
            return "上午"
        elif 12 <= hour < 14:
            return "中午"
        elif 14 <= hour < 18:
            return "下午"
        elif 18 <= hour < 23:
            return "晚上"
        else:
            return "深夜"

    @staticmethod
    def _format_memories(memories: list[dict]) -> str:
        """将检索结果格式化为叙述式记忆文本块"""
        from datetime import datetime as dt
        lines = []
        for mem in memories:
            keywords_str = mem.get("keywords", "")
            first_kw = keywords_str.split(",")[0].strip() if keywords_str else "记忆"
            ts = mem.get("created_at", 0)
            d = dt.fromtimestamp(ts)
            period = MemoryAgent._get_time_period(d.hour)
            date_str = d.strftime(f"%Y年%m月%d日 {period}（%H:%M）")
            nickname = mem.get("nickname", "") or "用户"
            user_text = mem.get("user_text", "")
            bot_text = mem.get("bot_text", "")
            user_short = user_text[:150] + ("..." if len(user_text) > 150 else "")
            bot_short = bot_text[:150] + ("..." if len(bot_text) > 150 else "")
            lines.append(
                f"关于「{first_kw}」的记忆：{date_str}，{nickname}说{user_short}，小雫对{nickname}说{bot_short}"
            )
        return "\n".join(lines)

    @staticmethod
    def _extract_hint(content: str) -> str:
        """从思考型模型输出里提取情境建议"""
        for line in reversed(content.splitlines()):
            line = line.strip()
            if "|" in line and len(line) <= 80:
                return line
        for line in reversed(content.splitlines()):
            line = line.strip()
            if line and len(line) <= 80 and not line.startswith("-") and not line.startswith("*"):
                return line
        return content.strip()[:80] if content.strip() else ""

    @staticmethod
    def _parse_json(content: str) -> dict:
        """容错 JSON 解析，兼容思考型模型"""
        matches = list(re.finditer(r'\{[^{}]*\}', content, re.DOTALL))
        for m in reversed(matches):
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass
        return {}


# ========================
# CoreAgent — 小雫内核系统
# ========================

_CORE_SYSTEM = """你是小雫的内核系统，负责小雫的日常节律管理（睡眠、醒来、日程、心跳）。

【角色关系】
- 小雫是你的主人格，你是为小雫服务的内核系统
- 生成反思/摘要/感受时，必须以小雫的第一人称视角写（"我"=小雫，用任务中给定的用户昵称称呼用户）

你有以下工具：

【检索类】
- search_memory(keywords: list[str], time_range?: [start, end]) → 语义检索对话历史记忆片段
- search_reflections(limit?: int) → 读取反思日记（每次睡前对上一段清醒期的压缩摘要与对话质量分，默认最近 3 条）
- search_image_desc(keywords: list[str]) → 检索用户发送过的图片描述
- search_web(query: str) → 联网搜索现实信息
- search_graph(query: str, depth: int) → 图记忆检索实体和关系网络
- list_graph(page?: int, page_size?: int) → 列出图数据库中的所有实体
- query_conversations(since?: float, before?: float, count?: int) → 按时间范围直接查询对话记录（不做语义检索，适合查某个时间段的所有对话）

【读取类】
- read_conversation(user_id: str, count: int, before_timestamp?: float) → 按时间顺序读取历史对话

【推理类】
- think(content: str) → 纯推理步骤，不调用外部工具
- get_character_info() → 读取小雫的角色设定

【写入类】
- save_note(user_id: str, content: str, tags: list[str], importance?: float) → 主动记录重要信息

【两套记忆库】
- 对话记忆库：search_memory / query_conversations / read_conversation（原始或向量检索的具体聊天）
- 反思日记库：search_reflections（清醒期日摘要，睡前写入；适合复盘「那天整体怎样」）
- 生成反思/打分任务：用 query_conversations 拉取时间段内全部对话；心跳决策：可先用 search_reflections 把握近期概况，再用 search_memory 查具体话题。

工具使用指南：
- 需要查看某段时间的全部对话（如睡前复盘、打分）→ query_conversations（指定 since/before 时间戳）
- 需要语义检索相关记忆 → search_memory
- 需要近期日摘要、整体相处感受 → search_reflections
- 需要了解小雫性格 → get_character_info
- 需要分析推理 → think

搜索策略完全由你决定。

输出格式（每次只输出一个 Thought + 一个 Action 或 finish）：
Thought: <推理>
Action: <工具调用>
或
Thought: <总结>
finish(type="<任务指定的类型>", content="<内容>")

⚠️ 重要：finish 的 type 必须严格使用任务指定的类型，不要自己编造类型。
⚠️ 重要：content 里不能有换行，单引号用\\'转义。
⚠️ 重要：任务完成后只需输出一次 finish，不要重复输出。"""


class CoreAgent(MemoryAgent):
    """复用 MemoryAgent 的 ReAct 循环和全部工具，用硬编码指令驱动小雫内核流程"""

    def __init__(self):
        super().__init__()

    # ========================
    # ① 生成反思摘要
    # ========================
    async def run_reflection(
        self,
        user_id: str,
        sleep_start: float,
        sleep_end: float,
        user_name: str = "",
    ) -> str:
        """Agent 生成反思摘要（≤500字），返回摘要文本"""
        from datetime import datetime as dt
        wake_str = dt.fromtimestamp(sleep_start).strftime("%Y-%m-%d %H:%M")
        sleep_str = dt.fromtimestamp(sleep_end).strftime("%Y-%m-%d %H:%M")
        today_str = dt.now().strftime("%Y年%m月%d日 %H:%M")

        user_label = user_name or "用户"
        user_ref = f"「{user_label}」" if user_name else "用户"

        user_msg = (
            f"当前时间：{today_str}\n"
            f"小雫刚刚睡着。本次清醒期是 {wake_str} 到 {sleep_str}，请复盘这一整段清醒期的对话。\n"
            f"用户昵称是{user_ref}，小雫平时叫 ta {user_ref}。\n"
            f"请用 query_conversations(since, before) 检索该时间段内所有对话（含睡眠中用户发来、小雫未回复的消息），"
            f"然后以小雫的第一人称视角输出 JSON（不要换行）：\n"
            f'{{"summary":"小雫视角的回忆，用「我」和{user_ref}，口语化，50字内","feeling":"小雫此刻的心情感受，30字内","highlights":["值得记住的细节1","细节2"]}}\n'
            f"⚠️ summary 必须是小雫的第一人称口吻（如「今天和{user_label}聊了…」），不要写成第三人称叙述。\n"
            f"⚠️ 必须使用 finish(type=\"reflect\", content=\"<上述JSON单行>\") 输出。"
        )

        messages = [
            Message(role="system", content=_CORE_SYSTEM),
            Message(role="user", content=user_msg),
        ]

        result = await self._react_loop(
            user_id=user_id,
            user_message=user_msg,
            messages=messages,
            valid_types=("reflect",),
        )
        raw = result.memory_block or result.context_hint or ""
        return self._parse_reflection_payload(raw)

    # ========================
    # ② 对话打分
    # ========================
    async def run_score(
        self,
        user_id: str,
        sleep_start: float,
        sleep_end: float,
    ) -> float:
        """Agent 给对话打分（1.0-10.0），返回分数"""
        from datetime import datetime as dt
        wake_str = dt.fromtimestamp(sleep_start).strftime("%Y-%m-%d %H:%M")
        sleep_str = dt.fromtimestamp(sleep_end).strftime("%Y-%m-%d %H:%M")
        today_str = dt.now().strftime("%Y年%m月%d日 %H:%M")

        user_msg = (
            f"当前时间：{today_str}\n"
            f"小雫刚刚睡着，正在对本次清醒期 {wake_str} 到 {sleep_str} 的对话质量打分。\n"
            f"请用 query_conversations 工具查询该时间段内的对话记录，"
            f"然后根据对话质量打分，1.0-10分（浮点数）。\n"
            f"⚠️ finish 的 content 只能是纯数字，不能包含其他文字。"
            f"例如 finish(type=\"score\", content=\"8.8\")"
        )

        messages = [
            Message(role="system", content=_CORE_SYSTEM),
            Message(role="user", content=user_msg),
        ]

        result = await self._react_loop(
            user_id=user_id,
            user_message=user_msg,
            messages=messages,
            valid_types=("score",),
        )

        # 从 finish content 中提取分数
        raw = result.memory_block or result.context_hint or "5.0"
        return self._extract_score(raw)

    # ========================
    # ③ 生成日程表
    # ========================
    async def run_daily_plan(self, user_id: str) -> list[dict]:
        """Agent 生成今日日程（15~20项，带时间），返回 [{"start":"HH:MM","end":"HH:MM","activity":"..."}]"""
        from datetime import datetime as dt
        today_str = dt.now().strftime("%Y年%m月%d日 %H:%M")

        user_msg = (
            f"当前时间：{today_str}\n"
            f"小雫睡醒了，请安排今天的日程，15~20项，覆盖从醒来到睡觉，可以闲着。\n"
            "⚠️ 必须使用 finish(type=\"schedule\", content='[{\"start\":\"HH:MM\",\"end\":\"HH:MM\",\"activity\":\"活动描述\"},...]') 输出结果。\n"
            "每项活动用 start 和 end 标记时间段（24小时制），activity 简短描述在做什么。"
        )

        messages = [
            Message(role="system", content=_CORE_SYSTEM),
            Message(role="user", content=user_msg),
        ]

        result = await self._react_loop(
            user_id=user_id,
            user_message=user_msg,
            messages=messages,
            valid_types=("schedule",),
        )

        raw = result.memory_block or result.context_hint or "[]"
        return self._extract_schedule(raw)

    # ========================
    # ④ 生成心跳计划
    # ========================
    async def run_wake_unread_reply(self, user_id: str, unread_text: str) -> str:
        """睡醒后处理睡眠期间未读消息，返回回复文本"""
        from datetime import datetime as dt
        today_str = dt.now().strftime("%Y年%m月%d日 %H:%M")
        user_msg = (
            f"当前时间：{today_str}\n"
            f"小雫刚睡醒，发现用户在你睡觉时发了这些消息：\n{unread_text}\n\n"
            f"可先 query_conversations 或 search_reflections 补充上下文，"
            f"然后自然回复，像刚看到一样。\n"
            f"⚠️ 必须使用 finish(type=\"send\", content=\"回复内容\") 输出。"
        )
        messages = [
            Message(role="system", content=_CORE_SYSTEM),
            Message(role="user", content=user_msg),
        ]
        result = await self._react_loop(
            user_id=user_id,
            user_message=user_msg,
            messages=messages,
            valid_types=("send",),
        )
        return (result.memory_block or result.context_hint or "").strip()

    async def run_heartbeat_plan(
        self,
        user_id: str,
        max_beats: int,
        min_beats: int = 3,
    ) -> dict:
        """Agent 生成心跳次数和随机间隔，返回 {"count": N, "offsets_minutes": [...]}"""
        from datetime import datetime as dt
        today_str = dt.now().strftime("%Y年%m月%d日 %H:%M")

        user_msg = (
            f"当前时间：{today_str}\n"
            f"小雫睡醒了，请为小雫生成今天心跳次数，"
            f"至少{min_beats}次、最多{max_beats}次心跳，"
            f"不要固定时间，请随机打乱心跳间隔或长或短。\n"
            f"⚠️ 必须使用 finish(type=\"heartbeat_plan\", content='{{\"count\":5,\"offsets_minutes\":[30,120,80,200,150]}}') 输出结果。"
        )

        messages = [
            Message(role="system", content=_CORE_SYSTEM),
            Message(role="user", content=user_msg),
        ]

        result = await self._react_loop(
            user_id=user_id,
            user_message=user_msg,
            messages=messages,
            valid_types=("heartbeat_plan",),
        )

        raw = result.memory_block or result.context_hint or "{}"
        return self._extract_heartbeat_plan(raw, max_beats, min_beats)

    # ========================
    # ⑤ 心跳决策
    # ========================
    async def run_heartbeat_decision(
        self,
        user_id: str,
        current_time: str,
        current_activity: str,
        reflections_summary: str,
        time_since_last: str,
    ) -> tuple[str, str]:
        """
        Agent 决定是否主动发消息。
        返回 (decision, message)：
          - ("skip", "") — 不发
          - ("send", "消息内容") — 发送
        """
        user_msg = (
            f"当前时间是{current_time}，小雫当前正在「{current_activity}」。\n"
            f"距上次与用户对话：{time_since_last}。\n"
            f"近期反思摘要：{reflections_summary}\n\n"
            f"请判断是否需要主动给用户发消息。你有三种信息来源，请灵活组合：\n\n"
            f"【① 记忆】search_memory — 检索过去的对话片段。\n"
            f"  → 用途：作为话题的起点或灵感，不要直接复述旧对话。\n"
            f"  → 例：想起「昨天答应过蛋包饭」→ 可以说「说起来那个蛋包饭呢」\n"
            f"  → 禁止：逐字复述旧对话内容、问用户「你还记得...吗」\n\n"
            f"【② 反思】search_reflections — 小雫自己的反思日记。\n"
            f"  → 用途：了解最近的生活状态和情绪变化，帮助决定聊什么。\n\n"
            f"【③ 联网】search_web — 小雫了解外面世界的唯一窗口。\n"
            f"  → 当前活动涉及外部信息时（歌、番、新闻、美食等），先搜再分享。\n"
            f"  → 例：在刷番 → search_web 搜「最近新番」→ 基于搜索结果说感想。\n"
            f"  → 这是让消息「有新鲜感」的关键，不要只聊旧事。\n\n"
            f"⚠️ 默认倾向 skip：大多数心跳不必打扰用户。\n"
            f"⚠️ 禁止早安打卡、固定关怀模板、重复上次说过的话。\n"
            f"⚠️ 好的消息 = 当前活动 + 三种来源的自然融合。\n"
            f"⚠️ 如果不需要发消息，使用 finish(type=\"skip\")。\n"
            f"⚠️ 如果需要发消息，先想清楚话题，再 finish(type=\"send\", content=\"消息内容\")。"
        )

        messages = [
            Message(role="system", content=_CORE_SYSTEM),
            Message(role="user", content=user_msg),
        ]

        result = await self._react_loop(
            user_id=user_id,
            user_message=user_msg,
            messages=messages,
            valid_types=("skip", "send"),
        )

        # 从 AgentResult 解析决策
        if result.need_retrieval and result.found_memory:
            return "send", result.memory_block
        elif result.context_hint:
            # 尝试从 hint 中提取 send 内容
            if "send" in result.context_hint.lower():
                return "send", result.context_hint
        return "skip", ""

    # ========================
    # 辅助方法
    # ========================

    @staticmethod
    def _parse_reflection_payload(raw) -> dict:
        """解析结构化反思 JSON，支持 str 或 dict 输入，失败则仅 summary"""
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, str):
            data = MemoryAgent._parse_json(raw)
            if not isinstance(data, dict) or not data.get("summary"):
                try:
                    data = json.loads(raw.strip())
                except json.JSONDecodeError:
                    data = {}
        else:
            data = {}

        if isinstance(data, dict) and data.get("summary"):
            hl = data.get("highlights", [])
            if not isinstance(hl, list):
                hl = [str(hl)] if hl else []
            return {
                "summary": str(data.get("summary", ""))[:500],
                "feeling": str(data.get("feeling", ""))[:200],
                "highlights": [str(x)[:120] for x in hl[:3]],
            }
        text = str(raw).strip()[:500] or "（今日无对话）"
        return {"summary": text, "feeling": "", "highlights": []}

    @staticmethod
    def _extract_score(raw: str) -> float:
        """从 Agent 输出中提取分数（找 1.0~10.0 范围内的数字）"""
        import re as _re
        # 找所有浮点数
        matches = _re.findall(r'(\d+\.\d+)', raw)
        # 优先找 1.0~10.0 范围内的
        for m in reversed(matches):
            val = float(m)
            if 1.0 <= val <= 10.0:
                return val
        # 兜底：找整数 1~10
        for m in reversed(_re.findall(r'\b(\d+)\b', raw)):
            val = float(m)
            if 1.0 <= val <= 10.0:
                return val
        return 5.0

    @staticmethod
    def _extract_json_list(raw: str) -> list[str]:
        """从 Agent 输出中提取 JSON 数组"""
        import re as _re
        # 尝试找 JSON 数组
        match = _re.search(r'\[.*?\]', raw, _re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return [str(item) for item in data]
            except json.JSONDecodeError:
                pass
        return ["休息"]

    @staticmethod
    def _extract_schedule(raw: str) -> list[dict]:
        """从 Agent 输出中提取日程（兼容新旧格式）"""
        import re as _re
        match = _re.search(r'\[.*\]', raw, _re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list) and data:
                    # 新格式：对象数组
                    if isinstance(data[0], dict) and "activity" in data[0]:
                        return data
                    # 旧格式：字符串数组 → 均分时间兜底
                    if isinstance(data[0], str):
                        return CoreAgent._strings_to_schedule(data)
            except json.JSONDecodeError:
                pass
        return [{"start": "08:00", "end": "22:00", "activity": "自由活动"}]

    @staticmethod
    def _strings_to_schedule(items: list[str]) -> list[dict]:
        """旧格式字符串数组 → 带时间的日程（均匀分配 8:00~22:00）"""
        if not items:
            return [{"start": "08:00", "end": "22:00", "activity": "自由活动"}]
        start_h, end_h = 8, 22
        span = (end_h - start_h) * 60  # 总分钟
        step = span // len(items)
        result = []
        for i, activity in enumerate(items):
            s_min = start_h * 60 + i * step
            e_min = s_min + step
            result.append({
                "start": f"{s_min // 60:02d}:{s_min % 60:02d}",
                "end": f"{e_min // 60:02d}:{e_min % 60:02d}",
                "activity": str(activity),
            })
        return result

    @staticmethod
    def _extract_heartbeat_plan(raw: str, max_beats: int, min_beats: int = 3) -> dict:
        """从 Agent 输出中提取心跳计划"""
        import re as _re
        min_beats = max(1, min(min_beats, max_beats))
        # 尝试找 JSON 对象
        match = _re.search(r'\{.*?\}', raw, _re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                count = int(data.get("count", min_beats))
                count = max(min_beats, min(count, max_beats))
                offsets = data.get("offsets_minutes", [])
                if isinstance(offsets, list) and len(offsets) >= count:
                    return {"count": count, "offsets_minutes": offsets[:count]}
                if isinstance(offsets, list) and offsets:
                    padded = list(offsets)
                    while len(padded) < count:
                        padded.append(padded[-1] + 60)
                    return {"count": count, "offsets_minutes": padded[:count]}
            except (json.JSONDecodeError, ValueError):
                pass
        # 兜底：均匀间隔
        count = max(min_beats, min(3, max_beats))
        return {"count": count, "offsets_minutes": [60 * (i + 1) for i in range(count)]}
