#=======================================================================================
#.       tui/widgets/loading_screen.py — 启动加载界面
#.       全屏展示，收到 bot 启动信号后才 dismiss。
#.       动画照抄 setup_screen welcome：
#.         overlay 整体淡入 → 停留等信号 → overlay 整体淡出 → dismiss。
#.       最长等待 30s，超时强制关闭。
#=======================================================================================

import asyncio

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static


class LoadingScreen(Screen):
    CSS = """
    LoadingScreen {
        align: center middle;
        background: $surface;
    }

    #loading-overlay {
        width: 100%;
        height: 100%;
        align: center middle;
        content-align: center middle;
        background: $primary;
        opacity: 0%;
        transition: opacity 900ms in_out_cubic;
    }

    #loading-overlay.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-overlay.-fade-out {
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-title {
        width: 100%;
        text-align: center;
        content-align: center middle;
        color: $text;
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-title.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-title.-fade-out {
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-subtitle {
        width: 100%;
        text-align: center;
        content-align: center middle;
        color: $text-muted;
        margin-top: 1;
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-subtitle.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }

    #loading-subtitle.-fade-out {
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #finish-overlay {
        dock: top;
        width: 100%;
        height: 100%;
        background: $surface;
        display: none;
        opacity: 0%;
    }
    #finish-overlay.-show {
        display: block;
    }
    #finish-overlay.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }
    """

    def __init__(self):
        super().__init__()
        self._ready = False
        self._success = False
        self._error_msg = ""

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="loading-overlay"):
            yield Static("", id="loading-title")
            yield Static("", id="loading-subtitle")
        # finish 遮罩（退出时淡入覆盖）
        yield VerticalScroll(id="finish-overlay")

    #===================================================================================
    #.       动画序列
    #===================================================================================

    def on_mount(self) -> None:
        self._min_wait_done = False  # 最短显示时间是否已过
        self.set_timer(0.3, self._fade_in)
        self.set_timer(1.0, self._on_min_wait_done)  # 最少显示 1s
        self.set_timer(30.0, lambda: self.signal_ready(success=False, error="timeout"))

    def _on_min_wait_done(self) -> None:
        """最短等待时间已过，如果信号已到则触发淡出。"""
        self._min_wait_done = True
        if self._ready:
            self.set_timer(0.5, self._fade_out_and_dismiss)

    def _fade_in(self) -> None:
        """设文字 + 同时加 -fade-in。"""
        try:
            from pyfiglet import figlet_format
            title_text = figlet_format("Assistant Bot", font="standard")
        except ImportError:
            title_text = "Assistant Bot"

        self.query_one("#loading-title", Static).update(title_text)
        from core.config import VERSION
        self.query_one("#loading-subtitle", Static).update(f"Version {VERSION} · Loading...")

        for wid in ("#loading-overlay", "#loading-title", "#loading-subtitle"):
            self.query_one(wid).add_class("-fade-in")

    #===================================================================================
    #.       外部信号 — bot 启动成功/失败时调用
    #===================================================================================

    def signal_ready(self, success: bool, error: str = "") -> None:
        """收到 bot 启动结果 → 更新文字；最短等待 + 信号都满足后才淡出。"""
        if self._ready:
            return
        self._ready = True
        self._success = success

        subtitle = self.query_one("#loading-subtitle", Static)
        if success:
            from core.config import VERSION
            subtitle.update(f"Version {VERSION} · Success   ")
        else:
            subtitle.update(f"Failed: {error or 'Unknown error'}")

        # 如果最短等待已过，延迟 0.5s 后淡出；否则等 _on_min_wait_done 触发
        if self._min_wait_done:
            self.set_timer(0.5, self._fade_out_and_dismiss)

    def _fade_out_and_dismiss(self) -> None:
        """finish-overlay 淡入覆盖全屏 → dismiss。"""
        overlay = self.query_one("#loading-overlay")
        overlay.remove_class("-fade-in")
        overlay.add_class("-fade-out")
        # overlay = self.query_one("#finish-overlay")
        # overlay.add_class("-show")
        # self.set_timer(0.03, lambda: overlay.add_class("-fade-in"))
        loop = asyncio.get_running_loop()
        loop.call_later(0.35, self.dismiss)

