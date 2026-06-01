"""
角色管理模块
负责组装"小雫"的人设系统提示
"""
from typing import Optional

from src.bot.core.config_loader import (
    get_bot_config,
    get_character_config,
    get_personality_config,
    get_behavior_config
)


class CharacterManager:
    """角色管理器"""
    
    def __init__(self):
        self._system_prompt_cache: Optional[str] = None
    
    def get_character_name(self) -> str:
        """获取角色名称"""
        bot_config = get_bot_config()
        return bot_config.get("bot", {}).get("name", "小雫")
    
    def get_short_desc(self) -> str:
        """获取角色简短描述"""
        character = get_character_config()
        return character.get("short_desc", "")
    
    def get_profile(self) -> str:
        """获取角色详细人设"""
        character = get_character_config()
        return character.get("profile", "").strip()
    
    def get_traits(self) -> list[str]:
        """获取性格关键词列表"""
        personality = get_personality_config()
        return personality.get("traits", [])
    
    def get_speaking_style(self) -> str:
        """获取说话风格"""
        personality = get_personality_config()
        return personality.get("speaking_style", "").strip()
    
    def get_behavior_constraints(self) -> dict:
        """获取行为约束"""
        return get_behavior_config()
    
    def get_remember_length(self) -> int:
        """获取记忆窗口长度"""
        behavior = get_behavior_config()
        return behavior.get("remember_length", 20)
    
    def get_reply_prefix(self) -> str:
        """获取回复前缀"""
        behavior = get_behavior_config()
        return behavior.get("reply_prefix", "")
    
    def build_system_prompt(self) -> str:
        """
        构建完整的系统提示
        将人设、性格、说话风格、行为约束组合成一段文字
        """
        if self._system_prompt_cache:
            return self._system_prompt_cache
        
        name = self.get_character_name()
        profile = self.get_profile()
        traits = self.get_traits()
        speaking_style = self.get_speaking_style()
        behavior = self.get_behavior_constraints()
        
        # 组装系统提示
        parts = []
        
        # 角色身份
        parts.append(f"你是{name}。")
        
        # 详细人设
        if profile:
            parts.append(f"\n【角色设定】\n{profile}")
        
        # 性格特点
        if traits:
            traits_str = "、".join(traits)
            parts.append(f"\n【性格特点】\n{traits_str}")
        
        # 说话风格
        if speaking_style:
            parts.append(f"\n【说话风格】\n{speaking_style}")
        
        # 行为约束
        constraints = []
        if not behavior.get("allow_nsfw", False):
            constraints.append("不涉及任何不适当或敏感的内容")
        
        if constraints:
            parts.append(f"\n【行为约束】\n" + "\n".join(f"- {c}" for c in constraints))
        
        # 通用指令
        parts.append(f"\n【重要提示】\n请始终以{name}的身份进行对话，保持角色一致性。")
        
        self._system_prompt_cache = "\n".join(parts)
        return self._system_prompt_cache
    
    def clear_cache(self) -> None:
        """清除缓存（配置更新后调用）"""
        self._system_prompt_cache = None


# 全局单例
_character_manager: Optional[CharacterManager] = None


def get_character_manager() -> CharacterManager:
    """获取角色管理器单例"""
    global _character_manager
    if _character_manager is None:
        _character_manager = CharacterManager()
    return _character_manager


# ========================
# 测试入口
# ========================
if __name__ == "__main__":
    from src.bot.core.config_loader import init_config
    init_config()
    
    manager = get_character_manager()
    
    print(f"角色名称: {manager.get_character_name()}")
    print(f"简短描述: {manager.get_short_desc()}")
    print(f"性格特点: {manager.get_traits()}")
    print(f"记忆长度: {manager.get_remember_length()}")
    print(f"\n=== 系统提示 ===\n{manager.build_system_prompt()}")
