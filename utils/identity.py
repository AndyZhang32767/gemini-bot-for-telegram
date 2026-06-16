#=======================================================================================
#.       utils/identity.py — 群聊发言者身份标签
#.       为群聊消息构造发言者身份前缀，注入到发给 Gemini 的消息中，
#.       让模型能够区分不同发言者（Admin / 已知用户 / 陌生人）。
#.
#.       被 bot/handlers.py 的 handle_message() / handle_reply() / handle_file() 调用。
#.
#.       核心依赖：core/config.py 中的 ADMIN_ID 常量，用于识别 Bot 拥有者。
#=======================================================================================

# -- 从 core/config.py 获取管理员 user_id
from core.config import ADMIN_ID


#=============================================================
#.       build_identity_tag() — 构造发言者身份标签
#.
#.       参数：
#.         sender_id   — Telegram user_id
#.         sender_name — Telegram 显示名称（full_name）
#.         chat_type   — "private" 或 "group" / "supergroup"
#.
#.       返回规则：
#.         - 私聊 (private)              → 返回空字符串（无需标注）
#.         - 发送者是 ADMIN_ID           → "[发言者: Admin, user_id=...]"
#.         - 其他群聊成员                 → "[发言者: <name>, user_id=..., 非管理员]"
#.
#.       群聊中标注"非管理员"的目的是告诉 Gemini：此人不是 Bot 拥有者，
#.       不要将其误认为特权用户。
#=============================================================
def build_identity_tag(sender_id: int, sender_name: str, chat_type: str) -> str:
    if chat_type == "private":
        return ""
    if sender_id == ADMIN_ID:
        return f"[发言者: Admin, user_id={sender_id}]"
    return f"[发言者: {sender_name}, user_id={sender_id}, 非管理员]"


#=============================================================
#.       tag_message() — 将身份标签前缀附加到消息内容上
#.
#.       组合 build_identity_tag() 的结果和原始消息，
#.       形成 "[发言者: ...]\n<原始消息>" 的格式发给 Gemini。
#.       私聊返回原内容不变。
#=============================================================
def tag_message(contents: str, sender_id: int, sender_name: str, chat_type: str) -> str:
    tag = build_identity_tag(sender_id, sender_name, chat_type)
    if tag:
        return f"{tag}\n{contents}"
    return contents
