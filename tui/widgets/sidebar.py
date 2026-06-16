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
#.       ITEMS — 开关定义列表
#.       每项为 (key, 中文标签)，key 对应 feature_flags.json 中的 key
#=============================================================
ITEMS = [
    # Skills (Gemini Tools)
    ("get_current_system_time",  "当前时间"),
    ("fetch_school_schedule",    "课表查询"),
    ("web_search",               "网页搜索"),
    ("add_local_reminder",       "添加提醒"),
    ("remove_local_reminder",    "删除提醒"),
    ("update_reminder_priority", "提醒优先级"),
    ("group_reminder",           "群组备忘录"),
    ("file_attachment",          "文件附件支持"),
    ("office_to_pdf",            "Office 自动转 PDF"),
    # Plans (定时任务)
    ("morning_push",             "早间推送"),
]


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
    }
    .toggle-label {
        width: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._flags = load_flags()

    #=========================================================
    #.       构建侧边栏：标题 + 逐行 Switch 控件
    #=========================================================
    def compose(self) -> ComposeResult:
        yield Static("Skills & Plans", id="sidebar-title")
        for key, label in ITEMS:
            on = self._flags.get(key, True)
            with Horizontal(classes="toggle-row"):
                yield Static(f" {label}", classes="toggle-label")
                yield Switch(value=on, id=f"sw-{key}", animate=False)

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
