"""
爬虫通用工具库
- clean_text / clean_text_strict: HTML 清洗
- parse_date: 日期解析
- save_batch_json / load_existing_urls: 分批保存与断点续传
- AsyncCrawler: 异步爬虫基类（Semaphore 5-8）
"""
import asyncio
import html
import json
import random
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

import aiohttp
from aiohttp import DummyCookieJar
from bs4 import BeautifulSoup
from dateparser import parse as dateparse

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# 非医疗相关样板文案（去除）
BOILERPLATE_PATTERNS = [
    r"选择语言.*?English",
    r"Skip to main content",
    r"Upgrade-Insecure-Requests",
    r"当有自动完成结果时.*?进行选择",
    r"京ICP备\d+[号\-]?\d*",
    r"建议使用\d+\*\d+分辨率",
    r"Copyright\s*©.*?All rights reserved",
    r"版权所有",
    r"联系我们",
    r"网站地图",
    r"隐私政策",
    r"使用条款",
]


def _random_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }


def get_safe_session(timeout: int = 30) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        cookie_jar=DummyCookieJar(),
        timeout=aiohttp.ClientTimeout(total=timeout),
    )


def clean_text(html_content: str) -> str:
    """基础 HTML 清洗，提取纯文本"""
    if not html_content or not str(html_content).strip():
        return ""
    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception:
        soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()
    for sel in ["div.ad", "div.ads", ".advertisement", "ins.adsbygoogle", ".related-links", ".download-section"]:
        for el in soup.select(sel):
            el.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 2:
            continue
        if re.match(r"^[\d\s\-\.\/\\\|]+$", line) and len(line) < 20:
            continue
        lines.append(line)
    return "\n\n".join(lines)


def clean_text_strict(text: str) -> str:
    """
    工业级文本清洗：HTML 实体、非法字符、样板文案。
    """
    if not text:
        return ""
    # 解码 HTML 实体
    text = html.unescape(text)
    # 去除控制字符、零宽字符
    text = "".join(c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\t")
    # 去除样板文案
    for pat in BOILERPLATE_PATTERNS:
        text = re.sub(pat, "", text, flags=re.I | re.DOTALL)
    # 归一化空白
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r" +", " ", text)
    return text


def parse_date(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    patterns = [
        r"(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})[日]?",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        r"(\d{4})\.(\d{1,2})\.(\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            g = m.groups()
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
            try:
                from datetime import date
                date(y, mo, d)
                return f"{y:04d}-{mo:02d}-{d:02d}"
            except ValueError:
                continue
    try:
        parsed = dateparse(text)
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass
    return ""


def _resolve_data_path(filename: str) -> Path:
    current_dir = Path(__file__).parent
    backend_root = current_dir.parent
    clean_filename = filename.replace("backend/", "").replace("backend\\", "")
    if clean_filename.startswith("data"):
        return backend_root / clean_filename
    return backend_root / "data" / clean_filename


def load_existing_urls(filename: str) -> Set[str]:
    """加载已存在 JSON 中的 source_url，用于断点续传"""
    path = _resolve_data_path(filename)
    if not path.exists():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {d.get("source_url") for d in data if d.get("source_url")}
        return set()
    except Exception:
        return set()


def save_batch_json(data: List[Dict[str, Any]], filename: str, batch_size: int = 100) -> None:
    path = _resolve_data_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    if len(data) <= batch_size:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ [Save] 已保存 {len(data)} 条数据到: {path}")
        return

    stem, suffix = path.stem, path.suffix
    for i in range(0, len(data), batch_size):
        chunk = data[i : i + batch_size]
        idx = i // batch_size + 1
        out_path = path.parent / f"{stem}_{idx}{suffix}"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=2)
        print(f"✅ [Save] 分批保存到: {out_path}")


def load_and_merge_json(filename: str) -> List[Dict[str, Any]]:
    """加载 JSON（含分批文件），合并为列表"""
    path = _resolve_data_path(filename)
    base = path.parent / path.stem
    suffix = path.suffix
    results = []
    # 主文件
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                results = json.load(f)
            if isinstance(results, list):
                return results
        except Exception:
            pass
    # 分批文件
    for p in sorted(path.parent.glob(f"{path.stem}_*{suffix}")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                results.extend(data)
        except Exception:
            pass
    return results if isinstance(results, list) else []


class AsyncCrawler:
    """异步爬虫基类：Semaphore 5-8，支持断点续传"""

    def __init__(
        self,
        semaphore: Optional[asyncio.Semaphore] = None,
        max_retries: int = 3,
        max_concurrent: int = 6,
    ):
        self.semaphore = semaphore or asyncio.Semaphore(max_concurrent)
        self.max_retries = max_retries
        self.timeout = aiohttp.ClientTimeout(total=30)

    async def fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        encoding: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        headers = {**_random_headers(), **(extra_headers or {})}
        for attempt in range(self.max_retries):
            async with self.semaphore:
                try:
                    async with session.get(url, headers=headers, timeout=self.timeout) as resp:
                        if resp.status == 404:
                            return None
                        resp.raise_for_status()
                        raw = await resp.read()
                        if encoding:
                            return raw.decode(encoding, errors="replace")
                        ct = resp.headers.get("Content-Type", "").lower()
                        if "gbk" in ct or "gb2312" in ct:
                            return raw.decode("gbk", errors="replace")
                        return raw.decode("utf-8", errors="replace")
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        print(f"❌ [Fetch Error] {url}: {e}")
                    else:
                        await asyncio.sleep(2 ** attempt)
        return None
