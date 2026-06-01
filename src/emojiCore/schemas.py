"""
表情数据结构定义
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmojiRecord:
    """表情记录"""
    id: int
    hash: str  # MD5 哈希
    file_path: str  # 文件路径
    desc: str  # 文本描述
    created_at: float  # 创建时间戳
    source: str  # 来源
    usage_count: int = 0  # 使用次数


@dataclass
class EmojiMatch:
    """表情匹配结果"""
    id: int
    file_path: str
    desc: str
    similarity: float
    hash: str = ""
