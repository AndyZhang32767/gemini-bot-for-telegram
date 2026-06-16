#=======================================================================================
#.       tui/feature_flags.py — 功能开关管理
#.       将各个工具和功能的启用/禁用状态持久化到 JSON 文件。
#.       用户在 TUI 侧边栏切换开关时实时生效（无需重启 Bot）。
#.
#.       数据文件: data/feature_flags.json
#.
#.       支持的开关：
#.         Skills: get_current_system_time, fetch_school_schedule, web_search,
#.                 add_local_reminder, remove_local_reminder, update_reminder_priority,
#.                 group_reminder
#.         Features: file_attachment, office_to_pdf
#.         Plans:    morning_push
#.
#.       被 tui/widgets/sidebar.py 渲染开关面板，
#.       被 bot/handlers.py 在处理消息时通过 flag() 函数检查开关状态。
#=======================================================================================

import json
import os

#=============================================================
#.       FLAGS_PATH — 功能开关持久化文件路径
#=============================================================
FLAGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "feature_flags.json",
)

#=============================================================
#.       DEFAULTS — 所有开关的默认值（新增 flag 自动补上默认值）
#=============================================================
DEFAULTS = {
    "get_current_system_time":  True,
    "fetch_school_schedule":    True,
    "web_search":               True,
    "add_local_reminder":       True,
    "remove_local_reminder":    True,
    "update_reminder_priority": True,
    "group_reminder":           True,
    "file_attachment":          True,
    "office_to_pdf":            True,
    "morning_push":             True,
}


#=============================================================
#.       load_flags() — 从 JSON 文件加载所有开关状态
#.       如果某个 key 在 JSON 中不存在（新增的 flag），
#.       自动从 DEFAULTS 补上。
#=============================================================
def load_flags() -> dict[str, bool]:
    if os.path.exists(FLAGS_PATH):
        try:
            with open(FLAGS_PATH) as f:
                data = json.load(f)
            # 合并默认值：新增的 flag 自动补上，已存在的保留用户设置
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


#=============================================================
#.       save_flags() — 将当前开关状态写入 JSON 文件
#.       自动创建 data/ 目录（如不存在）
#=============================================================
def save_flags(flags: dict[str, bool]) -> None:
    os.makedirs(os.path.dirname(FLAGS_PATH), exist_ok=True)
    with open(FLAGS_PATH, "w") as f:
        json.dump(flags, f, indent=2)


#=============================================================
#.       flag() — 读取单个开关的状态
#.       被 bot/handlers.py 在处理消息时调用，以判断某个功能是否启用。
#.       参数 key 为开关名称，返回 bool。
#=============================================================
def flag(key: str) -> bool:
    return load_flags().get(key, DEFAULTS.get(key, False))
