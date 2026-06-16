#=======================================================================================
#.       tools/search.py — DuckDuckGo 网页搜索工具
#.       使用 ddgs 库通过 DuckDuckGo 进行网页搜索，返回前 N 条结果的标题、摘要和链接。
#.       供 Gemini 在需要查询实时信息、新闻、时事、价格等内容时调用。
#.
#.       被 core/gemini_setup.py 注册为 web_search 工具函数。
#=======================================================================================

import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)

#=============================================================
#.       DDG_MAX_RESULTS — 每次搜索返回的最大结果条数
#=============================================================
DDG_MAX_RESULTS = 10


#=============================================================
#.       web_search() — 执行 DuckDuckGo 网页搜索
#.
#.       参数：
#.         query — 搜索查询字符串
#.
#.       返回：格式化后的搜索结果文本，每条包含标题、摘要和链接。
#.       无结果或异常时返回描述性字符串。
#.
#.       DDGS().text() 是同步调用，返回生成器，使用 list() 收集结果。
#=============================================================
def web_search(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=DDG_MAX_RESULTS, backend="auto"))

        if not results:
            logger.info(f"[web_search] 查询='{query}' 无结果")
            return "没有找到相关结果。"

        # 逐条格式化为 标题 + 摘要 + 链接
        lines = []
        for i, r in enumerate(results, 1):
            title   = r.get("title", "")
            snippet = r.get("body", "").replace("\n", " ")
            link    = r.get("href", "")
            lines.append(f"{i}. {title}\n   {snippet}\n   {link}")

        logger.info(f"[web_search] 查询='{query}' 返回 {len(results)} 条")
        return "\n\n".join(lines)

    except Exception as e:
        logger.error(f"[web_search] 异常: {e}")
        return f"搜索出错: {e}"
