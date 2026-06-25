#==TOOL=======================================================================
#.       name: window_manager
#.       access: pr
#.       title: 窗口管理
#.       description: 获取活动窗口列表、截图并用视觉模型分析。capture_window(window_name, question) 根据用户问题分析截图，question 传入具体问题
#.       version: 3.0
#.       sidebar: window_manager=窗口管理
#==END TOOL===================================================================

#=======================================================================================
#.       tools/window_manager.py — 窗口管理与截图分析工具
#.       依赖: pyobjc-framework-Quartz, google-genai
#.       截图后自动调用 Gemini Vision 分析，返回文字结果给外层 AFC。
#.       access=pr 仅 Premium 模式可用。
#=======================================================================================

import os
import subprocess
import time

import Quartz

#==CONFIG=======================================================================
#.       (此工具无可配置参数)
#==END CONFIG===================================================================


def list_windows() -> str:
    """获取当前 macOS 所有活动窗口的名称列表。"""
    try:
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID
        )
        seen = set()
        items = []
        for win in window_list:
            owner = win.get(Quartz.kCGWindowOwnerName, "")
            name = win.get(Quartz.kCGWindowName, "")
            bounds = win.get(Quartz.kCGWindowBounds, {})
            ww = int(bounds.get("Width", 0))
            hh = int(bounds.get("Height", 0))
            if not owner or ww < 100 or hh < 50:
                continue
            key = f"{owner}|{name}"
            if key not in seen:
                seen.add(key)
                items.append(f"{owner} — {name}" if name else owner)
        if not items:
            return "当前没有检测到活动窗口。"
        numbered = [f"  {i+1}. {item}" for i, item in enumerate(items)]
        return "当前活动窗口：\n" + "\n".join(numbered)
    except Exception as e:
        return f"获取窗口列表失败: {e}"


def capture_fullscreen() -> str:
    """截取全屏并保存到本地。

    截取整个屏幕（所有显示器），保存到项目根目录 fullscreen_screenshot.png。
    """
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    save_path = os.path.join(project_dir, "fullscreen_screenshot.png")

    subprocess.run(
        ["screencapture", "-x", save_path],
        capture_output=True, timeout=10
    )
    if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
        return "全屏截图失败。"

    kb = os.path.getsize(save_path) / 1024
    return f"全屏截图已保存: {save_path} ({kb:.0f} KB)"


def capture_window(window_name: str, question: str = "") -> str:
    """截取指定窗口并用 Gemini 分析截图内容。

    先截取窗口截图，再用 Gemini Vision 根据 question 分析截图。
    外层 Gemini 应将用户的具体问题通过 question 参数传入。

    Args:
        window_name: 窗口名称关键词（模糊匹配进程名或窗口标题）
        question: 需要分析的特定问题，如 "有哪些新消息"、"现在在播什么"
                  留空则进行通用描述。
    """
    # ---- 1. 找窗口 ----
    try:
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID
        )
    except Exception as e:
        return f"无法获取窗口列表: {e}"

    target_owner = target_name = target_bounds = None
    for win in window_list:
        owner = win.get(Quartz.kCGWindowOwnerName, "")
        name = win.get(Quartz.kCGWindowName, "")
        bounds = win.get(Quartz.kCGWindowBounds, {})
        if not owner:
            continue
        if (window_name.lower() in owner.lower() or
                (name and window_name.lower() in name.lower())):
            target_owner = owner
            target_name = f"{owner} — {name}" if name else owner
            target_bounds = bounds
            break

    if not target_bounds:
        return f"未找到匹配 '{window_name}' 的窗口。请用 list_windows 确认名称。"

    # ---- 2. 激活窗口 ----
    subprocess.run([
        "osascript", "-e",
        f'tell application "System Events" to '
        f'set frontmost of process "{target_owner}" to true'
    ], capture_output=True, timeout=10)
    time.sleep(0.5)

    # ---- 3. 截图 ----
    x = int(target_bounds.get("X", 0))
    y = int(target_bounds.get("Y", 0))
    w = int(target_bounds.get("Width", 0))
    h = int(target_bounds.get("Height", 0))

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(project_dir, "window_screenshot.png")

    subprocess.run(
        ["screencapture", "-R", f"{x},{y},{w},{h}", "-x", path],
        capture_output=True, timeout=10
    )
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return f"截图失败：无法截取 {target_name}"

    kb = os.path.getsize(path) / 1024

    # ---- 4. 调用 Gemini Vision 分析 ----
    try:
        analysis = _analyze_image(path, target_name, question)
        return (
            f"截图成功: {target_name} ({w}x{h}, {kb:.0f} KB)\n"
            f"分析结果:\n{analysis}"
        )
    except Exception as e:
        return (
            f"截图成功: {target_name} ({w}x{h}, {kb:.0f} KB)\n"
            f"自动分析失败: {e}\n"
            f"截图文件: {path}"
        )


def _analyze_image(image_path: str, window_title: str, question: str = "") -> str:
    """将图片发送给 Gemini 分析，返回文字描述。"""
    from google.genai import types
    from core.gemini_setup import get_gemini_client
    from core.config import MODEL_TYPE

    with open(image_path, "rb") as f:
        image_data = f.read()

    prompt = (
        f"请根据以下问题分析这张截图: \"{question}\"。"
        if question else
        f"请详细描述这张截图的内容。"
    )
    prompt += f" 窗口标题: {window_title}。用中文回复。"

    client = get_gemini_client()
    response = client.models.generate_content(
        model=MODEL_TYPE,
        contents=[
            types.Part.from_bytes(data=image_data, mime_type="image/png"),
            types.Part.from_text(text=prompt),
        ]
    )
    return response.text.strip() if response.text else "(Gemini 返回空)"
