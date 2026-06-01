"""
Agent 工作流日志
记录每次 Agent 处理的完整 ReAct 轨迹到 data/logs/AGENT_LOG.log
"""
from datetime import datetime
from pathlib import Path

AGENT_LOG_PATH = Path(__file__).parent.parent / "data" / "logs" / "AGENT_LOG.log"


def _write(lines: list[str]) -> None:
    AGENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def log_agent_start(session_id: str, user_id: str, user_message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write([
        "=" * 80,
        f"[{ts}] session={session_id} user={user_id}",
        "--- 用户消息 ---",
        user_message,
    ])


def log_react_step(step: int, output: str, usage: dict | None = None) -> None:
    """记录每一步模型输出（Thought/Action）"""
    lines = [f"--- Step {step} ---", output.strip()]
    if usage:
        prompt_t = usage.get("prompt_tokens", 0)
        completion_t = usage.get("completion_tokens", 0)
        total_t = usage.get("total_tokens", 0)
        lines.append(f"Token: prompt={prompt_t} completion={completion_t} total={total_t}")
    _write(lines)


def log_react_observation(search_count: int, keywords: list[str], results: list[dict]) -> None:
    """记录工具执行结果"""
    lines = [f"--- Observation (第{search_count}次搜索) ---"]
    lines.append(f"关键词: {keywords}")
    if results:
        for i, mem in enumerate(results, 1):
            from datetime import datetime as dt
            date_str = dt.fromtimestamp(mem.get("created_at", 0)).strftime("%Y-%m-%d")
            score = mem.get("_final_score", 0)
            importance = mem.get("importance", 0)
            nickname = mem.get("nickname", "用户")
            user_text = mem.get("user_text", "")[:50]
            bot_text = mem.get("bot_text", "")[:50]
            lines.append(
                f"  [{i}] {date_str} | score={score:.3f} importance={importance:.2f} | {nickname}：{user_text} → 小雫：{bot_text}"
            )
    else:
        lines.append("  （无结果）")
    _write(lines)


def log_agent_result(result_block: str) -> None:
    """记录最终输出给回复 LLM 的内容"""
    _write([
        "--- 最终输出给回复LLM ---",
        result_block if result_block else "（空）",
        "",
    ])


# ========================
# 兼容旧接口（保留，避免其他地方报错）
# ========================

def log_agent_start_compat(session_id: str, user_id: str, user_message: str) -> None:
    log_agent_start(session_id, user_id, user_message)


def log_agent_judge(need_retrieval: bool, reason: str) -> None:
    flag = "需要检索" if need_retrieval else "不需要检索"
    _write([f"--- 判断结果: {flag} ---", f"原因: {reason}"])


def log_agent_hint(hint: str) -> None:
    _write(["--- 路径A: 情境建议 ---", hint])


def log_agent_retrieval_round(
    round_num: int,
    keywords: list[str],
    results: list[dict],
    is_relevant: bool,
    reason: str,
) -> None:
    log_react_observation(round_num, keywords, results)
    _write([f"验证结果: {'相关 ✓' if is_relevant else '不相关 ✗'} | {reason}"])


def log_agent_no_memory() -> None:
    _write(["--- 搜索完成，无相关记忆 ---"])


def log_web_observation(search_count: int, query: str, results: list[dict]) -> None:
    """记录联网搜索结果"""
    lines = [f"--- Observation (第{search_count}次搜索 · 联网) ---"]
    lines.append(f"查询: {query}")
    if results:
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            snippet = r.get("snippet", "")[:100]
            lines.append(f"  [{i}] {title}：{snippet}")
    else:
        lines.append("  （无结果）")
    _write(lines)


def log_agent_total_tokens(total_prompt: int, total_completion: int) -> None:
    """记录本次 Agent 调用的总 token 消耗"""
    _write([f"--- Token 汇总: prompt={total_prompt} completion={total_completion} total={total_prompt + total_completion} ---"])
