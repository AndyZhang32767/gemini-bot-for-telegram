#=======================================================================================
#.       bot/session.py — 会话管理（授权、持久化、黑名单）
#.
#.       管理所有与用户会话相关的运行时状态和持久化：
#.         1. sessions 字典 — 内存中的用户授权信息 {chat_id: {mode, chk, ...}}
#.         2. save_history 字典 — 内存中的对话历史 {chat_id: [types.Content, ...]}
#.         3. denied_ids 集合 — 已被拒绝的用户黑名单
#.         4. 新用户授权 — get_chat_session() 通过 TUI 弹窗或 console input 获取授权
#.         5. 持久化 — 将以上数据读写到 data/ 目录下的 JSON 文件
#.
#.       被 bot/main.py 加载/保存，被 bot/handlers.py 每条消息调用。
#=======================================================================================

import asyncio
import json
import logging
import os

# -- 从 core/config.py 拉取会话文件路径和两种 System Prompt
from core.config import SESSION_FILE, PRIVATE_INSTRUCTION, PUBLIC_INSTRUCTION

logger = logging.getLogger(__name__)

#=======================================================================================
#.       持久化文件路径
#.       HISTORY_FILE — 对话历史 JSON（只保存文本部分，跳过二进制 blob）
#.       DENIED_FILE  — 黑名单 JSON
#=======================================================================================
HISTORY_FILE = os.path.join(os.path.dirname(SESSION_FILE), "history.json")
DENIED_FILE  = os.path.join(os.path.dirname(SESSION_FILE), "denied.json")

#=======================================================================================
#.       模块级运行时状态（内存中）
#.
#.       sessions     — {chat_id: {"mode": <System Prompt 字符串>,
#.                                  "chk": "T"(premium) / "F"(normal),
#.                                  "session": None,
#.                                  "creation": "false"}}
#.       save_history — {chat_id: [types.Content, ...]}  对话历史（Gemini 格式）
#.       denied_ids   — {int, ...}  已被拒绝授权的用户 chat_id 集合
#=======================================================================================
sessions = {}
save_history = {}
denied_ids = set()


#=======================================================================================
#.       Sessions 持久化 — 读写 sessions 字典到 JSON 文件
#=======================================================================================

#=============================================================
#.       将内存中的 sessions 字典异步写入 JSON 文件
#.       使用 asyncio.to_thread 避免阻塞事件循环
#=============================================================
async def persist_sessions():
    def _save():
        with open(SESSION_FILE, 'w') as f:
            json.dump(sessions, f)
    await asyncio.to_thread(_save)


#=============================================================
#.       从 JSON 文件恢复 sessions 字典到内存
#.       JSON 的 key 是字符串，恢复时转为 int
#=============================================================
def load_sessions() -> None:
    sessions.clear()
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                sessions[int(k)] = v
            logger.info(f"已恢复 {len(sessions)} 个历史会话。")
        except Exception as e:
            logger.error(f"加载 sessions 失败: {e}")
            sessions.clear()


#=======================================================================================
#.       黑名单持久化 — 读写 denied_ids 集合到 JSON 文件
#=======================================================================================

#=============================================================
#.       将内存中的 denied_ids 集合异步写入 JSON 文件
#=============================================================
async def persist_denied():
    def _save():
        with open(DENIED_FILE, 'w') as f:
            json.dump(sorted(denied_ids), f)
    await asyncio.to_thread(_save)


#=============================================================
#.       从 JSON 文件恢复 denied_ids 集合到内存
#=============================================================
def load_denied() -> None:
    denied_ids.clear()
    if os.path.exists(DENIED_FILE):
        try:
            with open(DENIED_FILE, 'r') as f:
                for uid in json.load(f):
                    denied_ids.add(int(uid))
            logger.info(f"已恢复 {len(denied_ids)} 个黑名单。")
        except Exception as e:
            logger.error(f"加载黑名单失败: {e}")
            denied_ids.clear()


#=======================================================================================
#.       History 持久化 — 读写对话历史
#.       只保存文本部分（types.Part.text），跳过二进制 blob（无法 JSON 序列化）。
#.       保存格式：{chat_id: [{role: "user"/"model", parts: [{text: "..."}]}, ...]}
#=======================================================================================

#=============================================================
#.       将内存中的 save_history 异步写入 JSON 文件
#.       遍历每个 chat 的 Content 列表，提取 role 和文本 parts，
#.       跳过二进制 blob（图片/文件等二进制数据不持久化）
#=============================================================
async def persist_history():
    def _save():
        data = {}
        for chat_id, contents in save_history.items():
            rows = []
            for c in contents:
                row = {"role": getattr(c, "role", "user"), "parts": []}
                if hasattr(c, "parts"):
                    for p in c.parts:
                        if hasattr(p, "text") and p.text is not None:
                            row["parts"].append({"text": p.text})
                        # 跳过二进制 blob（无法 JSON 序列化）
                rows.append(row)
            data[str(chat_id)] = rows
        with open(HISTORY_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
    await asyncio.to_thread(_save)


#=============================================================
#.       从 JSON 文件恢复 save_history 到内存（仅文本部分）
#.       将 JSON 中的 {role, parts: [{text}]} 结构转回 google.genai.types.Content 对象
#=============================================================
def load_history() -> None:
    from google.genai import types

    save_history.clear()
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
            for chat_id_str, rows in data.items():
                contents = []
                for row in rows:
                    parts = []
                    for p in row.get("parts", []):
                        if "text" in p:
                            parts.append(types.Part.from_text(text=p["text"]))
                    if parts:
                        contents.append(types.Content(role=row["role"], parts=parts))
                save_history[int(chat_id_str)] = contents
            logger.info(f"已恢复 {len(save_history)} 个会话的历史记录。")
        except Exception as e:
            logger.error(f"加载 history 失败: {e}")
            save_history.clear()


#=======================================================================================
#.       会话授权 — 新用户接入流程
#=======================================================================================

# -- _auth_callback → tui/app.py on_mount() 通过 set_auth_callback() 设置 TUI 弹窗回调
#=============================================================
#.       _auth_callback — TUI 模式下的新用户授权回调
#.       当 get_chat_session() 遇到新用户时，调用此回调弹出授权弹窗。
#.       若为 None 则降级为 console input 模式。
#=============================================================
_auth_callback = None


def set_auth_callback(cb):
    #.       TUI 调用此函数注入弹窗授权回调，替代 console input。
    global _auth_callback
    _auth_callback = cb


#=============================================================
#.       get_chat_session() — 获取或创建用户会话（授权入口）
#.
#.       调用时机：每次收到用户消息时（bot/handlers.py 中的各个 handler）。
#.
#.       逻辑分支：
#.         1. chat_id 已在 sessions 中 → 直接返回已授权会话
#.         2. chat_id 在 denied_ids 中 → 返回 None（黑名单拦截）
#.         3. 新用户 → 通过 TUI 弹窗（_auth_callback）或 console input 获取管理员选择：
#.            - "pr" → 分配 PRIVATE_INSTRUCTION，chk="T"（premium）→ 写入 sessions
#.            - "pb" → 分配 PUBLIC_INSTRUCTION，chk="F"（normal）→ 写入 sessions
#.            - 其他 → 加入 denied_ids，返回 None
#.
#.       返回：sessions[chat_id] dict 或 None（被拒绝）
#=============================================================
async def get_chat_session(chat_id: int, chat_name: str, chat_type: str):
    # 1. 已授权用户直接返回
    if chat_id in sessions:
        return sessions[chat_id]

    # 2. 黑名单用户直接拒绝
    if chat_id in denied_ids:
        logger.info(f"拦截已拒绝 ID: {chat_id} ({chat_name})")
        return None

    # 3. 新用户 — 输出日志等待管理员决定
    logger.info("=" * 20)
    logger.info(f"[新请求] chat_id={chat_id} | 名称={chat_name} | 类型={chat_type}")
    logger.info("=" * 20)

    try:
        if _auth_callback is not None:
            # TUI 模式：通过弹窗获取管理员选择（由 tui/app.py 注入）
            choice = await _auth_callback(chat_id, chat_name, chat_type)
        else:
            # 命令行模式：阻塞等待 console input
            choice = await asyncio.to_thread(input, "[pr=私聊 / pb=群聊 / n=拒绝]: ")
            choice = choice.lower().strip()

        if choice == 'pr':
            # Premium 模式：分配私聊 System Prompt，开放全部工具
            selected_instruction = PRIVATE_INSTRUCTION
            mode_label = "私聊(premium)"
            chk = "T"
        elif choice == 'pb':
            # Normal 模式：分配群聊 System Prompt，限制工具集
            selected_instruction = PUBLIC_INSTRUCTION
            mode_label = "群聊(普通)"
            chk = "F"
        else:
            # 拒绝：加入黑名单并持久化
            logger.warning(f"[拒绝] chat_id={chat_id} ({chat_name})")
            denied_ids.add(chat_id)
            await persist_denied()
            return None

        # 创建会话条目并持久化
        sessions[chat_id] = {
            "session":  None,
            "mode":     selected_instruction,
            "creation": "false",
            "chk":      chk,
        }
        save_history[chat_id] = []
        await persist_sessions()
        logger.info(f"[授权] chat_id={chat_id} ({chat_name}) -> 模式={mode_label}")
        return sessions[chat_id]

    except Exception as e:
        logger.error(f"审核过程异常: {e}")
        return None


#=============================================================
#.       clear_chat_history() — 清除指定 chat 的对话历史
#.       将 save_history[chat_id] 重置为空列表并立即持久化。
#.       被 bot/handlers.py 的 /clear 命令调用。
#=============================================================
async def clear_chat_history(chat_id: int) -> None:
    save_history[chat_id] = []
    await persist_history()
    logger.info(f"[清除] chat_id={chat_id} 的对话历史已清除")
