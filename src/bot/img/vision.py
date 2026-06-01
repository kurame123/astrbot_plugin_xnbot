"""
src/bot/img/vision.py - 调用视觉模型描述图片
"""
import httpx
import base64
from nonebot.log import logger


async def describe_image(image_url: str) -> str:
    """
    调用视觉模型描述图片内容
    返回描述文本，失败返回空字符串
    """
    from src.bot.core.config_loader import get_vision_prompt, get_model_config, get_server_config
    from ai_server.client import call_model
    from ai_server.schemas import Message

    try:
        system_prompt, user_prompt = get_vision_prompt("image")

        # 构造带图片的消息（OpenAI vision 格式）
        model_config = get_model_config("vision_image_desc")
        if not model_config:
            logger.error("[ImgVision] 找不到 vision_image_desc 模型配置")
            return ""

        provider = model_config.get("provider", "siliconflow")
        server_config = get_server_config(provider)
        base_url = server_config.get("base_url", "")
        api_key = server_config.get("api_key", "")
        model_id = model_config.get("model", "")

        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            "max_tokens": 1024,
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"].get("content", "")
            # 处理 <think> 标签
            if "<think>" in content:
                parts = content.split("</think>", 1)
                content = parts[1].strip() if len(parts) == 2 else content
            return content.strip()

    except Exception as e:
        logger.error(f"[ImgVision] 图片描述失败: {type(e).__name__}: {e}")
        return ""
