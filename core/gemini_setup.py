#=======================================================================================
#.       core/gemini_setup.py — Gemini 客户端初始化与工具函数注册
#.       负责三件事：
#.         1. 单例化 Gemini 客户端创建（支持代理配置）
#.         2. 注册可供模型调用的工具函数列表（Function Calling）
#.         3. 安全过滤器设置（私聊模式关闭过滤以允许更自由的内容）
#.       被 bot/handlers.py 中的消息处理器调用。
#=======================================================================================

import logging

from google import genai
from google.genai import types

# -- 从 core/config.py 拉取 API 密钥和代理配置
from core.config import GEMINI_API_KEY, PROXY_URL
# -- 从 tools/ 模块导入所有可用工具函数，注册给 Gemini 调用
from tools.reminder import get_current_system_time, add_local_reminder, remove_local_reminder, update_reminder_priority, update_reminder_settings, fetch_local_reminders
from tools.schooldays import fetch_school_schedule
from tools.notice import group_reminder
from tools.search import web_search

logger = logging.getLogger(__name__)

#=======================================================================================
#.       Gemini 客户端单例
#.       通过 get_gemini_client() 获取，首次调用时初始化并缓存。
#.       若 PROXY_URL 非空，将代理参数注入 HTTP 选项，所有 API 请求走代理通道。
#=======================================================================================

_client = None


def get_gemini_client() -> genai.Client:
    #.
    #.       获取或初始化 Gemini 客户端单例。
    #.       若 core/config.py 中 PROXY_URL 非空，则所有请求经代理转发。
    #.
    global _client
    if _client is None:
        try:
            if PROXY_URL:
                http_options = types.HttpOptions(client_args={"proxy": PROXY_URL})
                _client = genai.Client(api_key=GEMINI_API_KEY, http_options=http_options)
                logger.info(f"Gemini 客户端初始化成功（使用代理: {PROXY_URL}）。")
            else:
                _client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Gemini 客户端初始化成功。")
        except Exception as e:
            logger.critical(f"Gemini 客户端初始化失败，程序退出: {e}")
            raise
    return _client


# -- tools_list → bot/handlers.py handle_message() / handle_reply() 中 premium 模式使用的工具集
#=======================================================================================
#.       tools_list — Premium 模式工具集（私聊专用）
#.       开放完整工具：系统时间、增删查提醒、优先级/提前提醒修改、
#.       课表查询、网页搜索。模型在生成回复时可自主决定调用这些函数获取实时数据。
#=======================================================================================
tools_list = [
    get_current_system_time,
    add_local_reminder,
    remove_local_reminder,
    update_reminder_priority,
    update_reminder_settings,
    fetch_local_reminders,
    fetch_school_schedule,
    web_search,
]

# -- toolsp_list → bot/handlers.py handle_message() / handle_reply() 中 normal 模式使用的工具集
#=======================================================================================
#.       toolsp_list — Normal 模式工具集（群聊专用）
#.       仅开放基础工具：系统时间、课表查询、网页搜索、群组备忘录。
#.       群聊场景下不开放个人提醒功能，避免跨用户数据泄露。
#=======================================================================================
toolsp_list = [
    get_current_system_time,
    fetch_school_schedule,
    web_search,
    group_reminder,
]

# -- safety_settings_off → bot/handlers.py handle_message() / handle_reply() 中 premium 模式使用
#=======================================================================================
#.       safety_settings_off — 安全过滤器关闭配置
#.       私聊 Premium 模式下将所有安全过滤类别设为 BLOCK_NONE，
#.       允许模型在私密场景下产生更自由的内容输出。
#.       群聊 Normal 模式下不使用此配置（保持默认安全级别）。
#=======================================================================================
safety_settings_off = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
