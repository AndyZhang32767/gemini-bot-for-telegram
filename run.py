#=======================================================================================
#.       run.py — 命令行模式入口
#.       最简单的入口点：直接调用 bot/main.py 的 main() 函数，
#.       启动 Telegram Bot 的阻塞式 polling 循环。
#.       如需 TUI 控制台，请使用 python tui_run.py。
#=======================================================================================

# -- main() 位于 bot/main.py，负责创建 Application 并启动 polling
from bot.main import main

if __name__ == "__main__":
    main()
