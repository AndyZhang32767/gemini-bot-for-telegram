#=======================================================================================
#.       bot/main.py — Bot 入口与组装
#.       负责三件事：
#.         1. create_application() — 构建 Telegram Application，注册消息/
#.            命令处理器和定时任务（同时供 TUI 模式复用）
#.         2. daily_morning_push() — 每日定时向 premium 用户推送课表
#.         3. main() — 命令行模式的阻塞式 polling 入口
#=======================================================================================

import datetime
import logging
import os
from zoneinfo import ZoneInfo

from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

# -- 从 bot/handlers.py 导入所有消息和命令处理器
from bot.handlers import start_command, class_command, clear_command, handle_message, handle_reply, handle_file
# -- 从 bot/session.py 导入会话持久化函数和运行时 sessions 字典
from bot.session import load_sessions, load_history, load_denied, persist_history, sessions
# -- 从 core/config.py 拉取 Bot Token、代理地址和版本号
from core.config import TELEGRAM_TOKEN, PROXY_URL, VERSION
# -- 从 core/logging_setup.py 获取日志初始化函数
from core.logging_setup import setup_logging
# -- 从 tools/schooldays.py 获取课表查询函数
from tools.schooldays import fetch_school_schedule

logger = logging.getLogger(__name__)


#=======================================================================================
#.       每日早间推送任务
#.       由 Application.job_queue 在每天 05:00 (Asia/Singapore) 触发。
#.       遍历 sessions 字典，找到所有 chk="T"（premium）用户，
#.       调用 fetch_school_schedule() 获取当日课表并逐一发送。
#=======================================================================================

async def daily_morning_push(context):
    logger.info("执行早间课表推送任务...")
    schedule_text = fetch_school_schedule()

    push_count = 0
    for cid, info in sessions.items():
        if info.get("chk") == "T":
            try:
                message = f"早上好，新的一天开始了，这是今天的课表：\n\n{schedule_text}"
                await context.bot.send_message(chat_id=cid, text=message)
                push_count += 1
                logger.info(f"课表推送成功 -> chat_id={cid}")
            except Exception as e:
                logger.error(f"课表推送失败 -> chat_id={cid}: {e}")

    logger.info(f"早间推送完成，共推送 {push_count} 个账户。")


#=======================================================================================
#.       create_application() — 构建并配置 Telegram Application
#.
#.       执行流程：
#.         1. 初始化日志系统（幂等）
#.         2. 将 PROXY_URL 写入环境变量（确保 httpx 所有请求走代理）
#.         3. 从本地 JSON 文件恢复 sessions / history / denied_ids
#.         4. 构建 Application 对象（有代理则注入 HTTPXRequest）
#.         5. 注册 Handler — 顺序很重要：
#.            a. REPLY + (TEXT|PHOTO) → handle_reply （回复消息，优先级最高）
#.            b. Document|PHOTO|VIDEO|AUDIO|VOICE → handle_file （文件/媒体）
#.            c. TEXT + 非命令 → handle_message （普通文字消息）
#.            d. /start → start_command
#.            e. /class → class_command
#.            f. /clear → clear_command
#.         6. 注册每日 05:00 SGT 的课表推送定时任务
#.
#.       返回配置完成但尚未启动的 Application 对象。
#=======================================================================================

def create_application() -> Application:
    # 1. 配置日志
    setup_logging()

    # 2. 设置代理环境变量（确保 httpx 所有请求都走代理）
    if PROXY_URL:
        os.environ["HTTP_PROXY"] = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL
        os.environ["ALL_PROXY"] = PROXY_URL
        logger.info(f"已设置代理环境变量: {PROXY_URL}")

    # 3. 从本地文件恢复上次的会话记录（sessions / history / denied_ids）
    load_sessions()
    load_history()
    load_denied()

    # 4. 构建 Application（如配置了代理则注入 HTTPXRequest 走代理通道）
    if PROXY_URL:
        request = HTTPXRequest(
            proxy=PROXY_URL,
            connect_timeout=15.0,
            read_timeout=30.0,
            write_timeout=15.0,
        )
        application = (
            Application.builder()
            .token(TELEGRAM_TOKEN)
            .request(request)
            .get_updates_request(request)
            .build()
        )
        logger.info(f"Telegram 使用代理: {PROXY_URL}")
    else:
        application = Application.builder().token(TELEGRAM_TOKEN).build()

    # 5. 注册 Handler（顺序很重要：reply 优先 → 文件/媒体 → 普通文字 → 命令）
    application.add_handler(MessageHandler(filters.REPLY & (filters.TEXT | filters.PHOTO), handle_reply))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE,
        handle_file
    ))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("class", class_command))
    application.add_handler(CommandHandler("clear", clear_command))

    # 6. 注册每日 05:00 SGT 课表推送任务
    application.job_queue.run_daily(
        daily_morning_push,
        time=datetime.time(hour=5, minute=0, second=0, tzinfo=ZoneInfo("Asia/Singapore"))
    )

    return application


#=======================================================================================
#.       Shutdown 回调 — 在 Bot 停止前将内存中的聊天历史持久化到 JSON 文件
#=======================================================================================

async def _save_history_on_shutdown(application):
    await persist_history()
    logger.info("历史记录已保存。")


#=======================================================================================
#.       main() — 命令行模式入口
#.       创建 Application → 注册 shutdown 回调 → 启动阻塞式 polling。
#.       该函数在 TUI 模式下不会被调用（TUI 使用 create_application() + 手动 start）。
#=======================================================================================

def main() -> None:
    application = create_application()
    application.add_shutdown_handler(_save_history_on_shutdown)
    logger.info(f"Bot {VERSION} 启动，开始轮询...")
    application.run_polling()


if __name__ == "__main__":
    main()
