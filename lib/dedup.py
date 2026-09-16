"""
去重引擎 — URL去重 + 跨日重复检测 + 跨报去重（早报/午报）。
"""
import json
import os
from datetime import datetime
from typing import Optional

from lib.parser import Article


def load_url_cache(cache_file: str) -> set:
    """加载URL缓存"""
    path = os.path.expanduser(cache_file) if cache_file.startswith("~") else cache_file
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data.get("urls", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def save_url_cache(urls: list[str], cache_file: str, date_str: str = None):
    """保存URL缓存"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    path = os.path.expanduser(cache_file) if cache_file.startswith("~") else cache_file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"date": date_str, "urls": urls}, f, ensure_ascii=False)


def deduplicate_by_url(articles: list[Article]) -> list[Article]:
    """按URL去重，保留首次出现的"""
    seen = set()
    result = []
    for a in articles:
        if a.url not in seen:
            seen.add(a.url)
            result.append(a)
    return result


def cross_morning_dedup(articles: list[Article], config: dict) -> list[Article]:
    """午报去重：剔除早报已出现的URL"""
    dedup_cfg = config.get("dedup", {})
    if not dedup_cfg.get("cross_period_enabled"):
        return articles

    morning_cache = dedup_cfg.get("morning_cache_file", "data/url_cache_morning.json")
    # 相对于项目根目录
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(base, morning_cache)

    morning_urls = load_url_cache(cache_path)
    if not morning_urls:
        return articles

    filtered = [a for a in articles if a.url not in morning_urls]
    return filtered


def check_cross_day_repetition(today_urls: list[str], config: dict) -> Optional[str]:
    """
    检查跨日重复率。
    返回 None（正常）或 "no_new"（>80%重复）。
    只比较缓存日期与今天不同的情况。
    """
    dedup_cfg = config.get("dedup", {})
    threshold = dedup_cfg.get("cross_day_threshold", 0.8)

    cache_file = config.get("output", {}).get("url_cache_file", "data/url_cache.json")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(base, cache_file)

    if not os.path.exists(cache_path):
        return None

    # 检查缓存日期
    try:
        with open(cache_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None

    cache_date = data.get("date", "")
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 如果缓存是今天的（刚写入），跳过——不是真正的"跨日"
    if cache_date == today_str:
        return None

    yesterday_urls = set(data.get("urls", []))
    if not yesterday_urls or not today_urls:
        return None

    overlap = len(set(today_urls) & yesterday_urls)
    ratio = overlap / len(today_urls) if today_urls else 0

    if ratio > threshold:
        return "no_new"

    return None


def format_no_new_brief(config: dict, fetch_ok: int, fetch_total: int,
                        elapsed_s: float, total_articles: int, new_articles: int,
                        waf_blocked: list = None) -> str:
    """生成"今日无新增"简报"""
    from datetime import datetime
    today = datetime.now().strftime("%m-%d")

    lines = [
        f"【四川电力简报】{today}",
        "",
        "今日判断：",
        "今日未发现新增高价值更新，主要动态与前日一致。",
        "",
        f"已检查：{fetch_total}个关键词，今日共捕获 {total_articles} 篇文章，"
        f"其中 {new_articles} 篇为新内容。",
    ]

    if waf_blocked:
        lines.append("")
        lines.append(f"⚠️ 抓取异常：北极星 WAF 验证拦截 {len(waf_blocked)} 个关键词，"
                     f"可能影响覆盖完整性。")

    lines.append("")
    status = "✅" if fetch_ok == fetch_total else f"⚠️ {fetch_ok}/{fetch_total}"
    lines.append(f"📊抓取: {status}  耗时: {elapsed_s:.0f}s  数据: 北极星·Firecrawl")

    return "\n".join(lines)
