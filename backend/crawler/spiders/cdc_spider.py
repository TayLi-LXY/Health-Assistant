import asyncio
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from ..utils import AsyncCrawler, get_safe_session, clean_text, save_batch_json, parse_date, load_existing_urls, load_and_merge_json

# CDC 官网：健康科普、健康提示、专题项目
START_URLS = [
    "https://www.chinacdc.cn/jkkp/crb/",
    "https://www.chinacdc.cn/jkkp/mxfcrb/",
    "https://www.chinacdc.cn/jkkp/mygh/",
    "https://www.chinacdc.cn/jkkp/yyjk/",
    "https://www.chinacdc.cn/jkkp/ggws/",
    "https://www.chinacdc.cn/jkkp/yckz/",
    "https://www.chinacdc.cn/jkkp/hjjk/",
    "https://www.chinacdc.cn/jkts/",
    "https://www.chinacdc.cn/jkts/index_1.html",
    "https://www.chinacdc.cn/jkts/index_2.html",
    "https://www.chinacdc.cn/ztxm/",
    "https://www.chinacdc.cn/ztxm/tzgln/",
    "https://www.chinacdc.cn/jkyj/crb2/",
    "https://www.chinacdc.cn/jkyj/mxfcrxjb2/",
]

SOURCE_NAME = "中国疾控中心"
DOCUMENT_TYPE = "guideline"


class CDCSpider:
    """中国疾控中心爬虫，供 __init__ 和 run_all 调用"""

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent

    async def run(
        self,
        output_file: str = "data/cdc_articles.json",
        max_articles: int = 500,
        resume: bool = True,
    ) -> List[Dict[str, Any]]:
        return await crawl_cdc(output_file, max_articles, self.max_concurrent, resume)


async def crawl_cdc(
    output_file: str = "data/cdc_articles.json",
    max_articles: int = 500,
    max_concurrent: int = 6,
    resume: bool = True,
):
    """主入口函数。支持断点续传。"""
    seen = load_existing_urls(output_file) if resume else set()
    crawler = AsyncCrawler(max_concurrent=max_concurrent)

    async with get_safe_session() as session:
        print(f"🚀 [CDC] 开始扫描 {len(START_URLS)} 个栏目...")
        list_tasks = [fetch_list_page(crawler, session, url) for url in START_URLS]
        results = await asyncio.gather(*list_tasks)

        article_links = set()
        for res in results:
            if res:
                article_links.update(res)

        to_fetch = [u for u in article_links if u not in seen][:max_articles]
        print(f"🧐 [CDC] 待抓取 {len(to_fetch)} 篇（已跳过 {len(seen)}）")

        detail_tasks = [fetch_detail(crawler, session, link) for link in to_fetch]
        articles = await asyncio.gather(*detail_tasks)
        valid_data = [a for a in articles if a]

    existing = [d for d in load_and_merge_json(output_file) if d.get("source_url") not in {r["source_url"] for r in valid_data}]
    merged = existing + valid_data
    if merged:
        save_batch_json(merged, output_file)
        print(f"🎉 [CDC] 共保存 {len(merged)} 篇")
    else:
        print("⚠️ [CDC] 未抓取到有效数据")
    return merged

async def fetch_list_page(crawler, session, url):
    html = await crawler.fetch(session, url)
    if not html: return []
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if "javascript" in href or not href.endswith(".html"):
            continue
        if "index" in href.lower() or "default" in href.lower():
            continue
        full = urljoin(url, href)
        if "chinacdc.cn" in full:
            links.append(full)
    print(f"✅ [CDC List] 发现 {len(links)} 个链接")
    return links

async def fetch_detail(crawler, session, url):
    html = await crawler.fetch(session, url)
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")

    # 标题：CDC 常用 h1-h5、.content_title、.tit 等
    title = ""
    for tag in ["h1", "h2", "h3", "h4", "h5"]:
        el = soup.find(tag)
        if el:
            t = el.get_text(strip=True)
            if len(t) > 2 and len(t) < 200:
                title = t
                break
    if not title:
        for sel in [".content_title", ".tit", ".title", ".article-title", "meta[property='og:title']"]:
            el = soup.select_one(sel)
            if el:
                t = el.get("content", "") if el.name == "meta" else el.get_text(strip=True)
                if t and len(t) > 2:
                    title = t
                    break
    if not title:
        return None

    # 正文：CDC 常用 TRS_Editor、Custom_UnionStyle、xilan_content、xl_content 等
    content_div = None
    for cls in ["TRS_Editor", "Custom_UnionStyle", "xilan_content", "xl_content", "content_main"]:
        content_div = soup.find("div", class_=cls)
        if content_div:
            break
    if not content_div:
        for div in soup.find_all("div", class_=True):
            c = " ".join(div.get("class", [])) if isinstance(div.get("class"), list) else str(div.get("class", ""))
            if "TRS" in c or "xilan" in c or "Custom_Union" in c:
                content_div = div
                break
    if not content_div:
        content_div = soup.find("div", id=lambda x: x and re.search(r"content|zoom|article", str(x), re.I))
    if not content_div:
        # 兜底：取包含正文关键词且文本较多的 div
        for div in soup.find_all("div"):
            txt = div.get_text()
            if len(txt) > 200 and ("温馨提示" in txt or "主要建议" in txt or "健康风险" in txt):
                content_div = div
                break
    content = clean_text(str(content_div) if content_div else html)
    if len(content) < 50:
        return None

    # 日期：meta PubDate 或 时间：2026-01-08
    pub_date = ""
    meta = soup.find("meta", {"name": "PubDate"})
    if meta and meta.get("content"):
        pub_date = parse_date(meta["content"])
    if not pub_date:
        m = re.search(r"时间[：:]\s*[\*_]?(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", html)
        if m:
            pub_date = parse_date(m.group(1))
    # 优先从 URL 提取日期（如 t20251105_xxx -> 2025-11-05）
    if not pub_date:
        m = re.search(r"t?(\d{4})[/_]?(\d{2})[/_]?(\d{2})", url)
        if m:
            pub_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if not pub_date:
        pub_date = "2024-01-01"

    return {
        "title": title, "content": content, "source_url": url,
        "source_name": SOURCE_NAME, "publication_date": pub_date,
        "document_type": DOCUMENT_TYPE,
    }

if __name__ == "__main__":
    asyncio.run(CDCSpider().run())