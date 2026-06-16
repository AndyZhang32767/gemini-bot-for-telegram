#=======================================================================================
#.       core/logging_setup.py — 日志系统配置
#.       提供幂等的 setup_logging() 函数：
#.         - 设置全局日志格式为 "时间 - 模块名 - 级别 - 消息"
#.         - 默认 INFO 级别
#.         - 过滤掉 httpx 的 getUpdates 轮询日志以减少终端噪音
#.       被 bot/main.py create_application() 和 tui/app.py on_mount() 调用。
#=======================================================================================

import logging

#=============================================================
#.       日志系统初始化标记
#.       确保 setup_logging() 多次调用只生效一次（幂等）
#=============================================================
_logging_initialized = False


#=============================================================
#.       TelegramFilter — Telegram 轮询日志过滤器
#.       过滤掉 httpx 发往 getUpdates 的轮询请求日志。
#.       Telegram Bot 使用 long polling 方式获取消息，
#.       每秒都会产生一条 HTTP 请求日志，该过滤器将其屏蔽。
#=============================================================
class TelegramFilter(logging.Filter):
    def filter(self, record):
        return "getUpdates" not in record.getMessage()


#=============================================================
#.       setup_logging() — 全局日志初始化（幂等）
#.       1. 配置日志格式和 INFO 级别
#.       2. 给 httpx logger 挂载 Telegram 轮询过滤器
#.       3. 重复调用不会重复添加 handler/filter
#=============================================================
def setup_logging() -> logging.Logger:
    global _logging_initialized
    if _logging_initialized:
        return logging.getLogger(__name__)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    httpx_logger = logging.getLogger("httpx")
    httpx_logger.addFilter(TelegramFilter())

    _logging_initialized = True
    return logging.getLogger(__name__)
