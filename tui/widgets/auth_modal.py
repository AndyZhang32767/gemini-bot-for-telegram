#=======================================================================================
#.       tui/widgets/auth_modal.py — 新用户授权弹窗
#.       当未知用户首次向 Bot 发送消息时，通过此弹窗让管理员选择：
#.         - 私人 (Private) — 分配 Premium 模式（完整工具集、宽松安全策略）
#.         - 公共 (Public)  — 分配 Normal 模式（受限工具集、默认安全策略）
#.         - 禁止 (Deny)    — 加入黑名单，拒绝服务
#.
#.       被 tui/app.py 的 _tui_auth 回调创建，结果通过 asyncio.Future
#.       传回 bot/session.py 的 get_chat_session()。
#=======================================================================================

import asyncio

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button


class AuthModal(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]
    CSS = """
    AuthModal {
        align: center middle;
    }
    #auth-dialog {
        width: 50%;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #auth-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #auth-info {
        padding: 1;
        margin: 1 0;
    }
    #auth-buttons {
        height: 3;
        align: center middle;
        margin-bottom: 1;
    }
    #auth-buttons Button {
        margin: 0 1;
        min-width: 10;
    }
    """

    def __init__(self, chat_id: int, chat_name: str, chat_type: str):
        super().__init__()
        self._chat_id = chat_id
        self._chat_name = chat_name
        self._chat_type = chat_type
        self._future: asyncio.Future | None = None

    #=========================================================
    #.       设置 Future，用于将用户选择传回调用方
    #=========================================================
    def set_future(self, future: asyncio.Future) -> None:
        self._future = future

    #=========================================================
    #.       构建弹窗界面：标题 + 用户信息 + 三个按钮
    #=========================================================
    def compose(self) -> ComposeResult:
        with VerticalScroll(id="auth-dialog", classes="modal-off"):
            yield Static("新用户请求接入", id="auth-title")
            yield Static(
                f"ID: {self._chat_id}\n"
                f"名称: {self._chat_name}\n"
                f"类型: {self._chat_type}",
                id="auth-info",
            )
            with Horizontal(id="auth-buttons"):
                yield Button(" 私人 (Private) ", id="auth-pr", variant="primary")
                yield Button(" 公共 (Public) ", id="auth-pb", variant="primary")
                yield Button(" 禁止 (Deny) ", id="auth-deny", variant="error")

    #=========================================================
    #.       按钮点击处理：将选择写入 Future 并关闭弹窗
    #.       选择值: "pr" / "pb" / "deny"
    #=========================================================
    def on_button_pressed(self, event: Button.Pressed) -> None:
        choice = event.button.id
        if choice == "auth-pr":
            self._resolve("pr")
        elif choice == "auth-pb":
            self._resolve("pb")
        elif choice == "auth-deny":
            self._resolve("deny")

    def _resolve(self, choice: str) -> None:
        if self._future and not self._future.done():
            self._future.set_result(choice)
        self.dismiss()
