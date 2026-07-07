"""
WAF检测 — 检测Firecrawl返回是否被阿里云WAF拦截。
"""

WAF_SIGNATURES = [
    "aliyun_waf",
    "renderData",
    "Access Verification",
    "访问验证",
    "滑动验证",
    "nc-container",
    "initAliyunCaptcha",
    "aliyunCaptcha",
]


def is_waf_blocked(html: str) -> bool:
    """检查HTML是否包含WAF验证页面特征"""
    if not html:
        return False

    for sig in WAF_SIGNATURES:
        if sig in html:
            return True

    # 额外检查：如果内容很短（<500字符）且包含验证相关关键词
    if len(html) < 500:
        short_sigs = ["验证", "verification", "captcha"]
        for sig in short_sigs:
            if sig.lower() in html.lower():
                return True

    return False


def check_batch(results: list[tuple[str, str]]) -> list[str]:
    """
    批量检查WAF拦截。
    results: [(keyword_name, html), ...]
    返回被拦截的关键词名称列表。
    """
    blocked = []
    for name, html in results:
        if is_waf_blocked(html):
            blocked.append(name)
    return blocked
