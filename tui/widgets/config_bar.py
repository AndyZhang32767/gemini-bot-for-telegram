#=======================================================================================
#.       tui/widgets/config_bar.py — 底部配置栏（legacy 组件）
#.       替代方案：当前 tui/app.py 直接在 compose() 中构建底部按钮栏，
#.       不再使用此独立组件。保留供参考或未来重构使用。
#=======================================================================================

from textual.app import ComposeResult
from textual.widgets import Static, Button
from textual.containers import Horizontal

# -- 从 tui/config_parser.py 获取数据结构
from tui.config_parser import Section
# -- ConfigModal 位于同目录 config_modal.py
from tui.widgets.config_modal import ConfigModal


class ConfigBar(Horizontal):
    #.       底部栏：每个配置区块一个按钮 + Save + Restart。

    def __init__(self, sections: list[Section], config_path: str, **kwargs):
        super().__init__(**kwargs)
        self._sections = sections
        self._config_path = config_path
        self._on_restart = None  # 由 App 设置重启回调

    def set_restart_callback(self, callback):
        #.       注入重启回调函数（由 App 调用）。
        self._on_restart = callback

    #=========================================================
    #.       构建按钮栏：区块按钮 + Save + Restart
    #=========================================================
    def compose(self) -> ComposeResult:
        yield Static(" ⚙ ", id="config-bar-label")
        for i, section in enumerate(self._sections):
            btn_id = f"btn-section-{i}"
            yield Button(f" {section.title} ", id=btn_id, variant="primary")
        yield Button(" 💾 Save ", id="btn-save-all", variant="success")
        yield Button(" 🔄 Restart ", id="btn-restart", variant="warning")

    #=========================================================
    #.       按钮点击处理：
    #.       - 区块按钮 → 打开 ConfigModal 编辑弹窗
    #.       - Save → 写回配置
    #.       - Restart → 调用注入的回调重启 Bot
    #=========================================================
    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id and btn_id.startswith("btn-section-"):
            idx = int(btn_id.split("-")[-1])
            if 0 <= idx < len(self._sections):
                self.app.push_screen(
                    ConfigModal(self._sections[idx], self._config_path)
                )

        elif btn_id == "btn-save-all":
            from tui.config_parser import write_config
            write_config(self._config_path, self._sections)
            self.app.notify("✅ 所有配置已保存到 config.py", title="保存完成")

        elif btn_id == "btn-restart":
            if self._on_restart:
                self.app.run_worker(self._on_restart(), exclusive=True)
                self.app.notify("🔄 正在重启 Bot...", title="重启中")
