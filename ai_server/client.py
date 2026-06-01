"""
AI HTTP 调用客户端
封装硅基流动 API 调用
"""
import httpx
from typing import Any, Optional

from ai_server.schemas import AIRequest, AIResponse, Message, ModelParameters


# 全局 HTTP 客户端（复用连接）
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """获取或创建 HTTP 客户端"""
    global _http_client
    if _http_client is None:
        # 大模型推理可能需要较长时间，设置 180 秒超时
        _http_client = httpx.AsyncClient(timeout=180.0)
    return _http_client


async def close_client() -> None:
    """关闭 HTTP 客户端"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def call_model(
    model_name: str,
    messages: list[Message],
    override_parameters: Optional[dict[str, Any]] = None,
    _is_fallback: bool = False,
    timeout: float = 180.0,
) -> AIResponse:
    """
    调用 AI 模型（支持自动降级到备用模型）
    
    Args:
        model_name: 模型别名（对应 ai_config.toml 中的 models.name）
        messages: 消息列表
        override_parameters: 覆盖默认参数的字典
        _is_fallback: 内部参数，标记是否已经是降级调用
        timeout: 请求超时秒数，默认 180
    
    Returns:
        AIResponse 响应对象
    
    Raises:
        ValueError: 找不到指定模型配置
        httpx.HTTPError: HTTP 请求失败（主模型和备用模型都失败时）
    """
    # 延迟导入，避免循环依赖
    from nonebot.log import logger
    from src.bot.core.config_loader import get_model_config, get_server_config
    
    # 获取模型配置
    model_config = get_model_config(model_name)
    if model_config is None:
        raise ValueError(f"找不到模型配置: {model_name}")
    
    # 根据模型的 provider 字段选对应服务商
    provider = model_config.get("provider", None)
    server_config = get_server_config(provider)
    base_url = server_config.get("base_url", "")
    api_key = server_config.get("api_key", "")
    # 服务商级别的 timeout 优先级低于调用方传入的 timeout
    server_timeout = server_config.get("timeout", None)
    if server_timeout and timeout == 180.0:
        timeout = float(server_timeout)
    
    model_id = model_config.get("model", "")
    default_params = model_config.get("parameters", {})
    fallback_model = model_config.get("fallback", None)
    
    # 合并参数（override 优先）
    merged_params = {**default_params}
    if override_parameters:
        merged_params.update(override_parameters)
    
    parameters = ModelParameters.from_dict(merged_params)
    
    # 构造请求
    request = AIRequest(
        model=model_id,
        messages=messages,
        parameters=parameters
    )
    
    # 发送 HTTP 请求
    client = _get_http_client()
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = await client.post(
            url,
            json=request.to_api_payload(),
            headers=headers,
            timeout=timeout,
        )
        
        # 检查 HTTP 状态码
        if response.status_code != 200:
            error_text = response.text
            logger.error(f"[AI_CLIENT] HTTP {response.status_code}: {error_text[:500]}")
            response.raise_for_status()
        
        # 解析响应
        ai_response = AIResponse.from_api_response(response.json())
        if not ai_response.content:
            logger.warning(f"[AI_CLIENT] 模型 {model_name} 返回空内容, raw={str(response.json())[:300]}")
        return ai_response
        
    except httpx.HTTPStatusError as e:
        # HTTP 错误（4xx, 5xx）
        error_detail = f"HTTP {e.response.status_code}"
        try:
            error_json = e.response.json()
            error_detail = f"{error_detail}: {error_json.get('error', {}).get('message', e.response.text[:200])}"
        except Exception:
            error_detail = f"{error_detail}: {e.response.text[:200]}"
        
        if fallback_model and not _is_fallback:
            logger.warning(f"[AI_CLIENT] 模型 {model_name}({model_id}) 调用失败: {error_detail}，尝试降级到 {fallback_model}")
            return await call_model(
                model_name=fallback_model,
                messages=messages,
                override_parameters=override_parameters,
                _is_fallback=True,
                timeout=timeout,
            )
        else:
            raise
            
    except Exception as e:
        # 其他异常（网络错误、超时等）
        error_detail = f"{type(e).__name__}: {str(e)}"
        
        if fallback_model and not _is_fallback:
            logger.warning(f"[AI_CLIENT] 模型 {model_name}({model_id}) 调用失败: {error_detail}，尝试降级到 {fallback_model}")
            return await call_model(
                model_name=fallback_model,
                messages=messages,
                override_parameters=override_parameters,
                _is_fallback=True,
                timeout=timeout,
            )
        else:
            raise


# ========================
# 测试入口
# ========================
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # 先初始化配置
        from src.bot.core.config_loader import init_config
        init_config()
        
        messages = [
            Message(role="system", content="你是小雫，一个温柔的虚拟少女。"),
            Message(role="user", content="你好，请介绍一下你自己。")
        ]
        
        try:
            response = await call_model("roleplay_main", messages)
            print(f"AI 回复: {response.content}")
            print(f"Token 消耗: {response.usage}")
        except Exception as e:
            print(f"调用失败: {e}")
        finally:
            await close_client()
    
    asyncio.run(test())
