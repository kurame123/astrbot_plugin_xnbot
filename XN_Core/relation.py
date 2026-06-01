"""
XN_Core.relation — 关系慢变量、时间梯度、态度 hint、有理由沉默

设计原则：
  - bot_config.toml [xn_core.relation]：全局默认与文案（可调，不硬编码在逻辑里）
  - data/core_state/{user_id}_relation.json：每人状态 + traits（会漂移）
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from nonebot.log import logger

_STATE_DIR = Path(__file__).parent.parent / "data" / "core_state"

# 运行时缓存，避免每条消息反复读 TOML
_cfg_cache: dict[str, Any] | None = None


def _xn_cfg() -> dict:
    from src.bot.core.config_loader import get_bot_config
    return get_bot_config().get("xn_core", {})


def _rel_cfg() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        _cfg_cache = _xn_cfg().get("relation", {})
    return _cfg_cache


def reload_relation_config() -> None:
    """配置热更新后调用（与 bot 配置重载挂钩时可扩展）"""
    global _cfg_cache
    _cfg_cache = None


def _cfg_float(key: str, default: float) -> float:
    v = _rel_cfg().get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _cfg_int(key: str, default: int) -> int:
    v = _rel_cfg().get(key, default)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _cfg_str(key: str, default: str) -> str:
    v = _rel_cfg().get(key, default)
    return str(v) if v is not None else default


def _default_relation() -> dict:
    c = _rel_cfg()
    return {
        "intimacy": float(c.get("initial_intimacy", 0.5)),
        "trust": float(c.get("initial_trust", 0.5)),
        "awkward": float(c.get("initial_awkward", 0.0)),
        "fatigue": float(c.get("initial_fatigue", 0.0)),
        "consecutive_silence": 0,
        "burst_count": 0,
        "burst_window_start": 0.0,
        "last_chat_at": 0.0,
        "last_user_text": "",
        "traits": {
            "silence_tendency": 0.0,
            "verbosity": 0.0,
        },
    }


def get_relation(user_id: str) -> dict:
    path = _STATE_DIR / f"{user_id}_relation.json"
    base = _default_relation()
    if not path.exists():
        return base
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = dict(base)
        out.update({k: v for k, v in data.items() if k != "traits"})
        traits = dict(base.get("traits", {}))
        if isinstance(data.get("traits"), dict):
            traits.update(data["traits"])
        out["traits"] = traits
        return out
    except Exception:
        return base


def _save_relation(user_id: str, rel: dict) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _STATE_DIR / f"{user_id}_relation.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rel, f, ensure_ascii=False, indent=2)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _effective_threshold(base_key: str, user_id: str, default: float) -> float:
    """阈值 + 用户 traits 偏移（silence_tendency 提高 → 更易疲劳/别扭体感）"""
    rel = get_relation(user_id)
    base = _cfg_float(base_key, default)
    traits = rel.get("traits") or {}
    tendency = float(traits.get("silence_tendency", 0.0))
    verbosity = float(traits.get("verbosity", 0.0))
    if "fatigue" in base_key:
        return _clamp(base + tendency * 0.12 - verbosity * 0.08)
    if "awkward" in base_key:
        return _clamp(base + tendency * 0.1)
    if "intimacy" in base_key:
        return _clamp(base - tendency * 0.08 + verbosity * 0.1)
    return _clamp(base)


def update_after_reflection(user_id: str, health_score: float) -> None:
    rel = get_relation(user_id)
    scale = _cfg_float("reflection_score_scale", 0.02)
    delta = (health_score - 5.0) * scale
    rel["intimacy"] = _clamp(rel["intimacy"] + delta)
    rel["trust"] = _clamp(rel["trust"] + delta * _cfg_float("reflection_trust_multiplier", 0.8))
    rel["awkward"] = _clamp(rel["awkward"] - delta * _cfg_float("reflection_awkward_multiplier", 0.5))
    rel["fatigue"] = _clamp(rel["fatigue"] - _cfg_float("reflection_fatigue_relief", 0.05))

    traits = rel.setdefault("traits", {})
    drift = _cfg_float("trait_drift_after_reflection", 0.03)
    if health_score >= 7:
        traits["verbosity"] = _clamp(float(traits.get("verbosity", 0)) + drift, -1, 1)
        traits["silence_tendency"] = _clamp(float(traits.get("silence_tendency", 0)) - drift, -1, 1)
    elif health_score <= 4:
        traits["silence_tendency"] = _clamp(float(traits.get("silence_tendency", 0)) + drift, -1, 1)

    _save_relation(user_id, rel)
    logger.info(
        f"[relation.delta] user={user_id} after_reflection "
        f"intimacy={rel['intimacy']:.2f} traits={traits}"
    )


def update_after_chat(user_id: str, user_text: str, replied: bool) -> None:
    rel = get_relation(user_id)
    now = time.time()
    if replied:
        rel["consecutive_silence"] = 0
        rel["intimacy"] = _clamp(rel["intimacy"] + _cfg_float("chat_intimacy_delta", 0.01))
        rel["fatigue"] = _clamp(rel["fatigue"] + _cfg_float("chat_fatigue_delta", 0.02))
    else:
        rel["consecutive_silence"] = int(rel.get("consecutive_silence", 0)) + 1

    if rel["last_user_text"] == user_text.strip():
        rel["awkward"] = _clamp(rel["awkward"] + _cfg_float("repeat_message_awkward_delta", 0.03))
    rel["last_user_text"] = user_text.strip()
    rel["last_chat_at"] = now

    window = _cfg_float("burst_window_seconds", 60.0)
    if now - rel.get("burst_window_start", 0) > window:
        rel["burst_window_start"] = now
        rel["burst_count"] = 1
    else:
        rel["burst_count"] = int(rel.get("burst_count", 0)) + 1

    _save_relation(user_id, rel)


def _get_current_activity(user_id: str) -> str:
    path = _STATE_DIR / f"{user_id}_schedule.json"
    default = _cfg_str("default_activity", "自由活动")
    if not path.exists():
        return default
    try:
        schedule = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(schedule, list) or not schedule or isinstance(schedule[0], str):
            return default
        now = datetime.now().strftime("%H:%M")
        h, m = map(int, now.split(":"))
        now_min = h * 60 + m
        for item in schedule:
            sh, sm = map(int, item["start"].split(":"))
            eh, em = map(int, item["end"].split(":"))
            if sh * 60 + sm <= now_min < eh * 60 + em:
                return item.get("activity", default)
    except Exception:
        pass
    return default


def _seconds_since_last_chat(user_id: str, session_id: str) -> float:
    rel = get_relation(user_id)
    if rel.get("last_chat_at"):
        return time.time() - rel["last_chat_at"]
    try:
        from src.bot.core.session_manager import get_session_manager
        hist = get_session_manager().get_timestamped_history(session_id, limit=1)
        if hist:
            return time.time() - hist[-1].timestamp
    except Exception:
        pass
    return _cfg_float("fallback_absence_seconds", 604800.0)


def build_attitude_hint(user_id: str, session_id: str) -> str:
    rel = get_relation(user_id)
    activity = _get_current_activity(user_id)
    gap = _seconds_since_last_chat(user_id, session_id)
    hour = datetime.now().hour
    time_cfg = _xn_cfg().get("time", {})

    parts = [f"正在：{activity}"]

    if gap < time_cfg.get("just_chatted_seconds", 1800):
        parts.append(_cfg_str("hint_just_chatted", "刚聊过，回复宜短、随意，不必展开"))
    elif gap > time_cfg.get("long_absence_seconds", 259200):
        parts.append(_cfg_str("hint_long_absence", "很久没聊，语气可试探或略带生疏，勿热情如初"))
    elif gap > time_cfg.get("medium_absence_seconds", 86400):
        parts.append(_cfg_str("hint_medium_absence", "有些日子没聊，自然一点即可"))

    if rel["fatigue"] > _effective_threshold("threshold_fatigue_tired", user_id, 0.65):
        parts.append(_cfg_str("hint_fatigue", "聊累了，可敷衍、可很短"))
    if rel["awkward"] > _effective_threshold("threshold_awkward_cold", user_id, 0.5):
        parts.append(_cfg_str("hint_awkward", "关系有点别扭，别太热情"))
    if rel["intimacy"] > _effective_threshold("threshold_intimacy_close", user_id, 0.7):
        parts.append(_cfg_str("hint_intimacy", "关系较近，可随意撒娇或吐槽"))
    late_h = int(time_cfg.get("late_night_hour", 1))
    early_h = int(time_cfg.get("early_morning_hour", 6))
    if hour >= late_h and hour < early_h:
        parts.append(_cfg_str("hint_late_night", "凌晨，困，含糊简短"))
    busy_kw = time_cfg.get("busy_activity_keywords", [])
    if any(k in activity for k in busy_kw):
        parts.append(_cfg_str("hint_busy", "手头有事，回复宜短、慢"))

    return "；".join(parts)


def get_reply_style_hint(user_id: str) -> str:
    rel = get_relation(user_id)
    if rel["fatigue"] > _effective_threshold("threshold_fatigue_brief", user_id, 0.7):
        return _cfg_str("style_fatigue", "优先一两句以内，可嗯、哦、不知道")
    if rel["intimacy"] > _effective_threshold("threshold_intimacy_verbose", user_id, 0.75):
        return _cfg_str("style_close", "可多说一两句，但仍像聊天不要写作文")
    return _cfg_str("style_default", "两句话以内，自然即可")


def get_send_interval_multiplier(user_id: str) -> float:
    rel = get_relation(user_id)
    activity = _get_current_activity(user_id)
    mult = 1.0
    if rel["fatigue"] > _effective_threshold("threshold_fatigue_slow_send", user_id, 0.6):
        mult += _cfg_float("send_slow_extra", 0.4)
    busy_kw = _xn_cfg().get("time", {}).get("busy_activity_keywords", [])
    if any(k in activity for k in busy_kw):
        mult += _cfg_float("send_busy_extra", 0.5)
    return mult


def soften_memory_block(block: str, user_id: str) -> str:
    if not block or block.startswith("（"):
        return block
    rel = get_relation(user_id)
    if rel["intimacy"] >= _effective_threshold("threshold_intimacy_soft_memory", user_id, 0.55):
        if "【相关记忆】" in block:
            prefix = _cfg_str(
                "memory_soften_prefix",
                "（以下记忆仅供参考，像印象一样用即可，不必逐字准确）",
            )
            return f"{prefix}\n{block}"
    return block


_EMOJI_ONLY = re.compile(
    r"^[\s\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
    r"\U0001F1E6-\U0001F1FF\[\](),.!?…~、。，！？￥$%&*+=\-—「」『』【】]+$"
)


def should_skip_reply(user_id: str, user_text: str, session_id: str) -> tuple[bool, str]:
    cfg = _xn_cfg().get("silence", {})
    if not cfg.get("enabled", True):
        return False, ""

    rel = get_relation(user_id)
    traits = rel.get("traits") or {}
    tendency = float(traits.get("silence_tendency", 0.0))

    max_silent = int(cfg.get("max_consecutive", 2))
    if rel.get("consecutive_silence", 0) >= max_silent:
        return False, "已连续沉默过多，本次应回复"

    text = user_text.strip()
    if len(text) <= 1 and cfg.get("skip_single_char", True):
        return True, "单字无必要回"
    if _EMOJI_ONLY.match(text) and cfg.get("skip_emoji_only", True):
        return True, "纯表情可不回"
    if text == rel.get("last_user_text") and cfg.get("skip_repeat", True):
        return True, "重复消息"

    burst_limit = int(cfg.get("burst_limit", 4))
    if tendency > 0.2:
        burst_limit = max(2, burst_limit - 1)
    if rel.get("burst_count", 0) >= burst_limit:
        return True, "短时消息过多"

    activity = _get_current_activity(user_id)
    skip_act = cfg.get("skip_activities", [])
    if any(a in activity for a in skip_act):
        return True, f"正在{activity}"

    awkward_th = float(cfg.get("awkward_threshold", 0.65))
    awkward_th = _clamp(awkward_th + tendency * 0.15 - float(traits.get("verbosity", 0)) * 0.1)
    short_max = _cfg_int("awkward_short_message_max_len", 8)
    if rel["awkward"] > awkward_th and len(text) < short_max:
        return True, "别扭期短消息可晾"

    return False, ""


def record_silent_turn(user_id: str, user_text: str, session_id: str, nickname: str) -> None:
    from src.bot.core.session_manager import get_session_manager
    from src.XN_Memory import get_writer

    now = time.time()
    get_session_manager().append_message(session_id, "user", user_text, timestamp=now)
    update_after_chat(user_id, user_text, replied=False)
    try:
        get_writer().submit(
            user_id=user_id,
            user_text=user_text,
            bot_text=_cfg_str("silent_bot_text", "[小雫选择暂不回复]"),
            session_id=session_id,
            nickname=nickname,
            created_at=now,
        )
    except Exception as e:
        logger.warning(f"[XN_Core] 沉默记录落库失败: {e}")
    logger.info(f"[core.silence] user={user_id} text={user_text[:40]}")
