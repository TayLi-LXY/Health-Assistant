"""
Level 2 - 百度医学科普爬虫（500+ 种子，H2/H3 元数据）
策略: 百度百科 baike.baidu.com，URL 可预测
"""
import asyncio
import re
from typing import List, Dict, Any, Optional
from urllib.parse import quote

import aiohttp
from bs4 import BeautifulSoup

from crawler.utils import (
    AsyncCrawler,
    get_safe_session,
    clean_text,
    clean_text_strict,
    save_batch_json,
    load_existing_urls,
    load_and_merge_json,
)
from crawler.spiders.baidu_seeds import SEEDS_500

SOURCE_NAME = "百度百科"
DOCUMENT_TYPE = "encyclopedia"
BAIKE_ITEM_URL = "https://baike.baidu.com/item/{}"


def _extract_publication_date(html: str, soup: BeautifulSoup) -> str:
    """
    提取百科词条的“更新时间/最后修订时间”。
    优先级：
    1) <meta itemprop="dateUpdate"> 或 <meta name="last-modified">
    2) 侧边栏 <dd class="description"> 等容器中的日期（YYYY-M-D）
    3) 全文中 “更新时间/最后修订” 后的日期
    4) 兜底固定值 "2020-01-01"（用于降低百科在时间排序中的权重）
    """
    # ---------- 优先级 1：Meta 标签 ----------
    # <meta itemprop="dateUpdate" content="2024-12-01 10:20:30">
    meta = soup.find("meta", attrs={"itemprop": "dateUpdate"})
    if meta and meta.get("content"):
        m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", meta["content"])
        if m:
            return m.group(1)

    # <meta name="last-modified" content="2024-12-01">
    meta_last = soup.find("meta", attrs={"name": "last-modified"})
    if meta_last and meta_last.get("content"):
        m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", meta_last["content"])
        if m:
            return m.group(1)

    # ---------- 优先级 2：侧边栏 description 区域 ----------
    # 如 <dd class="description">2024-12-01</dd> 或 “创建日期：2024-12-01”
    for dd in soup.find_all("dd", class_=re.compile(r"description")):
        text = dd.get_text(" ", strip=True)
        if not text:
            continue
        m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", text)
        if m:
            return m.group(1)

    # ---------- 优先级 3：全文关键字 + 正则兜底 ----------
    # 在原始 HTML 文本中查找 “更新时间/最后修订” 附近的日期
    # 示例：更新时间：2024-12-01 10:00  或  最后修订  2023-08-09
    pattern = re.compile(r"(更新时间|最后修订)[^0-9]{0,20}(\d{4}-\d{1,2}-\d{1,2})")
    m = pattern.search(html)
    if m:
        return m.group(2)

    # ---------- 优先级 4：固定兜底值 ----------
    # 禁止使用当前时间，统一用 2020-01-01 以降低百科在时间排序中的权重
    return "2020-01-01"


class BaiduMedSpider:
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent

    async def run(
        self,
        output_file: str = "backend/data/baidu_med_encyclopedia.json",
        seeds: Optional[List[str]] = None,
        resume: bool = True,
        max_items: int = 600,
    ) -> List[Dict[str, Any]]:
        seeds = list(dict.fromkeys(seeds or SEEDS_500))[:max_items]
        seen = load_existing_urls(output_file) if resume else set()
        crawler = AsyncCrawler(max_concurrent=self.max_concurrent)
        results = []

        async with get_safe_session() as session:
            for i, kw in enumerate(seeds):
                url = BAIKE_ITEM_URL.format(quote(kw, safe=""))
                if url in seen:
                    continue
                doc = await self._parse_baike(crawler, session, url, kw)
                if doc:
                    results.append(doc)
                    seen.add(url)
                    print(f"[Baidu] [{i+1}/{len(seeds)}] {doc.get('title', '')[:35]}...")
                await asyncio.sleep(0.5)

        existing = [d for d in load_and_merge_json(output_file) if d.get("source_url") not in {r["source_url"] for r in results}]
        merged = existing + results
        save_batch_json(merged, output_file)
        print(f"[Baidu] 共保存 {len(merged)} 篇")
        return merged

    async def _parse_baike(
        self,
        crawler: AsyncCrawler,
        session: aiohttp.ClientSession,
        url: str,
        keyword: str,
    ) -> Optional[Dict[str, Any]]:
        html = await crawler.fetch(session, url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        # 标题
        title = ""
        for el in [soup.select_one(".lemmaWgt-lemmaTitle h1"), soup.select_one("h1")]:
            if el and hasattr(el, "get_text"):
                t = el.get_text(strip=True)
                if t and len(t) < 200:
                    title = t
                    break
        if not title:
            og = soup.find("meta", property="og:title")
            if og and og.get("content"):
                title = og["content"].strip().split("_")[0]
        if not title:
            title = keyword or "百科词条"

        # 正文内容
        content_div = None
        for cls in ["main-content", "J-lemma-content", "lemma-summary"]:
            content_div = soup.find("div", class_=cls)
            if content_div:
                break
        if not content_div:
            paras = soup.find_all("div", class_="para")
            if paras:
                content_div = soup.new_tag("div")
                for p in paras[:30]:
                    content_div.append(p)

        content = ""
        if content_div:
            content = clean_text(str(content_div))
            if len(content) > 80:
                content = clean_text_strict(content)

        if not content:
            paras = soup.find_all("div", class_="para")
            parts = [clean_text(str(p)) for p in paras[:25] if len(clean_text(str(p))) > 15]
            if parts:
                content = clean_text_strict("\n\n".join(parts))

        if len(content) < 30:
            return None

        # publication_date：只代表“最近更新时间”，不代表权威指南发布时间
        publication_date = _extract_publication_date(html, soup)

        return {
            "title": title,
            "content": content,
            "source_url": url,
            "source_name": SOURCE_NAME,
            # 可能为空字符串，但字段含义明确
            "publication_date": publication_date,
            "document_type": DOCUMENT_TYPE,
        }


async def main():
    spider = BaiduMedSpider(max_concurrent=5)
    await spider.run(max_items=550)


if __name__ == "__main__":
    asyncio.run(main())
