#=======================================================================================
#.       tui/widgets/log_panel.py — 日志面板组件
#.       核心组件：
#.         _TUILogHandler — 自定义 logging.Handler，将 Python 日志转发到
#.                          Textual RichLog 组件，并按来源模块/关键词标色
#.         LogPanel — 继承 RichLog，管理 handler 生命周期并提供纯文本缓冲
#.                   （供 Ctrl+L 弹窗可选中复制）
#.
#.       标色优先级：错误级别 > 来源模块 > 关键词匹配 > 默认 INFO 白色
#.
#.       被 tui/app.py 的 compose() 创建为主面板左侧的日志区域。
#=======================================================================================

import logging
from logging import LogRecord

from rich.text import Text, Style
from textual.widgets import RichLog


#=======================================================================================
#.       _TUILogHandler — 将 logging 日志转发到 Textual RichLog 组件
#.
#.       标色逻辑（优先级从高到低）：
#.         1. 日志级别 >= ERROR   → bright_red
#.         2. 日志级别 >= WARNING → bright_yellow
#.         3. 来源模块匹配        → _SOURCE_COLORS 中定义的颜色
#.         4. 关键词匹配          → _KEYWORD_COLORS 中定义的颜色
#.         5. 默认                → white (INFO) / dim grey (DEBUG)
#=======================================================================================

class _TUILogHandler(logging.Handler):
    # 来源模块 → 颜色映射
    _SOURCE_COLORS = {
        "bot.handlers":   "bright_cyan",
        "bot.main":       "bright_green",
        "bot.session":    "magenta",
        "core.gemini_setup": "bright_yellow",
        "httpx":          "dim cyan",
        "telegram":       "dim blue",
        "httpcore":       "dim cyan",
        "apscheduler":    "dim magenta",
    }

    # 关键词 → (颜色, 是否加粗) 映射
    _KEYWORD_COLORS = [
        ("触发",    "bright_cyan", True),
        ("[消息] 触发", "bright_cyan", True),
        ("[回复消息] 触发", "bright_cyan", True),
        ("[文件] 触发", "bright_cyan", True),
        ("[回复文件]", "bright_cyan", False),
        ("监听",    "dim grey", False),
        ("[生成]",  "bright_yellow", False),
        ("[回复生成]", "bright_yellow", False),
        ("[文件生成]", "bright_yellow", False),
        ("[回复]",  "bright_green", False),
        ("[新请求]", "bold magenta", False),
        ("[授权]",  "green", False),
        ("[拒绝]",  "red", False),
        ("[拦截]",  "dark_red", False),
        ("Bot 启动", "bold green", False),
        ("Bot started", "bold green", False),
        ("启动完成", "bold green", False),
        ("Restarting",  "bold yellow", False),
        ("已停止",  "yellow", False),
        ("推送成功", "green", False),
        ("推送失败", "red", False),
        ("下载成功", "bright_blue", False),
        ("下载图片成功", "bright_blue", False),
        ("HTTP Request", "dim cyan", False),
        ("Gemini 客户端初始化成功", "bold bright_yellow", False),
        ("已设置代理", "dim magenta", False),
    ]

    def __init__(self, rich_log: RichLog):
        super().__init__()
        self._rich_log = rich_log
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s"))

    def emit(self, record: LogRecord) -> None:
        #.       收到一条日志记录 → 标色 → 写入 RichLog + 纯文本缓冲。
        try:
            msg = self.format(record)

            # 1. 根据日志级别确定基础颜色
            if record.levelno >= logging.ERROR:
                color = "bright_red"
            elif record.levelno >= logging.WARNING:
                color = "bright_yellow"
            elif record.levelno >= logging.INFO:
                color = "white"
            else:
                color = "dim grey"

            bold = False
            name = record.name

            # 2. 按来源模块匹配颜色（优先级高于级别默认色）
            if name in self._SOURCE_COLORS:
                color = self._SOURCE_COLORS[name]

            # 3. 按关键词匹配颜色（优先级最高，可覆盖模块色）
            for kw, kw_color, kw_bold in self._KEYWORD_COLORS:
                if kw in record.getMessage():
                    color = kw_color
                    bold = kw_bold
                    break

            # 写入 RichLog（彩色渲染）
            style = Style(color=color, bold=bold)
            self._rich_log.write(Text(msg, style=style))

            # 写入纯文本缓冲（供 LogViewer 复制用）
            if hasattr(self._rich_log, 'append_text'):
                self._rich_log.append_text(msg)
        except Exception:
            self.handleError(record)


#=======================================================================================
#.       LogPanel — RichLog 子类，管理 handler 生命周期 + 纯文本缓冲
#.
#.       on_mount 时挂载 _TUILogHandler 到 root logger（开始捕获日志）
#.       on_unmount 时移除 handler（防止内存泄漏）
#.       _buf 维护纯文本环形缓冲（最多 1000 行）
#=======================================================================================

class LogPanel(RichLog):
    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, wrap=True, max_lines=1000, **kwargs)
        self._handler: _TUILogHandler | None = None
        self._buf: list[str] = []

    #=========================================================
    #.       追加纯文本行到缓冲（由 _TUILogHandler.emit 调用）
    #.       环形缓冲：超过 1000 行时丢弃最早的行
    #=========================================================
    def append_text(self, line: str) -> None:
        self._buf.append(line)
        if len(self._buf) > 1000:
            self._buf = self._buf[-1000:]

    #=========================================================
    #.       获取完整日志文本（供 LogViewModal 选中复制）
    #=========================================================
    def get_text(self) -> str:
        return "\n".join(self._buf)

    #=========================================================
    #.       on_mount — 创建 handler 并挂载到 root logger
    #.       设置 root logger 级别为 DEBUG（确保所有日志都能被捕获）
    #=========================================================
    def on_mount(self) -> None:
        self._handler = _TUILogHandler(self)
        self._handler.setLevel(logging.DEBUG)
        root_logger = logging.getLogger()
        root_logger.addHandler(self._handler)
        if root_logger.level == logging.NOTSET or root_logger.level > logging.DEBUG:
            root_logger.setLevel(logging.DEBUG)

    #=========================================================
    #.       on_unmount — 从 root logger 移除 handler
    #=========================================================
    def on_unmount(self) -> None:
        if self._handler:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
