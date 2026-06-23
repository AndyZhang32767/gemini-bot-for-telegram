#=======================================================================================
#.       tui/widgets/schedule_modal.py — 定时任务查看
#.       展示所有已注册的定时唤起计划，每 10s 自动刷新。
#.
#.       动画方案与 config_modal 一致：壳 fade-in → 替换为真实 dialog。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button

from utils.scheduler import get_schedules


class ScheduleModal(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    ScheduleModal {
        align: center middle;
    }

    /* ================================================================
    .   Fade 空壳 — 仅用于淡入动画
    .=============================================================== */

    #schedule-shell {
        width: 55%;
        height: 60;
        max-height: 70%;
        border: thick $secondary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #schedule-shell.-visible {
        display: block;
    }

    #schedule-shell.-fade-in {
        opacity: 100%;
        transition: opacity 300ms in_out_cubic;
    }

    /* ================================================================
    .   真实 dialog — 无渐变，fade 完成后替换壳
    .=============================================================== */

    #schedule-dialog {
        width: 55%;
        height: 60;
        max-height: 70%;
        border: thick $secondary;
        background: $surface;
        padding: 1 2;
        display: none;
    }

    #schedule-dialog.-visible {
        display: block;
    }

    /* title / body 初始透明，由 -fade-children 触发淡入 */

    #schedule-title {
        text-align: center;
        padding: 1;
        background: $secondary;
        color: $text;
        text-style: bold;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #schedule-body {
        height: 1fr;
        margin-bottom: 1;
        overflow-y: auto;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #schedule-dialog.-fade-children #schedule-title,
    #schedule-dialog.-fade-children #schedule-body {
        opacity: 100%;
    }

    #schedule-header {
        height: 1;
        margin-top: 1;
        padding: 0 2;
        background: $panel;
        color: $text-disabled;
        text-style: bold;
    }

    .schedule-row {
        height: 1;
        padding: 0 2;
    }

    #schedule-close {
        dock: bottom;
        height: 3;
        align: right middle;
    }
    """

    def __init__(self):
        super().__init__()
        self._timer = None

    #===================================================================================
    #.       界面构建 — 壳 + 真实 dialog
    #===================================================================================

    def compose(self) -> ComposeResult:
        items = get_schedules()

        # -- Fade 空壳
        yield VerticalScroll(id="schedule-shell")

        # -- 真实 dialog（初始隐藏）
        with VerticalScroll(id="schedule-dialog"):
            yield Static("🕐 定时唤起计划", id="schedule-title")
            with VerticalScroll(id="schedule-body"):
                if not items:
                    yield Static("  暂无已注册的定时任务", classes="schedule-row")
                else:
                    yield Static("  时间          唤起的函数", id="schedule-header")
                    for item in items:
                        yield Static(f"  {item['time']}        {item['callback']}", classes="schedule-row")
            with Horizontal(id="schedule-close"):
                yield Button("Close (Esc)", id="schedule-close-btn")

    #===================================================================================
    #.       挂载 — 壳淡入 → 替换为真实 dialog
    #===================================================================================

    def on_mount(self) -> None:
        shell = self.query_one("#schedule-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        self.set_timer(0.35, self._swap_to_real)
        # 每 10s 刷新
        self._timer = self.set_interval(10, self._refresh)

    def _swap_to_real(self) -> None:
        """壳淡入完成 → 隐藏壳，显示真实 dialog，子控件淡入。"""
        self.query_one("#schedule-shell").display = False
        dialog = self.query_one("#schedule-dialog")
        dialog.add_class("-visible")
        self.set_timer(0.03, lambda: dialog.add_class("-fade-children"))

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    #===================================================================================
    #.       刷新 — 直接更新 body 内容
    #===================================================================================

    def _refresh(self) -> None:
        body = self.query_one("#schedule-body")
        body.remove_children()
        items = get_schedules()
        if not items:
            body.mount(Static("  暂无已注册的定时任务", classes="schedule-row"))
        else:
            body.mount(Static("  时间          唤起的函数", id="schedule-header"))
            for item in items:
                body.mount(Static(f"  {item['time']}        {item['callback']}", classes="schedule-row"))

    #===================================================================================
    #.       按钮事件
    #===================================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
