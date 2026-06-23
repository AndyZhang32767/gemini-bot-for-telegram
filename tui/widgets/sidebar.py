#=======================================================================================
#.       tui/widgets/sidebar.py — 右侧功能开关侧边栏
#.       以 Switch 控件列表展示所有功能开关，用户在 TUI 中实时切换
#.       （立即写入 feature_flags.json，由 bot/handlers.py 在下一条消息时生效）。
#.
#.       开关分两类：
#.         Skills  — Gemini 工具函数（时间/课表/搜索/提醒/备忘录）+ 文件功能
#.         Plans   — 定时任务（早间推送）
#.
#.       依赖：tui/feature_flags.py 的 load_flags() / save_flags()
#.       被 tui/app.py 的 compose() 创建在右侧栏位。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.widgets import Static, Switch

# -- 从 tui/feature_flags.py 获取开关加载/保存函数
from tui.feature_flags import load_flags, save_flags


#=============================================================
#.       ITEMS — 从 tools/ 目录自动扫描 + 固定项
#=============================================================
def _build_items():
    import sys
    from utils.tool_scanner import scan_tools as _scan
    items = []
    for t in _scan():
        items.extend(t.switches)
    sys.modules.pop("tools.schooldays", None)
    try:
        import tools.schooldays  # noqa: F401
        items.append(("morning_push", "早间推送"))
    except ImportError:
        pass
    return items


class Sidebar(VerticalScroll):
    DEFAULT_CSS = """
    Sidebar {
        background: $panel;
        padding: 1;
    }
    #sidebar-title {
        text-align: center;
        text-style: bold;
        padding: 1 0;
        background: $primary;
        color: $text;
        margin-bottom: 1;
    }
    .toggle-row {
        height: 3;
        align: left middle;
        padding: 0 1;
        opacity: 0%;
        offset-x: -4;
    }
    .toggle-row.-visible {
        opacity: 100%;
        offset-x: 0;
        transition: opacity 250ms linear,
                    offset-x 250ms in_out_cubic;
    }
    .toggle-label {
        width: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._flags = load_flags()

    #=========================================================
    #.       内部：构建 title + rows，可选触发逐行动画
    #=========================================================
    def _make_widgets(self) -> list:
        widgets: list = [Static("Skills & Plans", id="sidebar-title")]
        for key, label in _build_items():
            on = self._flags.get(key, True)
            row = Horizontal(
                Static(f" {label}", classes="toggle-label"),
                Switch(value=on, id=f"sw-{key}", animate=False),
                classes="toggle-row",
            )
            widgets.append(row)
        return widgets

    def _animate_rows(self, widgets: list, delay: float = 0.07, base_delay: float = 0.0) -> None:
        """每 100ms 并发触发两个 row 的 -visible 动画。"""
        rows = [w for w in widgets if isinstance(w, Horizontal)]
        pair_gap = 0.1  # 每对间隔 100ms
        for i, row in enumerate(rows):
            pair_index = i // 2
            t = base_delay + pair_index * pair_gap
            self.set_timer(t, lambda row=row: row.add_class("-visible"))

    #=========================================================
    #.       构建侧边栏：标题 + 逐行 Switch 控件
    #=========================================================
    def compose(self) -> ComposeResult:
        widgets = self._make_widgets()
        self._rows = widgets          # 存起来供 on_mount 用
        for w in widgets:
            yield w

    def on_mount(self) -> None:
        # 不再自动播放动画，等 loading/setup 完成后由 app._after_setup 触发
        pass

    def animate(self) -> None:
        """公开方法：由外部（app._after_setup）调用来播放逐行动画。"""
        self._animate_rows(self._rows, base_delay=0.1)
    #=========================================================
    #.       重建侧边栏（重新扫描 tools/ → 更新开关列表）
    #=========================================================
    async def rebuild(self) -> None:
        """重新扫描 tools/ 目录，更新开关列表并刷新 UI。"""
        import importlib
        import utils.tool_scanner
        import tui.feature_flags
        importlib.reload(utils.tool_scanner)
        importlib.reload(tui.feature_flags)
        from tui.feature_flags import load_flags
        self._flags = load_flags()
        await self.remove_children()

        widgets = self._make_widgets()
        await self.mount_all(widgets)
        self._animate_rows(widgets, base_delay=1)

    #=========================================================
    #.       Switch 切换时立即写入 feature_flags.json
    #=========================================================
    def on_switch_changed(self, event: Switch.Changed) -> None:
        key = event.switch.id.replace("sw-", "")
        self._flags[key] = event.value
        save_flags(self._flags)

    #=========================================================
    #.       暴露当前开关状态（供外部只读访问）
    #=========================================================
    @property
    def flags(self) -> dict[str, bool]:
        return dict(self._flags)