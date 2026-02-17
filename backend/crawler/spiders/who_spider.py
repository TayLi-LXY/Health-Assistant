"""
Level 4 - 世界卫生组织 WHO 全站爬虫
- 修复正文解析：sf-detail-body_content、sf-content-block，剔除导航占位符
- 全站式抓取：fact-sheets + health-topics A-Z 主题页
"""
import asyncio
import re
from typing import List, Dict, Any, Optional, Set

import httpx
from bs4 import BeautifulSoup

from crawler.utils import (
    clean_text,
    clean_text_strict,
    parse_date,
    save_batch_json,
    load_existing_urls,
    load_and_merge_json,
)

BASE_URL = "https://www.who.int"
ZH = "https://www.who.int/zh"
FACT_SHEETS_LIST = "https://www.who.int/news-room/fact-sheets"
HEALTH_TOPICS = "https://www.who.int/zh/health-topics"
ZH_FACT_DETAIL = "https://www.who.int/zh/news-room/fact-sheets/detail/"
SOURCE_NAME = "世界卫生组织 WHO"
DOCUMENT_TYPE = "fact_sheet"

# 正文选择器优先级（WHO Sitefinity 结构）
BODY_SELECTORS = [
    "div.sf-detail-body_content",
    "div.sf-content-block",
    "div.sf-richtext",
    "div[class*='sf-detail']",
    "div[class*='content-block']",
    "div.reading",
    "article",
]


class WhoSpider:
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        async with self.semaphore:
            for attempt in range(3):
                try:
                    r = await client.get(url, timeout=30.0)
                    r.raise_for_status()
                    return r.text
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        print(f"[WHO fetch error] {url}: {e}")
        return None

    async def fetch_fact_sheet_links(self, client: httpx.AsyncClient) -> Set[str]:
        """从 fact-sheets 列表页提取详情链接"""
        html = await self._fetch(client, FACT_SHEETS_LIST)
        if not html:
            return set()
        soup = BeautifulSoup(html, "lxml")
        slugs = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/news-room/fact-sheets/detail/" in href:
                parts = href.rstrip("/").split("/detail/")
                if len(parts) >= 2 and parts[-1]:
                    slugs.add(parts[-1].split("?")[0])
        return {ZH_FACT_DETAIL + s for s in slugs}

    async def fetch_health_topic_links(self, client: httpx.AsyncClient) -> Set[str]:
        """从 health-topics 索引页提取主题链接（含 fact-sheets）"""
        html = await self._fetch(client, HEALTH_TOPICS)
        if not html:
            return set()
        soup = BeautifulSoup(html, "lxml")
        links = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/health-topics/" in href and "mega-menu" not in href and "countries" not in href:
                full = href if href.startswith("http") else BASE_URL + href
                if "who.int" in full:
                    links.add(full)
        return links

    def _extract_body(self, soup: BeautifulSoup, html: str) -> str:
        """精准提取主正文，排除 All topics 等导航"""
        candidates = []
        # 1. 按 class 选择
        for div in soup.find_all("div", class_=True):
            c = " ".join(div.get("class", [])) if isinstance(div.get("class"), list) else str(div.get("class", ""))
            if any(x in c for x in ["sf-detail", "sf-content", "sf-richtext", "content-block", "reading"]):
                raw = clean_text(str(div))
                if len(raw) > 150 and raw.strip() not in ("All topics", "所有主题"):
                    candidates.append((len(raw), raw))
        # 2. article 标签
        for art in soup.find_all("article"):
            raw = clean_text(str(art))
            if len(raw) > 150 and "All topics" not in raw[:100]:
                candidates.append((len(raw), raw))
        # 3. 包含 WHO 正文特征（重要事实、概述等）
        for div in soup.find_all("div"):
            t = div.get_text()
            if ("重要事实" in t or "概述" in t or "风险因素" in t) and len(t) > 200:
                raw = clean_text(str(div))
                if len(raw) > 200:
                    candidates.append((len(raw), raw))

        if not candidates:
            return ""
        # 取最长的合理正文
        candidates.sort(key=lambda x: -x[0])
        for _, raw in candidates:
            if raw.count("http") <= raw.count("。") + 5:
                return clean_text_strict(raw)
        return clean_text_strict(candidates[0][1])

    async def parse_detail(
        self, client: httpx.AsyncClient, url: str, skip_if_empty: bool = True
    ) -> Optional[Dict[str, Any]]:
        html = await self._fetch(client, url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        title = ""
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
        if not title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        content = self._extract_body(soup, html)
        if skip_if_empty and (not content or len(content) < 80):
            return None
        if content in ("All topics", "所有主题"):
            return None

        date_text = " ".join(
            n if isinstance(n, str) else getattr(n, "get_text", lambda: "")()
            for n in soup.find_all(string=re.compile(r"\d{4}[-年]\d{1,2}"))
        )
        pub_date = parse_date(date_text) if date_text else ""

        return {
            "title": title or "WHO 实况报道",
            "content": content or "",
            "source_url": url,
            "source_name": SOURCE_NAME,
            "publication_date": pub_date,
            "document_type": DOCUMENT_TYPE,
        }

    async def run(
        self,
        output_file: str = "backend/data/who_fact_sheets.json",
        resume: bool = True,
        max_items: int = 1000,
    ) -> List[Dict[str, Any]]:
        seen = load_existing_urls(output_file) if resume else set()
        all_links: Set[str] = set()

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"},
        ) as client:
            print("[WHO] 采集 fact-sheets 链接...")
            all_links.update(await self.fetch_fact_sheet_links(client))
            print("[WHO] 采集 health-topics 链接...")
            topic_links = await self.fetch_health_topic_links(client)
            all_links.update(topic_links)
            # 主题页也可能是详情页，或链到 fact-sheet
            to_fetch = [u for u in all_links if u not in seen][:max_items]
            print(f"[WHO] 待抓取 {len(to_fetch)} 个链接（已跳过 {len(seen)}）")

            results = []
            for i, url in enumerate(to_fetch):
                doc = await self.parse_detail(client, url)
                if doc and doc.get("content"):
                    results.append(doc)
                    seen.add(url)
                    print(f"[WHO] [{i+1}/{len(to_fetch)}] {doc.get('title', '')[:35]}...")
                await asyncio.sleep(0.3)

        # 合并已有数据
        existing = [d for d in load_and_merge_json(output_file) if d.get("source_url") not in {r["source_url"] for r in results}]
        merged = existing + results
        save_batch_json(merged, output_file)
        print(f"[WHO] 共保存 {len(merged)} 篇")
        return merged


async def main():
    spider = WhoSpider(max_concurrent=5)
    await spider.run(max_items=800)


if __name__ == "__main__":
    asyncio.run(main())
