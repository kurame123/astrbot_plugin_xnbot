"""
astrbot_plugin_xnbot — 小雫 AstrBot 插件入口

接管所有对话消息，完整复用小雫的核心逻辑：
- Agent 记忆检索
- 角色扮演回复
- XN_Core（睡眠/心跳/日程/关系）
- 情绪系统
- 表情系统
- 记忆系统（SQLite + FAISS + Kùzu）
"""
import asyncio
import sys
import time
from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.event import filter
from astrbot.api.event.filter import EventMessageType

# 小雫核心模块路径（相对于本插件目录）
PLUGIN_DIR = Path(__file__).parent
sys.path.insert(0, str(PLUGIN_DIR))

# 应用 NoneBot 兼容层（必须在导入小雫模块之前，且只执行一次）
if "nonebot" not in sys.modules:
    from nonebot_compat import patch_nonebot_imports
    patch_nonebot_imports()

from astrbot import logger


class XNBotPlugin(star.Star):
    """小雫 AstrBot 插件 — 接管所有对话"""

    def __init__(self, context: star.Context) -> None:
        self.context = context
        self._initialized = False
        self._bot = None  # AstrBot 的 bot 实例，用于主动发消息

    async def initialize(self) -> None:
        """插件激活时初始化小雫核心"""
        if self._initialized:
            return

        # 防止重载时重复初始化（全局单例无法重置）
        import importlib
        if "src.XN_Memory" in sys.modules:
            mod = sys.modules["src.XN_Memory"]
            if hasattr(mod, "_store") and mod._store is not None:
                logger.info("[XNBot] 检测到已初始化，跳过重复初始化")
                self._initialized = True
                return

        try:
            # 启动横幅
            _xn_banner = """
\033[38;5;111m  ██╗  ██╗███╗   ██╗     ██████╗ ██████╗ ██████╗ ███████╗
\033[38;5;117m  ╚██╗██╔╝████╗  ██║    ██╔════╝██╔═══██╗██╔══██╗██╔════╝
\033[38;5;123m   ╚███╔╝ ██╔██╗ ██║    ██║     ██║   ██║██████╔╝█████╗
\033[38;5;129m   ██╔██╗ ██║╚██╗██║    ██║     ██║   ██║██╔══██╗██╔══╝
\033[38;5;135m  ██╔╝ ██╗██║ ╚████║    ╚██████╗╚██████╔╝██║  ██║███████╗
\033[38;5;141m  ╚═╝  ╚═╝╚═╝  ╚═══╝     ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝\033[0m"""
            print(_xn_banner)

            # 初始化配置
            from src.bot.core.config_loader import init_config
            init_config()
            logger.info("[XNBot] 配置加载完成")

            # 初始化记忆系统
            from src.XN_Memory import init_memory
            init_memory()
            logger.info("[XNBot] 记忆系统初始化完成")

            # 初始化图片描述数据库
            from src.bot.img.store import get_image_store
            get_image_store()
            logger.info("[XNBot] 图片描述数据库初始化完成")

            # 初始化表情系统
            from src.emojiCore import init_emoji_system
            init_emoji_system()
            logger.info("[XNBot] 表情系统初始化完成")

            # 启动记忆写入 worker
            from src.XN_Memory import get_writer
            get_writer().start_worker()
            logger.info("[XNBot] 记忆写入 worker 已启动")

            # 启动图记忆写入
            from src.XN_Memory.graph_writer import get_graph_writer
            get_graph_writer().start()
            logger.info("[XNBot] 图记忆 writer 已启动")

            # 恢复 XN_Core 睡眠状态
            from XN_Core.reflection import restore_sleep_states
            from XN_Core.heartbeat import get_monitor
            restored = restore_sleep_states()
            monitor = get_monitor()
            for item in restored:
                if not item.get("already_wake"):
                    monitor.start_user_cycle(item["user_id"], item["sleep_hours"])
                    logger.info(f"[XNBot] 已恢复心跳计时器 user={item['user_id']}")
                else:
                    # 已过唤醒时间，但 bot 实例此时还未绑定，登记到 pending
                    # 等 on_message 首次触发时绑定 bot 后再处理
                    monitor._pending_wake_on_connect[item["user_id"]] = True
                    logger.info(f"[XNBot] 已过唤醒时间 user={item['user_id']}，等待 bot 实例绑定后触发醒来")
            if restored:
                logger.info(f"[XNBot] 恢复了 {len(restored)} 个睡眠状态")
            monitor.restore_pending_heartbeats()

            # 启动小雫 WebUI（端口 8081）
            asyncio.create_task(self._start_webui())

            self._initialized = True
            logger.info("[XNBot] ✓ 小雫核心初始化完成！")

        except Exception as e:
            logger.error(f"[XNBot] 初始化失败: {e}", exc_info=True)

    async def terminate(self) -> None:
        """插件禁用/重载时清理资源"""
        try:
            # 关闭心跳监控
            from XN_Core.heartbeat import get_monitor
            get_monitor().cancel_all()
        except Exception:
            pass

        try:
            # 关闭表情系统（释放数据库连接）
            from src.emojiCore import close_emoji_system
            close_emoji_system()
        except Exception:
            pass

        try:
            # 关闭记忆系统
            from src.XN_Memory import get_writer
            get_writer().stop_worker()
        except Exception:
            pass

        try:
            # 关闭图片描述数据库
            from src.bot.img.store import get_image_store
            store = get_image_store()
            if hasattr(store, 'close'):
                store.close()
        except Exception:
            pass

        self._initialized = False
        logger.info("[XNBot] 小雫插件已卸载，资源已清理")

    # ========================
    # 消息处理：接管所有对话
    # ========================

    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> None:
        """拦截所有消息，交给小雫处理"""
        if not self._initialized:
            await self.initialize()

        # 获取消息信息
        user_text = event.get_message_str().strip()
        if not user_text:
            return

        # 以 / 开头的是命令，不拦截
        if user_text.startswith("/"):
            return

        # 阻止 AstrBot 默认的 LLM 处理
        event.call_llm = True

        user_id = event.get_sender_id()
        group_id = event.get_group_id() if hasattr(event, 'get_group_id') else None
        user_name = event.get_sender_name() or f"用户{user_id}"

        # 存储 bot 实例用于主动发消息
        if self._bot is None:
            self._bot = event.bot
            # 绑定 bot 到心跳监控器，并触发重启时未及时执行的醒来流程
            try:
                from XN_Core.heartbeat import get_monitor
                monitor = get_monitor()
                monitor.set_bot(self._bot)
                for user_id in list(monitor._pending_wake_on_connect.keys()):
                    logger.info(f"[XNBot] bot 已绑定，补触发醒来流程 user={user_id}")
                    asyncio.create_task(monitor._on_wake(user_id))
                monitor._pending_wake_on_connect.clear()
            except Exception as e:
                logger.warning(f"[XNBot] 心跳监控绑定失败: {e}")

        try:
            # 调用小雫的消息处理流程
            reply = await self._handle_xnbot_message(
                user_id=str(user_id),
                user_text=user_text,
                user_name=user_name,
                group_id=str(group_id) if group_id else None,
                event=event,
            )

            if reply:
                # 发送回复
                result = MessageEventResult()
                result.result_content_type = "text"
                result.async_stream_callback = None
                await event.send(result.message(reply).stop_event())

        except Exception as e:
            logger.error(f"[XNBot] 处理消息失败: {e}", exc_info=True)
            result = MessageEventResult()
            await event.send(result.message("抱歉，小雫现在有点迷糊...请稍后再试～").stop_event())

    async def _handle_xnbot_message(
        self,
        user_id: str,
        user_text: str,
        user_name: str,
        group_id: str | None,
        event: AstrMessageEvent,
    ) -> str | None:
        """
        小雫核心消息处理流程
        完整复用原 XNBot 的逻辑
        """
        from src.bot.core.session_manager import get_session_manager
        from src.bot.core.config_loader import get_bot_config

        session_manager = get_session_manager()
        session_id = session_manager.make_session_id(user_id, group_id)

        # ========== XN_Core：睡眠状态检查 + 用户意图检测 ==========
        from XN_Core.reflection import is_sleeping, check_user_sleep_intent, save_user_route
        if is_sleeping(user_id):
            now = time.time()
            session_manager.append_message(session_id, "user", user_text, timestamp=now)
            save_user_route(user_id, session_id, group_id, user_name)
            try:
                # 睡眠期间消息直接写入 SQLite，不走关键词提取队列
                # 避免因 LLM 调用失败导致消息丢失，醒来后无法读取未读
                from src.XN_Memory import get_store
                get_store().insert_memory(
                    user_id=user_id,
                    user_text=user_text,
                    bot_text="[睡眠中，小雫未回复]",
                    keywords=[],
                    importance=0.5,
                    session_id=session_id,
                    nickname=user_name,
                    created_at=now,
                )
            except Exception as e:
                logger.warning(f"[XNBot] 睡眠中消息落库失败: {e}")
            return None

        check_user_sleep_intent(user_id, user_text)
        save_user_route(user_id, session_id, group_id, user_name)

        # ========== 沉默决策 ==========
        from XN_Core.relation import should_skip_reply, record_silent_turn
        skip, _reason = should_skip_reply(user_id, user_text, session_id)
        if skip:
            record_silent_turn(user_id, user_text, session_id, user_name)
            return None

        # ========== 生成回复 ==========
        reply = await self._generate_reply(
            session_id=session_id,
            user_id=user_id,
            user_text=user_text,
            user_name=user_name,
        )

        if reply:
            # 检测晚安信号
            try:
                from XN_Core.reflection import check_sleep_signal
                await check_sleep_signal(user_id=user_id, bot_reply=reply)
            except Exception as e:
                logger.warning(f"[XNBot] 睡眠信号检测异常: {e}")

        return reply

    async def _generate_reply(
        self,
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
        from src.bot.core.session_manager import get_session_manager
        from src.bot.core.reply_manager import segment_reply
        from ai_server.client import call_model
        from ai_server.schemas import Message
        from src.bot.core.config_loader import (
            get_character_config,
            get_model_system_prompt,
            get_rey_config,
        )
        from src.bot.core.character_manager import get_character_manager

        session_manager = get_session_manager()
        now = time.time()

        # ========== 情绪系统：记录用户消息 ==========
        await on_new_message("user", user_text, now)

        # ========== 获取历史对话 ==========
        history_msgs = session_manager.get_history(session_id)

        # 转换为 Agent 需要的格式
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
        current_emotion = get_emotion_text(now)
        reply_text = await self._call_roleplay_model(
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

        update_after_chat(user_id, user_text, replied=True)

        # ========== 回复切分 ==========
        segments = await segment_reply(user_text, reply_text)
        if len(segments) > 1:
            # 多条消息，返回第一条，其余通过主动消息发送
            for seg in segments[1:]:
                await asyncio.sleep(0.6)
                await self._send_to_user(user_id, group_id, seg)
            return segments[0]

        return reply_text

    async def _call_roleplay_model(
        self,
        session_id: str,
        user_id: str,
        history: list,
        user_text: str,
        user_name: str,
        agent_block: str,
        current_emotion: str = "",
    ) -> str:
        """调用回复 LLM"""
        from src.bot.core.session_manager import get_session_manager
        from src.bot.core.config_loader import (
            get_character_config,
            get_model_system_prompt,
            get_rey_config,
        )
        from src.bot.core.character_manager import get_character_manager
        from ai_server.client import call_model
        from ai_server.schemas import Message
        from datetime import datetime
        from XN_Core.relation import build_attitude_hint, get_reply_style_hint
        from src.EmotionCore import get_current_emotion

        character_config = get_character_config()
        character_desc = character_config.get("short_desc", "")
        profile = character_config.get("profile", "").strip()
        bot_name = get_character_manager().get_character_name()

        # 格式化聊天记录
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
        current_activity = self._get_current_activity_from_schedule(user_id)
        attitude_hint = build_attitude_hint(user_id, session_id)
        reply_style = get_reply_style_hint(user_id)

        # System Prompt
        reply_sp = get_model_system_prompt("roleplay_main")
        reply_sp = (
            reply_sp
            .replace("{character_desc}", character_desc)
            .replace("{profile}", profile)
        )

        # User Prompt
        rey_cfg = get_rey_config()
        user_tpl = rey_cfg.get("roleplay_main", {}).get(
            "user_prompt_template",
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
        return response.content.strip()

    def _get_current_activity_from_schedule(self, user_id: str) -> str:
        """从 core_state 读取当日日程，返回当前正在进行的活动"""
        from datetime import datetime
        from pathlib import Path
        import json

        core_state_dir = PLUGIN_DIR / "data" / "core_state"
        schedule_path = core_state_dir / f"{user_id}_schedule.json"

        if not schedule_path.exists():
            return "自由活动"
        try:
            schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
            if not isinstance(schedule, list) or not schedule or isinstance(schedule[0], str):
                return "自由活动"
            now = datetime.now()
            now_min = now.hour * 60 + now.minute
            for item in schedule:
                sh, sm = map(int, item["start"].split(":"))
                eh, em = map(int, item["end"].split(":"))
                if sh * 60 + sm <= now_min < eh * 60 + em:
                    return item["activity"]
        except Exception:
            pass
        return "自由活动"

    async def _send_to_user(self, user_id: str, group_id: str | None, text: str) -> None:
        """通过 AstrBot 发送消息，经过切分后逐条发送（模拟真实聊天节奏）"""
        if not self._bot:
            return
        try:
            from src.bot.core.reply_manager import segment_reply, get_send_interval
            segments = await segment_reply("", text)
            for i, seg in enumerate(segments):
                if i > 0:
                    await asyncio.sleep(get_send_interval())
                if group_id:
                    await self._bot.send_group_msg(group_id=int(group_id), message=seg)
                else:
                    await self._bot.send_private_msg(user_id=int(user_id), message=seg)
        except Exception as e:
            logger.warning(f"[XNBot] 发送消息失败 user={user_id}: {e}")

    # ========================
    # WebUI 启动
    # ========================

    async def _start_webui(self) -> None:
        """在后台启动小雫 WebUI（端口 8081）"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8081))
        sock.close()
        if result == 0:
            logger.info("[XNBot] 小雫 WebUI 已在运行，跳过启动")
            return
        try:
            import uvicorn
            from web.server import app as web_app

            config = uvicorn.Config(
                web_app,
                host="0.0.0.0",
                port=8081,
                log_level="warning",
            )
            server = uvicorn.Server(config)
            logger.info("[XNBot] 小雫 WebUI 启动中... http://0.0.0.0:8081/web/app")
            await server.serve()
        except Exception as e:
            logger.warning(f"[XNBot] 小雫 WebUI 启动失败: {e}")

    # ========================
    # 管理命令
    # ========================

    @filter.command("xntest")
    async def test_command(self, event: AstrMessageEvent) -> None:
        """测试小雫是否正常工作"""
        await event.send(MessageEventResult().message("小雫在线！").stop_event())
