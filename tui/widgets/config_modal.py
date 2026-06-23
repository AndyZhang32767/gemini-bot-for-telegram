#=======================================================================================
#.       tui/widgets/config_modal.py — 配置编辑弹窗
#.       ConfigModal：主配置弹窗，编辑 core/config.py 所有变量。
#.       被 tui/app.py 的 config 按钮/快捷键触发。
#.
#.       动画方案：空壳 fade-in → 替换为真实 dialog。
#.       关闭直接 dismiss（ModalScreen 的 Esc 默认行为）。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input, TextArea, Button, Label

from tui.config_parser import Section, write_config


#=======================================================================================
#.       ConfigModal — 主配置弹窗
#=======================================================================================

class ConfigModal(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    ConfigModal {
        align: center middle;
    }

    /* ================================================================
    .   Fade 空壳 — 仅用于淡入动画
    .=============================================================== */

    #config-modal-shell {
        width: 70%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #config-modal-shell.-visible {
        display: block;
    }

    #config-modal-shell.-fade-in {
        opacity: 100%;
        transition: opacity 300ms in_out_cubic;
    }

    /* ================================================================
    .   真实 dialog — 无渐变，fade 完成后替换壳
    .=============================================================== */

    #config-modal-dialog {
        width: 70%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        display: none;
    }

    #config-modal-dialog.-visible {
        display: block;
    }

    /* title / body / buttons 初始透明，由 -fade-children 触发淡入 */

    #config-modal-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #config-modal-body {
        height: 1fr;
        margin: 1 0;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #config-modal-buttons {
        dock: bottom;
        align: right middle;
        height: 3;
    }

    #config-modal-dialog.-fade-children #config-modal-title,
    #config-modal-dialog.-fade-children #config-modal-body {
        opacity: 100%;
    }

    .var-label {
        margin-top: 1;
        text-style: bold;
        color: $secondary;
    }

    .var-input {
        margin-bottom: 1;
    }
    """

    def __init__(self, section: Section, config_path: str):
        super().__init__()
        self._section = section
        self._config_path = config_path
        self._inputs: dict[str, Input | TextArea] = {}

    #===================================================================================
    #.       界面构建 — 壳 + 真实 dialog
    #===================================================================================

    def compose(self) -> ComposeResult:
        # -- Fade 空壳
        yield VerticalScroll(id="config-modal-shell")

        # -- 真实 dialog（初始隐藏）
        with VerticalScroll(id="config-modal-dialog"):
            yield Static(f"📝 {self._section.title}", id="config-modal-title")
            with VerticalScroll(id="config-modal-body"):
                for var in self._section.variables:
                    yield Label(f"{var.name}", classes="var-label")
                    if var.is_multiline:
                        ta = TextArea(var.value, id=f"var-{var.name}", classes="var-input")
                        ta.styles.height = 10
                        self._inputs[var.name] = ta
                        yield ta
                    else:
                        inp = Input(value=var.value, id=f"var-{var.name}", classes="var-input")
                        self._inputs[var.name] = inp
                        yield inp
            with Horizontal(id="config-modal-buttons"):
                yield Button(" Cancel ", id="btn-modal-cancel")
                yield Button(" 💾 Save & Close ", id="btn-modal-save", variant="success")

    #===================================================================================
    #.       挂载 — 壳淡入 → 替换为真实 dialog
    #===================================================================================

    def on_mount(self) -> None:
        shell = self.query_one("#config-modal-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        self.set_timer(0.35, self._swap_to_real)

    def _swap_to_real(self) -> None:
        """壳淡入完成 → 隐藏壳，显示真实 dialog，子控件依次淡入。"""
        self.query_one("#config-modal-shell").display = False
        dialog = self.query_one("#config-modal-dialog")
        dialog.add_class("-visible")
        # 延迟一帧触发 title/body/buttons 的 opacity 过渡
        self.set_timer(0.03, lambda: dialog.add_class("-fade-children"))

    #===================================================================================
    #.       按钮事件
    #===================================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-modal-save":
            for var in self._section.variables:
                widget = self._inputs.get(var.name)
                if widget:
                    if isinstance(widget, TextArea):
                        var.value = widget.text
                    else:
                        var.value = widget.value
            write_config(self._config_path, [self._section])
            self.app.notify(f"✅ '{self._section.title}' 已保存", title="保存完成")
            self.dismiss()
        elif event.button.id == "btn-modal-cancel":
            self.dismiss()
