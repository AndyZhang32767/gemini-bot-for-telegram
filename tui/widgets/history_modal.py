#=======================================================================================
#.       tui/widgets/history_modal.py — 会话历史查看器
#.       两层弹窗结构：
#.         HistoryList     — 第一层：列出所有活跃会话（chat_id + premium/normal 标记）
#.         ChatHistoryView — 第二层：显示单个会话的对话历史（role + 截断文本）
#.
#.       数据来源：bot/session.py 的 sessions 和 save_history 字典。
#.       被 tui/app.py 的 "h" 快捷键 / History 按钮触发。
#.
#.       动画方案与 config_modal 一致：
#.         空壳 fade-in → 替换为真实 dialog → title/body 淡入。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button


#=======================================================================================
#.       HistoryList — 会话列表弹窗
#=======================================================================================

class HistoryList(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    HistoryList {
        align: center middle;
    }

    /* ---- fade 空壳 ---- */

    #history-shell {
        width: 60%;
        height: 70%;
        border: thick $primary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #history-shell.-visible {
        display: block;
    }

    #history-shell.-fade-in {
        opacity: 100%;
        transition: opacity 300ms in_out_cubic;
    }

    /* ---- 真实 dialog ---- */

    #history-dialog {
        width: 60%;
        height: 70%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        display: none;
    }

    #history-dialog.-visible {
        display: block;
    }

    #history-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #history-body {
        height: 1fr;
        margin: 1 0;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #history-dialog.-fade-children #history-title,
    #history-dialog.-fade-children #history-body {
        opacity: 100%;
    }

    #history-body Button {
        width: 100%;
        margin-bottom: 1;
    }

    #history-close {
        dock: bottom;
        height: 3;
        align: right middle;
    }
    """

    def __init__(self):
        super().__init__()
        from bot.session import sessions
        self._sessions = list(sessions.items())

    #===================================================================================
    #.       界面构建
    #===================================================================================

    def compose(self) -> ComposeResult:
        # -- Fade 空壳
        yield VerticalScroll(id="history-shell")

        # -- 真实 dialog
        with VerticalScroll(id="history-dialog"):
            yield Static("Chat History — 会话列表", id="history-title")
            with VerticalScroll(id="history-body"):
                if not self._sessions:
                    yield Static("暂无活跃会话")
                for chat_id, info in self._sessions:
                    chk = info.get("chk", "?")
                    label = f"[{'premium' if chk == 'T' else 'normal'}] chat_id={chat_id}"
                    yield Button(label, id=f"hist-{chat_id}")
            with Horizontal(id="history-close"):
                yield Button("Close", id="hist-close")

    #===================================================================================
    #.       动画
    #===================================================================================

    def on_mount(self) -> None:
        shell = self.query_one("#history-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        self.set_timer(0.35, self._swap_to_real)

    def _swap_to_real(self) -> None:
        self.query_one("#history-shell").display = False
        dialog = self.query_one("#history-dialog")
        dialog.add_class("-visible")
        self.set_timer(0.03, lambda: dialog.add_class("-fade-children"))

    #===================================================================================
    #.       按钮事件
    #===================================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "hist-close":
            self.dismiss()
        elif bid.startswith("hist-"):
            try:
                chat_id = int(bid[5:])
                self.app.push_screen(ChatHistoryView(chat_id))
            except ValueError:
                pass


#=======================================================================================
#.       ChatHistoryView — 单个会话的对话历史详情（二级菜单）
#=======================================================================================

class ChatHistoryView(ModalScreen):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    ChatHistoryView {
        align: center middle;
    }

    /* ---- fade 空壳 ---- */

    #chatview-shell {
        width: 80%;
        height: 85%;
        border: thick $primary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #chatview-shell.-visible {
        display: block;
    }

    #chatview-shell.-fade-in {
        opacity: 100%;
        transition: opacity 300ms in_out_cubic;
    }

    /* ---- 真实 dialog ---- */

    #chatview-dialog {
        width: 80%;
        height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        display: none;
    }

    #chatview-dialog.-visible {
        display: block;
    }

    #chatview-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #chatview-body {
        height: 1fr;
        margin: 1 0;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #chatview-dialog.-fade-children #chatview-title,
    #chatview-dialog.-fade-children #chatview-body {
        opacity: 100%;
    }

    #chatview-close {
        dock: bottom;
        height: 3;
        align: right middle;
    }
    """

    def __init__(self, chat_id: int):
        super().__init__()
        self._chat_id = chat_id

    #===================================================================================
    #.       界面构建
    #===================================================================================

    def compose(self) -> ComposeResult:
        from bot.session import sessions, save_history
        info = sessions.get(self._chat_id, {})
        history = save_history.get(self._chat_id, [])

        chk = info.get("chk", "?")
        mode = "premium" if chk == "T" else "normal"

        # -- Fade 空壳
        yield VerticalScroll(id="chatview-shell")

        # -- 真实 dialog
        with VerticalScroll(id="chatview-dialog"):
            yield Static(f"Chat {self._chat_id} ({mode}) — 共 {len(history)} 条", id="chatview-title")
            with VerticalScroll(id="chatview-body"):
                if not history:
                    yield Static("暂无历史记录")
                for i, content in enumerate(history, 1):
                    role = getattr(content, 'role', '?')
                    text = ""
                    if hasattr(content, 'parts'):
                        for p in content.parts:
                            if hasattr(p, 'text') and p.text:
                                text += p.text
                    text = text.replace("\n", " ")[:200]
                    color = "$accent" if role == "model" else "$text"
                    yield Static(f"[{color}][{i}] [{role}] {text}[/{color}]")
            with Horizontal(id="chatview-close"):
                yield Button("Back", id="chatview-back")
                yield Button("Clear", id="chatview-clear", variant="error")

    #===================================================================================
    #.       动画
    #===================================================================================

    def on_mount(self) -> None:
        shell = self.query_one("#chatview-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        self.set_timer(0.35, self._swap_to_real)

    def _swap_to_real(self) -> None:
        self.query_one("#chatview-shell").display = False
        dialog = self.query_one("#chatview-dialog")
        dialog.add_class("-visible")
        self.set_timer(0.03, lambda: dialog.add_class("-fade-children"))

    #===================================================================================
    #.       按钮事件
    #===================================================================================

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "chatview-clear":
            import asyncio
            from bot.session import clear_chat_history
            asyncio.ensure_future(clear_chat_history(self._chat_id))
            self.app.notify(f"已清除 chat_id={self._chat_id} 的对话历史")
            self.dismiss()
        elif bid == "chatview-back":
            self.dismiss()
