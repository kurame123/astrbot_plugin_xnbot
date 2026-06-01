"""
情绪状态缓存
管理当前情绪和最近消息记录
支持情绪惯性：情绪有动量，不会瞬间改变
"""
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MessageRecord:
    """消息记录"""
    role: str  # "user" 或 "assistant"
    text: str
    timestamp: float


@dataclass
class EmotionStateView:
    """情绪状态视图（只读）"""
    emotion: str
    intensity: float
    comment: str
    mood: float  # 心情值 0~1
    momentum: float  # 情绪动量


class EmotionDynamics:
    """
    情绪动力学系统
    让情绪有惯性，不会瞬间改变
    """
    
    def __init__(self):
        self.base_mood: float = 0.6  # 基础心情（长期趋势）
        self.current_mood: float = 0.6  # 当前心情 0~1
        self.volatility: float = 0.1  # 情绪波动性（性格特征）
        self.momentum: float = 0.0  # 情绪动量（惯性）
        self.last_drift_at: float = 0.0  # 上次漂移时间
    
    def natural_drift(self, dt_seconds: float) -> None:
        """
        自然漂移：即使没有外部刺激，情绪也会微微变化
        
        Args:
            dt_seconds: 距离上次漂移的秒数
        """
        if dt_seconds <= 0:
            return
        
        dt = dt_seconds / 3600  # 转换为小时
        
        # 向基础心情回归（阻尼效应）
        self.momentum += (self.base_mood - self.current_mood) * 0.05 * dt
        
        # 应用动量
        self.current_mood += self.momentum * dt
        
        # 动量衰减
        self.momentum *= 0.95
        
        # 微小随机波动（模拟心情的自然起伏）
        self.current_mood += random.gauss(0, self.volatility * 0.01 * dt)
        
        # 限制范围
        self.current_mood = max(0.0, min(1.0, self.current_mood))
        self.momentum = max(-0.5, min(0.5, self.momentum))
    
    def on_event(self, intensity: float, valence: float = 0.0) -> None:
        """
        事件影响：施加"力"而不是直接设置
        
        Args:
            intensity: 事件强度 0~1
            valence: 情感效价 -1~1（负=消极，正=积极）
        """
        # 情绪有惯性，不会瞬间改变
        # 施加的力与强度和效价相关
        force = intensity * valence * 0.3
        self.momentum += force
        
        # 高强度事件会略微改变基础心情
        if intensity > 0.7:
            self.base_mood += valence * 0.05
            self.base_mood = max(0.3, min(0.8, self.base_mood))
    
    def on_interaction(self, is_positive: bool = True) -> None:
        """
        互动影响：有人聊天通常会让心情变好
        
        Args:
            is_positive: 是否是积极互动
        """
        if is_positive:
            self.momentum += 0.05
        else:
            self.momentum -= 0.03
    
    def on_silence(self, hours: float) -> None:
        """
        沉默影响：长时间没人聊天
        
        Args:
            hours: 沉默的小时数
        """
        if hours > 2:
            # 长时间没人聊天，心情会略微下降
            loneliness_factor = min(0.1, hours * 0.01)
            self.momentum -= loneliness_factor
    
    def get_mood_description(self) -> str:
        """获取心情描述"""
        if self.current_mood >= 0.8:
            return "心情很好"
        elif self.current_mood >= 0.6:
            return "心情不错"
        elif self.current_mood >= 0.4:
            return "心情平平"
        elif self.current_mood >= 0.2:
            return "有点低落"
        else:
            return "心情不太好"


class EmotionState:
    """情绪状态管理"""

    def __init__(self):
        self.current_emotion: str = "平静"
        self.intensity: float = 0.2
        self.comment: str = "默认平稳心情"
        self.updated_at: float = 0.0  # 上次情绪分析时间
        self.last_message_at: float = 0.0  # 最近一次收到消息的时间
        self.recent_messages: list[MessageRecord] = []
        self._max_messages: int = 20  # 默认值，会被配置覆盖
        
        # 情绪动力学系统
        self.dynamics = EmotionDynamics()

    def set_max_messages(self, limit: int) -> None:
        """设置最大消息数量"""
        self._max_messages = limit

    def add_message(self, role: str, text: str, timestamp: float) -> None:
        """
        添加一条消息到缓存

        Args:
            role: "user" 或 "assistant"
            text: 消息文本
            timestamp: 时间戳
        """
        # 更新情绪动力学
        if self.last_message_at > 0:
            dt = timestamp - self.dynamics.last_drift_at
            self.dynamics.natural_drift(dt)
        
        self.dynamics.last_drift_at = timestamp
        self.dynamics.on_interaction(is_positive=True)  # 有互动通常是积极的
        
        self.last_message_at = timestamp
        self.recent_messages.append(MessageRecord(role=role, text=text, timestamp=timestamp))

        # 超出限制则从前面丢弃
        while len(self.recent_messages) > self._max_messages:
            self.recent_messages.pop(0)

    def set_emotion(
        self,
        emotion: str,
        intensity: float,
        comment: str,
        timestamp: float,
    ) -> None:
        """
        更新情绪状态

        Args:
            emotion: 情绪标签
            intensity: 强度 0~1
            comment: 说明
            timestamp: 更新时间
        """
        # 根据情绪变化更新动力学
        old_emotion = self.current_emotion
        valence = self._emotion_to_valence(emotion)
        old_valence = self._emotion_to_valence(old_emotion)
        
        # 如果情绪变化明显，施加力
        if abs(valence - old_valence) > 0.2 or intensity > 0.6:
            self.dynamics.on_event(intensity, valence)
        
        self.current_emotion = emotion
        self.intensity = intensity
        self.comment = comment
        self.updated_at = timestamp
    
    def _emotion_to_valence(self, emotion: str) -> float:
        """将情绪标签转换为效价值"""
        positive = {"开心": 0.7, "兴奋": 0.8, "激动": 0.9, "放松": 0.5}
        negative = {"疲惫": -0.3, "难过": -0.6, "沮丧": -0.7}
        
        if emotion in positive:
            return positive[emotion]
        elif emotion in negative:
            return negative[emotion]
        else:
            return 0.0  # 平静等中性情绪

    def reset_to_default(self, default_emotion: str, timestamp: float) -> None:
        """
        重置为默认情绪（不调用模型）
        但保留情绪动力学状态，只是标签回归

        Args:
            default_emotion: 默认情绪标签
            timestamp: 重置时间
        """
        # 自然漂移
        if self.dynamics.last_drift_at > 0:
            dt = timestamp - self.dynamics.last_drift_at
            self.dynamics.natural_drift(dt)
        self.dynamics.last_drift_at = timestamp
        
        # 检查是否长时间没人聊天
        if self.last_message_at > 0:
            hours_since_msg = (timestamp - self.last_message_at) / 3600
            self.dynamics.on_silence(hours_since_msg)
        
        self.current_emotion = default_emotion
        self.intensity = 0.2
        self.comment = f"默认平稳心情，{self.dynamics.get_mood_description()}"
        self.updated_at = timestamp

    def get_view(self) -> EmotionStateView:
        """获取情绪状态视图"""
        return EmotionStateView(
            emotion=self.current_emotion,
            intensity=self.intensity,
            comment=self.comment,
            mood=self.dynamics.current_mood,
            momentum=self.dynamics.momentum,
        )

    def get_emotion_text(self) -> str:
        """获取用于 prompt 的情绪描述文本"""
        intensity_desc = "较弱" if self.intensity < 0.4 else "中等" if self.intensity < 0.7 else "较强"
        mood_desc = self.dynamics.get_mood_description()
        
        # 如果有动量，说明情绪在变化中
        momentum_desc = ""
        if abs(self.dynamics.momentum) > 0.1:
            if self.dynamics.momentum > 0:
                momentum_desc = "，心情正在好转"
            else:
                momentum_desc = "，心情有些下滑"
        
        return f"小雫现在整体是「{self.current_emotion}」状态，情绪强度{intensity_desc}，{mood_desc}{momentum_desc}。{self.comment}"
    
    def update_dynamics(self, timestamp: float) -> None:
        """
        更新情绪动力学（定时调用）
        
        Args:
            timestamp: 当前时间戳
        """
        if self.dynamics.last_drift_at > 0:
            dt = timestamp - self.dynamics.last_drift_at
            self.dynamics.natural_drift(dt)
        self.dynamics.last_drift_at = timestamp


# 全局单例
_emotion_state: Optional[EmotionState] = None


def get_emotion_state() -> EmotionState:
    """获取情绪状态单例"""
    global _emotion_state
    if _emotion_state is None:
        _emotion_state = EmotionState()
    return _emotion_state
