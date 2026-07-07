#!/usr/bin/env python3
"""
四川电力新闻早报 — v2.0
搜索策略：短词探针"四川" + 15个长关键词
用法: cd ~/sichuan_news_brief && python3 fetch_morning.py
输出: data/brief_morning.md + stdout
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.firecrawl import load_config, scrape, FirecrawlError, read_api_key
from lib.parser import parse_html, filter_by_date, parse_all
from lib.scorer import score_and_sort, filter_by_level
from lib.dedup import (deduplicate_by_url, save_url_cache,
                       check_cross_day_repetition, format_no_new_brief)
from lib.waf_check import check_batch


def scrape_probe(config: dict) -> list:
    """搜探针关键词，返回 articles + 耗时"""
    probe = config.get("probe", {})
    if not probe.get("enabled"):
        return [], 0

    kw = probe["keyword"]
    print(f"🔍 探针: '{kw}' ...", flush=True, end=" ")
    t0 = time.time()

    try:
        html = scrape(kw, config)
        elapsed = time.time() - t0
        articles = parse_html(html, kw, config)
        print(f"{len(articles)}篇, {elapsed:.0f}s", flush=True)
        return articles, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        print(f"❌ {e}", flush=True)
        return [], elapsed


def scrape_keywords(config: dict) -> tuple[list, int, int, list]:
    """搜长关键词，返回 (all_articles, fetch_ok, elapsed, waf_blocked_names)"""
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

    # WAF检测
    blocked = check_batch(html_results)
    if blocked:
        print(f"  ⚠️ WAF拦截: {', '.join(blocked)}", flush=True)

    elapsed = time.time() - t0
    return all_articles, fetch_ok, elapsed, blocked


def format_brief_v2(scored, config: dict, fetch_ok: int, fetch_total: int,
                    elapsed_s: float, waf_blocked: list, probe_articles: int = 0) -> str:
    """基于评分的新版简报格式化"""
    today = datetime.now().strftime("%m-%d")
    max_focus = config["output"]["max_focus"]
    max_dynamic = config["output"]["max_dynamic"]
    max_chars = config["output"]["max_chars"]

    # 分级提取
    focus = [(a, s) for a, s in scored if s["level"] == "focus"][:max_focus]
    normal = [(a, s) for a, s in scored if s["level"] == "normal"][:max_dynamic]

    lines = [f"【四川电力简报】{today}"]

    if not focus and not normal:
        lines.append("")
        lines.append("📭 今日未发现高价值四川电力交易相关信息。")
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

    # WAF告警
    if waf_blocked:
        lines.append("")
        lines.append(f"⚠️ WAF拦截: {len(waf_blocked)}个关键词 ({', '.join(waf_blocked[:5])})")

    # 抓取状态
    status = "✅" if fetch_ok == fetch_total else f"⚠️ {fetch_ok}/{fetch_total}"
    lines.append("")
    lines.append(f"📊抓取: {status}  耗时: {elapsed_s:.0f}s  "
                 f"探针: {probe_articles}篇  数据: 北极星·Firecrawl")

    # 截断
    brief = "\n".join(lines)
    if len(brief) > max_chars:
        cut = brief.rfind("\n", 0, max_chars)
        if cut == -1:
            cut = max_chars - 20
        brief = brief[:cut] + "\n\n...(已截断)"

    return brief


def main():
    config = load_config("config.yaml")
    output = config["output"]
    total_kw = len(config.get("keywords", [])) + (1 if config.get("probe", {}).get("enabled") else 0)

    start_time = time.time()

    # ── Step 1: 探针 ──
    probe_articles, probe_time = scrape_probe(config)

    # ── Step 2: 长关键词 ──
    print(f"📡 长关键词: {len(config.get('keywords', []))}个 ...", flush=True)
    kw_articles, fetch_ok, kw_time, waf_blocked = scrape_keywords(config)

    # ── Step 3: 合并+去重 ──
    all_articles = probe_articles + kw_articles
    all_articles = deduplicate_by_url(all_articles)
    all_articles = filter_by_date(all_articles, output["date_window_days"])

    total_count = len(all_articles)

    # ── Step 4: 评分 ──
    scored = score_and_sort(all_articles, config)
    focus_count = sum(1 for _, s in scored if s["level"] == "focus")
    normal_count = sum(1 for _, s in scored if s["level"] == "normal")
    noise_count = sum(1 for _, s in scored if s["level"] == "noise")

    print(f"📊 总共: {total_count}篇 | 🔴{focus_count} 🟡{normal_count} ⚪{noise_count}", flush=True)

    # ── Step 5: 跨日重复检测（在保存缓存之前！）──
    all_urls = [a.url for a in all_articles]
    repeat_check = check_cross_day_repetition(all_urls, config)

    # ── Step 6: 保存URL缓存（检测之后）──
    save_url_cache(all_urls, output["url_cache_file"])

    # ── Step 7: 格式化输出 ──
    if repeat_check == "no_new":
        # 计算新文章数
        from lib.dedup import load_url_cache
        import json
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_path = os.path.join(base, output["url_cache_file"])
        yesterday_urls = load_url_cache(cache_path)
        new_count = len(set(all_urls) - yesterday_urls) if yesterday_urls else total_count

        brief = format_no_new_brief(
            config, fetch_ok, total_kw,
            time.time() - start_time,
            total_count, new_count, waf_blocked
        )
    else:
        brief = format_brief_v2(
            scored, config,
            fetch_ok, total_kw,
            time.time() - start_time,
            waf_blocked,
            len(probe_articles)
        )

    # ── 写入文件 ──
    os.makedirs(os.path.dirname(output["output_file"]), exist_ok=True)
    with open(output["output_file"], "w") as f:
        f.write(brief)
    with open(output["latest_file"], "w") as f:
        f.write(brief)

    elapsed_total = time.time() - start_time
    print(f"\n📄 早报已写入 {output['output_file']} ({len(brief)} chars, {elapsed_total:.0f}s)", flush=True)
    print(f"\n{brief}", flush=True)


if __name__ == "__main__":
    main()
