# Assistant Bot

基于 Google Gemini 的模块化 Telegram Bot，支持多模态对话、macOS 提醒事项集成、网页搜索、课表查询等功能，附带 Textual TUI 管理控制台。

## 功能

- **AI 对话** — 支持文字、图片、文档、音频、视频等多模态输入
- **提醒事项** — 通过自然语言增删改查 macOS Reminders.app 中的提醒
- **课表查询** — 查询 CSV 格式的课程表，支持按日期查询
- **网页搜索** — 基于 DuckDuckGo 的实时搜索
- **Office 文档** — 自动将 `.docx`/`.pptx`/`.xlsx` 转换为 PDF 后传给 Gemini
- **TUI 管理** — 终端图形界面，实时日志查看、功能开关、历史记录浏览、配置编辑
- **权限分级** — Premium/Normal 两级用户，各自有不同的 System Prompt 和可用工具
- **群聊支持** — 支持 Telegram 群组中 @bot 触发，自动标注发言者身份
- **每日推送** — 定时向 Premium 用户推送当日课表

## 架构

```
                  ┌──────────────────────────┐
                  │       Telegram API        │
                  └────────────┬─────────────┘
                               │
                  ┌────────────▼─────────────┐
                  │         bot/              │
                  │  main.py      应用生命周期 │
                  │  handlers.py  消息处理     │
                  │  session.py   授权与会话   │
                  └────────────┬─────────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
  ┌──────▼──────┐   ┌──────────▼─────────┐   ┌───────▼──────┐
  │    core/    │   │      tools/        │   │     tui/     │
  │ config.py   │   │ reminder.py (Mac) │   │ app.py       │
  │ gemini_setup│   │ schooldays.py     │   │ widgets/     │
  │ file_support│   │ search.py (DDG)   │   │              │
  │ logging     │   │ notice.py         │   │              │
  └─────────────┘   │ doc_converter.py  │   └──────────────┘
                    └────────────────────┘
```

## 环境要求

- **Python 3.10+**（使用了 `zoneinfo` 标准库）
- **Telegram Bot Token** — 通过 [@BotFather](https://t.me/BotFather) 创建
- **Google Gemini API Key** — [Google AI Studio](https://aistudio.google.com/apikey) 获取

### 可选依赖

| 功能 | 依赖 | 平台 |
|---|---|---|
| Office→PDF 转换 | [LibreOffice](https://www.libreoffice.org/) | 全平台 |
| 提醒事项集成 | macOS（通过 `osascript` 调用 AppleScript） | 仅 macOS |
| 课表查询 | CSV 文件（格式见下方说明） | 全平台 |

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url>
cd <project-directory>

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置
# 在 core/config.py 中填入你的 TELEGRAM_TOKEN、GEMINI_API_KEY 等

# 4. 启动（命令行模式）
python run.py

# 5. 或启动（TUI 管理控制台模式，推荐）
python tui_run.py
```

## 配置说明

所有配置项集中在 [`core/config.py`](core/config.py) 中：

| 配置项 | 必填 | 说明 |
|---|---|---|
| `TELEGRAM_TOKEN` | 是 | Telegram Bot Token，从 @BotFather 获取 |
| `GEMINI_API_KEY` | 是 | Google Gemini API 密钥 |
| `ADMIN_ID` | 是 | 管理员的 Telegram 用户 ID（给 `0` 则不会将任何人设为管理员）。可通过 @userinfobot 获取自己的 ID |
| `MODEL_TYPE` | 否 | Gemini 模型，默认 `gemini-2.5-flash` |
| `PROXY_URL` | 否 | HTTP 代理地址，如 `http://127.0.0.1:10808`，留空则不使用代理 |
| `CUSTOM_SEARCH_API` | 否 | Google Custom Search API 密钥（备用，当前未启用） |
| `SCHEDULE_FILE` | 否 | 课表 CSV 文件路径 |
| `PRIVATE_INSTRUCTION` | 否 | 私聊/Premium 模式的 System Prompt |
| `PUBLIC_INSTRUCTION` | 否 | 群聊/Normal 模式的 System Prompt |
| `SESSION_FILE` | 否 | 会话数据持久化路径，默认 `data/sessions_data.json` |

### System Prompt

`PRIVATE_INSTRUCTION`（私聊模式）和 `PUBLIC_INSTRUCTION`（群聊模式）均已预填引导模板，包含：
- 角色设定示例
- 可用工具列表及使用场景（帮助 Gemini 正确调用 Function Calling）
- 注意事项（日期格式、时间确认等）

直接编辑 `core/config.py` 中对应变量即可自定义。

### 课表 CSV 格式

课表文件需包含以下列：

| 列名 | 说明 |
|---|---|
| `排课日期` | 日期，YYYYMMDD 格式（如 `20260617`） |
| `节次` | 节次编号（如 `01`、`02`） |
| `课程名称` | 课程名称 |
| `上课地点` | 教室/地点 |
| `教师` | 教师姓名 |

示例：
```csv
排课日期,节次,课程名称,上课地点,教师
20260617,01,高等数学,教学楼301,张教授
20260617,02,大学物理,实验楼B,李教授
```

## 使用说明

### 命令行模式 (`python run.py`)

后台运行，新用户授权通过终端输入处理。

### TUI 模式 (`python tui_run.py`)

启动 Textual 终端界面，提供：
- **日志面板** — 实时彩色日志
- **侧边栏** — 运行时开关各项功能
- **配置编辑器** — 可视化修改配置（快捷键 `c`）
- **历史浏览器** — 查看/清除用户对话记录（快捷键 `h`）
- **授权弹窗** — 新用户接入时图形化审批

#### TUI 快捷键

| 按键 | 功能 |
|---|---|
| `q` | 退出 |
| `c` | 打开配置编辑器 |
| `s` | 保存配置 |
| `r` | 重启 Bot |
| `h` | 打开历史记录 |
| `Ctrl+L` | 聚焦日志面板 |

### Telegram 命令

| 命令 | 功能 | 权限 |
|---|---|---|
| `/start` | 打招呼 | 所有人 |
| `/class` | 查询今日课表 | Premium 用户 |
| `/clear` | 清除对话历史 | 已授权用户 |

### 群聊使用

在群组中 @bot 即可触发回复。Bot 会自动为每条消息标注发言者名称，帮助 AI 区分不同用户。

## 可用工具（Gemini Function Calling）

Bot 注册了以下工具供 Gemini 调用：

| 函数 | 适用模式 | 功能 |
|---|---|---|
| `get_current_system_time` | 全部 | 获取系统当前时间 |
| `add_local_reminder` | Premium | 添加提醒事项 |
| `remove_local_reminder` | Premium | 删除提醒事项 |
| `update_reminder_priority` | Premium | 调整提醒优先级 |
| `update_reminder_settings` | Premium | 更新提醒设置（优先级、提前提醒） |
| `fetch_local_reminders` | Premium | 列出所有提醒事项 |
| `fetch_school_schedule` | 全部 | 查询课表 |
| `web_search` | 全部 | DuckDuckGo 网页搜索 |
| `group_reminder` | Normal | 创建群组备忘录 |

## 目录结构

```
├── run.py                     # 命令行入口
├── tui_run.py                 # TUI 入口
├── requirements.txt           # Python 依赖
├── .gitignore
│
├── bot/                       # Telegram Bot 核心
│   ├── main.py                # 应用组装、每日推送
│   ├── handlers.py            # 消息/命令处理器
│   └── session.py             # 授权、会话持久化
│
├── core/                      # 配置与初始化
│   ├── config.py              # 配置中心（密钥、模型、System Prompt）
│   ├── gemini_setup.py        # Gemini 客户端单例、工具注册
│   ├── file_support.py        # MIME 类型映射
│   └── logging_setup.py       # 日志配置
│
├── tools/                     # Gemini Function Calling 工具
│   ├── reminder.py            # macOS Reminders.app 集成 (AppleScript)
│   ├── schooldays.py          # 课表 CSV 解析查询
│   ├── search.py              # DuckDuckGo 搜索
│   ├── notice.py              # 群组备忘录
│   └── doc_converter.py       # Office→PDF 转换 (LibreOffice)
│
├── tui/                       # Textual TUI 管理控制台
│   ├── app.py                 # TUI 主应用
│   ├── config_parser.py       # config.py 读写解析
│   ├── feature_flags.py       # 功能开关持久化
│   └── widgets/               # UI 组件
│       ├── auth_modal.py      # 授权弹窗
│       ├── config_modal.py    # 配置编辑器
│       ├── history_modal.py   # 历史记录查看器
│       ├── log_panel.py       # 实时日志面板
│       └── sidebar.py         # 功能开关侧边栏
│
├── utils/
│   └── helpers.py             # 历史裁剪、输入状态动画
│
├── scripts/
│   └── gemini_module.py       # 实验性：Gemini 提醒解析（备用方案）
│
└── data/                      # 运行时数据（已 gitignore）
    └── .gitkeep
```

## 平台说明

### macOS 提醒事项

`tools/reminder.py` 通过 `osascript` 调用 AppleScript 与 Reminders.app 交互，**仅在 macOS 上可用**。其他平台上提醒相关功能会报错。

### LibreOffice

`tools/doc_converter.py` 需要安装 LibreOffice 才能进行 Office 文档转换：

- **macOS**：`brew install --cask libreoffice`
- **Linux**：`sudo apt install libreoffice`
- **Windows**：从 [libreoffice.org](https://www.libreoffice.org/) 下载

未安装 LibreOffice 不影响其他功能。

## 安全提示

- 请勿将含真实密钥的 `core/config.py` 提交到公开仓库
- `data/` 目录下的 JSON 文件包含运行时用户数据，已在 `.gitignore` 中排除
- 提醒功能通过 `osascript` 执行由 AI 生成的参数构造的 shell 命令，请注意安全风险
- 如密钥曾提交到 Git 历史，建议立即轮换并清理历史

## License

MIT
