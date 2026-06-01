"""
OneBot V11 适配器配置
封装适配器初始化逻辑
"""
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter


def setup(driver: nonebot.Driver) -> None:
    """
    注册 OneBot V11 适配器
    
    Args:
        driver: NoneBot Driver 实例
    """
    driver.register_adapter(OneBotV11Adapter)
