"""
NoneBot 兼容层
让原来的 src/ 模块能在 AstrBot 插件环境下正常工作
"""
import logging

# 创建一个兼容的 logger
logger = logging.getLogger("astrbot.xnbot")


class _LoguruLikeLogger:
    """模拟 loguru logger 的接口，兼容 AstrBot 日志格式"""

    def _log(self, level, msg, *args, **kwargs):
        """统一日志方法，添加 AstrBot 需要的 extra 字段"""
        import logging
        # 获取 AstrBot 的 logger
        astrbot_logger = logging.getLogger("astrbot")
        if astrbot_logger.handlers:
            # 创建 LogRecord 并添加 extra
            record = astrbot_logger.makeRecord(
                name="astrbot.xnbot",
                level=level,
                fn="",
                lno=0,
                msg=msg,
                args=(),
                exc_info=None,
            )
            record.plugin_tag = "[XNBot]"
            record.short_levelname = logging.getLevelName(level)
            record.astrbot_version_tag = ""
            record.source_file = "xnbot"
            record.source_line = 0
            record.is_trace = False
            astrbot_logger.handle(record)
        else:
            # fallback: 直接用 print
            print(f"[XNBot] {msg}")

    def debug(self, msg, *args, **kwargs):
        self._log(logging.DEBUG, msg)

    def info(self, msg, *args, **kwargs):
        self._log(logging.INFO, msg)

    def success(self, msg, *args, **kwargs):
        self._log(logging.INFO, f"✓ {msg}")

    def warning(self, msg, *args, **kwargs):
        self._log(logging.WARNING, msg)

    def error(self, msg, *args, **kwargs):
        self._log(logging.ERROR, msg)

    def critical(self, msg, *args, **kwargs):
        self._log(logging.CRITICAL, msg)


# 创建全局 logger 实例
_loguru_logger = _LoguruLikeLogger()


def patch_nonebot_imports():
    """
    动态修补 nonebot 导入，让 src/ 模块正常工作
    在插件初始化时调用
    """
    import sys

    # 创建 fake nonebot.log 模块
    class FakeNonebotLog:
        logger = _loguru_logger

    # 创建 fake nonebot 模块
    class FakeNonebot:
        log = FakeNonebotLog()

        @staticmethod
        def get_plugin_config(*args, **kwargs):
            return {}

        @staticmethod
        def on_message(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

        @staticmethod
        def on_command(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

        @staticmethod
        def get_asgi():
            return None

        @staticmethod
        def get_driver():
            return None

        @staticmethod
        def get_bot():
            return None

        class plugin:
            class PluginMetadata:
                def __init__(self, *args, **kwargs):
                    pass

        class exception:
            class MatcherException(Exception):
                pass

        class params:
            @staticmethod
            def CommandArg():
                return None

        class adapters:
            class onebot:
                class v11:
                    class Adapter:
                        pass

                    class Bot:
                        pass

                    class MessageEvent:
                        pass

                    class GroupMessageEvent:
                        pass

                    class PrivateMessageEvent:
                        pass

                    class Message:
                        pass

                    class MessageSegment:
                        @staticmethod
                        def image(url):
                            return {"type": "image", "data": {"url": url}}

    # 注册到 sys.modules
    if "nonebot" not in sys.modules:
        sys.modules["nonebot"] = FakeNonebot()
        sys.modules["nonebot.log"] = FakeNonebotLog()
        sys.modules["nonebot.plugin"] = FakeNonebot.plugin
        sys.modules["nonebot.exception"] = FakeNonebot.exception
        sys.modules["nonebot.params"] = FakeNonebot.params
        sys.modules["nonebot.adapters"] = FakeNonebot.adapters
        sys.modules["nonebot.adapters.onebot"] = FakeNonebot.adapters.onebot
        sys.modules["nonebot.adapters.onebot.v11"] = FakeNonebot.adapters.onebot.v11
