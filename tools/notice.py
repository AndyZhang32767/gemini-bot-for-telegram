#=======================================================================================
#.       tools/notice.py — 群组备忘录工具
#.       为群聊场景提供创建备忘录的功能。
#.       通过 tools/reminder.py 的 add_reminder() 实际写入系统提醒事项，
#.       在备忘录内容中附带群组 ID 以区分来源。
#.
#.       被 core/gemini_setup.py 注册为 toolsp_list 中的 group_reminder 工具函数，
#.       供 Gemini 在群聊 Normal 模式下调用。
#=======================================================================================

import datetime

# -- 调用 tools/reminder.py 的 add_reminder() 将备忘录写入 macOS 提醒事项
from tools.reminder import add_reminder


#=============================================================
#.       group_reminder() — 为群组创建备忘录
#.
#.       参数：
#.         chat_id      — Telegram 群组 ID，用于标识备忘录来源
#.         name         — 备忘录标题
#.         body         — 备忘录内容/描述（可选）
#.         due_date_str — 提醒时间，格式 'YYYY-MM-DD HH:MM:SS'，为空则使用当前时间
#.         priority     — 优先级 1-3（1=低, 2=中, 3=高）
#.
#.       返回：结果字符串（供 Gemini 组织语言告知用户）
#=============================================================
def group_reminder(chat_id: str, name: str, body: str = "", due_date_str: str = None, priority: int = 0):
    print(f"\n[Reminder] group_reminder: chat={chat_id} | {name} | due: {due_date_str}")

    try:
        # 如果没有指定时间，使用当前时间
        if due_date_str is None:
            due_date_obj = datetime.datetime.now()
        else:
            # 处理时间格式：Gemini 可能传入 'T' 分隔的 ISO 格式
            clean_date_str = due_date_str.replace('T', ' ')
            due_date_obj = datetime.datetime.strptime(clean_date_str, '%Y-%m-%d %H:%M:%S')

        # 在备忘录内容中添加群组来源标识，便于区分个人提醒和群组备忘录
        full_body = f"[群组ID: {chat_id}]\n{body}" if body else f"[群组ID: {chat_id}]"

        # 调用 reminder 模块的 add_reminder() — 通过 AppleScript 写入系统提醒事项
        result = add_reminder(name, body=full_body, due_date=due_date_obj, priority=priority)

        if result:
            return f"已记录群组备忘录：'{name}'，来自群组{chat_id}，提醒时间 {due_date_obj.strftime('%Y-%m-%d %H:%M:%S')}。"
        else:
            return f"群组备忘录创建失败，请检查权限设置。"

    except Exception as e:
        return f"创建群组备忘录时出错: {str(e)}"
