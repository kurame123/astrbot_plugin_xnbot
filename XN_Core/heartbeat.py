"""
XN_Core.heartbeat — 醒来流程 + 日程表 + 心跳计划 + 心跳决策 + 主动消息

流程：
  计时器到 → 小雫睡醒
    → 检查未读消息（有则处理）
    → Agent 生成日程 → 存 JSON
    → Agent 生成心跳计划 → 存 JSON
    → 按计划依次心跳 → Agent 决策 skip/send
"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from nonebot.log import logger

# JSON 存储目录
_CORE_STATE_DIR = Path(__file__).parent.parent / "data" / "core_state"


class HeartbeatMonitor:
    """管理所有用户的心跳循环"""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._bot = None
        self._schedules: dict[str, list[dict]] = {}      # user_id → 日程列表 [{"start","end","activity"}]
        self._heartbeat_plans: dict[str, dict] = {}      # user_id → {count, offsets_minutes}
        self._pending_wake_on_connect: dict[str, bool] = {}  # bot 连接前需要触发醒来的用户

    def set_bot(self, bot) -> None:
        self._bot = bot
        logger.info("[XN_Core] HeartbeatMonitor 已绑定 Bot")

    def start_user_cycle(self, user_id: str, sleep_hours: float) -> None:
        """注册唤醒任务（sleep_hours 小时后触发）"""
        # 取消已有任务
        self.cancel_user_cycle(user_id)

        delay_seconds = sleep_hours * 3600
        task = asyncio.create_task(self._wake_later(user_id, delay_seconds))
        self._tasks[user_id] = task
        logger.info(f"[XN_Core] 唤醒任务已注册 user={user_id} delay={sleep_hours:.1f}h")

    def cancel_user_cycle(self, user_id: str) -> None:
        """取消用户的循环任务"""
        task = self._tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"[XN_Core] 已取消循环任务 user={user_id}")

    def cancel_all(self) -> None:
        """取消所有循环任务（Bot 断开时调用）"""
        for user_id in list(self._tasks.keys()):
            self.cancel_user_cycle(user_id)
        logger.info("[XN_Core] 已取消所有心跳任务")

    # ========================
    # 醒来流程
    # ========================

    async def _wake_later(self, user_id: str, delay: float) -> None:
        """等待 sleep_hours 后触发醒来"""
        try:
            await asyncio.sleep(delay)
            await self._on_wake(user_id)
        except asyncio.CancelledError:
            logger.info(f"[XN_Core] 唤醒任务被取消 user={user_id}")
        except Exception as e:
            logger.error(f"[XN_Core] 唤醒流程异常 user={user_id}: {e}", exc_info=True)

    async def _on_wake(self, user_id: str) -> None:
        """醒来流程：处理未读 → 生成日程 → 生成心跳计划 → 开始心跳"""
        from XN_Core.reflection import on_wake, get_sleep_state
        from src.XN_Memory import get_store

        on_wake(user_id)
        sleep_state = get_sleep_state(user_id)
        sleep_start = sleep_state.get("sleep_start", time.time() - 3600) if sleep_state else time.time() - 3600

        logger.info(f"[XN_Core] === 小雫醒来 user={user_id} ===")

        # 1. 检查睡眠期间未读消息
        store = get_store()
        unread = store.get_conversations_in_range(
            user_id=user_id, since=sleep_start, count=50,
        )
        # 过滤：只保留 user 消息（排除小雫自己的回复）
        user_msgs_during_sleep = [m for m in unread if m["role"] == "user"]

        if user_msgs_during_sleep and self._bot:
            logger.info(f"[XN_Core] 睡眠期间有 {len(user_msgs_during_sleep)} 条未读消息，处理中...")
            await self._handle_unread(user_id, user_msgs_during_sleep)

        # 2. 生成今日日程
        logger.info(f"[XN_Core] ③ 生成日程 user={user_id}")
        from src.Agent import get_core_agent
        core_agent = get_core_agent()
        schedule = await core_agent.run_daily_plan(user_id)
        self._schedules[user_id] = schedule
        self._save_json(user_id, "schedule", schedule)
        logger.info(f"[XN_Core] 日程完成 user={user_id} items={len(schedule)}")

        # 3. 生成心跳计划
        min_beats, max_beats = self._get_beats_range()
        logger.info(f"[XN_Core] ④ 生成心跳计划 user={user_id} min={min_beats} max={max_beats}")
        plan = await core_agent.run_heartbeat_plan(user_id, max_beats, min_beats)
        self._heartbeat_plans[user_id] = plan
        self._save_json(user_id, "heartbeat", plan)
        logger.info(
            f"[XN_Core] 心跳计划完成 user={user_id} "
            f"count={plan.get('count', 0)} offsets={plan.get('offsets_minutes', [])}"
        )

        # 4. 按计划注册心跳
        await self._schedule_heartbeats(user_id, plan, wake_anchor=time.time())

    # ========================
    # 未读消息处理
    # ========================

    async def _handle_unread(self, user_id: str, messages: list[dict]) -> None:
        """处理睡眠期间的未读消息（CoreAgent + 原会话路由）"""
        try:
            from src.Agent import get_core_agent
            from XN_Core.reflection import get_user_route

            unread_text = "\n".join(
                f"用户: {m['content']}" for m in messages[-10:]
            )
            core_agent = get_core_agent()
            reply = await core_agent.run_wake_unread_reply(user_id, unread_text)

            if reply and self._bot:
                await self._send_to_user(user_id, reply)
                logger.info(f"[XN_Core] 未读消息已回复 user={user_id}")

                route = get_user_route(user_id) or {}
                session_id = route.get("session_id") or f"user:{user_id}"
                from src.XN_Memory import get_writer
                get_writer().submit(
                    user_id=user_id,
                    user_text=unread_text,
                    bot_text=reply,
                    session_id=session_id,
                    nickname="",
                    created_at=time.time(),
                )
        except Exception as e:
            logger.error(f"[XN_Core] 处理未读消息失败: {e}", exc_info=True)

    # ========================
    # 心跳调度
    # ========================

    async def _schedule_heartbeats(
        self, user_id: str, plan: dict, wake_anchor: float | None = None,
    ) -> None:
        """按心跳计划依次注册心跳任务，并持久化 pending 供崩溃恢复"""
        offsets = plan.get("offsets_minutes", [])
        anchor = wake_anchor or time.time()
        pending = {
            "wake_anchor": anchor,
            "offsets_minutes": offsets,
            "completed": [],
        }
        self._save_json(user_id, "heartbeat_pending", pending)
        for i, offset_min in enumerate(offsets):
            delay = offset_min * 60
            asyncio.create_task(
                self._heartbeat_later(user_id, i + 1, delay, offset_min),
            )

    @staticmethod
    def _get_current_activity(schedule: list[dict], current_time: str | None = None) -> str:
        """根据当前时间匹配日程中的活动

        Args:
            schedule: [{"start":"HH:MM","end":"HH:MM","activity":"..."}]
            current_time: "HH:MM" 格式，默认取 datetime.now()
        """
        if not schedule:
            return "自由活动"
        if current_time is None:
            current_time = datetime.now().strftime("%H:%M")
        h, m = map(int, current_time.split(":"))
        now_min = h * 60 + m
        for item in schedule:
            try:
                sh, sm = map(int, item["start"].split(":"))
                eh, em = map(int, item["end"].split(":"))
                if sh * 60 + sm <= now_min < eh * 60 + em:
                    return item["activity"]
            except (KeyError, ValueError):
                continue
        return "自由活动"

    async def _heartbeat_later(
        self, user_id: str, beat_num: int, delay: float, offset_min: int,
    ) -> None:
        """等待指定时间后执行心跳"""
        try:
            await asyncio.sleep(delay)
            await self._execute_heartbeat(user_id, beat_num, offset_min)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[XN_Core] 心跳执行异常 user={user_id} beat={beat_num}: {e}", exc_info=True)

    async def _execute_heartbeat(
        self, user_id: str, beat_num: int, offset_min: int | None = None,
    ) -> None:
        """执行一次心跳：Agent 决策 skip/send"""
        from src.Agent import get_core_agent
        from src.XN_Memory import get_store

        # 检查用户是否还在醒着（可能又睡了）
        from XN_Core.reflection import is_sleeping
        if is_sleeping(user_id):
            logger.info(f"[XN_Core] 心跳跳过 user={user_id}（已入睡）")
            return

        logger.info(f"[XN_Core] === 心跳触发 user={user_id} beat={beat_num} ===")

        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")

        # 读取当前日程 & 匹配当前活动
        schedule = self._schedules.get(user_id, [])
        current_activity = self._get_current_activity(schedule)

        # 读取最近反思
        store = get_store()
        reflections = store.get_recent_reflections(user_id, limit=1)
        ref0 = reflections[0] if reflections else {}
        reflections_summary = ref0.get("summary", "暂无反思记录")
        if ref0.get("feeling"):
            reflections_summary += f"（感受：{ref0['feeling']}）"

        time_since = self._get_time_since_last_chat(user_id)

        from XN_Core.relation import get_relation
        rel = get_relation(user_id)
        if rel.get("awkward", 0) > 0.6:
            reflections_summary += "；关系略别扭，若无事可 skip"

        # 读取最近几条对话，让 Agent 感知当前话题和上次说了什么
        recent_context = self._get_recent_chat_context(user_id, limit=6)

        core_agent = get_core_agent()
        decision, message = await core_agent.run_heartbeat_decision(
            user_id=user_id,
            current_time=current_time,
            current_activity=current_activity,
            reflections_summary=reflections_summary,
            time_since_last=time_since,
            recent_context=recent_context,
        )

        # 记录日志
        store.insert_heartbeat_log(
            user_id=user_id,
            trigger_time=time.time(),
            decision=decision,
            message=message if decision == "send" else None,
        )

        if offset_min is not None:
            self._mark_heartbeat_done(user_id, offset_min)

        if decision == "send" and message and self._bot:
            await self._send_to_user(user_id, message)
            logger.info(f"[core.heartbeat.send] user={user_id} beat={beat_num}")
        else:
            logger.info(f"[core.heartbeat.skip] user={user_id} beat={beat_num}")

    def _mark_heartbeat_done(self, user_id: str, offset_min: int) -> None:
        pending = self._load_json(user_id, "heartbeat_pending") or {}
        done = pending.get("completed", [])
        if offset_min not in done:
            done.append(offset_min)
        pending["completed"] = done
        self._save_json(user_id, "heartbeat_pending", pending)
        if len(done) >= len(pending.get("offsets_minutes", [])):
            path = _CORE_STATE_DIR / f"{user_id}_heartbeat_pending.json"
            if path.exists():
                path.unlink()

    def restore_pending_heartbeats(self) -> None:
        """启动时恢复未完成的心跳任务"""
        if not _CORE_STATE_DIR.exists():
            return
        now = time.time()
        for f in _CORE_STATE_DIR.glob("*_heartbeat_pending.json"):
            user_id = f.stem.replace("_heartbeat_pending", "")
            try:
                pending = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            anchor = pending.get("wake_anchor", now)
            done = set(pending.get("completed", []))
            schedule = self._load_json(user_id, "schedule")
            if schedule:
                self._schedules[user_id] = schedule
            for i, offset_min in enumerate(pending.get("offsets_minutes", [])):
                if offset_min in done:
                    continue
                fire_at = anchor + offset_min * 60
                delay = max(0.0, fire_at - now)
                asyncio.create_task(
                    self._heartbeat_later(user_id, i + 1, delay, offset_min),
                )
                logger.info(
                    f"[XN_Core] 恢复心跳 user={user_id} offset={offset_min}m "
                    f"delay={delay/60:.1f}m"
                )

    # ========================
    # 辅助方法
    # ========================

    async def _send_to_user(self, user_id: str, text: str) -> None:
        """通过 Bot 发送消息，经过切分后逐条发送（模拟真实聊天节奏）"""
        if not self._bot:
            return
        try:
            from XN_Core.reflection import get_user_route
            from src.bot.core.reply_manager import segment_reply, get_send_interval

            route = get_user_route(user_id)
            is_group = route and route.get("is_group") and route.get("group_id")

            segments = await segment_reply("", text)

            for i, seg in enumerate(segments):
                if i > 0:
                    await asyncio.sleep(get_send_interval())
                if is_group:
                    await self._bot.send_group_msg(
                        group_id=int(route["group_id"]),
                        message=seg,
                    )
                else:
                    await self._bot.send_private_msg(user_id=int(user_id), message=seg)

        except Exception as e:
            logger.warning(f"[XN_Core] 发送消息失败 user={user_id}: {e}")

    def _get_time_since_last_chat(self, user_id: str) -> str:
        """计算距上次对话的自然语言描述"""
        from src.XN_Memory import get_store
        store = get_store()
        msgs = store.get_conversations_in_range(user_id=user_id, count=1)
        if not msgs:
            return "很久没有对话了"
        last_ts = msgs[-1]["timestamp"]
        diff = time.time() - last_ts
        if diff < 3600:
            return f"{int(diff / 60)}分钟前"
        elif diff < 86400:
            return f"{int(diff / 3600)}小时前"
        else:
            return f"{int(diff / 86400)}天前"

    def _get_recent_chat_context(self, user_id: str, limit: int = 6) -> str:
        """获取最近几轮对话的文本，供心跳决策感知当前话题和上次说了什么"""
        from src.XN_Memory import get_store
        store = get_store()
        msgs = store.get_conversations_in_range(user_id=user_id, count=limit)
        if not msgs:
            return ""
        lines = []
        for m in msgs:
            if m["role"] == "user":
                lines.append(f"用户：{m['content']}")
            elif m["content"] != "[睡眠中，小雫未回复]":
                lines.append(f"小雫：{m['content']}")
        return "\n".join(lines)

    def _save_json(self, user_id: str, name: str, data) -> None:
        """保存 JSON 到 data/core_state/"""
        _CORE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CORE_STATE_DIR / f"{user_id}_{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_json(self, user_id: str, name: str):
        """从 data/core_state/ 读取 JSON"""
        path = _CORE_STATE_DIR / f"{user_id}_{name}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    @staticmethod
    def _get_beats_range() -> tuple[int, int]:
        from src.bot.core.config_loader import get_bot_config
        cfg = get_bot_config()
        hb = cfg.get("xn_core", {}).get("heartbeat", {})
        max_b = int(hb.get("max_beats_per_day", 8))
        min_b = int(hb.get("min_beats_per_day", 3))
        min_b = max(1, min(min_b, max_b))
        return min_b, max_b


# ========================
# 全局单例
# ========================

_monitor: HeartbeatMonitor | None = None


def get_monitor() -> HeartbeatMonitor:
    global _monitor
    if _monitor is None:
        _monitor = HeartbeatMonitor()
    return _monitor
