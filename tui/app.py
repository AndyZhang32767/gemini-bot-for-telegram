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

# -- 从 core/config.py 获取版本号和 SETUP 标志
from core.config import VERSION, SETUP
# -- 从 core/logging_setup.py 获取日志初始化函数
from core.logging_setup import setup_logging
# -- 从 tui/config_parser.py 获取配置解析和写回函数
from tui.config_parser import parse_config, Section, write_config
# -- TUI 子组件（各 widget）
from tui.widgets.log_panel import LogPanel
from tui.widgets.config_modal import ConfigModal
from tui.widgets.history_modal import HistoryList
from tui.widgets.sidebar import Sidebar
from tui.widgets.setup_screen import SetupScreen
from tui.widgets.loading_screen import LoadingScreen

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
        opacity: 0%;
        offset-y: -1;
    }
    #title-bar.-visible {
        opacity: 100%;
        offset-y: 0;
        transition: opacity 250ms linear,
                    offset-y 500ms in_out_cubic;
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
    /* footer — 纯文字壳，fade-in 后替换为真按钮 */
    #bottom-shell {
        height: 1;
        background: $panel;
        color: $text-muted;
        content-align: left middle;
        padding: 0 1;
        display: none;
        opacity: 0%;
    }
    #bottom-shell.-visible {
        display: block;
    }
    #bottom-shell.-fade-in {
        opacity: 100%;
        transition: opacity 250ms in_out_cubic;
    }
    /* footer — 真实按钮，壳 fade 完成后直接替换（无渐变） */
    #bottom-bar {
        height: 1;
        background: $panel;
        align: left middle;
        display: none;
    }
    #bottom-bar.-visible {
        display: block;
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
        ("s", "show_schedule", "Schedule"),
        ("r", "restart", "Restart"),
        ("h", "show_history", "History"),
        ("t", "tools", "Tools"),
        ("m", "show_manage", "Manage"),
        ("ctrl+s", "save_config", "Save"),
        ("p", "show_status", "Status"),
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
            # -- footer 纯文字壳（先渲染）
            yield Static("c.Config     | t.Tools        | s.Schedule       | h.History       | m.Manage       | p.Status        | r.Restart       | Ctrl+S Save       | q.Quit",
                         id="bottom-shell")
            # -- footer 真按钮（初始隐藏，fade 后替换壳）
            with Horizontal(id="bottom-bar"):
                for i in range(len(self._sections)):
                    yield Button("c.Config", id=f"sect-{i}")
                yield Button("t.Tools", id="sect-tools")
                yield Button("s.Schedule", id="sect-schedule")
                yield Button("h.History", id="sect-hist")
                yield Button("m.Manage", id="sect-manage")
                yield Button("p.Status", id="sect-status")
                yield Button("r.Restart", id="sect-restart")
                yield Button("Ctrl+S Save", id="sect-save")
                yield Button("q.Quit", id="sect-quit")

    #===================================================================================
    #.       初始化 — on_mount()
    #.       1. 初始化日志系统
    #.       2. 设置 TUI 弹窗授权回调（替代 console input）
    #.       3. 启动 Bot
    #===================================================================================

    def on_mount(self) -> None:
        if SETUP:
            self.push_screen(SetupScreen(CONFIG_PATH), callback=self._after_setup)
        else:
            # 正常模式：先显示 loading，后台启动 bot，收到信号后关闭 loading
            loading = LoadingScreen()
            self.push_screen(loading, callback=self._after_loading)
            setup_logging()
            self._setup_auth()
            self._start_bot(on_ready=lambda success, error="": loading.signal_ready(success, error))

    def _after_setup(self, _result=None) -> None:
        """设置完成后：重启进程 → 走正常 loading 流程。"""
        self.notify("设置完成，正在重启...")
        self.set_timer(0.5, lambda: asyncio.create_task(self._restart_bot()))

    def _after_loading(self, _result=None) -> None:
        """Loading 结束：触发动画（bot 已在后台运行）。"""
        self._start_animations()

    def _start_animations(self) -> None:
        """header + sidebar + footer 动画。"""
        self.set_timer(0.01, lambda: (
            self.query_one("#title-bar").add_class("-visible"),
            self.query_one(Sidebar).animate(),
            self._show_footer(),
        ))

    def _setup_auth(self) -> None:
        """注入 TUI 弹窗授权回调到 bot/session.py。"""
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

    def _show_footer(self) -> None:
        """shell fade-in → 隐藏壳 → 显示真按钮。"""
        shell = self.query_one("#bottom-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        # fade 完成后替换为真按钮
        self.set_timer(0.3, self._swap_footer)

    def _swap_footer(self) -> None:
        """隐藏 shell，显示真按钮。"""
        try:
            self.query_one("#bottom-shell").display = False
        except Exception:
            pass
        self.query_one("#bottom-bar").add_class("-visible")

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
            elif tag == "tools":
                from tui.widgets.tools_modal import ToolsModal
                self.push_screen(ToolsModal())
            elif tag == "schedule":
                self.action_show_schedule()
            elif tag == "status":
                self.action_show_status()
            elif tag == "manage":
                self.action_show_manage()
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

    def action_tools(self) -> None:
        #.       快捷键 t：打开 Tools 参数管理。
        from tui.widgets.tools_modal import ToolsModal
        self.push_screen(ToolsModal())

    def action_show_schedule(self) -> None:
        #.       快捷键 s：查看定时唤起计划。
        from tui.widgets.schedule_modal import ScheduleModal
        self.push_screen(ScheduleModal())

    def action_show_status(self) -> None:
        #.       快捷键 p：查看系统资源占用。
        from tui.widgets.status_modal import StatusModal
        self.push_screen(StatusModal())

    def action_show_manage(self) -> None:
        #.       快捷键 m：工具管理（查看已安装/可安装工具）。
        from tui.widgets.manage_modal import ManageModal
        self.push_screen(ManageModal())

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

    def _start_bot(self, on_ready=None) -> None:
        #.       创建并启动 Telegram Bot（内部复用 create_application）。
        #.       on_ready(success, error) — 启动成功/失败时回调。
        if self._bot_task and not self._bot_task.done():
            return

        async def _run():
            try:
                import core.config as config_mod
                importlib.reload(config_mod)
                from bot.main import create_application
                self._application = create_application()
                await self._application.initialize()
                await self._application.start()
                await self._application.updater.start_polling()
                logger.info("Bot started")
                if on_ready:
                    on_ready(True, "")
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"Bot start failed: {e}")
                if on_ready:
                    on_ready(False, str(e))

        self._bot_task = asyncio.create_task(_run())

    async def _restart_bot(self) -> None:
        #.       完全重启：保存状态 → 停止 Bot → 用 os.execv 替换当前进程。
        #.       这样可以确保所有模块缓存被清空，tools/ 变更全部生效。
        import os
        import sys
        logger.info("Restarting whole process...")
        # 1) 保存会话历史
        try:
            from bot.session import persist_history
            await persist_history()
        except Exception as e:
            logger.error(f"Save history error: {e}")
        # 2) 停止 Bot
        if self._application:
            try:
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
        # 3) 用 execv 替换当前进程
        self.notify("Restarting process...")
        await asyncio.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

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
