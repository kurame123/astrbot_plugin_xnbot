"""
基础角色扮演插件
"""
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .handler import *

__plugin_meta__ = PluginMetadata(
    name="basic_roleplay",
    description="小雫角色扮演插件",
    usage="直接发送消息即可与小雫对话",
)
