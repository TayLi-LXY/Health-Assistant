"""
Level 1 - 百度贴吧爬虫（养生吧、民间偏方吧）
目的: 作为 RAG 系统的低可信度/噪音数据
注: 百度贴吧反爬严格(403)，使用 httpx + 完整浏览器头
"""
import asyncio
import re
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup

from crawler.utils import clean_text, clean_text_strict, save_batch_json

SOURCE_NAME = "百度贴吧"
DOCUMENT_TYPE = "forum_post"
TIEBA_KWS = ["养生", "民间偏方"]
BASE_URL = "https://tieba.baidu.com"

# 完整浏览器请求头，降低 403
TIEBA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://tieba.baidu.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


class TiebaSpider:
    def __init__(self, max_concurrent: int = 3):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        async with self.semaphore:
            for attempt in range(3):
                try:
                    r = await client.get(url, headers=TIEBA_HEADERS, timeout=20.0)
                    if r.status_code == 403:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    r.raise_for_status()
                    return r.text
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        print(f"[Tieba fetch error] {url}: {e}")
        return None

    async def fetch_list(
        self, client: httpx.AsyncClient, kw: str, pn: int = 0
    ) -> List[Dict[str, Any]]:
        url = f"{BASE_URL}/f?kw={kw}&ie=utf-8&pn={pn}"
        html = await self._fetch(client, url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        items = []
        for li in soup.select("li.j_thread_list"):
            try:
                tid = li.get("data-tid")
                if not tid:
                    continue
                title_el = li.select_one(".j_th_tit a")
                title = title_el.get_text(strip=True) if title_el else ""
                reply_el = li.select_one(".threadlist_rep_num")
                reply_count = 0
                if reply_el:
                    m = re.search(r"\d+", reply_el.get_text(strip=True))
                    if m:
                        reply_count = int(m.group())
                if title:
                    items.append({"tid": tid, "title": title, "reply_count": reply_count, "kw": kw})
            except Exception:
                continue
        return items

    async def fetch_post(
        self, client: httpx.AsyncClient, tid: str, kw: str
    ) -> Optional[Dict[str, Any]]:
        url = f"{BASE_URL}/p/{tid}"
        html = await self._fetch(client, url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")
        post = (
            soup.select_one(".d_post_content_main")
            or soup.select_one(".p_postlist .d_post")
            or soup.find("div", class_=re.compile(r"d_post_content|post_content"))
        )
        if not post:
            return None

        content = clean_text_strict(clean_text(str(post)))
        if len(content) < 20:
            return None

        title_el = soup.select_one("h3.core_title_txt") or soup.select_one("title")
        title = (title_el.get_text(strip=True).split("_")[0] if title_el else "")[:200]

        return {
            "title": title or "贴吧帖子",
            "content": content,
            "source_url": url,
            "source_name": f"{SOURCE_NAME}-{kw}吧",
            "publication_date": "",
            "document_type": DOCUMENT_TYPE,
        }

    async def run(
        self,
        output_file: str = "backend/data/tieba_posts.json",
        max_posts: int = 100,
    ) -> List[Dict[str, Any]]:
        all_items = []
        seen_tids = set()

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=TIEBA_HEADERS,
        ) as client:
            for kw in TIEBA_KWS:
                for pn in range(0, 150, 50):
                    items = await self.fetch_list(client, kw, pn)
                    for it in items:
                        if it["tid"] not in seen_tids:
                            seen_tids.add(it["tid"])
                            all_items.append(it)
                    await asyncio.sleep(1.0)
                    if len(all_items) >= max_posts * 2:
                        break
                if len(all_items) >= max_posts * 2:
                    break

            all_items.sort(key=lambda x: -x["reply_count"])
            to_fetch = all_items[:max_posts]

            print(f"[Tieba] 待抓取 {len(to_fetch)} 篇主楼...")
            results = []
            for i, it in enumerate(to_fetch):
                doc = await self.fetch_post(client, it["tid"], it.get("kw", TIEBA_KWS[0]))
                if doc:
                    results.append(doc)
                    print(f"[Tieba] [{i+1}/{len(to_fetch)}] {doc.get('title', '')[:30]}...")
                await asyncio.sleep(0.8)

        # 若 403 导致 0 条，生成合成 Level 1 噪音样本用于证据分级测试
        if len(results) == 0:
            print("[Tieba] 爬取失败(403)，生成合成 Level 1 样本用于证据分级测试...")
            results = _synthetic_level1_samples(max_posts)

        save_batch_json(results, output_file)
        print(f"[Tieba] 共保存 {len(results)} 篇")
        return results


def _synthetic_level1_samples(n: int = 50) -> List[Dict[str, Any]]:
    """合成 Level 1 噪音样本（贴吧 403 时的兜底）"""
    samples = [
        {"title": "老偏方：生姜擦头皮治脱发", "content": "奶奶传下来的偏方，用生姜切片每天擦头皮，坚持三个月头发真的多了。很多人试过都有效。"},
        {"title": "喝醋软化血管是真的吗", "content": "听说每天喝一勺醋能软化血管、降血压，我喝了半年感觉头不晕了。不过医生说没科学依据。"},
        {"title": "艾叶泡脚治失眠", "content": "每晚用艾叶煮水泡脚20分钟，睡得很香。邻居大妈教的，说是祖传秘方。"},
        {"title": "生吃大蒜杀菌", "content": "每天早上空腹吃两瓣生蒜，能杀菌防感冒。我冬天没感冒过，不知道是不是大蒜的功劳。"},
        {"title": "蜂蜜水治咳嗽", "content": "咳嗽喝蜂蜜水比吃药管用，特别是晚上咳得睡不着时，喝一口就能缓过来。"},
        {"title": "花椒水治牙痛", "content": "牙疼时用花椒泡水漱口，几分钟就不疼了。土办法但很见效。"},
        {"title": "洋葱放在房间里能防感冒？", "content": "听说在房间四角各放一个切开的洋葱能吸收细菌防感冒，不知道有没有用。"},
        {"title": "红糖姜水治痛经", "content": "来月经时煮红糖姜水喝，肚子暖了就不疼了。我妈一直这么喝。"},
        {"title": "白醋洗头去屑", "content": "洗头时在水里加几勺白醋，头皮屑少了很多。偏方治大病。"},
        {"title": "生土豆片消肿", "content": "摔肿了贴生土豆片，消肿很快。老人都这么用。"},
    ]
    out = []
    for i in range(min(n, len(samples) * 5)):
        s = samples[i % len(samples)]
        out.append({
            "title": s["title"],
            "content": s["content"],
            "source_url": f"https://tieba.baidu.com/p/synthetic_level1_{i}",
            "source_name": f"{SOURCE_NAME}-合成样本",
            "publication_date": "",
            "document_type": DOCUMENT_TYPE,
        })
    return out


async def main():
    spider = TiebaSpider(max_concurrent=3)
    await spider.run(max_posts=100)


if __name__ == "__main__":
    asyncio.run(main())
