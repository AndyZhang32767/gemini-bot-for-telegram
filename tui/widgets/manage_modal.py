#=======================================================================================
#.       tui/widgets/manage_modal.py — 工具管理界面
#.
#.       左侧列出当前已安装的工具（可选中），支持删除。
#.       右侧从 GitHub API 拉取可用工具列表，选中后可从 raw.githubusercontent.com
#.       下载安装。
#.       Esc 关闭。
#.
#.       动画方案：空壳 fade-in → 替换为真实 dialog → title/body 淡入。
#=======================================================================================

import os
import ssl
import asyncio
import urllib.request
import json

import certifi

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Button, ListItem, ListView

from utils.tool_scanner import scan_tools


def _installed_module_names() -> set[str]:
    return {t.name for t in scan_tools()}


# GitHub raw 基础 URL
RAW_BASE = "https://raw.githubusercontent.com/AndyZhang32767/assistant/main/tools"


class DeleteConfirm(ModalScreen[bool]):
    """删除确认弹窗。"""

    CSS = """
    DeleteConfirm {
        align: center middle;
    }
    #del-dialog {
        width: 42;
        height: 12;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #del-title {
        text-align: center;
        padding: 1;
        background: $error;
        color: $text;
        text-style: bold;
    }
    #del-body {
        height: 3;
        margin: 1 0;
        text-align: center;
    }
    #del-buttons {
        dock: bottom;
        height: auto;
        align: right middle;
    }
    """

    def __init__(self, tool_name: str):
        super().__init__()
        self._tool_name = tool_name

    def compose(self) -> ComposeResult:
        with Vertical(id="del-dialog"):
            yield Static("确认删除", id="del-title")
            yield Static(f"确定要删除工具 [bold red]{self._tool_name}[/bold red] 吗？\n该操作不可撤销。", id="del-body")
            with Horizontal(id="del-buttons"):
                yield Button(" 确认删除 ", id="btn-del-confirm", variant="error")
                yield Button(" 取消 ", id="btn-del-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-del-confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ManageModal(ModalScreen[str | None]):
    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    CSS = """
    ManageModal {
        align: center middle;
    }

    /* ================================================================
    .   Fade 空壳 — 仅用于淡入动画
    .=============================================================== */

    #manage-shell {
        width: 85;
        height: 80;
        max-height: 75%;
        border: thick $primary;
        background: $surface;
        display: none;
        opacity: 0%;
    }

    #manage-shell.-visible {
        display: block;
    }

    #manage-shell.-fade-in {
        opacity: 100%;
        transition: opacity 300ms in_out_cubic;
    }

    /* ================================================================
    .   真实 dialog — 无渐变，fade 完成后替换壳
    .=============================================================== */

    #manage-dialog {
        width: 85;
        height: 80;
        max-height: 75%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
        display: none;
        overflow: hidden hidden;
    }

    #manage-dialog.-visible {
        display: block;
    }

    #manage-title {
        text-align: center;
        padding: 1;
        background: $primary;
        color: $text;
        text-style: bold;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #manage-main {
        height: 1fr;
        margin: 1 0;
        opacity: 0%;
        transition: opacity 250ms in_out_cubic;
    }

    #manage-dialog.-fade-children #manage-title,
    #manage-dialog.-fade-children #manage-main {
        opacity: 100%;
    }

    #manage-left {
        width: 1fr;
        height: 100%;
        border-right: solid $primary-darken-2;
        padding: 0 1;
    }
    #manage-right {
        width: 1fr;
        height: 100%;
        padding: 0 1;
    }
    #manage-left-title, #manage-right-title {
        text-style: bold underline;
        padding-bottom: 1;
    }
    #manage-installed-scroll, #manage-remote-scroll {
        height: 1fr;
    }
    #manage-installed-list, #manage-remote-list {
        height: 1fr;
    }
    #manage-footer {
        dock: bottom;
        align: right middle;
        height: 5;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._tools = scan_tools()
        self._selected_index: int | None = None
        self._remote_files: list[dict] = []  # [{name, download_url, installed}, ...]

    #===================================================================================
    #.       界面构建 — 壳 + 真实 dialog
    #===================================================================================

    def compose(self) -> ComposeResult:
        # -- Fade 空壳
        yield VerticalScroll(id="manage-shell")

        # -- 真实 dialog（初始隐藏）
        with Vertical(id="manage-dialog"):
            yield Static("Manage Tools（工具管理）", id="manage-title")
            with Horizontal(id="manage-main"):
                with Vertical(id="manage-left"):
                    yield Static("已安装的工具 (Installed)", id="manage-left-title")
                    yield Static("[dim]↑↓ 选择  |  Delete 删除[/dim]")
                    with VerticalScroll(id="manage-installed-scroll"):
                        yield ListView(id="manage-installed-list")
                with Vertical(id="manage-right"):
                    yield Static("可安装的工具 (Available)", id="manage-right-title")
                    yield Static("[dim]↑↓ 选择  |  Enter 下载安装[/dim]")
                    with VerticalScroll(id="manage-remote-scroll"):
                        yield ListView(id="manage-remote-list")
            with Horizontal(id="manage-footer"):
                yield Button(" Delete ", id="btn-current-del", variant="error")
                yield Button(" Download ", id="btn-remote-dl")
                yield Button(" Refresh ", id="btn-avail-refresh")
                yield Button(" Cancel ", id="btn-modal-cancel")

    #===================================================================================
    #.       挂载 — 壳淡入 → 替换为真实 dialog
    #===================================================================================

    def on_mount(self) -> None:
        # 后台加载数据（不等待动画）
        self._populate_installed_list()
        asyncio.create_task(self._fetch_remote())

        # 壳淡入动画
        shell = self.query_one("#manage-shell")
        shell.add_class("-visible")
        self.set_timer(0.03, lambda: shell.add_class("-fade-in"))
        self.set_timer(0.35, self._swap_to_real)

    def _swap_to_real(self) -> None:
        """壳淡入完成 → 隐藏壳，显示真实 dialog，子控件淡入。"""
        self.query_one("#manage-shell").display = False
        dialog = self.query_one("#manage-dialog")
        dialog.add_class("-visible")
        self.set_timer(0.03, lambda: dialog.add_class("-fade-children"))

    #=============================================================
    #.       填充左侧 ListView（已安装）
    #=============================================================
    def _populate_installed_list(self) -> None:
        view = self.query_one("#manage-installed-list", ListView)
        view.clear()
        for t in self._tools:
            access_label = "PB" if t.access == "pb" else "PR"
            label = f"[bold]{t.name}[/bold]  [dim]({access_label})[/dim]  {t.title}"
            view.append(ListItem(Static(label)))

    #=============================================================
    #.       填充右侧 ListView（远程可用）
    #=============================================================
    def _populate_remote_list(self) -> None:
        view = self.query_one("#manage-remote-list", ListView)
        view.clear()
        for f in self._remote_files:
            name = f["name"]
            if f["installed"]:
                label = f"✓ [green]{name}[/green] [dim](已安装)[/dim]"
            else:
                label = f"○ [yellow]{name}[/yellow] [dim](未安装)[/dim]"
            view.append(ListItem(Static(label)))

    #=============================================================
    #.       按钮处理
    #=============================================================
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-current-del":
            self._delete_selected()
        elif bid == "btn-remote-dl":
            self._download_selected()
        elif bid == "btn-avail-refresh":
            asyncio.create_task(self._fetch_remote())
        elif bid == "btn-modal-cancel":
            self.dismiss(None)

    #=============================================================
    #.       ListView 选择变化
    #=============================================================
    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        if event.list_view.id == "manage-installed-list":
            self._selected_index = event.list_view.index
        elif event.list_view.id == "manage-remote-list":
            # track remote selection for download
            self._remote_selected_index = event.list_view.index

    #=============================================================
    #.       下载安装选中的远程工具
    #=============================================================
    def _download_selected(self) -> None:
        idx = getattr(self, '_remote_selected_index', None)
        if idx is None or idx >= len(self._remote_files):
            self.notify("请先在右侧选择一个工具", severity="warning")
            return
        f = self._remote_files[idx]
        if f["installed"]:
            self.notify(f"{f['name']} 已安装，无需下载", severity="information")
            return
        asyncio.create_task(self._do_download(f))

    async def _do_download(self, f: dict) -> None:
        url = f["download_url"]
        tools_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "tools",
        )
        filepath = os.path.join(tools_dir, f["name"])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "assistant-tui"})
            resp_data = await asyncio.to_thread(
                lambda: urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT)
            )
            content = resp_data.read()
            resp_data.close()
            with open(filepath, "wb") as out:
                out.write(content)
            self.notify(f"已下载安装 {f['name']}", severity="information")
            self._tools = scan_tools()
            self._populate_installed_list()
            await self._fetch_remote()
        except Exception as e:
            self.notify(f"下载失败: {e}", severity="error")

    #=============================================================
    #.       删除选中的工具
    #=============================================================
    def _delete_selected(self) -> None:
        if self._selected_index is None or self._selected_index >= len(self._tools):
            self.notify("请先选择一个工具", severity="warning")
            return
        tool = self._tools[self._selected_index]
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "tools", f"{tool.name}.py",
        )
        if not os.path.exists(filepath):
            self.notify(f"文件不存在: {filepath}", severity="error")
            return
        self.app.push_screen(DeleteConfirm(tool.name), callback=self._on_delete_confirmed)

    def _on_delete_confirmed(self, confirmed: bool) -> None:
        if not confirmed or self._selected_index is None:
            return
        tool = self._tools[self._selected_index]
        filepath = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "tools", f"{tool.name}.py",
        )
        try:
            os.remove(filepath)
            import glob
            cache_dir = filepath.replace("tools/", "tools/__pycache__/").replace(".py", ".cpython-*.pyc")
            for cached in glob.glob(cache_dir):
                os.remove(cached)
            self.notify(f"已删除 {tool.name}.py", severity="information")
            self._tools = scan_tools()
            self._selected_index = min(self._selected_index, len(self._tools) - 1) if self._tools else None
            self._populate_installed_list()
            self._fetch_remote()
        except Exception as e:
            self.notify(f"删除失败: {e}", severity="error")

    #=============================================================
    #.       从 GitHub API 拉取文件列表，download_url 用 raw 地址
    #=============================================================
    async def _fetch_remote(self) -> None:
        try:
            await self._fetch_remote_api()
        except Exception:
            try:
                await self._fetch_remote_html()
            except Exception as e:
                self._set_remote_error(f"拉取失败: {e}")

    async def _fetch_remote_api(self) -> None:
        """通过 GitHub API 获取文件列表（有认证时 5000次/小时，无认证 60次/小时）。"""
        api_url = "https://api.github.com/repos/AndyZhang32767/assistant/contents/tools"
        req = urllib.request.Request(api_url, headers={"User-Agent": "assistant-tui"})
        resp_data = await asyncio.to_thread(
            lambda: urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT)
        )
        data = json.loads(resp_data.read().decode("utf-8"))
        resp_data.close()
        self._parse_api_data(data)

    async def _fetch_remote_html(self) -> None:
        """Fallback：解析 GitHub 仓库页面 HTML 获取 .py 文件列表。"""
        import re
        html_url = "https://github.com/AndyZhang32767/assistant/tree/main/tools"
        req = urllib.request.Request(html_url, headers={"User-Agent": "assistant-tui"})
        resp_data = await asyncio.to_thread(
            lambda: urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT)
        )
        html = resp_data.read().decode("utf-8", errors="replace")
        resp_data.close()

        # 匹配 /AndyZhang32767/assistant/blob/main/tools/xxx.py
        pattern = re.compile(r'/AndyZhang32767/assistant/blob/main/tools/([^/"]+\.py)')
        names = set(pattern.findall(html))

        installed = _installed_module_names()
        self._remote_files.clear()
        for name in sorted(names):
            if name.startswith("__"):
                continue
            mod_name = name.replace(".py", "")
            self._remote_files.append({
                "name": name,
                "download_url": f"{RAW_BASE}/{name}",
                "installed": mod_name in installed,
            })
        self._populate_remote_list()

    def _parse_api_data(self, data: list) -> None:
        installed = _installed_module_names()
        self._remote_files.clear()
        for item in data:
            if item["type"] == "file" and item["name"].endswith(".py") and not item["name"].startswith("__"):
                mod_name = item["name"].replace(".py", "")
                self._remote_files.append({
                    "name": item["name"],
                    "download_url": f"{RAW_BASE}/{item['name']}",
                    "installed": mod_name in installed,
                })
        self._populate_remote_list()

    def _set_remote_error(self, msg: str) -> None:
        body = self.query_one("#manage-remote-list", ListView)
        body.clear()
        body.append(ListItem(Static(f"[red]{msg}[/red]")))
