#=======================================================================================
#.       tui/widgets/history_modal.py — 会话历史查看器
#.       两层弹窗结构：
#.         HistoryList     — 第一层：列出所有活跃会话（chat_id + premium/normal 标记）
#.         ChatHistoryView — 第二层：显示单个会话的对话历史（role + 截断文本）
#.
#.       数据来源：bot/session.py 的 sessions 和 save_history 字典。
#.       被 tui/app.py 的 "h" 快捷键 / History 按钮触发。
#=======================================================================================

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Label


#=======================================================================================
#.       HistoryList — 会话列表弹窗
#.       列出所有已授权会话，点击某个会话按钮进入 ChatHistoryView 查看详情。
#=======================================================================================

class HistoryList(ModalScreen):
    CSS = """
    HistoryList {
        align: center middle;
    }
    #history-dialog {
        width: 60%;
        height: 70%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #history-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #history-body {
        height: 1fr;
        margin: 1 0;
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
        # -- 从 bot/session.py 获取运行时 sessions 字典
        from bot.session import sessions
        self._sessions = list(sessions.items())  # [(chat_id, info), ...]

    #=========================================================
    #.       构建会话列表：每行一个按钮，标注 premium/normal
    #=========================================================
    def compose(self) -> ComposeResult:
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

    #=========================================================
    #.       Close → 关闭；点击会话按钮 → 进入 ChatHistoryView
    #=========================================================
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
#.       ChatHistoryView — 单个会话的对话历史详情
#.       用不同颜色显示 user/model 消息，每条截断到 200 字符。
#=======================================================================================

class ChatHistoryView(ModalScreen):
    CSS = """
    ChatHistoryView {
        align: center middle;
    }
    #chatview-dialog {
        width: 80%;
        height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #chatview-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
    }
    #chatview-body {
        height: 1fr;
        margin: 1 0;
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

    #=========================================================
    #.       构建历史详情视图
    #.       从 save_history 读取对话记录，逐条显示 role + 文本预览
    #=========================================================
    def compose(self) -> ComposeResult:
        # -- 从 bot/session.py 获取会话信息和历史记录
        from bot.session import sessions, save_history
        info = sessions.get(self._chat_id, {})
        history = save_history.get(self._chat_id, [])

        chk = info.get("chk", "?")
        mode = "premium" if chk == "T" else "normal"

        with VerticalScroll(id="chatview-dialog"):
            yield Static(f"Chat {self._chat_id} ({mode}) — 共 {len(history)} 条", id="chatview-title")
            with VerticalScroll(id="chatview-body"):
                if not history:
                    yield Static("暂无历史记录")
                for i, content in enumerate(history, 1):
                    role = getattr(content, 'role', '?')
                    # 提取所有文本 parts
                    text = ""
                    if hasattr(content, 'parts'):
                        for p in content.parts:
                            if hasattr(p, 'text') and p.text:
                                text += p.text
                    # 截断显示，避免撑爆界面
                    text = text.replace("\n", " ")[:200]
                    color = "$accent" if role == "model" else "$text"
                    yield Static(f"[{color}][{i}] [{role}] {text}[/{color}]")
            with Horizontal(id="chatview-close"):
                yield Button("Back", id="chatview-back")
                yield Button("Clear", id="chatview-clear", variant="error")

    #=========================================================
    #.       Back → 回到 HistoryList；Clear → 清除该会话历史并返回
    #=========================================================
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
