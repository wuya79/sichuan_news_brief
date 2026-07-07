#!/usr/bin/env python3
"""
四川电力新闻午报 — v2.0
搜索策略：10个长关键词（跨区域+省间+行业）
去重：自动剔除早报已出现的文章
用法: cd ~/sichuan_news_brief && python3 fetch_afternoon.py
输出: data/brief_afternoon.md + stdout
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.firecrawl import load_config, scrape, FirecrawlError
from lib.parser import parse_html, filter_by_date
from lib.scorer import score_and_sort
from lib.dedup import (deduplicate_by_url, save_url_cache,
                       cross_morning_dedup)
from lib.waf_check import check_batch


def scrape_keywords(config: dict) -> tuple[list, int, int, list]:
    """搜长关键词"""
    keywords = config.get("keywords", [])
    interval = config["firecrawl"]["request_interval_s"]

    all_articles = []
    fetch_ok = 0
    blocked = []
    t0 = time.time()
    html_results = []

    for i, kw in enumerate(keywords):
        kw_name = kw["name"]
        kw_str = kw["kw"]

        if i > 0:
            time.sleep(interval)

        try:
            html = scrape(kw_str, config)
            if html:
                html_results.append((kw_name, html))
                articles = parse_html(html, kw_str, config)
                all_articles.extend(articles)
                fetch_ok += 1
                print(f"  ✅ {kw_name}: {len(articles)}篇", flush=True)
            else:
                print(f"  ⚠️ {kw_name}: 空响应", flush=True)
        except FirecrawlError as e:
            print(f"  ❌ {kw_name}: {e}", flush=True)
        except Exception as e:
            print(f"  ❌ {kw_name}: {e}", flush=True)

    blocked = check_batch(html_results)
    if blocked:
        print(f"  ⚠️ WAF拦截: {', '.join(blocked)}", flush=True)

    elapsed = time.time() - t0
    return all_articles, fetch_ok, elapsed, blocked


def format_afternoon_brief(scored, config: dict, fetch_ok: int, fetch_total: int,
                           elapsed_s: float, waf_blocked: list, removed_by_dedup: int = 0) -> str:
    """午报格式化"""
    today = datetime.now().strftime("%m-%d")
    max_focus = config["output"]["max_focus"]
    max_dynamic = config["output"]["max_dynamic"]
    max_chars = config["output"]["max_chars"]

    focus = [(a, s) for a, s in scored if s["level"] == "focus"][:max_focus]
    normal = [(a, s) for a, s in scored if s["level"] == "normal"][:max_dynamic]

    lines = [f"【四川电力简报·午报】{today}"]

    if not focus and not normal:
        lines.append("")
        lines.append("📭 午报未发现新增高价值信息。")
    else:
        if focus:
            lines.append("")
            lines.append("⚡重点关注")
            for i, (a, s) in enumerate(focus, 1):
                lines.append(f"{i} [{s['score']}分] {a.title} · {a.date} · {a.source}")
                if a.summary:
                    lines.append(f"   摘要: {a.summary[:120]}")
                lines.append(f"   {a.url}")

        if normal:
            lines.append("")
            lines.append("📋一般动态")
            for a, s in normal:
                lines.append(f"· [{s['score']}分] {a.title} · {a.date} · {a.source}")
                lines.append(f"  {a.url}")

    # 去重信息
    if removed_by_dedup > 0:
        lines.append("")
        lines.append(f"ℹ️ 已自动剔除 {removed_by_dedup} 篇早报已覆盖文章")

    if waf_blocked:
        lines.append("")
        lines.append(f"⚠️ WAF拦截: {len(waf_blocked)}个关键词")

    status = "✅" if fetch_ok == fetch_total else f"⚠️ {fetch_ok}/{fetch_total}"
    lines.append("")
    lines.append(f"📊抓取: {status}  耗时: {elapsed_s:.0f}s  数据: 北极星·Firecrawl")

    brief = "\n".join(lines)
    if len(brief) > max_chars:
        cut = brief.rfind("\n", 0, max_chars)
        if cut == -1:
            cut = max_chars - 20
        brief = brief[:cut] + "\n\n...(已截断)"

    return brief


def main():
    config = load_config("config_afternoon.yaml")
    output = config["output"]
    total_kw = len(config.get("keywords", []))

    start_time = time.time()

    # ── Step 1: 搜关键词 ──
    print(f"📡 午报: {total_kw}个关键词 ...", flush=True)
    all_articles, fetch_ok, kw_time, waf_blocked = scrape_keywords(config)

    # ── Step 2: 去重 ──
    all_articles = deduplicate_by_url(all_articles)
    before_morning_dedup = len(all_articles)

    # ── Step 3: 跨早报去重 ──
    all_articles = cross_morning_dedup(all_articles, config)
    removed = before_morning_dedup - len(all_articles)
    if removed > 0:
        print(f"  ℹ️ 剔除早报重复: {removed}篇", flush=True)

    # ── Step 4: 日期过滤 ──
    all_articles = filter_by_date(all_articles, output["date_window_days"])

    # ── Step 5: 评分 ──
    scored = score_and_sort(all_articles, config)
    focus_count = sum(1 for _, s in scored if s["level"] == "focus")
    normal_count = sum(1 for _, s in scored if s["level"] == "normal")

    print(f"📊 午报: {len(all_articles)}篇 | 🔴{focus_count} 🟡{normal_count}", flush=True)

    # ── Step 6: 保存URL缓存 ──
    all_urls = [a.url for a in all_articles]
    save_url_cache(all_urls, output["url_cache_file"])

    # ── Step 7: 格式化 ──
    brief = format_afternoon_brief(
        scored, config,
        fetch_ok, total_kw,
        time.time() - start_time,
        waf_blocked,
        removed
    )

    # ── 写入文件 ──
    os.makedirs(os.path.dirname(output["output_file"]), exist_ok=True)
    with open(output["output_file"], "w") as f:
        f.write(brief)
    with open(output["latest_file"], "w") as f:
        f.write(brief)

    elapsed_total = time.time() - start_time
    print(f"\n📄 午报已写入 {output['output_file']} ({len(brief)} chars, {elapsed_total:.0f}s)", flush=True)
    print(f"\n{brief}", flush=True)


if __name__ == "__main__":
    main()
