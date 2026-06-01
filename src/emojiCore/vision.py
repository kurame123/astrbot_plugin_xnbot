"""
视觉模型客户端
调用 Qwen-VL 生成表情描述
"""
import base64
import httpx
from pathlib import Path
from typing import Optional

from nonebot.log import logger


# 全局 HTTP 客户端
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """获取或创建 HTTP 客户端"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=120.0)
    return _http_client


def _image_to_base64(image_path: str) -> str:
    """将本地图片转为 base64"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(file_path: str) -> str:
    """根据文件扩展名获取 MIME 类型"""
    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_map.get(ext, "image/png")


async def describe_emoji_image(image_path: str) -> str:
    """
    使用视觉模型描述表情图片

    Args:
        image_path: 本地图片路径

    Returns:
        表情的文本描述
    """
    # 延迟导入避免循环依赖
    from src.bot.core.config_loader import (
        get_emoji_config,
        get_model_config,
        get_rey_config,
        get_server_config,
    )

    emoji_config = get_emoji_config()
    models_config = emoji_config.get("models", {})
    vision_model_name = models_config.get("vision_model", "vision_emoji_desc")

    # 从 rey_config 读取提示词
    rey_config = get_rey_config()
    vision_prompts = rey_config.get(vision_model_name, {})
    system_prompt = vision_prompts.get("system_prompt", "")
    user_prompt = vision_prompts.get("user_prompt", "请描述这张表情图。")

    # 获取模型配置
    model_config = get_model_config(vision_model_name)
    if model_config is None:
        raise ValueError(f"找不到视觉模型配置: {vision_model_name}")

    server_config = get_server_config()
    base_url = server_config.get("base_url", "")
    api_key = server_config.get("api_key", "")
    model_id = model_config.get("model", "")
    params = model_config.get("parameters", {})

    # 读取图片并转 base64
    image_base64 = _image_to_base64(image_path)
    mime_type = _get_mime_type(image_path)

    # 构造多模态消息（OpenAI Vision 格式）
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_base64}",
                    },
                },
                {"type": "text", "text": user_prompt},
            ],
        },
    ]

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": params.get("temperature", 0.3),
        "max_tokens": params.get("max_tokens", 256),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    client = _get_http_client()
    url = f"{base_url.rstrip('/')}/chat/completions"

    logger.debug(f"[EMOJI_VISION] 请求视觉模型: {model_id}, 图片: {image_path}")

    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()

    result = response.json()
    choices = result.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        # 清洗描述
        desc = _clean_description(content)
        logger.info(f"[EMOJI_VISION] 描述生成完成: {desc}")
        return desc

    logger.warning("[EMOJI_VISION] 视觉模型返回空内容")
    return ""


def _clean_description(text: str) -> str:
    """清洗视觉模型返回的描述文本"""
    import re

    desc = text.strip()

    # 去除 markdown 格式
    desc = re.sub(r"\*\*(.+?)\*\*", r"\1", desc)  # **粗体**
    desc = re.sub(r"\*(.+?)\*", r"\1", desc)  # *斜体*
    desc = re.sub(r"^#+\s*", "", desc, flags=re.MULTILINE)  # # 标题
    desc = re.sub(r"^\d+\.\s*", "", desc, flags=re.MULTILINE)  # 1. 序号
    desc = re.sub(r"^-\s*", "", desc, flags=re.MULTILINE)  # - 列表

    # 只取第一行/第一句
    desc = desc.split("\n")[0].strip()
    if "。" in desc:
        desc = desc.split("。")[0] + "。"

    # 限制长度
    if len(desc) > 50:
        desc = desc[:50]

    return desc
