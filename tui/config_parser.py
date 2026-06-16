#=======================================================================================
#.       tui/config_parser.py — 配置解析与写回
#.       解析 core/config.py 的变量定义，将配置项组织为可编辑的 Section 列表，
#.       并提供 write_config() 将修改写回文件（保留注释和格式）。
#.
#.       数据结构：
#.         Var     — 单个变量（name, value, 行号范围, 是否多行字符串）
#.         Section — 一个配置区块（title + 变量列表）
#.
#.       被 tui/app.py 在启动/重启时解析配置，被 ConfigModal 保存时写回。
#=======================================================================================

import re
from dataclasses import dataclass, field


#=======================================================================================
#.       数据结构定义
#=======================================================================================

#=============================================================
#.       Var — config.py 中的一个变量定义
#.         name        — 变量名（如 "TELEGRAM_TOKEN"）
#.         value       — 当前值（字符串形式，已去引号）
#.         line_start  — 定义起始行号（1-based）
#.         line_end    — 定义结束行号（1-based）
#.         is_multiline — 是否为多行字符串（三引号）
#.         indent      — 变量前的缩进（用于写回时保持格式）
#=============================================================
@dataclass
class Var:
    name: str
    value: str
    line_start: int
    line_end: int
    is_multiline: bool = False
    indent: str = ""


#=============================================================
#.       Section — config.py 中的一个区块
#.         title     — 区块标题（取自分隔线后的注释行）
#.         variables — 该区块包含的 Var 列表
#=============================================================
@dataclass
class Section:
    title: str
    variables: list[Var] = field(default_factory=list)


#=============================================================
#.       分节分隔线判断 — 匹配 #====...==== 格式的行
#.       config.py 中每个 Section 以 #====...==== 行分隔，
#.       "=" 长度随注释文本变化，所以用模式匹配而非精确字符串比较。
#=============================================================
def _is_section_sep(line: str) -> bool:
    s = line.strip()
    return s.startswith("#====") and s.endswith("====") and s.count("=") > len(s) * 0.6

#=============================================================
#.       只读变量集合 — 这些变量显示在弹窗中但不可修改
#=============================================================
_READONLY_VARS = {"VERSION"}


#=======================================================================================
#.       parse_config() — 解析 config.py 文件
#.
#.       解析策略：
#.         1. 逐行扫描文件
#.         2. 遇到分节分隔线 → 标记新区块的开始
#.         3. 分隔线后的第一行注释作为区块标题
#.         4. 遇到变量赋值 → 调用 _try_parse_variable() 解析
#.         5. 跳过只读变量和 imports
#.
#.       返回：Section 列表
#=======================================================================================

def parse_config(filepath: str) -> list[Section]:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sections: list[Section] = []
    current_section: Section | None = None
    in_separator = False
    pending_title: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i]

        # 检测分节分隔线（"# =====...===="）
        if _is_section_sep(line):
            if pending_title:
                current_section = Section(title=pending_title)
                sections.append(current_section)
                pending_title = None
            elif current_section is None:
                # 文件头（首条分隔线之前的内容：imports 等），跳过
                pending_title = None
            in_separator = True
            i += 1
            continue

        # 分隔线后的第一行注释作为区块标题
        stripped = line.strip()
        if in_separator and not pending_title and stripped.startswith("#") and not _is_section_sep(line):
            pending_title = stripped.lstrip("# ").strip()
            in_separator = False
            i += 1
            continue

        in_separator = False

        # 检测变量赋值（跳过只读变量如 VERSION）
        var = _try_parse_variable(lines, i)
        if var:
            if var.name in _READONLY_VARS:
                i = var.line_end
                continue
            if current_section is not None:
                current_section.variables.append(var)
            i = var.line_end
        else:
            i += 1

    # 将所有有变量的 Section 合并为单个"基础配置"
    merged_sections = []
    base_vars = []
    for section in sections:
        if section.variables:
            base_vars.extend(section.variables)
    if base_vars:
        merged_sections.append(Section(title="Config", variables=base_vars))
    return merged_sections


#=======================================================================================
#.       _try_parse_variable() — 尝试从指定行解析一个变量定义
#.
#.       支持的格式：
#.         - 简单赋值: NAME = "value"
#.         - 表达式:   NAME = os.path.join(...)
#.         - 多行字符串: NAME = """...\n..."""
#.         - 数字/布尔: NAME = 123 / NAME = True
#.
#.       返回 Var 对象或 None（该行不是变量定义）。
#=======================================================================================

def _try_parse_variable(lines: list[str], start: int) -> Var | None:
    line = lines[start]

    # 匹配简单赋值: NAME = VALUE（允许任意缩进）
    m = re.match(r'^(\s*)([A-Za-z_]\w*)\s*=\s*(.+)$', line)
    if not m:
        return None

    indent = m.group(1)
    name = m.group(2)
    value = m.group(3).rstrip()

    # 情况 A：多行字符串（"""...开头但本行未闭合）
    if value.strip().startswith('"""') and not value.strip().endswith('"""'):
        is_multiline = True
        full_value = value + "\n"
        end = start + 1
        while end < len(lines):
            full_value += lines[end]
            if '"""' in lines[end]:
                break
            end += 1
        # 提取实际字符串内容（去掉首尾的 """ 标记）
        raw = full_value.strip()
        if raw.startswith('"""'):
            raw = raw[3:]
        idx = raw.rfind('"""')
        if idx >= 0:
            raw = raw[:idx]
        value = raw.strip()
        end += 1
        return Var(name=name, value=value, line_start=start + 1, line_end=end,
                   is_multiline=True, indent=indent)

    # 情况 B：三引号字符串在同一行闭合
    if value.strip().startswith('"""') and '"""' in value[3:]:
        raw = value.strip()
        raw = raw[3:]
        idx = raw.rfind('"""')
        if idx >= 0:
            raw = raw[:idx]
        return Var(name=name, value=raw.strip(), line_start=start + 1, line_end=start + 2,
                   is_multiline=True, indent=indent)

    # 情况 C：简单值 — 去掉尾部注释和首尾引号
    value_clean = value.strip()

    # 去掉外引号（单引号或双引号）
    if (value_clean.startswith('"') and value_clean.endswith('"')) or \
       (value_clean.startswith("'") and value_clean.endswith("'")):
        value_clean = value_clean[1:-1]
    elif "#" in value_clean:
        # 非字符串值，去掉 # 之后的注释
        value_clean = value_clean.split("#", 1)[0].strip()

    # 对于 os.path.join(...) 等表达式，保留原样
    if "(" in value_clean and ")" in value_clean:
        value_clean = value.strip()
        if not (value_clean.strip().startswith('"') or value_clean.strip().startswith("'")):
            value_clean = value_clean.split("#", 1)[0].strip()

    return Var(name=name, value=value_clean, line_start=start + 1, line_end=start + 2,
               is_multiline=False, indent=indent)


#=======================================================================================
#.       write_config() — 将修改后的变量值写回 config.py
#.
#.       重建文件时保留：
#.         - 原始行序
#.         - 注释
#.         - 非变量行
#.         - 变量缩进
#.
#.       变量类型判断：
#.         - 多行字符串 → 三引号包裹
#.         - 表达式变量（含括号调用如 os.path.join）→ 不加引号
#.         - 字符串变量 → 双引号包裹
#.         - 其他（数字/布尔）→ 原样写入
#=======================================================================================

def write_config(filepath: str, sections: list[Section]) -> None:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 构建 变量名 → Var 的映射（所有区块合并）
    var_map: dict[str, Var] = {}
    for section in sections:
        for var in section.variables:
            var_map[var.name] = var

    # 逐行重建文件内容
    result: list[str] = []
    i_line = 0
    while i_line < len(lines):
        line = lines[i_line]
        m = re.match(r'^(\s*)([A-Za-z_]\w*)\s*=\s*(.+)$', line)
        if m:
            name = m.group(2)
            if name in var_map:
                var = var_map[name]
                indent = m.group(1)
                if var.is_multiline:
                    # 多行字符串：写入 NAME = """value"""
                    result.append(f'{indent}{name} = """{var.value}"""\n')
                    # 跳过原文件中的多行内容（直到包含 """ 的行）
                    i_line += 1
                    while i_line < len(lines) and '"""' not in lines[i_line]:
                        i_line += 1
                    if i_line < len(lines):
                        i_line += 1
                    continue
                else:
                    # 单行值：根据类型决定是否加引号
                    val = var.value.strip()
                    expr_vars = {"SESSION_FILE"}   # 表达式变量，不加引号
                    str_vars = {"TELEGRAM_TOKEN", "GEMINI_API_KEY", "MODEL_TYPE",
                                "CUSTOM_SEARCH_API", "PROXY_URL", "SCHEDULE_FILE"}

                    if name in expr_vars or ("(" in val and ")" in val):
                        result.append(f'{indent}{name} = {val}\n')
                    elif name in str_vars or (val and not val[0].isdigit() and val not in ("True", "False", "None")):
                        result.append(f'{indent}{name} = "{val}"\n')
                    else:
                        result.append(f'{indent}{name} = {val}\n')
                    i_line += 1
                    continue
        result.append(line)
        i_line += 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(result)
