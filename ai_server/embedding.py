"""
嵌入模型客户端
调用硅基流动 embedding API
"""
import httpx
from typing import Optional

from nonebot.log import logger


# 全局 HTTP 客户端
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """获取或创建 HTTP 客户端"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=60.0)
    return _http_client


async def embed_texts(
    texts: list[str],
    model_name: str = "embedding_bge_m3",
) -> list[list[float]]:
    """
    将文本列表转换为嵌入向量

    Args:
        texts: 文本列表
        model_name: 模型别名（对应 ai_config.toml）

    Returns:
        向量列表，每个向量 1024 维
    """
    if not texts:
        return []

    # 延迟导入避免循环依赖
    from src.bot.core.config_loader import get_model_config, get_server_config

    model_config = get_model_config(model_name)
    if model_config is None:
        raise ValueError(f"找不到嵌入模型配置: {model_name}")

    provider = model_config.get("provider", None)
    server_config = get_server_config(provider)
    base_url = server_config.get("base_url", "")
    api_key = server_config.get("api_key", "")

    model_id = model_config.get("model", "")

    client = _get_http_client()
    url = f"{base_url.rstrip('/')}/embeddings"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model_id,
        "input": texts,
        "encoding_format": "float",
    }

    response = await client.post(url, json=payload, headers=headers)
    response.raise_for_status()

    result = response.json()
    data = result.get("data", [])

    # 按 index 排序确保顺序正确
    data = sorted(data, key=lambda x: x.get("index", 0))
    vectors = [item.get("embedding", []) for item in data]

    logger.debug(f"[EMBEDDING] 生成 {len(vectors)} 个向量，维度={len(vectors[0]) if vectors else 0}")

    return vectors


async def embed_text(text: str, model_name: str = "embedding_bge_m3") -> list[float]:
    """
    将单个文本转换为嵌入向量

    Args:
        text: 文本
        model_name: 模型别名

    Returns:
        1024 维向量
    """
    vectors = await embed_texts([text], model_name)
    return vectors[0] if vectors else []


# ========================
# 测试入口
# ========================
if __name__ == "__main__":
    import asyncio

    async def test():
        from src.bot.core.config_loader import init_config
        init_config()

        texts = ["你好，我是小雫", "今天天气真好"]
        vectors = await embed_texts(texts)
        print(f"向量数量: {len(vectors)}")
        print(f"向量维度: {len(vectors[0])}")
        print(f"向量前5维: {vectors[0][:5]}")

    asyncio.run(test())
