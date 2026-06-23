#=======================================================================================
#.       tui/widgets/setup_screen.py — 首次设置向导
#.       当 core/config.py 中 SETUP = True 时全屏展示。
#.       动画流程：全屏白色 → 欢迎淡入 → 停留 → 淡出 → 设置向导淡入。
#.       引导用户依次设置 Telegram Token、Gemini API Key、
#.       管理员 ID、代理、Bot 名称、私聊/群聊 Instruction。
#.       完成后将 SETUP 写为 False 并进入主界面。
#=======================================================================================

import asyncio
import re

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Input, TextArea, Button

from tui.config_parser import parse_config, write_config


#=============================================================
#.       设置步骤定义
#.       每个步骤包含：
#.         var_name  — config.py 中的变量名
#.         title     — 显示标题
#.         desc      — 说明文字
#.         multiline — 是否使用 TextArea
#.         password  — 是否隐藏输入
#=============================================================
SETUP_STEPS = [
    {
        "var_name": "TELEGRAM_TOKEN",
        "title": "Telegram Bot Token",
        "desc": "从 @BotFather 获取的 Bot 身份凭证。\n用于连接 Telegram API 进行消息收发。",
        "multiline": False,
        "password": False,
    },
    {
        "var_name": "GEMINI_API_KEY",
        "title": "Gemini API Key",
        "desc": "Google Gemini API 密钥。\n用于调用 Gemini 模型生成回复内容。\n可在 Google AI Studio 中创建。",
        "multiline": False,
        "password": False,
    },
    {
        "var_name": "ADMIN_ID",
        "title": "管理员 ID",
        "desc": "管理员的 Telegram user_id（数字）。\n群聊中用于识别 Bot 拥有者，赋予特殊身份标签。\n你自己的 ID 可在 @userinfobot 查询。",
        "multiline": False,
        "password": False,
    },
    {
        "var_name": "PROXY_URL",
        "title": "网络代理",
        "desc": "HTTP 代理地址，所有请求将经过此代理。\n格式示例: http://127.0.0.1:10808\n留空则不使用代理。",
        "multiline": False,
        "password": False,
    },
    {
        "var_name": "BOT_NAME",
        "title": "Bot 名称",
        "desc": "定义 Bot 在群组中被唤起的名称。\n群聊中 @这个名字 即可触发 Bot 响应。",
        "multiline": False,
        "password": False,
    },
    {
        "var_name": "PRIVATE_INSTRUCTION",
        "title": "私聊 System Prompt",
        "desc": "私聊 / Premium 模式的 System Prompt。\n定义角色在私聊中的性格、行为准则和可用能力。\n该模式开放完整工具集并关闭安全过滤。",
        "multiline": True,
        "password": False,
    },
    {
        "var_name": "PUBLIC_INSTRUCTION",
        "title": "群聊 System Prompt",
        "desc": "群聊 / Normal 模式的 System Prompt。\n定义角色在群组中的性格、行为准则和边界。\n该模式下工具集更少，回答风格更谨慎。",
        "multiline": True,
        "password": False,
    },
]


#=======================================================================================
#.       SetupScreen — 全屏设置向导（含欢迎动画）
#=======================================================================================

class SetupScreen(Screen):

    CSS = """
    SetupScreen {
        align: center middle;
        background: $surface;
    }

    /* ================================================================
    .   Welcome 层 — 居中欢迎文字
    .=============================================================== */

    #welcome-overlay {
        width: 100%;
        height: 100%;
        align: center middle;
        content-align: center middle;
        background: $primary;
        opacity: 0%;
    }

    #welcome-overlay.-visible {
        display: block;
    }

    #welcome-overlay.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }

    #welcome-overlay.-fade-out {
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #welcome-overlay.-fade-out #welcome-title,
    #welcome-overlay.-fade-out #welcome-subtitle {
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    #welcome-title {
        width: 100%;
        text-align: center;
        content-align: center middle;
        color: $text;
        opacity: 0%;
    }

    #welcome-subtitle {
        width: 100%;
        text-align: center;
        content-align: center middle;
        color: $text-muted;
        margin-top: 1;
        opacity: 0%;
    }

    #welcome-overlay.-fade-in #welcome-title,
    #welcome-overlay.-fade-in #welcome-subtitle {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }

    /* ================================================================
    .   完成过渡遮罩 — 结束时淡入覆盖全屏
    .=============================================================== */

    #finish-overlay {
        width: 100%;
        height: 100%;
        background: $surface;
        opacity: 0%;
        display: none;
        transition: opacity 600ms in_out_cubic;
    }

    #finish-overlay.-show {
        display: block;
        opacity: 0%;
    }

    #finish-overlay.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }
    #finish-overlay.-fade-out{
        opacity: 0%;
        transition: opacity 500ms in_out_cubic;
    }

    /* ================================================================
    .   设置向导 — fade 空壳（仅用于淡入动画）
    .=============================================================== */

    #setup-fade-shell {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #setup-fade-shell.-visible {
        display: block;
    }

    #setup-fade-shell.-fade-in {
        opacity: 100%;
        transition: opacity 500ms in_out_cubic;
    }

    /* ================================================================
    .   设置向导 — 真实容器（无渐变，fade 完成后替换壳）
    .=============================================================== */

    #setup-container {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
        display: none;
    }

    #setup-container.-visible {
        display: block;
    }

    #setup-header {
        height: 3;
        background: $primary;
        color: $text;
        text-style: bold;
        content-align: center middle;
    }

    #setup-progress {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        content-align: center middle;
    }

    #setup-body {
        height: 1fr;
        padding: 2 3;
        transition: opacity 200ms linear;
    }

    #setup-body.-fade-out {
        opacity: 0%;
    }

    #setup-step-title {
        text-style: bold;
        color: $text;
        padding: 1 0;
    }

    #setup-step-desc {
        color: $text-muted;
        padding: 0 0 1 0;
    }

    #setup-input {
        width: 100%;
    }

    #setup-textarea {
        width: 100%;
        height: 1fr;
    }

    #setup-footer {
        dock: bottom;
        height: 3;
        align: right middle;
        padding: 0 2;
    }

    #setup-footer Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    def __init__(self, config_path: str):
        super().__init__()
        self._config_path = config_path
        self._current_step = 0
        self._total_steps = len(SETUP_STEPS)
        self._defaults: dict[str, str] = {}
        self._load_defaults()

    #===================================================================================
    #.       加载默认值
    #===================================================================================

    def _load_defaults(self) -> None:
        """从 config.py 读取所有变量的当前值作为默认值。"""
        try:
            import importlib
            import core.config as config_mod
            importlib.reload(config_mod)
            for step in SETUP_STEPS:
                val = getattr(config_mod, step["var_name"], "")
                self._defaults[step["var_name"]] = str(val)
        except Exception:
            pass

    #===================================================================================
    #.       界面构建
    #.       Welcome 层和设置向导容器同时构建，通过 CSS 控制显隐。
    #===================================================================================

    def compose(self) -> ComposeResult:
        # -- Welcome 层（初始不可见，由动画序列控制淡入）
        with VerticalScroll(id="welcome-overlay"):
            yield Static("", id="welcome-title")
            yield Static("", id="welcome-subtitle")

        # -- Fade 空壳（仅用于淡入动画，与真实容器外观一致）
        yield VerticalScroll(id="setup-fade-shell")

        # -- 真实设置向导容器（fade 完成后替换壳）
        with VerticalScroll(id="setup-container"):
            yield Static(" 首次设置向导", id="setup-header")
            yield Static(
                f"Step {self._current_step + 1} / {self._total_steps}",
                id="setup-progress",
            )
            with VerticalScroll(id="setup-body"):
                step0 = SETUP_STEPS[0]
                yield Static(step0["title"], id="setup-step-title")
                yield Static(step0["desc"], id="setup-step-desc")
                # Input 和 TextArea 同时创建，通过 display 切换
                yield Input(value=self._defaults.get(step0["var_name"], ""),
                            id="setup-input")
                yield TextArea(self._defaults.get(step0["var_name"], ""),
                               id="setup-textarea")
            with Horizontal(id="setup-footer"):
                yield Button("← Back", id="btn-back", variant="primary")
                yield Button("Skip →", id="btn-skip", variant="warning")
                yield Button("Next →", id="btn-next", variant="primary")

        # -- 完成过渡遮罩（初始隐藏，结束时淡入覆盖全屏）
        yield VerticalScroll(id="finish-overlay")

    #===================================================================================
    #.       动画序列 — on_mount()
    #.
    #.       时间线：
    #.         t=0.0s   全屏白色已就绪（CSS background: #FFFFFF）
    #.         t=0.3s   Welcome 层开始淡入（900ms ease-in-out）
    #.         t=1.2s   Welcome 完全可见
    #.         t=2.8s   Welcome 开始淡出（500ms ease-in-out）
    #.         t=3.3s   Welcome 完全消失，设置向导容器显示
    #===================================================================================

    def on_mount(self) -> None:
        """启动 Welcome → 向导 动画序列。"""
        try:
            from pyfiglet import figlet_format
            title_text = figlet_format("Assistant Bot", font="standard")
        except ImportError:
            title_text = "Assistant Bot"

        title = self.query_one("#welcome-title", Static)
        title.update(title_text)

        subtitle = self.query_one("#welcome-subtitle", Static)
        from core.config import VERSION
        subtitle.update(f"Version {VERSION}  ·  准备进入首次设置向导")

        self._update_buttons()

        # Phase 1: Welcome 淡入
        self.set_timer(0.3, self._welcome_fade_in)

    def _welcome_fade_in(self) -> None:
        """Welcome 层淡入：0.4s → visible(0%) → 0.03s → fade-in。"""
        overlay = self.query_one("#welcome-overlay")
        self.set_timer(0.4, lambda: (
            overlay.add_class("-visible"),
            self.set_timer(0.03, lambda: overlay.add_class("-fade-in")),
        ))

        # Phase 2: 停留后淡出
        self.set_timer(2.5, self._welcome_fade_out)

    def _welcome_fade_out(self) -> None:
        """Welcome 层淡出。"""
        overlay = self.query_one("#welcome-overlay")
        overlay.remove_class("-fade-in")
        overlay.add_class("-fade-out")

        # Phase 3: 淡出完成后显示设置向导
        self.set_timer(0.6, self._show_wizard)

    def _show_wizard(self) -> None:
        """隐藏 Welcome 层 → fade 空壳淡入 → 替换为真实容器。"""
        overlay = self.query_one("#welcome-overlay")
        overlay.display = False

        # Step 1: 显示 fade 空壳并淡入
        shell = self.query_one("#setup-fade-shell")
        shell.add_class("-visible")
        self.set_timer(0.05, lambda: shell.add_class("-fade-in"))

        # Step 2: fade 完成后隐藏壳，显示无渐变的真实容器
        self.set_timer(0.6, self._swap_to_real)

    def _swap_to_real(self) -> None:
        """fade 空壳淡入完成 → 隐藏壳，显示真实容器（无渐变，文字不会丢失）。"""
        self.query_one("#setup-fade-shell").display = False
        self.query_one("#setup-container").add_class("-visible")
        self._init_input_visibility()
        self._update_buttons()

    #===================================================================================
    #.       按钮事件
    #===================================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._save_current_value()
            if self._current_step < self._total_steps - 1:
                self._current_step += 1
                self._rebuild_body()
            else:
                self._finish_setup()
        elif event.button.id == "btn-skip":
            # 跳过：不保存当前值，直接前进
            if self._current_step < self._total_steps - 1:
                self._current_step += 1
                self._rebuild_body()
            else:
                # 最后一步跳过仍然进入完成流程
                self._finish_setup()
        elif event.button.id == "btn-back":
            if self._current_step > 0:
                self._save_current_value()
                self._current_step -= 1
                self._rebuild_body()

    #===================================================================================
    #.       键盘快捷键动作
    #===================================================================================

    def action_prev_step(self) -> None:
        if self._current_step > 0:
            self._save_current_value()
            self._current_step -= 1
            self._rebuild_body()

    def action_next_step(self) -> None:
        if self._current_step < self._total_steps - 1:
            self._save_current_value()
            self._current_step += 1
            self._rebuild_body()

    def action_noop(self) -> None:
        """屏蔽 Esc 关闭行为 — 设置向导不能跳过。"""
        pass

    #===================================================================================
    #.       内部方法
    #===================================================================================

    def _save_current_value(self) -> None:
        """保存当前步骤输入的值到 _defaults。"""
        step = SETUP_STEPS[self._current_step]
        if step["multiline"]:
            try:
                widget = self.query_one("#setup-textarea", TextArea)
                self._defaults[step["var_name"]] = widget.text
            except Exception:
                pass
        else:
            try:
                widget = self.query_one("#setup-input", Input)
                self._defaults[step["var_name"]] = widget.value
            except Exception:
                pass

    def _rebuild_body(self) -> None:
        """触发淡出，延迟后更新内容再淡入。"""
        body = self.query_one("#setup-body", VerticalScroll)
        body.add_class("-fade-out")
        self.set_timer(0.22, self._do_rebuild_body)

    def _do_rebuild_body(self) -> None:
        """淡出完成后执行实际内容更新，再淡入。"""
        step = SETUP_STEPS[self._current_step]

        try:
            progress = self.query_one("#setup-progress", Static)
            progress.update(f"Step {self._current_step + 1} / {self._total_steps}")
        except Exception:
            pass

        try:
            self.query_one("#setup-step-title", Static).update(step["title"])
        except Exception:
            pass

        try:
            self.query_one("#setup-step-desc", Static).update(step["desc"])
        except Exception:
            pass

        default_val = self._defaults.get(step["var_name"], "")
        input_widget = self.query_one("#setup-input", Input)
        textarea_widget = self.query_one("#setup-textarea", TextArea)

        if step["multiline"]:
            input_widget.display = False
            textarea_widget.display = True
            textarea_widget.text = default_val
        else:
            textarea_widget.display = False
            input_widget.display = True
            input_widget.value = default_val
            input_widget.password = step["password"]

        self._update_buttons()

        # 淡入
        body = self.query_one("#setup-body", VerticalScroll)
        body.remove_class("-fade-out")

    def _update_buttons(self) -> None:
        """更新按钮文字和状态。"""
        try:
            back_btn = self.query_one("#btn-back", Button)
            skip_btn = self.query_one("#btn-skip", Button)
            next_btn = self.query_one("#btn-next", Button)

            # Back：第一步隐藏
            back_btn.display = self._current_step != 0

            if self._current_step == self._total_steps - 1:
                next_btn.label = " Finish Setup"
                next_btn.variant = "success"
                skip_btn.label = "⏭ Skip & Finish"
            else:
                next_btn.label = "Next →"
                next_btn.variant = "primary"
                skip_btn.label = "Skip →"

            skip_btn.display = True
        except Exception:
            pass

    def _init_input_visibility(self) -> None:
        """根据第一步的类型初始化 Input/TextArea 的显示状态。"""
        step0 = SETUP_STEPS[0]
        inp = self.query_one("#setup-input", Input)
        ta = self.query_one("#setup-textarea", TextArea)
        if step0["multiline"]:
            inp.display = False
            ta.display = True
        else:
            ta.display = False
            inp.display = True

    def _finish_setup(self) -> None:
        """完成设置：写配置 → 白色遮罩淡入 → 进入主界面。"""
        sections = parse_config(self._config_path)

        for step in SETUP_STEPS:
            new_val = self._defaults.get(step["var_name"], "")
            for section in sections:
                for var in section.variables:
                    if var.name == step["var_name"]:
                        var.value = new_val

        write_config(self._config_path, sections)

        # SETUP 是只读变量，write_config 不会处理它，需要手动替换
        with open(self._config_path, "r", encoding="utf-8") as f:
            content = f.read()
        content = re.sub(r"^SETUP\s*=\s*True", "SETUP = False", content, flags=re.MULTILINE)
        with open(self._config_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 白色遮罩从透明 → 不透明，覆盖全屏后再 dismiss
        overlay = self.query_one("#finish-overlay")
        overlay.add_class("-show")        # display: block, opacity: 0%
        overlay.add_class("-fade-in")     # transition opacity → 100%
        loop = asyncio.get_running_loop()
        loop.call_later(0.7, self.dismiss)