#!/usr/bin/env python3
"""
四川电力新闻简报 — 主入口
用法: cd ~/sichuan_news_brief && python3 fetch.py [config_file]
  默认: config.yaml（早报·四川）
  午报: config_afternoon.yaml（重庆+宁夏）
输出: data/brief.md + stdout（供 cron 推送）
"""

import os
import sys
import time

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.firecrawl import load_config, scrape, FirecrawlError
from lib.parser import parse_all
from lib.formatter import format_brief


def load_empty_streak(config: dict) -> int:
    """读取连续空结果计数"""
    path = config["output"]["empty_streak_file"]
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def save_empty_streak(count: int, config: dict):
    """保存连续空结果计数"""
    path = config["output"]["empty_streak_file"]
    with open(path, "w") as f:
        f.write(str(count))


def main():
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = load_config(config_file)
    keywords = config.get("keywords", [])
    interval = config["firecrawl"]["request_interval_s"]
    
    label = "午报·重庆宁夏" if "afternoon" in config_file else "早报·四川"
    print(f"📡 电力新闻简报({label}) — 抓取 {len(keywords)} 个关键词...", flush=True)

    # ── 抓取阶段 ──
    results = []
    fetch_ok = 0
    start_time = time.time()

    for i, kw in enumerate(keywords):
        kw_name = kw["name"]
        kw_str = kw["kw"]
        
        if i > 0:
            time.sleep(interval)

        try:
            html = scrape(kw_str, config)
            if html:
                results.append((kw_name, html))
                fetch_ok += 1
                print(f"  ✅ {kw_name}", flush=True)
            else:
                print(f"  ⚠️ {kw_name}: 空响应", flush=True)
        except FirecrawlError as e:
            print(f"  ❌ {kw_name}: {e}", flush=True)
        except Exception as e:
            print(f"  ❌ {kw_name}: 未知错误 {e}", flush=True)

    elapsed = time.time() - start_time

    # ── 解析阶段 ──
    articles = parse_all(results, config)
    article_count = len(articles)

    # ── 空结果计数 ──
    empty_streak = load_empty_streak(config)
    if article_count == 0:
        empty_streak += 1
    else:
        empty_streak = 0
    save_empty_streak(empty_streak, config)

    # ── 格式化输出 ──
    brief = format_brief(
        articles, config,
        fetch_ok=fetch_ok,
        fetch_total=len(keywords),
        elapsed_s=elapsed,
        empty_streak=empty_streak,
    )

    # ── 写入文件 ──
    output_file = config["output"]["output_file"]
    latest_file = config["output"]["latest_file"]
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w") as f:
        f.write(brief)
    with open(latest_file, "w") as f:
        f.write(brief)

    print(f"\n📄 简报已写入 {output_file} ({len(brief)} chars)", flush=True)
    print(f"   {article_count} 篇文章, {fetch_ok}/{len(keywords)} 关键词成功, {elapsed:.0f}s", flush=True)
    
    # ── 输出给 cron ──
    print(f"\n{brief}", flush=True)


if __name__ == "__main__":
    main()
