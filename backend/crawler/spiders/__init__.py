"""
爬虫子模块
"""
from .who_spider import WhoSpider
from .cdc_spider import CDCSpider
from .baidu_med_spider import BaiduMedSpider
from .tieba_spider import TiebaSpider

__all__ = ["WhoSpider", "CDCSpider", "BaiduMedSpider", "TiebaSpider"]
