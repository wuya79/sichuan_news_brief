"""
评分引擎 — 关键词匹配 + 地域加权 + 时效 + 来源分级。
"""
import re
from datetime import datetime, timedelta

from lib.parser import Article


def score_article(article: Article, config: dict, today_str: str = None) -> dict:
    """
    对单篇文章评分，返回 {score, level, matched_high, matched_low, geo, time_bonus, source_bonus}
    level: "focus" (≥70), "normal" (45-69), "noise" (<45)
    """
    scoring = config["scoring"]
    title = article.title
    score = 0
    matched_high = []
    matched_low = []

    # ── 关键词分值 ──
    for kw, pts in scoring.get("high_keywords", {}).items():
        if kw in title:
            score += pts
            matched_high.append(f"{kw}(+{pts})")

    for kw, pts in scoring.get("low_keywords", {}).items():
        if kw in title:
            score += pts
            matched_low.append(f"{kw}({pts})")

    # ── 地域加权 ──
    geo_score = 0
    # boost
    for pat in scoring.get("geo_boost", {}).get("patterns", []):
        if pat in title:
            geo_score += scoring["geo_boost"]["score"]
            break  # 只加一次

    # penalty（仅在不含 boost 地域时检查）
    if geo_score == 0:
        for pat in scoring.get("geo_penalty", {}).get("patterns", []):
            if pat in title:
                geo_score += scoring["geo_penalty"]["score"]
                break

    score += geo_score

    # ── 时效分 ──
    if today_str is None:
        today_str = datetime.now().strftime("%Y-%m-%d")

    time_score = 0
    if article.date == today_str:
        time_score = scoring.get("time_bonus", {}).get("today", 20)
    elif article.date == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
        time_score = scoring.get("time_bonus", {}).get("yesterday", 10)
    else:
        # 检查是否超过阈值
        try:
            article_dt = datetime.strptime(article.date, "%Y-%m-%d")
            cutoff = datetime.now() - timedelta(days=scoring.get("time_penalty_days", 3))
            if article_dt < cutoff:
                time_score = scoring.get("time_penalty", -20)
        except (ValueError, TypeError):
            pass

    score += time_score

    # ── 来源权重 ──
    source_weights = scoring.get("source_weights", {})
    source_score = source_weights.get(article.source, source_weights.get("默认", 15))
    score += source_score

    # ── 分级 ──
    thresholds = scoring.get("thresholds", {})
    if score >= thresholds.get("focus", 70):
        level = "focus"
    elif score >= thresholds.get("normal", 45):
        level = "normal"
    else:
        level = "noise"

    return {
        "score": score,
        "level": level,
        "matched_high": matched_high,
        "matched_low": matched_low,
        "geo_score": geo_score,
        "time_score": time_score,
        "source_score": source_score,
    }


def score_and_sort(articles: list[Article], config: dict) -> list[tuple[Article, dict]]:
    """批量评分+排序，返回 [(article, score_dict), ...]"""
    today = datetime.now().strftime("%Y-%m-%d")
    scored = []

    for a in articles:
        s = score_article(a, config, today)
        scored.append((a, s))

    scored.sort(key=lambda x: x[1]["score"], reverse=True)
    return scored


def filter_by_level(scored: list[tuple[Article, dict]], level: str) -> list[Article]:
    """按级别筛选"""
    return [a for a, s in scored if s["level"] == level]
