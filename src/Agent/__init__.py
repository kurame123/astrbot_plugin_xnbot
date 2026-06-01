"""
Agent - 记忆检索 Agent
负责判断是否需要检索、执行检索、验证结果、生成情境建议
"""
from src.Agent.agent import MemoryAgent, CoreAgent

_agent: MemoryAgent | None = None
_core_agent: CoreAgent | None = None


def get_agent() -> MemoryAgent:
    global _agent
    if _agent is None:
        _agent = MemoryAgent()
    return _agent


def get_core_agent() -> CoreAgent:
    global _core_agent
    if _core_agent is None:
        _core_agent = CoreAgent()
    return _core_agent
