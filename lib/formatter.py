"""
简报格式化 — Article 列表 → brief.md + stdout。
"""

from datetime import datetime, timedelta

from lib.parser import Article


def format_brief(articles: list[Article], config: dict, 
                 fetch_ok: int, fetch_total: int, elapsed_s: float,
                 empty_streak: int) -> str:
    """
    生成简报 Markdown 文本。
    """
    today = datetime.now().strftime("%m-%d")
    max_focus = config["output"]["max_focus"]
    max_dynamic = config["output"]["max_dynamic"]
    max_chars = config["output"]["max_chars"]
    streak_alert = config["output"]["empty_streak_alert"]

    lines = []
    lines.append(f"【四川电力简报】{today}")

    # 连续空结果告警
    if empty_streak >= streak_alert:
        lines.append(f"")
        lines.append(f"⚠️ 连续 {empty_streak} 天无结果，可能源失效/改版，请人工检查。")

    if not articles:
        lines.append("")
        lines.append("📭 今日未发现相关新闻。")
    else:
        # 分桶：D0/D-1 为重点，D-2/D-3 为动态
        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        focus = [a for a in articles if a.date >= yesterday][:max_focus]
        dynamic = [a for a in articles if a not in focus][:max_dynamic]

        if focus:
            lines.append("")
            lines.append("⚡重点")
            for i, a in enumerate(focus, 1):
                lines.append(f"{i} {a.title} · {a.date} · {a.source}")
                if a.summary:
                    lines.append(f"   摘要: {a.summary[:120]}")
                lines.append(f"   {a.url}")

        if dynamic:
            lines.append("")
            lines.append("📋动态")
            for a in dynamic:
                lines.append(f"· {a.title} · {a.date} · {a.source}")
                lines.append(f"  {a.url}")

    # 抓取状态
    status = "✅" if fetch_ok == fetch_total else f"⚠️ {fetch_ok}/{fetch_total}"
    lines.append("")
    lines.append(f"📊抓取: {status}  耗时: {elapsed_s:.0f}s  数据: 北极星·Firecrawl")

    # 截断：按行截断，不在中间切断
    brief = "\n".join(lines)
    if len(brief) > max_chars:
        # 找到 max_chars 位置前的最后一个换行
        cut = brief.rfind("\n", 0, max_chars)
        if cut == -1:
            cut = max_chars - 20
        brief = brief[:cut] + "\n\n...(已截断)"

    return brief
