#=======================================================================================
#.       tui/widgets/config_modal.py — 配置编辑弹窗
#.       点击底部配置按钮后弹出的编辑窗口。
#.       根据 Var 类型自动选择输入控件：
#.         - 多行字符串 (System Prompt) → TextArea（高度 10 行）
#.         - 单行值 (Token/Key/Path 等) → Input
#.
#.       Save & Close 按钮将修改写回 core/config.py（通过 config_parser.write_config），
#.       并显示保存成功通知。配置在下次 Bot 重启后生效。
#.
#.       被 tui/app.py 的按钮/快捷键处理函数创建和推入屏幕。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input, TextArea, Button, Label

# -- 从 tui/config_parser.py 获取数据结构和写回函数
from tui.config_parser import Section, Var, write_config


class ConfigModal(ModalScreen):
    CSS = """
    ConfigModal {
        align: center middle;
    }
    #config-modal-dialog {
        width: 70%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #config-modal-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #config-modal-body {
        height: 1fr;
        margin: 1 0;
    }
    #config-modal-buttons {
        dock: bottom;
        align: right middle;
        height: 3;
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
        # 存储 变量名 → Input/TextArea 的映射，用于保存时收集值
        self._inputs: dict[str, Input | TextArea] = {}

    #=========================================================
    #.       构建表单：遍历 Section 中的每个变量
    #.       - is_multiline → TextArea（适合编辑 System Prompt）
    #.       - 单行值 → Input
    #=========================================================
    def compose(self) -> ComposeResult:
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
                yield Button(" 💾 Save & Close ", id="btn-modal-save", variant="success")
                yield Button(" Cancel ", id="btn-modal-cancel")

    #=========================================================
    #.       按钮处理：
    #.       Save & Close → 收集表单值 → 更新 Var → 写回文件 → 关闭
    #.       Cancel → 直接关闭（不保存）
    #=========================================================
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-modal-save":
            # 收集所有表单控件的当前值，更新 Var 对象
            for var in self._section.variables:
                widget = self._inputs.get(var.name)
                if widget:
                    if isinstance(widget, TextArea):
                        var.value = widget.text
                    else:
                        var.value = widget.value
            # 写回 core/config.py（仅写当前 Section 的变量）
            write_config(self._config_path, [self._section])
            self.app.notify(f"✅ '{self._section.title}' 已保存", title="保存完成")
            self.dismiss()

        elif event.button.id == "btn-modal-cancel":
            self.dismiss()
