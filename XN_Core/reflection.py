"""
XN_Core.reflection — 睡眠识别 + 反思生成 + 睡眠状态管理

流程：
  用户说晚安 → 设置意图
  小雫回复晚安 → 两步确认 → Agent 生成摘要 → Agent 打分 → 计算睡眠时长 → 注册唤醒
"""
import json
import time
from datetime import datetime
from pathlib import Path

from nonebot.log import logger

# ========================
# 睡眠状态（内存 + JSON 持久化）
# ========================

_STATE_DIR = Path(__file__).parent.parent / "data" / "core_state"

# user_id → {sleeping, sleep_start, wake_time, ref_id}
_sleep_state: dict[str, dict] = {}

# user_id → True（用户消息含睡眠关键词时设为 True）
_sleep_intent: dict[str, bool] = {}

# user_id → 上次醒来的时间戳（用于过滤本次醒来到现在的对话）
_last_wake_time: dict[str, float] = {}


# ========================
# 配置读取
# ========================

def _get_sleep_keywords() -> list[str]:
    from src.bot.core.config_loader import get_bot_config
    cfg = get_bot_config()
    return cfg.get("xn_core", {}).get("sleep", {}).get(
        "keywords", ["晚安", "去睡了", "睡觉了", "要睡了", "休息了"]
    )


def _get_sleep_hours_range() -> tuple[float, float]:
    from src.bot.core.config_loader import get_bot_config
    cfg = get_bot_config()
    sleep_cfg = cfg.get("xn_core", {}).get("sleep", {})
    return (
        sleep_cfg.get("min_sleep_hours", 6.0),
        sleep_cfg.get("max_sleep_hours", 12.0),
    )


def _get_max_beats() -> int:
    from src.bot.core.config_loader import get_bot_config
    cfg = get_bot_config()
    return cfg.get("xn_core", {}).get("heartbeat", {}).get("max_beats_per_day", 8)


def _is_enabled() -> bool:
    from src.bot.core.config_loader import get_bot_config
    return get_bot_config().get("xn_core", {}).get("enabled", True)


# ========================
# 公共接口
# ========================

def is_sleeping(user_id: str) -> bool:
    """查询用户是否在睡眠中"""
    return _sleep_state.get(user_id, {}).get("sleeping", False)


def get_sleep_state(user_id: str) -> dict | None:
    """获取用户完整睡眠状态"""
    return _sleep_state.get(user_id)


def check_user_sleep_intent(user_id: str, user_text: str) -> None:
    """检查用户消息是否含睡眠关键词，设置意图标记"""
    if not _is_enabled():
        return
    keywords = _get_sleep_keywords()
    matched = [kw for kw in keywords if kw in user_text]
    if matched:
        _sleep_intent[user_id] = True
        logger.info(f"[core.sleep] 检测到用户睡眠意图 user={user_id} 命中={matched}")


async def check_sleep_signal(user_id: str, bot_reply: str) -> None:
    """
    两步确认：用户意图 + 小雫回复都含睡眠关键词 → 触发睡眠流程。
    在 handler.py 中 reply 发送后调用。
    """
    if not _is_enabled():
        return

    # 第一步：用户是否已表达要睡觉
    if not _sleep_intent.pop(user_id, False):
        return

    # 第二步：小雫回复是否含睡眠关键词
    keywords = _get_sleep_keywords()
    if not any(kw in bot_reply for kw in keywords):
        return

    logger.info(f"[core.sleep] 睡眠确认 user={user_id}，进入反思流程")
    try:
        await _enter_sleep(user_id)
    except Exception as e:
        logger.error(f"[XN_Core] 睡眠流程异常: {e}", exc_info=True)


def on_wake(user_id: str) -> None:
    """唤醒用户（由 heartbeat 调用）"""
    if user_id in _sleep_state:
        _sleep_state[user_id]["sleeping"] = False
        _last_wake_time[user_id] = time.time()
        _remove_sleep_file(user_id)
        logger.info(f"[XN_Core] 小雫已醒来 user={user_id}")


# ========================
# 持久化
# ========================

def _save_sleep_state(user_id: str) -> None:
    """将睡眠状态写入 JSON 文件"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _STATE_DIR / f"{user_id}_sleep.json"
    state = _sleep_state.get(user_id)
    if state:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)


def _remove_sleep_file(user_id: str) -> None:
    """唤醒后删除持久化文件"""
    path = _STATE_DIR / f"{user_id}_sleep.json"
    if path.exists():
        path.unlink()


def restore_sleep_states() -> list[dict]:
    """
    启动时调用：从 JSON 文件恢复所有睡眠中的用户状态。
    返回需要重新注册心跳的列表 [{user_id, sleep_hours}, ...]
    """
    if not _STATE_DIR.exists():
        return []

    restored = []
    now = time.time()

    for f in _STATE_DIR.glob("*_sleep.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                state = json.load(fh)

            if not state.get("sleeping"):
                f.unlink()
                continue

            user_id = f.stem.replace("_sleep", "")
            wake_time = state.get("wake_time", 0)

            if now >= wake_time:
                # 已经过了唤醒时间，标记为醒来
                state["sleeping"] = False
                _sleep_state[user_id] = state
                _last_wake_time[user_id] = now
                logger.info(f"[XN_Core] 恢复：user={user_id} 已过唤醒时间，标记为醒来")
                restored.append({"user_id": user_id, "sleep_hours": 0, "already_wake": True})
            else:
                # 还在睡眠中，重新注册计时器
                remaining_hours = (wake_time - now) / 3600
                _sleep_state[user_id] = state
                logger.info(
                    f"[XN_Core] 恢复：user={user_id} 仍在睡眠，"
                    f"剩余 {remaining_hours:.1f}h，唤醒时间 {datetime.fromtimestamp(wake_time).strftime('%H:%M')}"
                )
                restored.append({"user_id": user_id, "sleep_hours": remaining_hours, "already_wake": False})

        except Exception as e:
            logger.warning(f"[XN_Core] 恢复睡眠状态失败 {f.name}: {e}")

    return restored


# ========================
# 内部：睡眠流程
# ========================

async def _enter_sleep(user_id: str) -> None:
    """确认睡着后执行：摘要 → 打分 → 计算睡眠时长 → 注册唤醒"""
    from src.Agent import get_core_agent
    from src.XN_Memory import get_store

    sleep_start = time.time()
    last_wake = _last_wake_time.get(user_id, sleep_start - 3600)

    # ① 生成反思摘要
    logger.info(f"[XN_Core] ① 生成反思摘要 user={user_id}")
    core_agent = get_core_agent()
    user_name = get_user_route(user_id).get("user_name", "") if get_user_route(user_id) else ""
    ref_data = await core_agent.run_reflection(user_id, last_wake, sleep_start, user_name=user_name)
    if not ref_data.get("summary"):
        ref_data["summary"] = "（今日无对话）"
    logger.info(
        f"[XN_Core] 反思摘要完成 user={user_id} len={len(ref_data['summary'])} "
        f"feeling={bool(ref_data.get('feeling'))}"
    )

    store = get_store()
    ref_id = store.insert_reflection(
        user_id=user_id,
        summary=ref_data["summary"],
        sleep_start=last_wake,
        sleep_end=sleep_start,
        health_score=0.0,
        feeling=ref_data.get("feeling", ""),
        highlights=ref_data.get("highlights", []),
    )

    # ② 对话打分
    logger.info(f"[XN_Core] ② 对话打分 user={user_id}")
    health_score = await core_agent.run_score(user_id, last_wake, sleep_start)
    health_score = max(1.0, min(10.0, health_score))
    store.update_reflection_score(ref_id, health_score)
    logger.info(f"[XN_Core] 打分完成 user={user_id} score={health_score:.1f}")

    try:
        from XN_Core.relation import update_after_reflection
        update_after_reflection(user_id, health_score)
    except Exception as e:
        logger.warning(f"[XN_Core] 关系更新失败: {e}")

    # 计算睡眠时长
    sleep_hours = _health_to_sleep_hours(health_score)
    wake_time = sleep_start + sleep_hours * 3600

    # 设置睡眠状态
    _sleep_state[user_id] = {
        "sleeping": True,
        "sleep_start": sleep_start,
        "wake_time": wake_time,
        "ref_id": ref_id,
    }
    _save_sleep_state(user_id)

    logger.info(
        f"[core.sleep] 睡眠设置完成 user={user_id} "
        f"sleep_hours={sleep_hours:.1f}h wake_at={datetime.fromtimestamp(wake_time).strftime('%H:%M')}"
    )

    # 通知 heartbeat 注册唤醒
    try:
        from XN_Core.heartbeat import get_monitor
        get_monitor().start_user_cycle(user_id, sleep_hours)
    except Exception as e:
        logger.error(f"[XN_Core] heartbeat 注册失败: {e}")


# ========================
# 消息路由（供心跳/未读按原会话发送）
# ========================

_ROUTE_DIR = _STATE_DIR


def save_user_route(user_id: str, session_id: str, group_id: str | None = None, user_name: str = "") -> None:
    """记录用户最近活跃的会话路由（私聊或群）"""
    _ROUTE_DIR.mkdir(parents=True, exist_ok=True)
    path = _ROUTE_DIR / f"{user_id}_route.json"
    # 保留已有的 user_name（如果本次没传）
    existing = get_user_route(user_id) or {}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "session_id": session_id,
                "group_id": group_id,
                "is_group": group_id is not None,
                "user_name": user_name or existing.get("user_name", ""),
            },
            f,
            ensure_ascii=False,
        )


def get_user_route(user_id: str) -> dict | None:
    path = _ROUTE_DIR / f"{user_id}_route.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _health_to_sleep_hours(score: float) -> float:
    """
    健康分 → 睡眠时长映射。
    分高睡少（充实的一天不需要太多睡眠）
    分低睡多（无聊/疲惫的一天需要更多休息）
    """
    min_h, max_h = _get_sleep_hours_range()
    ratio = (score - 1.0) / 9.0
    return max_h - ratio * (max_h - min_h)
