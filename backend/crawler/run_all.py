"""
统一执行所有爬虫，合并输出为知识库可用 JSON
目标: 2000+ 篇，支撑 10,000+ Chunks 向量库
运行: cd backend && python -m crawler.run_all
"""
import asyncio
import json
from pathlib import Path

from crawler.spiders.who_spider import WhoSpider
from crawler.spiders.cdc_spider import CDCSpider
from crawler.spiders.baidu_med_spider import BaiduMedSpider
from crawler.spiders.tieba_spider import TiebaSpider


async def main():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_docs = []

    # 1. WHO 实况报道 + health-topics (Level 4)
    print("\n=== [Level 4] WHO 实况报道 + 健康主题 ===")
    try:
        who = WhoSpider(max_concurrent=5)
        docs = await who.run(
            str(data_dir / "who_fact_sheets.json"),
            resume=True,
            max_items=400,
        )
        all_docs.extend(docs)
    except Exception as e:
        print(f"[WHO] 异常: {e}")

    # 2. 中国疾控中心 (Level 3)
    print("\n=== [Level 3] 中国疾控中心 ===")
    try:
        cdc = CDCSpider(max_concurrent=6)
        docs = await cdc.run(
            str(data_dir / "cdc_articles.json"),
            max_articles=500,
            resume=True,
        )
        all_docs.extend(docs)
    except Exception as e:
        print(f"[CDC] 异常: {e}")

    # 3. 百度百科医典 (Level 2)
    print("\n=== [Level 2] 百度百科医典 ===")
    try:
        baidu = BaiduMedSpider(max_concurrent=5)
        docs = await baidu.run(
            str(data_dir / "baidu_med_encyclopedia.json"),
            resume=True,
            max_items=550,
        )
        all_docs.extend(docs)
    except Exception as e:
        print(f"[Baidu] 异常: {e}")

    # 4. 贴吧 (Level 1 噪音数据)
    print("\n=== [Level 1] 百度贴吧（养生/民间偏方） ===")
    try:
        tieba = TiebaSpider(max_concurrent=4)
        docs = await tieba.run(
            str(data_dir / "tieba_posts.json"),
            max_posts=100,
        )
        all_docs.extend(docs)
    except Exception as e:
        print(f"[Tieba] 异常: {e}")

    # 去重（按 source_url）
    seen = set()
    unique = []
    for d in all_docs:
        u = d.get("source_url")
        if u and u not in seen:
            seen.add(u)
            unique.append(d)

    merged_path = data_dir / "crawled_knowledge_base.json"
    with open(merged_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    print(f"\n合计 {len(unique)} 篇，已合并到 {merged_path}")


if __name__ == "__main__":
    asyncio.run(main())
