#=======================================================================================
#.       tui/app.py — Textual TUI 主应用
#.       使用 Textual 框架构建的 Bot 控制台界面，提供：
#.         - 实时日志面板（按来源/级别/关键词标色）
#.         - 配置区块编辑弹窗（修改 core/config.py 中的变量）
#.         - 功能开关侧边栏（动态启用/禁用各个工具和计划任务）
#.         - Bot 启停控制（启动 / 重启 / 保存配置）
#.         - 新用户授权弹窗（替代 console input）
#.         - 会话历史查看器
#.         - 可选中复制的日志查看弹窗 (Ctrl+L)
#.
#.       通过 tui_run.py 或直接 python tui/app.py 启动。
#.       内部复用 bot/main.py 的 create_application() 来运行 Bot。
#=======================================================================================

import asyncio
import importlib
import logging
import os
import subprocess

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TextArea

# -- 从 core/config.py 获取版本号显示在标题栏
from core.config import VERSION
# -- 从 core/logging_setup.py 获取日志初始化函数
from core.logging_setup import setup_logging
# -- 从 tui/config_parser.py 获取配置解析和写回函数
from tui.config_parser import parse_config, Section, write_config
# -- TUI 子组件（各 widget）
from tui.widgets.log_panel import LogPanel
from tui.widgets.config_modal import ConfigModal
from tui.widgets.history_modal import HistoryList
from tui.widgets.sidebar import Sidebar

logger = logging.getLogger(__name__)

#=============================================================
#.       CONFIG_PATH — core/config.py 的绝对路径
#.       用于解析配置区块和写回修改
#=============================================================
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "core", "config.py",
)


#=======================================================================================
#.       LogViewModal — 日志查看弹窗
#.       按 Ctrl+L 打开，用 TextArea 显示完整日志内容。
#.       支持鼠标选中和复制（不同于主面板的 RichLog 只读渲染）。
#=======================================================================================

class LogViewModal(ModalScreen):
    CSS = """
    LogViewModal {
        align: center middle;
    }
    #log-view-dialog {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #log-view-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #log-view-area {
        height: 1fr;
        margin: 1 0;
    }
    #log-view-close {
        dock: bottom;
        height: 3;
        align: right middle;
    }
    """

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="log-view-dialog"):
            yield Static("Log Viewer — 可选中复制", id="log-view-title")
            yield TextArea(self._text, id="log-view-area", read_only=True)
            with Horizontal(id="log-view-close"):
                yield Button("Close (Esc)", id="log-view-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


#=======================================================================================
#.       BotTUI — TUI 主应用类
#.       继承 textual.app.App，管理界面布局、事件处理和 Bot 生命周期。
#=======================================================================================

class BotTUI(App):
    CSS = """
    #title-bar {
        height: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        content-align: center middle;
    }
    #main-area {
        height: 1fr;
    }
    #log-panel {
        width: 1fr;
    }
    #sidebar {
        width: 35;
        border-left: solid $primary-darken-2;
    }
    #bottom-bar {
        height: 1;
        background: $panel;
        align: left middle;
    }
    #bottom-bar Button {
        padding: 0 1;
        border: none;
        background: transparent;
        color: $text;
    }
    #bottom-bar Button:hover {
        background: $primary;
        color: $text;
    }
    """

    # 键盘快捷键绑定
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "section(0)", "Config"),
        ("s", "save_config", "Save"),
        ("r", "restart", "Restart"),
        ("h", "show_history", "History"),
        ("ctrl+l", "view_log", "查看日志"),
    ]

    def __init__(self):
        super().__init__()
        self._bot_task: asyncio.Task | None = None   # Bot 运行任务
        self._application = None                       # PTB Application 实例
        self._sections: list[Section] = []             # 配置区块列表

    #===================================================================================
    #.       界面构建 — compose()
    #.       布局结构：
    #.         ┌─ title-bar ─────────────────────────────┐
    #.         │  main-area                              │
    #.         │  ┌─ log_panel ───┬─ sidebar ─┐          │
    #.         │  │               │           │          │
    #.         │  └───────────────┴───────────┘          │
    #.         │  bottom-bar (配置按钮 + Save + Restart)  │
    #.         └─────────────────────────────────────────┘
    #===================================================================================

    def compose(self) -> ComposeResult:
        # 解析 core/config.py 为可编辑的 Section 列表
        self._sections = parse_config(CONFIG_PATH)
        with Vertical():
            yield Static(f"Assistant Bot Control Panel  {VERSION}", id="title-bar")
            with Horizontal(id="main-area"):
                yield LogPanel(id="log-panel")          # 左侧日志面板
                yield Sidebar(id="sidebar")             # 右侧功能开关
            with Horizontal(id="bottom-bar"):
                # 动态生成底部按钮：每个配置区块一个按钮 + 功能按钮
                for i, section in enumerate(self._sections):
                    title = section.title
                    # 去掉 #. 注释前缀和多余空白
                    title = title.lstrip(". ") if title.startswith(".") else title
                    title = title.replace("core/config.py — ", "")
                    # 截断过长的标题（取第一个 — 之前或前 12 字）
                    if " — " in title:
                        title = title.split(" — ")[0]
                    if len(title) > 12:
                        title = title[:12]
                    yield Button(title, id=f"sect-{i}")
                yield Button("h.History", id="sect-hist")
                yield Button("s.Save", id="sect-save")
                yield Button("r.Restart", id="sect-restart")
                yield Button("q.Quit", id="sect-quit")

    #===================================================================================
    #.       初始化 — on_mount()
    #.       1. 初始化日志系统
    #.       2. 设置 TUI 弹窗授权回调（替代 console input）
    #.       3. 启动 Bot
    #===================================================================================

    def on_mount(self) -> None:
        setup_logging()

        # 注入 TUI 弹窗授权回调到 bot/session.py
        # 当新用户连接时，get_chat_session() 会调用此回调弹出 AuthModal
        from bot.session import set_auth_callback

        async def _tui_auth(chat_id: int, chat_name: str, chat_type: str) -> str:
            loop = asyncio.get_event_loop()
            future = loop.create_future()

            from tui.widgets.auth_modal import AuthModal
            modal = AuthModal(chat_id, chat_name, chat_type)
            modal.set_future(future)
            self.push_screen(modal)
            return await future

        set_auth_callback(_tui_auth)

        self._start_bot()

    #===================================================================================
    #.       事件处理 — 底部按钮点击
    #.       按钮 id 格式:
    #.         sect-<N>    — 打开第 N 个配置区块编辑弹窗
    #.         sect-save   — 保存配置到 core/config.py
    #.         sect-restart — 重启 Bot
    #.         sect-hist   — 打开会话历史弹窗
    #.         sect-quit   — 退出 TUI
    #===================================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("sect-"):
            tag = bid[5:]
            if tag.isdigit():
                idx = int(tag)
                if 0 <= idx < len(self._sections):
                    # 打开配置编辑弹窗（ConfigModal 位于 tui/widgets/config_modal.py）
                    self.push_screen(ConfigModal(self._sections[idx], CONFIG_PATH))
            elif tag == "save":
                write_config(CONFIG_PATH, self._sections)
                self.notify("Saved to config.py")
            elif tag == "restart":
                self.run_worker(self._restart_bot(), exclusive=True)
            elif tag == "hist":
                self.push_screen(HistoryList())
            elif tag == "quit":
                self.exit()

    #===================================================================================
    #.       键盘快捷键动作
    #===================================================================================

    def action_section(self, index: int) -> None:
        #.       快捷键：打开第 N 个配置区块弹窗。
        if 0 <= index < len(self._sections):
            self.push_screen(ConfigModal(self._sections[index], CONFIG_PATH))

    def action_save_config(self) -> None:
        #.       快捷键 s：保存配置。
        write_config(CONFIG_PATH, self._sections)
        self.notify("Saved to config.py")

    async def action_restart(self) -> None:
        #.       快捷键 r：重启 Bot。
        await self._restart_bot()

    def action_show_history(self) -> None:
        #.       快捷键 h：打开会话历史弹窗。
        self.push_screen(HistoryList())

    def action_view_log(self) -> None:
        #.       快捷键 Ctrl+L：打开可选中/复制的日志弹窗。
        log_panel = self.query_one("#log-panel", LogPanel)
        self.push_screen(LogViewModal(log_panel.get_text()))

    def action_quit(self) -> None:
        #.       快捷键 q：退出 TUI。
        self.exit()

    #===================================================================================
    #.       Bot 生命周期管理
    #.       _start_bot()   — 创建并启动 Bot（复用 bot/main.py 的 create_application()）
    #.       _restart_bot() — 停止 → 重载配置 → 重新启动
    #.       on_unmount()   — TUI 关闭时停止 Bot 并保存历史
    #===================================================================================

    def _start_bot(self) -> None:
        #.       创建并启动 Telegram Bot（内部复用 create_application）。
        if self._bot_task and not self._bot_task.done():
            return

        async def _run():
            try:
                # 重载 core.config 模块以获取最新配置
                import core.config as config_mod
                importlib.reload(config_mod)
                # -- create_application() 来自 bot/main.py
                from bot.main import create_application
                self._application = create_application()
                await self._application.initialize()
                await self._application.start()
                await self._application.updater.start_polling()
                logger.info("Bot started")
                # 保持运行，直到被取消
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"Bot start failed: {e}")

        self._bot_task = asyncio.create_task(_run())

    async def _restart_bot(self) -> None:
        #.       重启 Bot：重新解析配置 → 停止旧实例 → 启动新实例。
        logger.info("Restarting bot...")
        # 重新解析配置（用户在弹窗中的修改已写回文件，这里重新读取）
        self._sections = parse_config(CONFIG_PATH)
        if self._application:
            try:
                # -- persist_history() 来自 bot/session.py
                from bot.session import persist_history
                await persist_history()
                await self._application.updater.stop()
                await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                logger.error(f"Stop error: {e}")
            self._application = None
        if self._bot_task and not self._bot_task.done():
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
            self._bot_task = None
        await asyncio.sleep(1)
        self._start_bot()
        self.notify("Bot restarted")

    def on_unmount(self) -> None:
        #.       TUI 关闭时的清理：取消 Bot 任务，尝试保存历史。
        if self._bot_task:
            self._bot_task.cancel()
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                _asyncio.ensure_future(self._save_history_safe())
        except Exception:
            pass

    async def _save_history_safe(self) -> None:
        #.       安全的 history 保存（静默失败，避免关闭时报错）。
        from bot.session import persist_history
        try:
            await persist_history()
        except Exception:
            pass
