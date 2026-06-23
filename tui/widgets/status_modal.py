#=======================================================================================
#.       tui/widgets/status_modal.py — 系统资源占用与工具列表状态界面
#.
#.       左侧实时显示 CPU 占用率、内存使用量、功耗，每 1 秒自动刷新。
#.       右侧列出 tools_list（Premium）和 toolsp_list（Normal）的工具函数。
#.       Esc 关闭。
#.
#.       动画方案与 config_modal 一致：
#.         空壳 fade-in → 替换为真实 dialog → title/main/close 淡入。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Button

from utils.system_stats import get_cpu_percent, get_memory_mb, get_power_breakdown
from core.gemini_setup import tools_list, toolsp_list


class StatusModal(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    StatusModal {
        align: center middle;
    }

    /* ================================================================
    .   Fade 空壳 — 仅用于淡入动画
    .=============================================================== */

    #status-shell {
        width: 120;
        height: 80%;
        border: thick $primary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #status-shell.-visible {
        display: block;
    }

    #status-shell.-fade-in {
        opacity: 100%;
        transition: opacity 300ms in_out_cubic;
    }

    /* ================================================================
    .   真实 dialog — 无渐变，fade 完成后替换壳
    .=============================================================== */

    #status-dialog {
        width: 120;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        overflow: hidden hidden;
        display: none;
    }

    #status-dialog.-visible {
        display: block;
    }

    /* title / main / close 初始透明，由 -fade-children 触发淡入 */

    #status-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #status-main {
        height: 1fr;
        margin: 1 0;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #status-close {
        dock: bottom;
        height: 3;
        align: right middle;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #status-dialog.-fade-children #status-title,
    #status-dialog.-fade-children #status-main,
    #status-dialog.-fade-children #status-close {
        opacity: 100%;
    }

    #status-left {
        width: 1fr;
        height: 100%;
        border-right: solid $primary-darken-2;
        padding: 0 1;
    }
    #status-right {
        width: 2fr;
        height: 100%;
        padding: 0 1;
    }
    #status-left-title, #status-right-title {
        text-style: bold underline;
        padding-bottom: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._timer = None

    #===================================================================================
    #.       界面构建 — 壳 + 真实 dialog
    #===================================================================================

    def compose(self) -> ComposeResult:
        # -- Fade 空壳
        yield VerticalScroll(id="status-shell")

        # -- 真实 dialog（初始隐藏）
        with Vertical(id="status-dialog"):
            yield Static("当前系统状态", id="status-title")
            with Horizontal(id="status-main"):
                with Vertical(id="status-left"):
                    yield Static("系统资源", id="status-left-title")
                    with VerticalScroll(id="status-left-scroll"):
                        yield Static(self._build_stats(), id="status-left-body")
                with Vertical(id="status-right"):
                    yield Static("工具列表", id="status-right-title")
                    with VerticalScroll(id="status-right-scroll"):
                        yield Static(self._build_tools_text(), id="status-right-body")
            with Horizontal(id="status-close"):
                yield Button("Close (Esc)", id="status-close-btn")

    #===================================================================================
    #.       挂载 — 壳淡入 → 替换为真实 dialog
    #===================================================================================

    def on_mount(self) -> None:
        # 初始化 psutil CPU 计数器（首次调用返回 0.0）。
        get_cpu_percent()
        # 每 1s 刷新左侧状态。
        self._timer = self.set_interval(1.0, self._refresh)

        # 动画序列
        shell = self.query_one("#status-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        self.set_timer(0.35, self._swap_to_real)

    def _swap_to_real(self) -> None:
        """壳淡入完成 → 隐藏壳，显示真实 dialog，子控件依次淡入。"""
        self.query_one("#status-shell").display = False
        dialog = self.query_one("#status-dialog")
        dialog.add_class("-visible")
        self.set_timer(0.03, lambda: dialog.add_class("-fade-children"))

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()

    #=============================================================
    #.       构建系统状态文本（左栏）
    #=============================================================
    def _build_stats(self) -> str:
        B = 16  # bar width
        lines = []

        # -- CPU --
        cpu = get_cpu_percent()
        lines.append(f"  CPU {cpu:>5.1f}%")
        lines.append(f"  {self._bar(cpu / 100.0, B)}")

        # -- Memory --
        used_mb, total_mb = get_memory_mb()
        if total_mb > 0:
            used_gb = used_mb / 1024
            total_gb = total_mb / 1024
            mem_pct = (used_mb / total_mb) * 100
            lines.append(f"  MEM {used_gb:.1f}/{total_gb:.1f}GB")
            lines.append(f"  {self._bar(mem_pct / 100.0, B)}")
        else:
            lines.append("  MEM N/A")

        # -- Power --
        pwr = get_power_breakdown()
        cpu_w = pwr.get("cpu", 0.0)
        gpu_w = pwr.get("gpu", 0.0)
        ane_w = pwr.get("ane", 0.0)
        package_w = pwr.get("package", 0.0)

        from utils.power_monitor import get_power_monitor
        pm = get_power_monitor()

        if pm.is_running:
            pwr_pct = min(package_w / 30.0, 1.0)
            lines.append(f"  CPU {cpu_w:.2f}W")
            lines.append(f"  GPU {gpu_w:.2f}W")
            lines.append(f"  ANE {ane_w:.2f}W")
            lines.append(f"  Package {package_w:.3f}W")
            lines.append(f"  {self._bar(pwr_pct, B)}")
        elif package_w > 0:
            pwr_pct = min(package_w / 30.0, 1.0)
            lines.append(f"  Sys {package_w:.1f}W")
            lines.append(f"  {self._bar(pwr_pct, B)}")
            lines.append("  [dim](awaiting powermetrics...)[/dim]")
        else:
            lines.append("  Power: N/A")

        return "\n".join(lines)

    #=============================================================
    #.       构建工具列表文本（右栏）
    #=============================================================
    def _build_tools_text(self) -> str:
        lines = []

        lines.append("[bold cyan]Premium (tools_list):[/bold cyan]")
        for i, fn in enumerate(tools_list, 1):
            mod = getattr(fn, '__module__', '?').split('.')[-1]
            lines.append(f"  {i}. [green]{fn.__name__}[/green] [dim]({mod})[/dim]")
        lines.append("=" * 70)
        lines.append("[bold magenta]Normal (toolsp_list):[/bold magenta]")
        for i, fn in enumerate(toolsp_list, 1):
            mod = getattr(fn, '__module__', '?').split('.')[-1]
            lines.append(f"  {i}. [green]{fn.__name__}[/green] [dim]({mod})[/dim]")

        return "\n".join(lines)

    #=============================================================
    #.       进度条绘制（纯文本 Unicode block + Rich 显式标签）
    #=============================================================
    @staticmethod
    def _bar(ratio: float, width: int = 20) -> str:
        ratio = max(0.0, min(1.0, ratio))
        filled = int(round(ratio * width))
        empty = width - filled
        bar = "█" * filled + "░" * empty
        if ratio < 0.5:
            return f"[green]{bar}[/green]"
        elif ratio < 0.8:
            return f"[yellow]{bar}[/yellow]"
        else:
            return f"[red]{bar}[/red]"

    #=============================================================
    #.       定时刷新左侧
    #=============================================================
    def _refresh(self) -> None:
        body = self.query_one("#status-left-body")
        body.update(self._build_stats())

    #=============================================================
    #.       关闭按钮
    #=============================================================
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()
