"""
回复处理模块

负责将 LLM 生成的长回复切分成多条自然的聊天消息，并提供发送间隔控制。
原 src/ReplyCore/ 模块集成于此。
"""
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from nonebot.log import logger

from ai_server.client import call_model
from ai_server.schemas import Message

# =========================
# 配置加载
# =========================

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "reply_config.toml"
_config: dict[str, Any] | None = None


def _get_reply_config() -> dict[str, Any]:
    global _config
    if _config is None:
        with open(_CONFIG_PATH, "rb") as f:
            _config = tomllib.load(f)
    return _config


# =========================
# 对外接口
# =========================

async def segment_reply(user_text: str, raw_reply: str) -> list[str]:
    """
    切分回复为多条消息

    Args:
        user_text: 用户最后一条消息
        raw_reply: 小雫的完整回复

    Returns:
        切分后的消息列表
    """
    return await _segment_with_llm(user_text, raw_reply)


def get_send_interval() -> float:
    """获取随机发送间隔（秒）"""
    send_cfg = _get_reply_config().get("send", {})
    min_i = send_cfg.get("min_interval", 0.4)
    max_i = send_cfg.get("max_interval", 0.9)
    return random.uniform(min_i, max_i)


# =========================
# LLM 切分
# =========================

async def _segment_with_llm(user_text: str, raw_reply: str) -> list[str]:
    config = _get_reply_config()
    segment_cfg = config.get("segment", {})
    skip_threshold = segment_cfg.get("skip_threshold", 20)

    if len(raw_reply) <= skip_threshold:
        logger.debug(f"[SEGMENTER] 回复较短({len(raw_reply)}字)，跳过切分")
        return [raw_reply]

    prompt_cfg = config.get("prompt", {})
    model_name = config.get("segment_model", {}).get("name", "reply_segmenter")

    system_prompt = prompt_cfg.get("system", "").strip()
    user_prompt = (
        prompt_cfg.get("user_template", "{reply_text}")
        .replace("{user_message}", user_text)
        .replace("{reply_text}", raw_reply)
        .strip()
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_prompt),
    ]

    logger.debug(f"[SEGMENTER] 调用模型切分回复，原文长度={len(raw_reply)}")

    try:
        response = await call_model(model_name, messages)
        raw_content = response.content.strip()
        segments = _parse_segments(raw_content)
        if segments:
            segments = _post_process(segments, segment_cfg)
            # 完整性校验：切分结果不能丢失原文内容
            if not _check_integrity(raw_reply, segments):
                logger.warning(
                    f"[SEGMENTER] 切分结果内容不完整，放弃切分直接发送原文 "
                    f"(原文={len(raw_reply)}字, 切分={len(segments)}条)"
                )
                return [raw_reply]
            logger.info(
                f"[SEGMENTER] 切分完成: {len(raw_reply)}字 -> {len(segments)}条 | "
                f"预览: {[s[:15]+'...' if len(s)>15 else s for s in segments]}"
            )
            return segments
    except Exception as e:
        logger.warning(f"[SEGMENTER] LLM 调用失败: {e}")

    logger.info("[SEGMENTER] 使用 fallback 本地切分")
    return _fallback_segment(raw_reply)


def _parse_segments(raw_content: str) -> list[str] | None:
    # 先剥掉 markdown 代码块
    stripped = re.sub(r'```(?:json)?\s*', '', raw_content).strip()

    for attempt in [stripped, raw_content, _clean_json(stripped)]:
        try:
            json_match = re.search(r'\{[^{}]*"segments"[^{}]*\[.*?\][^{}]*\}', attempt, re.DOTALL)
            data = json.loads(json_match.group() if json_match else attempt)
            segments = data.get("segments", [])
            if isinstance(segments, list) and segments:
                result = [str(s).strip() for s in segments if s and str(s).strip()]
                if result:
                    return result
        except (json.JSONDecodeError, Exception):
            continue

    # 正则兜底：只取看起来像完整句子的内容（长度 > 4，不含 JSON 关键字）
    json_keywords = {"segments", "json", "true", "false", "null"}
    matches = re.findall(r'"([^"]{4,})"', raw_content)
    results = [m.strip() for m in matches
               if m.strip() and m.strip().lower() not in json_keywords
               and not m.strip().startswith(("{", "}", "[", "]"))]
    if results:
        return results

    logger.warning(f"[SEGMENTER] JSON 解析失败, raw={raw_content[:200]}")
    return None


def _clean_json(s: str) -> str:
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffd]', '', s)
    s = re.sub(r'\bf"', '"', s)
    s = re.sub(r'\\(?!["\\/bfnrtu])', '', s)
    return s


def _post_process(segments: list[str], config: dict) -> list[str]:
    min_chars = config.get("min_chars", 4)
    max_segments = config.get("max_segments", 5)

    result = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) < min_chars and result:
            result[-1] += seg
        else:
            result.append(seg)

    if len(result) > max_segments:
        result = result[:max_segments]

    return result if result else segments[:1]


def _check_integrity(original: str, segments: list[str], threshold: float = 0.85) -> bool:
    """
    校验切分结果是否完整保留了原文内容。
    把所有 segment 拼接后，计算与原文的字符重叠率。
    低于 threshold 说明有内容丢失，切分结果不可信。
    """
    combined = "".join(segments)
    # 去掉空白后比较
    orig_clean = re.sub(r'\s', '', original)
    comb_clean = re.sub(r'\s', '', combined)

    if not orig_clean:
        return True

    # 计算原文中有多少字符出现在拼接结果里（顺序无关的字符覆盖率）
    orig_chars = {}
    for c in orig_clean:
        orig_chars[c] = orig_chars.get(c, 0) + 1

    comb_chars = {}
    for c in comb_clean:
        comb_chars[c] = comb_chars.get(c, 0) + 1

    matched = sum(min(orig_chars[c], comb_chars.get(c, 0)) for c in orig_chars)
    coverage = matched / len(orig_clean)

    return coverage >= threshold


def _fallback_segment(raw_reply: str) -> list[str]:
    lines = raw_reply.split("\n")
    segments = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if len(line) > 50:
            parts = re.split(r'([。！？~]+)', line)
            current = ""
            for i, part in enumerate(parts):
                current += part
                if i % 2 == 1 and len(current) >= 10:
                    segments.append(current.strip())
                    current = ""
            if current.strip():
                segments.append(current.strip())
        else:
            segments.append(line)

    result = []
    for seg in segments:
        if len(seg) < 4 and result:
            result[-1] += seg
        else:
            result.append(seg)

    return result if result else [raw_reply]
