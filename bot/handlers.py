#=======================================================================================
#.       bot/handlers.py — Telegram 消息与命令处理器
#.
#.       处理所有入站消息的核心模块，包含六类处理器：
#.         1. /start 命令 — 发送随机欢迎语
#.         2. /class 命令 — 查询当日课表（仅限 premium 用户）
#.         3. /clear 命令 — 清除当前会话的对话历史
#.         4. handle_message — 处理普通文字消息（私聊直接触发，群聊需 @bot）
#.         5. handle_reply — 处理回复消息（支持多模态：图片/文件/音视频，
#.            含 Office→PDF 自动转换）
#.         6. handle_file — 处理文件/媒体消息（鉴权+记录，实际处理走 handle_reply）
#.
#.       核心流程：判断触发条件 → 授权检查 → 构建上下文 → 调用 Gemini → 回复。
#=======================================================================================

import asyncio
import logging
import os
import random
import re

from google.genai import types
from telegram import Update
from telegram.ext import ContextTypes

# -- 从 bot/session.py 获取会话运行时状态和授权函数
from bot.session import sessions, save_history, get_chat_session
# -- 从 core/config.py 获取当前使用的模型类型
from core.config import MODEL_TYPE
# -- 从 core/gemini_setup.py 获取 Gemini 客户端和工具配置
from core.gemini_setup import get_gemini_client, tools_list, toolsp_list, safety_settings_off
# -- 从 utils/identity.py 获取群聊发言者身份标签工具
from utils.identity import build_identity_tag, tag_message
# -- 从 utils/helpers.py 获取历史记录裁剪和 typing 动画工具
from utils.helpers import trim_history, typing_loop
# -- 从 tools/schooldays.py 获取课表查询函数（供 /class 命令使用）
from tools.schooldays import fetch_school_schedule

logger = logging.getLogger(__name__)

#=============================================================
#.       Bot @username 的正则匹配（备用，当前使用 entity 方式检测）
#=============================================================
_pattern = re.compile(r'^[@username]\s*(.*)', re.DOTALL)


#=======================================================================================
#.       命令处理器
#=======================================================================================

#=============================================================
#.       /start 命令处理器
#.       发送随机欢迎语。适用于任何用户。
#=============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    replies = ["你好！", "嗨，有什么可以帮你的？", "在的，请说。"]
    reply = random.choice(replies)
    logger.info(f"/start 来自 chat_id={update.effective_chat.id}")
    await update.message.reply_text(reply)


#=============================================================
#.       /class 命令处理器
#.       查询当日课表。仅 chk="T"（premium）用户可用。
#.       调用 tools/schooldays.py 的 fetch_school_schedule() 获取并格式化课表。
#=============================================================
async def class_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    auth_info = sessions.get(chat_id)

    if not auth_info or auth_info.get("chk") != "T":
        logger.warning(f"/class 被非授权用户调用: chat_id={chat_id}")
        await update.message.reply_text("抱歉，此功能仅限管理员使用。")
        return

    logger.info(f"/class 查询课表: chat_id={chat_id}")
    schedule = fetch_school_schedule()
    await update.message.reply_text(schedule)


#=============================================================
#.       /clear 命令处理器
#.       清除当前会话的对话历史（save_history[chat_id] 重置为空）。
#.       适用于任何已授权用户（premium 和 normal 均可使用）。
#=============================================================
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    auth_info = sessions.get(chat_id)

    if auth_info is None:
        logger.warning(f"/clear 被未授权用户调用: chat_id={chat_id}")
        await update.message.reply_text("抱歉，你还没有获得使用权限哦。")
        return

    logger.info(f"/clear 清除历史: chat_id={chat_id}")
    from bot.session import clear_chat_history
    await clear_chat_history(chat_id)
    await update.message.reply_text("对话历史已清除，让我们重新开始吧。")


#=======================================================================================
#.       消息处理器：普通文字消息
#=======================================================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #.
    #.       处理所有非命令的文字消息。
    #.
    #.       触发逻辑：
    #.         - 私聊 (chat_type == "private")：所有消息立即触发 Gemini 生成回复
    #.         - 群聊：检测消息中是否有 @bot 的 mention entity
    #.           · 有 → 去掉 @bot 部分，触发 Gemini 生成回复
    #.           · 无 → 静默写入 history（供后续上下文参考），不触发回复
    #.
    #.       处理流程：
    #.         1. 提取 chat_id / chat_name / chat_type / sender 信息
    #.         2. 判断是否触发（私聊自动触发，群聊检测 @mention）
    #.         3. 调用 get_chat_session() 获取/创建授权会话（新用户走 TUI 弹窗/console input）
    #.         4. 黑名单用户直接拦截
    #.         5. 群聊消息附加身份标签（让 Gemini 知道谁在说话）
    #.         6. 未触发 → 写入 history 后返回
    #.         7. 已触发 → 写入 history → 调用 Gemini API → 回复用户 → 将回复写入 history
    #.
    # 1. 获取聊天基本信息
    chat_obj = update.effective_chat
    chat_id = chat_obj.id
    chat_name = chat_obj.full_name or chat_obj.title
    chat_type = chat_obj.type

    # 获取真实发言者信息（群聊中 chat_id 是群组 ID，sender_id 才是个人 ID）
    sender = update.effective_user
    sender_id = sender.id if sender else None
    sender_name = (sender.full_name if sender else None) or chat_name

    contents = update.message.text
    if not contents:
        return

    # 2. 判断是否触发回复：私聊直接触发，群聊检测 @mention entity
    is_triggered = False
    if chat_type == "private":
        is_triggered = True
    else:
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == 'mention':
                    mention_text = update.message.text[entity.offset:entity.offset + entity.length]
                    if mention_text == '@' + context.bot.username:
                        # 去掉 @bot 部分，只保留实际消息内容
                        contents = update.message.text[entity.offset + entity.length:].strip()
                        is_triggered = True
                        break
        if not contents:
            return

    logger.info(f"[消息] {'触发' if is_triggered else '监听'} | chat_id={chat_id} | sender={sender_name}(uid={sender_id}) | 内容={contents[:50]}")

    # 3. 获取/初始化会话 — get_chat_session() 位于 bot/session.py
    #    首次访问的用户会触发 TUI 弹窗（或 console input）进行授权选择
    auth_info = await get_chat_session(chat_id, chat_name, chat_type)
    if auth_info is None:
        logger.info(f"[拦截] 黑名单 chat_id={chat_id}")
        if is_triggered:
            await update.message.reply_text("抱歉，你没有使用权限。")
        return

    # 4. 从会话中提取 premium 状态、System Prompt 和历史记录
    premium = auth_info.get("chk") == "T"
    mode = auth_info["mode"]          # mode 即 System Prompt（PRIVATE_INSTRUCTION 或 PUBLIC_INSTRUCTION）
    history = save_history.get(chat_id, [])

    # 群聊消息附加身份标签，确保 Gemini 能正确识别每位发言者身份
    tagged_contents = tag_message(contents, sender_id, sender_name, chat_type)

    # 5. 未触发：静默记录到 history（供后续 @bot 触发时作为上下文参考）
    if not is_triggered:
        history.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=tagged_contents)]
        ))
        history = trim_history(history)
        save_history[chat_id] = history
        logger.debug(f"[监听] 写入 history, 当前长度={len(history)}")
        return

    # 6. 已触发：写入用户消息到 history，裁剪后准备调用 Gemini
    history.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=tagged_contents)]
    ))
    history = trim_history(history)

    try:
        logger.info(f"[生成] chat_id={chat_id} | 模式={'premium' if premium else '普通'} | history={len(history)} | 模型={MODEL_TYPE}")

        # 获取 Gemini 客户端单例（来自 core/gemini_setup.py）
        client = get_gemini_client()

        # 启动 typing 循环 — 在等待 Gemini 响应期间持续向 Telegram 发送 "typing..." 状态
        # typing_loop() 位于 utils/helpers.py，每 4 秒续一次（Telegram typing 持续约 5 秒）
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(typing_loop(context, chat_id, stop_typing))

        try:
            if premium:
                # Premium 模式：完整 System Instruction + 全部工具 + 安全过滤器关闭
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_TYPE,
                    contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=mode,
                        safety_settings=safety_settings_off,
                        tools=tools_list,
                    )
                )
            else:
                # Normal 模式：System Instruction + 受限工具集 + 默认安全设置
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_TYPE,
                    contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=mode,
                        tools=toolsp_list,
                    )
                )
        finally:
            # 无论 API 调用成功或异常，都必须停止 typing 动画
            stop_typing.set()
            try:
                await asyncio.wait_for(typing_task, timeout=1.0)
            except Exception:
                pass

        # 7. 处理 Gemini 响应：成功则回复用户并写入 history
        if response and response.text:
            reply = response.text
            history.append(types.Content(
                role="model",
                parts=[types.Part.from_text(text=reply)]
            ))
            save_history[chat_id] = history
            logger.info(f"[回复] chat_id={chat_id} | 长度={len(reply)} | history={len(history)}")
            await update.message.reply_text(reply)
        else:
            save_history[chat_id] = history
            logger.warning(f"[生成] chat_id={chat_id} | response 无文本内容")
            await update.message.reply_text("抱歉，请再说一遍。")

    except Exception as e:
        # 出错也保存 history，避免丢失已记录的上下文
        save_history[chat_id] = history
        logger.exception(f"[错误] 生成回复失败 chat_id={chat_id}: {e}")
        await update.message.reply_text(f"出错了：{e}")


#=======================================================================================
#.       消息处理器：回复消息（含图片/文件等多模态内容）
#=======================================================================================

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #.
    #.       处理 Telegram reply 类消息——用户引用某条消息并附加文字/图片进行回复。
    #.
    #.       支持的多模态类型：
    #.         - 图片 (photo) — 下载后以 image/jpeg 传给 Gemini
    #.         - 文档 (document) — 含 Office 格式（.docx/.pptx/.xlsx 等）自动 LibreOffice → PDF 转换
    #.         - 视频 (video)
    #.         - 音频 (audio)
    #.         - 语音 (voice)
    #.         - 纯文字 (text) — 直接将被引用文字传给 Gemini
    #.
    #.       触发逻辑与 handle_message 相同：私聊自动触发，群聊需 @bot。
    #.       未触发的 reply 静默写入 history（附带被引用内容的摘要）。
    #.
    #.       处理流程：
    #.         1. 提取 chat/sender 信息 + 判断触发
    #.         2. 授权检查
    #.         3. 未触发 → 将被引用内容摘要写入 history
    #.         4. 已触发 → 下载被引用的媒体文件 → (可选)Office→PDF 转换 → 构造 Gemini 多模态请求
    #.         5. 调用 Gemini API → 回复用户 → 写入 history
    #.
    # 1. 提取基本信息
    chat_obj = update.effective_chat
    chat_id = chat_obj.id
    chat_name = chat_obj.full_name or chat_obj.title
    chat_type = chat_obj.type

    # 获取真实发言者信息
    sender = update.effective_user
    sender_id = sender.id if sender else None
    sender_name = (sender.full_name if sender else None) or chat_name

    contents = update.message.text

    # 2. 判断触发条件 — 私聊直接触发，群聊检测 @mention
    is_triggered = False
    if chat_type == "private":
        is_triggered = True
    else:
        if update.message.entities:
            for entity in update.message.entities:
                if entity.type == 'mention':
                    mention_text = update.message.text[entity.offset:entity.offset + entity.length]
                    if mention_text == '@' + context.bot.username:
                        contents = update.message.text[entity.offset + entity.length:].strip()
                        is_triggered = True
                        break
        if not contents:
            return

    if not contents:
        return

    message = update.message
    replied_content = message.reply_to_message
    user_instruction = message.text or "请评价或解释一下"

    logger.info(f"[回复消息] {'触发' if is_triggered else '监听'} | chat_id={chat_id} | sender={sender_name}(uid={sender_id})")

    # 3. 授权检查 — get_chat_session() 位于 bot/session.py
    auth_info = await get_chat_session(chat_id, chat_name, chat_type)
    if auth_info is None:
        logger.info(f"[拦截] 黑名单 chat_id={chat_id}")
        if is_triggered:
            await update.message.reply_text("抱歉，你没有使用权限。")
        return

    mode = auth_info["mode"]
    history = save_history.get(chat_id, [])
    logger.debug(f"[回复消息] history 长度={len(history)}")

    # 4. 未触发：静默写入 history（附带被回复内容的摘要，不存二进制）
    if not is_triggered:
        rep_cont = (
            getattr(replied_content, 'text', None) or
            getattr(replied_content, 'caption', None) or
            "[媒体/表情]"
        )
        identity_tag = build_identity_tag(sender_id, sender_name, chat_type) or sender_name
        history.append(types.Content(
            role="user",
            parts=[types.Part.from_text(
                text=f"[{identity_tag}]: {contents} (回复自: \"{rep_cont}\")"
            )]
        ))
        history = trim_history(history)
        save_history[chat_id] = history
        logger.debug(f"[监听回复] 写入 history, 当前长度={len(history)}")
        return

    # 5. 已触发：构造发给 Gemini 的多模态内容列表
    gemini_contents = []

    try:
        file_bytes = None
        file_mime = None
        file_name = ""          # 原始文件名（用于 Office 格式检测）
        file_type_label = ""

        # 按优先级检测被回复消息的媒体类型，下载文件内容到内存
        if replied_content.photo:
            photo_file = await context.bot.get_file(replied_content.photo[-1].file_id)
            file_bytes = await photo_file.download_as_bytearray()
            file_mime = "image/jpeg"
            file_name = "photo.jpg"
            file_type_label = "图片"
            if replied_content.caption:
                gemini_contents.append(f"原图附带的文字: {replied_content.caption}")
        elif replied_content.document:
            doc = replied_content.document
            doc_file = await context.bot.get_file(doc.file_id)
            file_bytes = await doc_file.download_as_bytearray()
            file_mime = doc.mime_type or "application/octet-stream"
            file_name = doc.file_name or ""
            file_type_label = f"文件({file_name}, {file_mime})"
            if replied_content.caption:
                gemini_contents.append(f"原文件附带的文字: {replied_content.caption}")
        elif replied_content.video:
            video = replied_content.video
            video_file = await context.bot.get_file(video.file_id)
            file_bytes = await video_file.download_as_bytearray()
            file_mime = video.mime_type or "video/mp4"
            file_name = video.file_name or "video.mp4"
            file_type_label = "视频"
            if replied_content.caption:
                gemini_contents.append(f"原视频附带的文字: {replied_content.caption}")
        elif replied_content.audio:
            audio = replied_content.audio
            audio_file = await context.bot.get_file(audio.file_id)
            file_bytes = await audio_file.download_as_bytearray()
            file_mime = audio.mime_type or "audio/mpeg"
            file_name = audio.file_name or "audio.mp3"
            file_type_label = "音频"
            if replied_content.caption:
                gemini_contents.append(f"原音频附带的文字: {replied_content.caption}")
        elif replied_content.voice:
            voice = replied_content.voice
            voice_file = await context.bot.get_file(voice.file_id)
            file_bytes = await voice_file.download_as_bytearray()
            file_mime = voice.mime_type or "audio/ogg"
            file_name = "voice.ogg"
            file_type_label = "语音"
        elif replied_content.text:
            gemini_contents.append(f"被引用的文字：\n{replied_content.text}")

        if file_bytes:
            logger.info(f"[回复文件] 收到 {file_type_label} | {len(file_bytes)}B")

            # 检查文件附件功能开关 — flag() 来自 tui/feature_flags.py
            from tui.feature_flags import flag
            if not flag("file_attachment"):
                await message.reply_text("文件附件功能已关闭，请在 TUI 侧边栏开启「文件附件支持」。")
                return

            # Office 文档 → PDF 自动转换（.doc/.docx/.ppt/.pptx/.xls/.xlsx）
            # convert_to_pdf_bytes() 位于 tools/doc_converter.py，调用 LibreOffice headless
            from tools.doc_converter import convert_to_pdf_bytes
            office_exts = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
            ext = os.path.splitext(file_name)[1].lower()
            if flag("office_to_pdf") and ext in office_exts:
                logger.info(f"[回复→PDF] 检测到 Office 格式 ({ext})，开始转换: {file_name}")
                pdf_bytes = await asyncio.to_thread(convert_to_pdf_bytes, bytes(file_bytes), file_name)
                if pdf_bytes:
                    logger.info(f"[回复→PDF] 转换完成: {file_name} ({len(file_bytes)}B) → PDF ({len(pdf_bytes)}B)")
                    file_bytes = pdf_bytes
                    file_mime = "application/pdf"
                else:
                    logger.error(f"[回复→PDF] 转换失败: {file_name}")
                    await message.reply_text("Office 文档转换失败，请确保已安装 LibreOffice。")
                    return

            # 将文件作为 Gemini 多模态 Part 追加到内容列表
            gemini_contents.append(types.Part.from_bytes(data=bytes(file_bytes), mime_type=file_mime))
            logger.info(f"[回复文件] → Gemini | {file_mime} | {len(file_bytes)}B")

        if not gemini_contents:
            await message.reply_text("抱歉，我目前只能评论图片、文件、音视频或文字回复哦！")
            return

        gemini_contents.append(f"用户指令：{user_instruction}")

        # 6. 写入用户操作到 history
        history.append(types.Content(role="user", parts=[types.Part(text=f"[reply] {user_instruction}")]))
        history = trim_history(history)
        sessions[chat_id]["history"] = history

        premium = auth_info.get("chk") == "T"
        logger.info(f"[回复生成] chat_id={chat_id} | 模式={'premium' if premium else '普通'} | 模型={MODEL_TYPE}")

        client = get_gemini_client()

        # 启动 typing 循环
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(typing_loop(context, chat_id, stop_typing))

        try:
            if premium:
                # Premium 模式：完整工具集 + 自动函数调用开启 + 安全过滤器关闭
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_TYPE,
                    contents=gemini_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=mode,
                        safety_settings=safety_settings_off,
                        tools=tools_list,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False),
                    )
                )
            else:
                # Normal 模式：仅 System Instruction，无工具
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_TYPE,
                    contents=gemini_contents,
                    config=types.GenerateContentConfig(system_instruction=mode),
                )
        finally:
            stop_typing.set()
            try:
                await asyncio.wait_for(typing_task, timeout=1.0)
            except Exception:
                pass

        await message.reply_text(response.text)

        # 7. 将本次交互写回 history（用户消息 + 模型回复各一条）
        existing_history = save_history.get(chat_id, [])
        existing_history.append(types.Content(role="user",  parts=[types.Part(text=contents)]))
        existing_history.append(types.Content(role="model", parts=[types.Part(text=response.text or "")]))
        existing_history = trim_history(existing_history)
        save_history[chat_id] = existing_history
        logger.info(f"[回复生成] 完成 chat_id={chat_id} | history={len(existing_history)}")

    except Exception as e:
        logger.exception(f"[错误] 回复处理失败 chat_id={chat_id}: {e}")
        await message.reply_text(f"出错了：{str(e)}")


#=======================================================================================
#.       消息处理器：文件 & 媒体
#=======================================================================================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #.
    #.       处理文件/媒体消息（文档、图片、音频、视频、语音）。
    #.
    #.       触发逻辑：
    #.         - 私聊：所有文件直接触发
    #.         - 群聊：需 @bot（mention entity 或 caption 中包含 @username）
    #.
    #.       当前实现：仅做鉴权和记录。实际的多模态文件处理走 handle_reply() 的 reply 流程。
    #.
    #.       处理流程：
    #.         1. 提取文件信息（file_id / mime_type / file_name / file_size / caption）
    #.         2. 判断触发（私聊 / @mention / caption 含 @bot）
    #.         3. 授权检查
    #.         4. 未触发 → 静默记录文件名到 history
    #.         5. 已触发 → 检查文件附件开关 → 当前直接忽略（文件处理在 handle_reply 中完成）
    #.
    # 1. 提取基本信息
    chat_obj = update.effective_chat
    chat_id = chat_obj.id
    chat_name = chat_obj.full_name or chat_obj.title
    chat_type = chat_obj.type

    sender = update.effective_user
    sender_id = sender.id if sender else None
    sender_name = (sender.full_name if sender else None) or chat_name

    message = update.message
    if not message:
        return

    # 2. 提取文件信息：按消息中的媒体类型分别获取元数据
    file_id = None
    mime_type = None
    file_name = None
    file_size = 0
    caption = message.caption or ""

    if message.document:
        doc = message.document
        file_id = doc.file_id
        mime_type = doc.mime_type or "application/octet-stream"
        file_name = doc.file_name or "file"
        file_size = doc.file_size or 0
    elif message.photo:
        photo = message.photo[-1]  # 取最高分辨率
        file_id = photo.file_id
        mime_type = "image/jpeg"
        file_name = "photo.jpg"
        file_size = photo.file_size or 0
    elif message.video:
        video = message.video
        file_id = video.file_id
        mime_type = video.mime_type or "video/mp4"
        file_name = video.file_name or "video.mp4"
        file_size = video.file_size or 0
    elif message.audio:
        audio = message.audio
        file_id = audio.file_id
        mime_type = audio.mime_type or "audio/mpeg"
        file_name = audio.file_name or "audio.mp3"
        file_size = audio.file_size or 0
    elif message.voice:
        voice = message.voice
        file_id = voice.file_id
        mime_type = voice.mime_type or "audio/ogg"
        file_name = "voice.ogg"
        file_size = voice.file_size or 0
    else:
        return

    # 3. 判断触发 — 私聊直接触发；群聊检测 @mention 或 caption 中 @bot
    is_triggered = chat_type == "private"
    if not is_triggered:
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mention = message.text[entity.offset:entity.offset + entity.length] if message.text else ""
                    if mention == "@" + context.bot.username:
                        is_triggered = True
                        break
        # 群聊中如果 caption 包含 @bot 也算触发
        if not is_triggered and message.caption:
            if f"@{context.bot.username}" in message.caption:
                is_triggered = True
                caption = message.caption.replace(f"@{context.bot.username}", "").strip()

    logger.info(f"[文件] {'触发' if is_triggered else '监听'} | chat_id={chat_id} | {file_name} ({mime_type}, {file_size}B)")

    # 4. 授权检查 — get_chat_session() 位于 bot/session.py
    auth_info = await get_chat_session(chat_id, chat_name, chat_type)
    if auth_info is None:
        if is_triggered:
            await message.reply_text("抱歉，你没有使用权限。")
        return

    # 5. 未触发：静默记录到 history（仅记录文件名，不存储二进制数据）
    if not is_triggered:
        history = save_history.get(chat_id, [])
        identity_tag = build_identity_tag(sender_id, sender_name, chat_type) or sender_name
        history.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"[{identity_tag}]: [文件: {file_name}] {caption}")]
        ))
        history = trim_history(history)
        save_history[chat_id] = history
        return

    # 6. 检查文件附件功能开关 — flag() 来自 tui/feature_flags.py
    from tui.feature_flags import flag
    if not flag("file_attachment"):
        await message.reply_text("文件附件功能已关闭，请在 TUI 侧边栏开启「文件附件支持」。")
        return

    # 7. 已触发：当前实现不做处理（文件的实际多模态处理在 handle_reply 中完成）
    logger.info(f"[文件] 已忽略 chat_id={chat_id} | {file_name}")
