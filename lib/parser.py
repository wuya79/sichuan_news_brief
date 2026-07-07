"""
北极星搜索结果 HTML 解析器。
从 rawHtml 中提取 div.item → 结构化 Article 列表。

北极星搜索结果 HTML 结构（div.item）：
<div class="item">
  <div class="top">
    <span><a href="https://news.bjx.com.cn/html/YYYYMMDD/ID.shtml">标题</a></span>
  </div>
  <div class="bottom">
    <div class="right">
      <p>
        <em>来源：xxx</em>
        <em>2026-07-02</em>
      </p>
      <p><span class="max-2">摘要文本</span></p>
    </div>
  </div>
</div>
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Article:
    title: str
    url: str
    date: str          # "2026-07-05"
    source: str        # "四川省发展和改革委员会"
    summary: str
    keyword: str       # 通过哪个关键词搜到的


def _clean(text: str) -> str:
    """去空白和 HTML 标签"""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_html(html: str, keyword: str, config: dict) -> list[Article]:
    """
    从北极星搜索结果 HTML 中提取文章列表。
    基于 div.item 结构解析。
    """
    articles = []
    # 分割出每个 div.item
    items = re.split(r'<div class="item[^"]*">', html)

    for item in items[1:]:  # items[0] 是第一个 div.item 之前的内容
        # 找 top 区域的链接和标题
        top_match = re.search(
            r'<a[^>]*href="(https://news\.bjx\.com\.cn/html/\d+/\d+\.shtml)"[^>]*>(.*?)</a>',
            item, re.DOTALL
        )
        if not top_match:
            continue

        url = top_match.group(1)
        title = _clean(top_match.group(2))

        if not title or len(title) < 3:
            continue

        # 找 bottom 区域的日期和来源（在 em 标签中）
        ems = re.findall(r'<em>(.*?)</em>', item, re.DOTALL)
        date = ""
        source = ""
        for em in ems:
            em_clean = _clean(em)
            if re.match(r"\d{4}-\d{2}-\d{2}", em_clean):
                date = em_clean
            elif re.match(r"\d{4}\.\d{2}\.\d{2}", em_clean):
                date = em_clean.replace(".", "-")
            elif em_clean.startswith("来源"):
                source = em_clean.replace("来源", "").replace("：", "").replace(":", "").strip()

        # 如果日期没提取到（"9分钟前"等相对时间），从URL提取
        if not date:
            url_date_match = re.search(r'/html/(\d{4})(\d{2})(\d{2})/', url)
            if url_date_match:
                date = f"{url_date_match.group(1)}-{url_date_match.group(2)}-{url_date_match.group(3)}"

        # 找摘要（max-2 span）
        summary_match = re.search(r'<span[^>]*class="max-2"[^>]*>(.*?)</span>', item, re.DOTALL)
        summary = _clean(summary_match.group(1)) if summary_match else ""

        articles.append(Article(
            title=title,
            url=url,
            date=date,
            source=source,
            summary=summary[:200],
            keyword=keyword,
        ))

    return articles


def deduplicate(articles: list[Article]) -> list[Article]:
    """按 URL 去重，保留首次出现的"""
    seen = set()
    result = []
    for a in articles:
        if a.url not in seen:
            seen.add(a.url)
            result.append(a)
    return result


def filter_by_date(articles: list[Article], max_days: int) -> list[Article]:
    """只保留 max_days 天内的新闻"""
    if not articles:
        return []
    cutoff = datetime.now() - timedelta(days=max_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    return [a for a in articles if a.date and a.date >= cutoff_str]


def parse_all(html_list: list[tuple[str, str]], config: dict) -> list[Article]:
    """
    处理所有关键词的 HTML 结果。
    html_list: [(keyword_name, raw_html), ...]
    返回：去重+日期过滤后的 Article 列表，按日期降序排列。
    """
    all_articles = []
    for keyword, html in html_list:
        if html:
            articles = parse_html(html, keyword, config)
            all_articles.extend(articles)

    all_articles = deduplicate(all_articles)
    all_articles = filter_by_date(all_articles, config["output"]["date_window_days"])
    all_articles.sort(key=lambda a: a.date, reverse=True)

    return all_articles
