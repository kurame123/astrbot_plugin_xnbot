"""
角色扮演消息处理器
流程：收消息 → Agent（判断/检索/建议）→ 回复 LLM → 发送 → 异步写入记忆
"""
import json as _json
import time
from datetime import datetime
from pathlib import Path

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.exception import MatcherException
from nonebot.log import logger

from ai_server.client import call_model
from ai_server.schemas import Message
from src.bot.core.character_manager import get_character_manager
from src.bot.core.config_loader import (
    get_behavior_config,
    get_bot_config,
    get_character_config,
    get_model_system_prompt,
    get_rey_config,
)
from src.bot.core.session_manager import get_session_manager
from src.bot.core.reply_manager import segment_reply, get_send_interval
from tools.logger import (
    log_llm_call,
    log_flow,
    log_progress,
    truncate_log,
)

# 用户名缓存
_user_name_cache: dict[str, str] = {}

# 已加载历史的会话缓存
_history_loaded_sessions: set[str] = set()

# 日程 JSON 路径
_CORE_STATE_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "core_state"


def _get_current_activity_from_schedule(user_id: str) -> str:
    """从 core_state 读取当日日程，返回当前正在进行的活动"""
    try:
        schedule_path = _CORE_STATE_DIR / f"{user_id}_schedule.json"
        if not schedule_path.exists():
            return "自由活动"
        schedule = _json.loads(schedule_path.read_text(encoding="utf-8"))
        if not isinstance(schedule, list) or not schedule:
            return "自由活动"
        # 兼容旧格式（字符串列表）
        if isinstance(schedule[0], str):
            return "自由活动"
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        for item in schedule:
            try:
                sh, sm = map(int, item["start"].split(":"))
                eh, em = map(int, item["end"].split(":"))
                if sh * 60 + sm <= now_min < eh * 60 + em:
                    return item["activity"]
            except (KeyError, ValueError):
                continue
    except Exception:
        pass
    return "自由活动"


# 创建消息处理器
roleplay = on_message(priority=99, block=False)


@roleplay.handle()
async def handle_message(bot: Bot, event: MessageEvent):
    """处理收到的消息"""
    # ========== 阶段 0：收到消息，处理图片/表情 ==========
    user_text = event.get_plaintext().strip()

    emoji_desc = await process_incoming_emoji(event)
    image_text = await process_incoming_image(event)

    if emoji_desc:
        if image_text:
            user_text = f"{image_text} [动画表情：{emoji_desc}]"
        elif user_text:
            user_text = f"{user_text} [动画表情：{emoji_desc}]"
        else:
            user_text = f"[动画表情：{emoji_desc}]"
    elif image_text:
        user_text = image_text

    if not user_text:
        return

    user_id = str(event.user_id)
    group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None
    user_name = await get_user_name(bot, event)

    session_manager = get_session_manager()
    session_id = session_manager.make_session_id(user_id, group_id)

    # ========== XN_Core：睡眠状态检查 + 用户意图检测 ==========
    from XN_Core.reflection import is_sleeping, check_user_sleep_intent, save_user_route
    if is_sleeping(user_id):
        now_sleep = time.time()
        session_manager.append_message(session_id, "user", user_text, timestamp=now_sleep)
        save_user_route(user_id, session_id, group_id, user_name)
        try:
            from src.XN_Memory import get_writer
            get_writer().submit(
                user_id=user_id,
                user_text=user_text,
                bot_text="[睡眠中，小雫未回复]",
                session_id=session_id,
                nickname=user_name,
                created_at=now_sleep,
            )
        except Exception as e:
            logger.warning(f"[XN_Core] 睡眠中消息落库失败: {e}")
        return
    check_user_sleep_intent(user_id, user_text)
    save_user_route(user_id, session_id, group_id)

    from XN_Core.relation import should_skip_reply, record_silent_turn
    skip, _reason = should_skip_reply(user_id, user_text, session_id)
    if skip:
        record_silent_turn(user_id, user_text, session_id, user_name)
        return

    # 首次对话时从 Napcat 加载历史
    if session_id not in _history_loaded_sessions:
        await load_history_from_napcat(bot, event, session_id)
        _history_loaded_sessions.add(session_id)

    log_flow(
        "RECEIVE_MESSAGE",
        session_id,
        f"user={user_name}({user_id}) | text={truncate_log(user_text, 100)}",
    )

    try:
        reply = await generate_reply(
            session_id=session_id,
            user_id=user_id,
            user_text=user_text,
            user_name=user_name,
        )

        segments = await segment_reply(user_text, reply)
        emoji_segment = await try_match_emoji(reply)

        import asyncio
        from XN_Core.relation import get_send_interval_multiplier
        interval_mul = get_send_interval_multiplier(user_id)
        for i, seg in enumerate(segments):
            if i > 0:
                await asyncio.sleep(get_send_interval() * interval_mul)
            await bot.send(event, seg)

        # 全部 segment 发送后检测晚安（在 finish 之前，因为 finish 会抛异常）
        try:
            from XN_Core.reflection import check_sleep_signal
            await check_sleep_signal(user_id=user_id, bot_reply=reply)
        except Exception as e:
            logger.warning(f"[XN_Core] 睡眠信号检测异常: {e}")

        if emoji_segment:
            await asyncio.sleep(get_send_interval())
            await roleplay.finish(emoji_segment)
        else:
            await roleplay.finish()

    except MatcherException:
        raise
    except Exception as e:
        logger.error(f"AI 调用失败: {e}", exc_info=True)
        await roleplay.finish("抱歉，小雫现在有点迷糊...请稍后再试～")


async def generate_reply(
    session_id: str,
    user_id: str,
    user_text: str,
    user_name: str,
) -> str:
    """
    生成 AI 回复
    流程：Agent 判断/检索 → 回复 LLM → 异步写入记忆
    """
    from src.Agent import get_agent
    from src.XN_Memory import get_writer
    from src.EmotionCore import on_new_message, get_current_emotion
    from src.EmotionCore.manager import get_emotion_text

    session_manager = get_session_manager()
    now = time.time()

    # ========== 情绪系统：记录用户消息 ==========
    await on_new_message("user", user_text, now)

    # ========== 获取历史对话 ==========
    history_msgs = session_manager.get_history(session_id)

    # 转换为 Agent 需要的格式（带时间戳和用户信息）
    history_for_agent = [
        {
            "role": msg.role,
            "content": msg.content,
            "nickname": user_name if msg.role == "user" else "小雫",
            "user_id": user_id if msg.role == "user" else "",
        }
        for msg in history_msgs
    ]

    # ========== Agent 工作：判断/检索/建议 ==========
    log_progress(1, 2, "Agent 分析中...")
    agent = get_agent()
    agent_result = await agent.run(
        user_id=user_id,
        user_message=user_text,
        history=history_for_agent,
    )
    from XN_Core.relation import soften_memory_block, update_after_chat
    agent_block = soften_memory_block(agent_result.to_prompt_block(), user_id)
    logger.info(
        f"[Agent] need_retrieval={agent_result.need_retrieval} "
        f"found_memory={agent_result.found_memory}"
    )

    # ========== 回复 LLM ==========
    log_progress(2, 2, "思考中...")
    current_emotion = get_emotion_text(now)

    reply_text = await call_roleplay_model(
        session_id=session_id,
        user_id=user_id,
        history=history_msgs,
        user_text=user_text,
        user_name=user_name,
        agent_block=agent_block,
        current_emotion=current_emotion,
    )

    # 回复前缀
    prefix = get_character_manager().get_reply_prefix()
    if prefix:
        reply_text = f"{prefix}{reply_text}"

    # ========== 更新会话历史 ==========
    session_manager.append_message(session_id, "user", user_text, timestamp=now)
    session_manager.append_message(session_id, "assistant", reply_text, timestamp=time.time())

    # ========== 喂给图记忆缓冲区 ==========
    try:
        from src.XN_Memory.graph_writer import get_graph_writer
        gw = get_graph_writer()
        gw.add_message(user_id=user_id, role="user", content=user_text, nickname=user_name, timestamp=now)
        gw.add_message(user_id=user_id, role="assistant", content=reply_text, nickname="小雫", timestamp=time.time())
    except Exception as e:
        logger.warning(f"[GraphWriter] 消息入队失败: {e}")

    # ========== 情绪系统：记录小雫回复 ==========
    await on_new_message("assistant", reply_text, time.time())

    # ========== 异步写入记忆（非阻塞） ==========
    try:
        writer = get_writer()
        writer.submit(
            user_id=user_id,
            user_text=user_text,
            bot_text=reply_text,
            session_id=session_id,
            nickname=user_name,
            created_at=now,
        )
    except Exception as e:
        logger.warning(f"[XN_Memory] 提交写入任务失败: {e}")

    log_flow("SEND_MESSAGE", session_id, f"reply={truncate_log(reply_text, 100)}")
    update_after_chat(user_id, user_text, replied=True)

    return reply_text


async def call_roleplay_model(
    session_id: str,
    user_id: str,
    history: list,
    user_text: str,
    user_name: str,
    agent_block: str,
    current_emotion: str = "",
) -> str:
    """
    调用回复 LLM

    system prompt 结构：
      角色设定 + 情绪 + 时间 + 聊天记录（带相对时间戳）+ 触发消息高亮 + 记忆/情境建议 + 回复要求
    """
    from src.bot.core.session_manager import get_session_manager

    character_config = get_character_config()
    character_desc = character_config.get("short_desc", "")
    profile = character_config.get("profile", "").strip()
    bot_name = get_character_manager().get_character_name()

    # 格式化聊天记录（带相对时间戳）
    now = time.time()
    timestamped_history = get_session_manager().get_timestamped_history(session_id)

    def _relative_time(ts: float) -> str:
        diff = int(now - ts)
        if diff < 60:
            return "刚刚"
        elif diff < 3600:
            return f"{diff // 60}分钟前"
        elif diff < 86400:
            return f"{diff // 3600}小时前"
        else:
            return f"{diff // 86400}天前"

    lines = []
    for msg in timestamped_history:
        role_name = user_name if msg.role == "user" else bot_name
        time_label = _relative_time(msg.timestamp)
        lines.append(f"{time_label}, {role_name}(你): {msg.content}" if msg.role == "assistant"
                     else f"{time_label}, {role_name}: {msg.content}")
    chat_history_text = "\n".join(lines) if lines else "（暂无聊天记录）"

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emotion_text = current_emotion if current_emotion else "平静"
    current_activity = _get_current_activity_from_schedule(user_id)
    from XN_Core.relation import build_attitude_hint, get_reply_style_hint
    attitude_hint = build_attitude_hint(user_id, session_id)
    reply_style = get_reply_style_hint(user_id)

    # 从 rey_config 取 system prompt 模板并替换静态变量（角色设定/性格）
    reply_sp = get_model_system_prompt("roleplay_main")
    reply_sp = (
        reply_sp
        .replace("{character_desc}", character_desc)
        .replace("{profile}", profile)
    )

    # 动态内容注入到 user message（有利于缓存命中）
    rey_cfg = get_rey_config()
    user_tpl = rey_cfg.get("roleplay_main", {}).get(
        "user_prompt_template",
        # 兜底模板（配置缺失时使用）
        "【现在是】{current_time}\n【心情】{current_emotion}\n【小雫正在】{current_activity}\n\n【聊天记录】\n{chat_history}\n\n【记忆参考】{memory}\n\n{user_name}：{trigger_message}"
    )
    user_prompt = (
        user_tpl
        .replace("{current_time}", current_time)
        .replace("{current_emotion}", emotion_text)
        .replace("{current_activity}", current_activity)
        .replace("{attitude_hint}", attitude_hint)
        .replace("{reply_style}", reply_style)
        .replace("{chat_history}", chat_history_text)
        .replace("{memory}", agent_block)
        .replace("{user_name}", user_name)
        .replace("{trigger_message}", user_text)
    )

    messages = [
        Message(role="system", content=reply_sp),
        Message(role="user", content=user_prompt),
    ]

    response = await call_model("roleplay_main", messages)
    reply_text = response.content.strip()

    log_llm_call(
        model_name="roleplay_main",
        session_id=session_id,
        messages=messages,
        response=reply_text,
        usage=response.usage,
        reasoning_content=response.reasoning_content,
    )

    return reply_text


# ========== 历史加载 ==========

async def load_history_from_napcat(
    bot: Bot, event: MessageEvent, session_id: str
) -> None:
    """从 Napcat 加载历史消息到会话缓存"""
    session_manager = get_session_manager()
    behavior = get_behavior_config()
    limit = behavior.get("history_load_limit", 12)
    self_id = str(bot.self_id)

    if session_manager.get_message_count(session_id) > 0:
        return

    try:
        if isinstance(event, GroupMessageEvent):
            result = await bot.call_api(
                "get_group_msg_history",
                group_id=event.group_id,
                count=limit,
            )
        else:
            result = await bot.call_api(
                "get_friend_msg_history",
                user_id=event.user_id,
                count=limit,
            )

        messages = sorted(
            result.get("messages", []), key=lambda m: m.get("time", 0)
        )

        error_keywords = ["抱歉，小雫现在有点迷糊"]

        for msg in messages:
            sender_id = str(msg.get("sender", {}).get("user_id", 0))
            content = "".join(
                seg.get("data", {}).get("text", "")
                for seg in msg.get("message", [])
                if seg.get("type") == "text"
            ).strip()

            if not content:
                continue
            if any(kw in content for kw in error_keywords):
                continue

            role = "assistant" if sender_id == self_id else "user"
            session_manager.append_message(session_id, role, content, timestamp=float(msg.get("time", time.time())))

        logger.info(f"[HISTORY] 加载完成 session={session_id} count={len(messages)}")

    except Exception as e:
        logger.warning(f"[HISTORY] 加载失败: {e}")


async def get_user_name(bot: Bot, event: MessageEvent) -> str:
    """获取用户昵称，优先使用好友备注"""
    user_id = str(event.user_id)
    if user_id in _user_name_cache:
        return _user_name_cache[user_id]

    # 优先尝试获取好友备注
    try:
        info = await bot.call_api("get_friend_info", user_id=event.user_id)
        remark = info.get("remark", "")
        if remark:
            _user_name_cache[user_id] = remark
            return remark
    except Exception:
        pass

    # 回退到 sender 字段
    nickname = event.sender.nickname or event.sender.card or f"用户{user_id}"
    _user_name_cache[user_id] = nickname
    return nickname


# ========== 表情 / 图片处理 ==========

async def process_incoming_emoji(event: MessageEvent) -> str | None:
    try:
        from src.emojiCore import handle_incoming_emoji
        session_manager = get_session_manager()
        user_id = str(event.user_id)
        group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None
        session_id = session_manager.make_session_id(user_id, group_id)

        for seg in event.message:
            if seg.type == "image":
                image_url = seg.data.get("url", "")
                if not image_url:
                    continue
                summary = seg.data.get("summary", "")
                if "动画表情" in summary:
                    emoji_record = await handle_incoming_emoji(
                        user_id=user_id,
                        session_id=session_id,
                        image_url=image_url,
                        is_animated_emoji=True,
                    )
                    if emoji_record:
                        return emoji_record.desc
    except Exception as e:
        logger.warning(f"[EMOJI] 处理失败: {e}")
    return None


async def process_incoming_image(event: MessageEvent) -> str | None:
    """处理收到的普通图片，返回格式化文本"""
    try:
        from src.bot.img import handle_image
        session_manager = get_session_manager()
        user_id = str(event.user_id)
        group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None
        session_id = session_manager.make_session_id(user_id, group_id)
        user_name = _user_name_cache.get(user_id, f"用户{user_id}")

        image_urls = [
            seg.data.get("url", "")
            for seg in event.message
            if seg.type == "image"
            and "动画表情" not in seg.data.get("summary", "")
            and seg.data.get("url", "")
        ]

        if not image_urls:
            return None

        original_text = event.get_plaintext().strip() or None

        # 多张图片只处理第一张，其余忽略（避免 token 爆炸）
        return await handle_image(
            user_id=user_id,
            nickname=user_name,
            image_url=image_urls[0],
            session_id=session_id,
            original_text=original_text,
        )

    except Exception as e:
        logger.warning(f"[IMG] 处理失败: {e}")
    return None


async def try_match_emoji(reply_text: str) -> MessageSegment | None:
    try:
        from src.emojiCore import find_best_emoji_for_text
        from pathlib import Path

        match = await find_best_emoji_for_text(reply_text)
        if match:
            file_path = Path(match.file_path)
            if file_path.exists():
                return MessageSegment.image(f"file:///{file_path.absolute()}")
    except Exception as e:
        logger.warning(f"[EMOJI_MATCH] 匹配失败: {e}")
    return None
