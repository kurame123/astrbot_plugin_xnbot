"""
debug.py - Agent 调试命令

命令格式：
  /debug <user_id> <测试消息>
  /debug <测试消息>          （使用发送者自己的 user_id）

功能：
  以指定用户身份向 Agent 发送测试消息，跳过回复 LLM，
  直接返回 Agent 的完整执行结果（判断类型 + 输出块 + 工具调用步骤）。

Agent 会收到一段 DEBUG 标注，知道这是调试行为而非正常对话。
"""
import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger

from src.Agent.agent import MemoryAgent, AgentResult, _REACT_SYSTEM

# 注册命令，以 / 开头
debug_cmd = on_command("debug", priority=1, block=True)


@debug_cmd.handle()
async def handle_debug(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """处理 /debug 命令"""
    raw = args.extract_plain_text().strip()
    if not raw:
        await debug_cmd.finish(
            "用法：\n"
            "/debug <user_id> <测试消息>\n"
            "/debug <测试消息>  （使用你自己的 user_id）"
        )

    # 解析参数：第一个 token 如果是纯数字则视为 user_id
    parts = raw.split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        target_user_id = parts[0]
        test_message = parts[1]
    else:
        target_user_id = str(event.user_id)
        test_message = raw

    await debug_cmd.send(
        f"[DEBUG] 开始测试\n"
        f"user_id: {target_user_id}\n"
        f"消息: {test_message}\n"
        f"{'─' * 30}"
    )

    try:
        result, steps_log = await run_debug_agent(
            user_id=target_user_id,
            test_message=test_message,
        )
    except Exception as e:
        logger.error(f"[DEBUG] Agent 执行失败: {e}", exc_info=True)
        await debug_cmd.finish(f"[DEBUG] 执行失败: {type(e).__name__}: {e}")

    # 格式化输出
    lines = []

    # 工具调用步骤
    if steps_log:
        lines.append("【工具调用步骤】")
        for step in steps_log:
            lines.append(f"  Step {step['step']}: {step['action']}")
            if step.get("observation_preview"):
                lines.append(f"    → {step['observation_preview']}")
        lines.append("")

    # 最终结果
    lines.append("【Agent 判断】")
    if result.need_retrieval:
        lines.append(f"  类型: memory（找到记忆）")
    elif result.context_hint:
        hint_type = "hint" if "|" in result.context_hint else "no_memory"
        lines.append(f"  类型: {hint_type}")
    else:
        lines.append(f"  类型: no_memory")

    lines.append("")
    lines.append("【最终输出块】")
    lines.append(result.to_prompt_block())

    output = "\n".join(lines)

    # QQ 消息有长度限制，超过 1000 字符分段发送
    if len(output) <= 1000:
        await debug_cmd.finish(output)
    else:
        chunks = [output[i:i+900] for i in range(0, len(output), 900)]
        for i, chunk in enumerate(chunks):
            prefix = f"[{i+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
            if i < len(chunks) - 1:
                await debug_cmd.send(prefix + chunk)
            else:
                await debug_cmd.finish(prefix + chunk)


async def run_debug_agent(
    user_id: str,
    test_message: str,
) -> tuple[AgentResult, list[dict]]:
    """
    以 DEBUG 模式运行 Agent，返回结果和步骤日志。

    DEBUG 模式下：
    - Agent system prompt 头部注入 [DEBUG MODE] 说明
    - 拦截工具调用，记录每一步的 action 和 observation 摘要
    - 不写入记忆，不触发情绪系统
    """
    from ai_server.client import call_model
    from ai_server.schemas import Message as AIMessage
    import json

    steps_log: list[dict] = []

    # 注入 DEBUG 说明到 system prompt
    debug_prefix = (
        "[DEBUG MODE]\n"
        "这是一次调试测试，不是真实用户对话。\n"
        "你需要正常执行工具调用和推理，但要知道：\n"
        "- 这条消息是开发者发来测试你的行为的\n"
        "- 你的输出会被直接展示给开发者查看，不会发给用户\n"
        "- 请正常执行，不要因为是调试就改变行为\n\n"
    )
    debug_system = debug_prefix + _REACT_SYSTEM

    # 获取该用户的历史记录（真实历史，用于测试检索）
    try:
        from src.bot.core.session_manager import get_session_manager
        session_manager = get_session_manager()
        session_id = session_manager.make_session_id(user_id, None)
        history_msgs = session_manager.get_history(session_id)
        history_for_agent = [
            {
                "role": msg.role,
                "content": msg.content,
                "nickname": "用户" if msg.role == "user" else "小雫",
                "user_id": user_id if msg.role == "user" else "",
            }
            for msg in history_msgs
        ]
    except Exception:
        history_for_agent = []

    history_text = MemoryAgent._format_history(history_for_agent)

    messages: list[AIMessage] = [
        AIMessage(role="system", content=debug_system),
        AIMessage(role="user", content=f"最近对话：\n{history_text}\n\n用户当前消息：{test_message}"),
    ]

    agent = MemoryAgent()
    MAX_STEPS = agent.MAX_STEPS

    for step in range(MAX_STEPS):
        try:
            response = await call_model(
                model_name=agent.model_name,
                messages=messages,
                override_parameters={"max_tokens": 3000},
                timeout=30.0,
            )
            output = response.content.strip()
            output = agent._extract_action_output(output)
        except Exception as e:
            logger.error(f"[DEBUG] step={step+1} 调用失败: {e}")
            break

        # 检查 finish
        finish_type, finish_content = agent._parse_finish(output)
        if finish_type:
            if finish_type == "memory":
                return AgentResult(
                    need_retrieval=True,
                    memory_block=finish_content,
                    found_memory=True,
                ), steps_log
            elif finish_type == "hint":
                return AgentResult(
                    need_retrieval=False,
                    context_hint=finish_content,
                ), steps_log
            else:  # no_memory
                hint = finish_content or "当前对话：日常聊天 | 用户情绪：平静"
                return AgentResult(
                    need_retrieval=False,
                    context_hint=hint,
                ), steps_log

        # 检查 Action
        action_match = re.search(
            r'Action:\s*(\w+)\(\s*(.*?)\s*\)',
            output, re.DOTALL
        )
        if action_match:
            tool_name = action_match.group(1)
            raw_arg = action_match.group(2).strip()

            # 记录步骤
            step_entry: dict = {
                "step": step + 1,
                "action": f"{tool_name}({raw_arg[:60]}{'...' if len(raw_arg) > 60 else ''})",
                "observation_preview": "",
            }

            # 执行工具（save_note 在 debug 模式下跳过实际写入）
            if tool_name == "save_note":
                observation = "[DEBUG] save_note 已跳过（不写入真实数据）"
            else:
                observation = await agent._dispatch_tool(
                    tool_name=tool_name,
                    raw_arg=raw_arg,
                    user_id=user_id,
                    step=step + 1,
                    total_prompt_tokens=0,
                    total_completion_tokens=0,
                )

            # 截取 observation 预览
            obs_preview = str(observation)[:120].replace("\n", " ")
            if len(str(observation)) > 120:
                obs_preview += "..."
            step_entry["observation_preview"] = obs_preview
            steps_log.append(step_entry)

            messages.append(AIMessage(role="assistant", content=output))
            messages.append(AIMessage(role="user", content=f"Observation: {observation}"))
            continue

        # 无结构化输出
        messages.append(AIMessage(role="assistant", content=output))
        messages.append(AIMessage(role="user", content="请继续，输出 Action 或 finish。"))

    # 超过最大步数
    return AgentResult(
        need_retrieval=False,
        context_hint="当前对话：日常聊天 | 用户情绪：平静",
    ), steps_log
