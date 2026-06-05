"""
配置加载模块
从 config/ai_config.toml 和 config/bot_config.toml 读取配置
"""
import sys
from pathlib import Path
from typing import Any, Optional

# Python 3.11+ 内置 tomllib，否则用 tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# ========================
# 全局配置存储
# ========================
AI_CONFIG: dict[str, Any] = {}
BOT_CONFIG: dict[str, Any] = {}
REY_CONFIG: dict[str, Any] = {}
EMOJI_CONFIG: dict[str, Any] = {}
EMOTION_CONFIG: dict[str, Any] = {}
RAG_CONFIG: dict[str, Any] = {}

# 配置文件路径（相对于项目根目录）
# 从 src/bot/core/ 向上 3 级到根目录
CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"

# 备选：直接使用工作目录（从根目录启动时）
if not CONFIG_DIR.exists():
    CONFIG_DIR = Path.cwd() / "config"


def _load_toml(file_path: Path) -> dict[str, Any]:
    """读取 TOML 文件并解析为字典"""
    with open(file_path, "rb") as f:
        return tomllib.load(f)


def _ensure_config_file(filename: str) -> Path:
    """确保配置文件存在，如果不存在则从示例文件复制"""
    config_path = CONFIG_DIR / filename
    example_path = CONFIG_DIR / f"{filename.rsplit('.', 1)[0]}.example.toml"

    if not config_path.exists():
        if example_path.exists():
            import shutil
            shutil.copy2(example_path, config_path)
            print(f"[XNBot] 已从示例创建配置文件: {filename}")
        else:
            raise FileNotFoundError(
                f"配置文件不存在: {config_path}\n"
                f"请复制 {example_path} 为 {config_path} 并填入你的配置"
            )
    return config_path


def load_ai_config() -> dict[str, Any]:
    """加载 AI 配置"""
    config_path = _ensure_config_file("ai_config.toml")
    return _load_toml(config_path)


def load_bot_config() -> dict[str, Any]:
    """加载 Bot 配置"""
    config_path = _ensure_config_file("bot_config.toml")
    return _load_toml(config_path)


def load_rey_config() -> dict[str, Any]:
    """加载 Rey 配置（模型专用 system_prompt 和调试开关）"""
    config_path = CONFIG_DIR / "rey_config.toml"
    return _load_toml(config_path)


def load_emoji_config() -> dict[str, Any]:
    """加载表情管理配置"""
    config_path = CONFIG_DIR / "emoji_config.toml"
    return _load_toml(config_path)


def load_emotion_config() -> dict[str, Any]:
    """加载情绪系统配置"""
    config_path = CONFIG_DIR / "emotion_config.toml"
    return _load_toml(config_path)


def load_rag_config() -> dict[str, Any]:
    """加载 RAG 记忆系统配置"""
    config_path = CONFIG_DIR / "rag_config.toml"
    if config_path.exists():
        return _load_toml(config_path)
    return {}


def init_config() -> None:
    """初始化配置，将配置加载到全局变量"""
    global AI_CONFIG, BOT_CONFIG, REY_CONFIG, EMOJI_CONFIG, EMOTION_CONFIG, RAG_CONFIG
    AI_CONFIG = load_ai_config()
    BOT_CONFIG = load_bot_config()
    REY_CONFIG = load_rey_config()
    EMOJI_CONFIG = load_emoji_config()
    EMOTION_CONFIG = load_emotion_config()
    RAG_CONFIG = load_rag_config()


def get_ai_config() -> dict[str, Any]:
    """获取 AI 配置"""
    if not AI_CONFIG:
        init_config()
    return AI_CONFIG


def get_bot_config() -> dict[str, Any]:
    """获取 Bot 配置"""
    if not BOT_CONFIG:
        init_config()
    return BOT_CONFIG


def get_model_config(model_name: str) -> Optional[dict[str, Any]]:
    """
    根据模型别名获取模型配置
    
    Args:
        model_name: 模型别名（如 "roleplay_main"）
    
    Returns:
        模型配置字典，包含 name, provider, model, parameters
        找不到返回 None
    """
    ai_config = get_ai_config()
    models = ai_config.get("models", [])
    
    for model in models:
        if model.get("name") == model_name:
            return model
    
    return None


def get_server_config(provider: str | None = None) -> dict[str, Any]:
    """
    获取 AI 服务器配置（base_url, api_key）
    
    Args:
        provider: 服务商标识（如 "siliconflow", "mimo"），
                  None 时返回默认 [server] 配置
    """
    ai_config = get_ai_config()
    if provider:
        servers = ai_config.get("servers", {})
        if provider in servers:
            return servers[provider]
    # 回退到默认 [server]
    return ai_config.get("server", {})


def get_character_config() -> dict[str, Any]:
    """获取角色设定配置"""
    bot_config = get_bot_config()
    return bot_config.get("character", {})


def get_personality_config() -> dict[str, Any]:
    """获取性格配置"""
    bot_config = get_bot_config()
    return bot_config.get("personality", {})


def get_behavior_config() -> dict[str, Any]:
    """获取行为约束配置"""
    bot_config = get_bot_config()
    return bot_config.get("behavior", {})


def get_rey_config() -> dict[str, Any]:
    """获取 Rey 配置"""
    if not REY_CONFIG:
        init_config()
    return REY_CONFIG


def get_emoji_config() -> dict[str, Any]:
    """获取表情管理配置"""
    if not EMOJI_CONFIG:
        init_config()
    return EMOJI_CONFIG


def get_emotion_config() -> dict[str, Any]:
    """获取情绪系统配置"""
    if not EMOTION_CONFIG:
        init_config()
    return EMOTION_CONFIG


def get_rag_config() -> dict[str, Any]:
    """获取 RAG 记忆系统配置"""
    if not RAG_CONFIG:
        init_config()
    return RAG_CONFIG


def get_model_system_prompt(model_name: str) -> str:
    """
    获取指定模型的 system_prompt
    
    Args:
        model_name: 模型别名（如 "roleplay_main", "scene_context"）
    
    Returns:
        对应的 system_prompt 字符串，找不到返回空字符串
    """
    rey_config = get_rey_config()
    model_section = rey_config.get(model_name, {})
    return model_section.get("system_prompt", "")


def get_debug_config() -> dict[str, Any]:
    """获取调试配置"""
    rey_config = get_rey_config()
    return rey_config.get("debug", {})


def get_vision_prompt(mode: str) -> tuple[str, str]:
    """
    获取视觉模型提示词
    
    Args:
        mode: "emoji" 或 "image"
    
    Returns:
        (system_prompt, user_prompt) 元组
    """
    rey_config = get_rey_config()
    
    if mode == "emoji":
        section = rey_config.get("vision_emoji_desc", {})
    elif mode == "image":
        section = rey_config.get("vision_image_desc", {})
    else:
        raise ValueError(f"未知的视觉模式: {mode}")
    
    system_prompt = section.get("system_prompt", "")
    user_prompt = section.get("user_prompt", "")
    
    return system_prompt, user_prompt


# ========================
# 测试入口
# ========================
if __name__ == "__main__":
    init_config()

    print("=== AI Config ===")
    print(f"Server: {get_server_config()}")
    print(f"Models: {AI_CONFIG.get('models', [])}")

    print("\n=== Bot Config ===")
    print(f"Bot Name: {BOT_CONFIG.get('bot', {}).get('name')}")
    print(f"Character: {get_character_config()}")
    print(f"Personality: {get_personality_config()}")
    print(f"Behavior: {get_behavior_config()}")

    print("\n=== Model Config Test ===")
    roleplay_model = get_model_config("roleplay_main")
    print(f"roleplay_main: {roleplay_model}")

    print("\n=== Rey Config ===")
    print(f"Debug: {get_debug_config()}")
    print(f"roleplay_main prompt: {get_model_system_prompt('roleplay_main')[:100]}...")
    print(f"scene_context prompt: {get_model_system_prompt('scene_context')[:100]}...")
