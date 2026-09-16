"""
Firecrawl API 封装 — 读取配置、发送请求、超时/重试处理。
"""

import json
import os
import time
import urllib.request
import urllib.error


class FirecrawlError(Exception):
    """Firecrawl 请求失败（非2xx、超时、解析失败）"""
    pass


def load_config(config_path: str = "config.yaml") -> dict:
    """加载 YAML 配置（使用 PyYAML）"""
    import yaml
    with open(config_path) as f:
        return yaml.safe_load(f)


def read_api_key(key_file: str) -> str:
    """从文件读取 API Key"""
    path = os.path.expanduser(key_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"API Key 文件不存在: {path}")
    with open(path) as f:
        return f.read().strip()


def scrape(keyword: str, config: dict):
    """
    对单个关键词执行 Firecrawl scrape。
    返回 raw HTML 字符串；失败抛出 FirecrawlError。
    """
    fc = config["firecrawl"]
    bjx = config["bjx"]
    search_url = bjx["search_url_template"].format(kw=keyword)

    api_key = read_api_key(fc["key_file"])
    body = json.dumps({
        "url": search_url,
        "formats": ["rawHtml"],
        "waitFor": fc["wait_for_ms"]
    }).encode("utf-8")

    req = urllib.request.Request(
        fc["base_url"],
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=fc["timeout_s"]) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise FirecrawlError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise FirecrawlError(f"网络错误: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise FirecrawlError(f"JSON解析失败") from e
    except TimeoutError as e:
        raise FirecrawlError(f"超时 ({fc['timeout_s']}s)") from e
    except Exception as e:
        raise FirecrawlError(f"未知错误: {e}") from e

    if not data.get("success"):
        raise FirecrawlError("API 返回 success=False")

    return data.get("data", {}).get("rawHtml", "")
