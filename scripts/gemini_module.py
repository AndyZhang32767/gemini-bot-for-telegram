#=======================================================================================
#.       scripts/gemini_module.py — Gemini 提醒解析模块（实验性/备用）
#.       使用 Gemini API 从自然语言消息中提取提醒信息（标题、描述、日期），
#.       然后调用 tools/reminder.py 的 add_reminder() 写入系统提醒事项。
#.
#.       当前主流程中，Gemini 通过 Function Calling 直接调用
#.       add_local_reminder() 等函数，而不是通过此模块的 JSON 解析方式。
#.       本模块保留作为替代方案参考。
#=======================================================================================

import json
import datetime

# -- 调用 tools/reminder.py 的 add_reminder()
from tools.reminder import add_reminder

#=============================================================
#.       add_local_reminder() — 用 Gemini 解析消息并添加提醒
#.
#.       参数：
#.         message    — 用户的自然语言消息
#.         client     — Gemini 客户端实例
#.         model_type — 模型类型字符串
#.
#.       流程：
#.         1. 构造 prompt 要求 Gemini 返回结构化 JSON
#.         2. 调用 Gemini API
#.         3. 解析 JSON 提取 name / body / due_date
#.         4. 调用 add_reminder() 写入系统
#=============================================================
def add_local_reminder(message, client, model_type):
    prompt = f"""
从以下用户消息中提取提醒信息，返回 JSON 格式：
{{"name": "提醒名称", "body": "提醒描述（可选）", "due_date": "YYYY-MM-DD HH:MM（可选，如果没有则为 null）"}}

用户消息：{message}

请确保日期格式为 YYYY-MM-DD HH:MM，如果没有时间则假设为当天。
"""

    try:
        response = client.models.generate_content(
            model=model_type,
            contents=prompt
        )

        # Gemini 响应可能包裹在 ```json ... ``` 中，需要去除
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:-3].strip()
        elif response_text.startswith('```'):
            response_text = response_text[3:-3].strip()

        data = json.loads(response_text)

        name = data.get('name')
        body = data.get('body')
        due_date_str = data.get('due_date')

        if not name:
            return "无法提取提醒名称"

        due_date = None
        if due_date_str and due_date_str != 'null':
            try:
                due_date = datetime.datetime.strptime(due_date_str, '%Y-%m-%d %H:%M')
            except ValueError:
                return "日期格式错误"

        result = add_reminder(name, body, due_date)
        if result:
            return f"提醒 '{name}' 已添加"
        else:
            return "添加提醒失败"

    except json.JSONDecodeError:
        return "Gemini 响应解析失败"
    except Exception as e:
        return f"错误：{str(e)}"
