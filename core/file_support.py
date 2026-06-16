#=======================================================================================
#.       core/file_support.py — 文件附件支持列表
#.       定义 Bot 支持接收的文件类型，按类别（文档/数据/图像/音频/视频）组织。
#.       提供后缀→MIME 映射、文本可读性判断、Gemini 多模态兼容性检查等工具函数。
#.       主要被 bot/handlers.py 的 handle_file() / handle_reply() 调用。
#=======================================================================================

#=======================================================================================
#.       SUPPORTED_FILES — 支持的文件类别定义
#.       每个类别为 (类别名称, 后缀列表, MIME 列表) 三元组
#=======================================================================================
SUPPORTED_FILES = [
    ("文本文档 & 代码",   [".txt", ".md", ".html", ".css", ".js", ".rtf"],
     ["text/plain", "text/markdown", "text/html", "text/css", "text/javascript", "text/rtf"]),
    ("结构化数据",       [".csv", ".json", ".xml"],
     ["text/csv", "application/json", "text/xml"]),
    ("复合文档",         [".pdf"],
     ["application/pdf"]),
    ("图像格式",         [".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".bmp"],
     ["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif", "image/bmp"]),
    ("音频格式",         [".wav", ".mp3", ".aac", ".flac", ".ogg"],
     ["audio/wav", "audio/mpeg", "audio/aac", "audio/flac", "audio/ogg"]),
    ("视频格式",         [".mp4", ".mpeg", ".mov", ".avi", ".webm", ".wmv", ".flv"],
     ["video/mp4", "video/mpeg", "video/quicktime", "video/avi", "video/webm", "video/wmv", "video/x-flv"]),
]

# -- EXT_TO_MIME → get_mime() 函数使用，O(1) 查找后缀对应的 MIME 类型
#=======================================================================================
#.       EXT_TO_MIME — 后缀 → MIME 快速映射表
#.       从 SUPPORTED_FILES 自动构建，避免手工维护两份数据
#=======================================================================================
EXT_TO_MIME: dict[str, str] = {}
for _cat, _exts, _mimes in SUPPORTED_FILES:
    for ext, mime in zip(_exts, _mimes):
        EXT_TO_MIME[ext] = mime

#=======================================================================================
#.       TEXT_READABLE — 可直接当文本读取的后缀集合
#.       这些格式的文件内容会被直接读出作为文本传给 Gemini 模型
#=======================================================================================
TEXT_READABLE = {".txt", ".md", ".html", ".css", ".js", ".rtf", ".csv", ".json", ".xml"}

#=======================================================================================
#.       GEMINI_MULTIMODAL — Gemini 原生多模态支持的 MIME 类型
#.       这些类型可直接作为 Part.from_bytes() 传入，无需额外格式转换
#=======================================================================================
GEMINI_MULTIMODAL = {
    "image/png", "image/jpeg", "image/webp", "image/heic", "image/heif",
    "application/pdf",
    "audio/wav", "audio/mpeg", "audio/aac", "audio/flac", "audio/ogg",
    "video/mp4", "video/mpeg", "video/quicktime", "video/avi", "video/webm", "video/wmv", "video/x-flv",
}


#=============================================================
#.       根据文件后缀获取对应的 MIME 类型
#.       未匹配则返回安全的默认值 "application/octet-stream"
#=============================================================
def get_mime(ext: str) -> str:
    return EXT_TO_MIME.get(ext.lower(), "application/octet-stream")


#=============================================================
#.       检查文件后缀是否在支持列表中
#=============================================================
def is_supported(ext: str) -> bool:
    return ext.lower() in EXT_TO_MIME


#=============================================================
#.       检查文件是否可直接当文本读取并发给模型
#=============================================================
def is_text(ext: str) -> bool:
    return ext.lower() in TEXT_READABLE


#=============================================================
#.       检查 MIME 类型是否被 Gemini 原生多模态支持
#=============================================================
def is_multimodal(mime: str) -> bool:
    return mime in GEMINI_MULTIMODAL
