#=======================================================================================
#.       utils/helpers.py — 通用辅助函数
#.       提供两个被 bot/handlers.py 频繁调用的工具函数：
#.         trim_history() — 对话历史裁剪（控制发送给 Gemini 的上下文长度）
#.         typing_loop()  — Telegram "正在输入…" 动画循环
#=======================================================================================

import asyncio
import logging

logger = logging.getLogger(__name__)


#=============================================================
#.       trim_history() — 对话历史裁剪
#.
#.       当历史记录超过 max_len 条时，仅保留最新的 keep 条。
#.       目的是控制发送给 Gemini 的上下文长度，避免：
#.         - Token 消耗过大
#.         - 上下文窗口溢出
#.         - 响应速度变慢
#.
#.       被 bot/handlers.py 中每条消息处理完后调用。
#.
#.       参数：
#.         history — types.Content 列表
#.         max_len — 触发裁剪的阈值（默认 20）
#.         keep    — 裁剪后保留的条数（默认 18）
#.       返回：裁剪后的列表（不修改原列表）
#=============================================================
def trim_history(history: list, max_len: int = 20, keep: int = 18) -> list:
    if len(history) > max_len:
        logger.debug(f"历史裁剪: {len(history)} -> {keep} 条")
        return history[-keep:]
    return history


#=============================================================
#.       typing_loop() — Telegram "正在输入…" 动画循环
#.
#.       在等待 Gemini API 响应期间，持续向指定 chat 发送 typing 状态。
#.       Telegram 的 typing action 仅持续约 5 秒，所以每 4 秒续一次。
#.
#.       用法（在 bot/handlers.py 中）：
#.         stop = asyncio.Event()
#.         task = asyncio.create_task(typing_loop(context, chat_id, stop))
#.         try:
#.             response = await call_gemini(...)
#.         finally:
#.             stop.set()
#.             await task
#.
#.       参数：
#.         context    — PTB ContextTypes.DEFAULT_TYPE
#.         chat_id    — 目标聊天 ID
#.         stop_event — asyncio.Event，set 后停止循环
#=============================================================
async def typing_loop(context, chat_id: int, stop_event: asyncio.Event):
    try:
        while not stop_event.is_set():
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
    except Exception as e:
        logger.debug(f"打字动画意外停止: {e}")
