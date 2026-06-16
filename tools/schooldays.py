#=======================================================================================
#.       tools/schooldays.py — 课表查询模块
#.       从 CSV 课表文件中读取并格式化课程信息。
#.
#.       数据来源：core/config.py 中配置的 SCHEDULE_FILE 路径指向的 CSV 文件。
#.       CSV 必须包含列：排课日期, 节次, 课程名称, 上课地点, 教师
#.
#.       主要函数：
#.         fetch_school_schedule() — 查询指定日期的课表（供 Gemini 调用 + /class 命令）
#.         get_courses_on_day()    — 查询某日课程列表
#.         get_classroom_for_course() — 查询指定课程的上课地点
#.         get_time_for_section()  — 节次编号 → 时间范围转换
#.
#.       被 core/gemini_setup.py 注册为工具函数，同时被 bot/handlers.py 的 /class 命令
#.       和 bot/main.py 的早间推送直接调用。
#=======================================================================================

import csv
import os
import datetime

# -- 从 core/config.py 获取课表 CSV 文件路径
from core.config import SCHEDULE_FILE

#=======================================================================================
#.       time_map — 节次编号到上课时间的映射
#.       key: 两位数字的节次编号（01-12）
#.       value: (开始时间, 结束时间) 元组
#=======================================================================================
time_map = {
    '01': ('8:30', '9:15'),
    '02': ('9:20', '10:05'),
    '03': ('10:25', '11:10'),
    '04': ('11:15', '12:00'),
    '05': ('13:50', '14:35'),
    '06': ('14:40', '15:25'),
    '07': ('15:30', '16:15'),
    '08': ('16:30', '17:15'),
    '09': ('17:20', '18:05'),
    '10': ('18:30', '19:15'),
    '11': ('19:20', '20:05'),
    '12': ('20:10', '20:55'),
}


#=============================================================
#.       get_time_for_section() — 节次字符串 → 时间范围字符串
#.       参数 section_str 如 '0102'（第1-2节连上）或 '101112'
#.       处理逻辑：
#.         - 每两位取一节次编号
#.         - 单节 → 返回该节的起止时间
#.         - 多节连续 → 返回第一节开始到最后一节结束
#.       返回格式如 '8:30-10:05'
#=============================================================
def get_time_for_section(section_str):
    if len(section_str) % 2 != 0:
        return section_str  # 非偶数长度 → 无法解析，返回原值

    # 每两位拆分为一个节次编号
    sections = [section_str[i:i+2] for i in range(0, len(section_str), 2)]

    if len(sections) == 1:
        # 单节课
        if sections[0] in time_map:
            start, end = time_map[sections[0]]
            return f"{start}-{end}"
        else:
            return section_str
    else:
        # 多节连排：取第一节的开始和最后一节的结束
        start_section = sections[0]
        end_section = sections[-1]
        if start_section in time_map and end_section in time_map:
            start_time = time_map[start_section][0]
            end_time = time_map[end_section][1]
            return f"{start_time}-{end_time}"
        else:
            return section_str


#=======================================================================================
#.       courses — 全量课程数据缓存
#.       在模块加载时从 CSV 文件一次性读入内存，后续查询直接过滤此列表。
#=======================================================================================
courses = []

if os.path.exists(SCHEDULE_FILE):
    with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            courses.append(row)


#=============================================================
#.       fetch_school_schedule() — 查询指定日期的课表（主入口）
#.
#.       当 Gemini 需要查询课表、用户发送 /class 命令或早间推送时调用。
#.       参数：
#.         target_date — 查询日期，格式 'YYYY-MM-DD'，为空则默认当天
#.       返回：格式化后的课表文本（纯文本，无 Markdown/LateX）
#=============================================================
def fetch_school_schedule(target_date: str = None):
    if not target_date:
        target_date = datetime.datetime.now().strftime('%Y-%m-%d')

    # 兼容 YYYY/MM/DD 和 YYYY-MM-DD
    search_date = target_date.replace('/', '-')

    # 从内存缓存中过滤当天的课程
    courses_on_date = []
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['排课日期'] == search_date:
                    courses_on_date.append(row)

    if not courses_on_date:
        return f"{search_date}好像没有安排课程呢，休息一下吧"

    # 格式化为纯文本输出（不使用 LateX/格式化标记）
    res = f"📅 {search_date} 的课程安排如下：\n"
    for c in courses_on_date:
        time_str = get_time_for_section(c['节次'])
        res += f"🔹 {time_str} | {c['课程名称']}\n   📍 地点：{c['上课地点']}\n   👨‍🏫 教师：{c['教师']}\n"
    return res


#=============================================================
#.       parse_date() — 日期格式转换：yyyy/mm/dd → yyyy-mm-dd
#=============================================================
def parse_date(date_str):
    return date_str.replace('/', '-')


#=============================================================
#.       get_courses_on_day() — 查询某日的全部课程
#.       参数 day 格式：yyyy/mm/dd
#.       返回：课程字典列表
#=============================================================
def get_courses_on_day(day):
    target_date = parse_date(day)
    day_courses = [course for course in courses if course['排课日期'] == target_date]
    return day_courses


#=============================================================
#.       get_classroom_for_course() — 查询指定课程的上课地点
#.       参数 course_name 格式：yyyy/mm/dd/<n>
#.         例如 '2026/03/10/06' 表示 2026年3月10日第6节
#.       返回：上课地点字符串
#=============================================================
def get_classroom_for_course(course_name):
    parts = course_name.split('/')
    if len(parts) != 4:
        return "格式错误"
    date_str = '/'.join(parts[:3])
    n = parts[3]
    if len(n) != 2:
        return "节次格式错误"
    target_date = parse_date(date_str)
    for course in courses:
        if course['排课日期'] == target_date and course['节次'].startswith(n):
            return course['上课地点']
    return "未找到课程"


#=============================================================
#.       本地测试入口（直接运行本文件时执行示例查询）
#=============================================================
if __name__ == "__main__":
    # 示例：查询 2026/03/10 的课程
    day = "2026/03/10"
    day_courses = get_courses_on_day(day)
    print(f"{day} 的课程：")
    for course in day_courses:
        print(f"课程：{course['课程名称']}, 教师：{course['教师']}, 地点：{course['上课地点']}, 节次：{course['节次']}")

    # 示例：查询 2026/03/10/06 的教室
    course_name = "2026/03/10/06"
    classroom = get_classroom_for_course(course_name)
    print(f"\n{course_name} 的教室：{classroom}")

    # 示例：查询 2026/03/10/10 的教室
    course_name2 = "2026/03/10/10"
    classroom2 = get_classroom_for_course(course_name2)
    print(f"{course_name2} 的教室：{classroom2}")

    # 测试 fetch_school_schedule
    print("\n测试 fetch_school_schedule:")
    result = fetch_school_schedule("2026-03-10")
    print(result)
