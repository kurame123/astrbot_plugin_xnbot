"""
AI 调用数据结构定义
定义消息格式、请求参数、响应结构
"""
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class Message:
    """聊天消息结构（兼容 OpenAI Chat 格式）"""
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class ModelParameters:
    """模型生成参数"""
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典，用于 API 请求"""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "max_completion_tokens": self.max_tokens,  # mimo 兼容
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelParameters":
        """从字典创建实例"""
        return cls(
            temperature=data.get("temperature", 0.7),
            top_p=data.get("top_p", 0.9),
            max_tokens=data.get("max_tokens", 2048),
            presence_penalty=data.get("presence_penalty", 0.0),
            frequency_penalty=data.get("frequency_penalty", 0.0),
        )


@dataclass
class AIRequest:
    """AI 请求结构"""
    model: str  # 模型 ID
    messages: list[Message]
    parameters: ModelParameters = field(default_factory=ModelParameters)
    
    def to_api_payload(self) -> dict[str, Any]:
        """转换为 API 请求体"""
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in self.messages],
            **self.parameters.to_dict()
        }
        return payload


@dataclass
class AIResponse:
    """AI 响应结构"""
    content: str  # 生成的文本
    reasoning_content: Optional[str] = None  # 推理模型的思考过程
    raw: Optional[dict[str, Any]] = None  # 原始响应（用于调试）
    usage: Optional[dict[str, int]] = None  # token 消耗信息

    @classmethod
    def from_api_response(cls, response: dict[str, Any]) -> "AIResponse":
        """从 API 响应创建实例"""
        content = ""
        reasoning_content = None
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            raw_content = message.get("content") or ""
            reasoning_content = message.get("reasoning_content")

            # 兼容思考型模型：<think>...</think> 标签后面才是真正输出
            if "<think>" in raw_content:
                parts = raw_content.split("</think>", 1)
                if len(parts) == 2:
                    # 把思考过程存到 reasoning_content，真正输出取后半段
                    think_part = parts[0].replace("<think>", "").strip()
                    if not reasoning_content:
                        reasoning_content = think_part
                    content = parts[1].strip()
                else:
                    # 只有 <think> 没有 </think>，说明还在思考中或格式异常
                    content = raw_content.replace("<think>", "").strip()
            else:
                content = raw_content

            # 推理模型有时 content 为空但 reasoning_content 有内容，兜底
            if not content and reasoning_content:
                content = reasoning_content
                reasoning_content = None

        usage = response.get("usage")

        return cls(
            content=content,
            reasoning_content=reasoning_content,
            raw=response,
            usage=usage,
        )


# ========================
# 测试入口
# ========================
if __name__ == "__main__":
    # 测试消息结构
    msg = Message(role="user", content="你好")
    print(f"Message: {msg}")
    
    # 测试参数结构
    params = ModelParameters(temperature=0.8)
    print(f"Parameters: {params.to_dict()}")
    
    # 测试请求结构
    request = AIRequest(
        model="test-model",
        messages=[
            Message(role="system", content="你是小雫"),
            Message(role="user", content="你好")
        ],
        parameters=params
    )
    print(f"Request payload: {request.to_api_payload()}")
