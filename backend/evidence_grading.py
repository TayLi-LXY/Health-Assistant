"""
证据分级模块 - 参考GRADE系统设计
根据来源权威性、内容时效性、文档类型等维度计算证据等级
"""
from typing import Dict, Any, Tuple
from datetime import datetime
from models import EvidenceLevel


# 权威来源白名单及基础分值 (0-100)
AUTHORITY_SCORES = {
    # Level 4: 顶级权威机构
    "who.int": 100,
    "cdc.gov": 98,
    "nih.gov": 95,
    "cdc.gov.cn": 95,
    "nhc.gov.cn": 95,
    "gov.cn": 90,
    # Level 3: 知名医疗机构
    "mayoclinic.org": 88,
    "mayoclinic.org.cn": 88,
    "webmd.com": 75,
    "medlineplus.gov": 85,
    "clevelandclinic.org": 82,
    "harvard.edu": 85,
    "healthline.com": 70,
    # Level 2: 信誉良好的健康资讯
    "dxy.cn": 65,
    "baikemy.com": 65,
    "chunyuyisheng.com": 60,
    "wiki.cn": 55,
    "baike.baidu.com": 52,
    # Level 1: 社区/论坛/偏方
    "tieba.baidu.com": 35,
    "default": 40,
}

# 文档类型关键词加分
DOC_TYPE_BONUS = {
    "guideline": 15,           # 临床指南
    "systematic review": 12,   # 系统综述
    "meta-analysis": 12,       # 荟萃分析
    "clinical trial": 10,      # 临床试验
    "fact sheet": 8,           # 事实清单
    "official": 10,            # 官方发布
    "encyclopedia": 5,         # 百科
    "forum_post": -5,          # 论坛帖（降分）
}


def _extract_domain(url: str) -> str:
    """从URL提取域名"""
    if not url:
        return "default"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # 去掉www前缀
        if domain.startswith("www."):
            domain = domain[4:]
        return domain if domain else "default"
    except Exception:
        return "default"


def _get_authority_score(source_url: str, source_name: str) -> Tuple[float, str]:
    """
    基于来源权威性计算得分
    返回: (分数, 解释)
    """
    domain = _extract_domain(source_url)
    score = AUTHORITY_SCORES.get(domain, AUTHORITY_SCORES["default"])
    
    # 通过source_name补充判断
    name_lower = (source_name or "").lower()
    if "who" in name_lower or "世界卫生组织" in name_lower:
        score = max(score, 98)
    if "cdc" in name_lower or "疾控" in name_lower:
        score = max(score, 95)
    if "mayo" in name_lower or "梅奥" in name_lower:
        score = max(score, 85)
    
    explanation = f"来源权威性得分: {score}/100 (域名: {domain})"
    return score, explanation


def _get_recency_score(publication_date: str) -> Tuple[float, str]:
    """
    基于内容时效性计算得分
    近1年内高分, 超过5年降低
    """
    if not publication_date:
        return 70, "未获取发布日期，给予默认时效性得分: 70/100"
    
    try:
        # 尝试多种日期格式
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y"]:
            try:
                pub_dt = datetime.strptime(publication_date[:10], fmt)
                break
            except ValueError:
                continue
        else:
            return 70, "日期格式无法解析，默认得分: 70/100"
        
        days_old = (datetime.now() - pub_dt).days
        if days_old < 365:
            score = 95
        elif days_old < 730:
            score = 85
        elif days_old < 1825:  # 5年
            score = 75
        else:
            score = max(60, 80 - (days_old / 365) * 2)
        
        explanation = f"时效性得分: {score}/100 (发布于 {days_old} 天前)"
        return score, explanation
    except Exception:
        return 70, "时效性默认得分: 70/100"


def _get_doc_type_bonus(title: str, content: str) -> Tuple[float, str]:
    """基于文档类型给予额外加分"""
    text = f"{(title or '')} {(content or '')}".lower()
    bonus = 0
    matched = []
    for keyword, points in DOC_TYPE_BONUS.items():
        if keyword in text:
            bonus = max(bonus, points)
            matched.append(keyword)
    
    explanation = f"文档类型加分: +{bonus} ({', '.join(matched) if matched else '无'})"
    return bonus, explanation


def compute_evidence_grade(
    content: str,
    source_url: str = "",
    source_name: str = "",
    publication_date: str = None,
    title: str = "",
    document_type: str = ""
) -> Tuple[EvidenceLevel, float, str]:
    """
    综合计算证据等级
    
    评分公式: 总分 = 权威性*0.5 + 时效性*0.3 + 文档类型*0.2
    等级映射:
    - Level 4: 总分 >= 90
    - Level 3: 80 <= 总分 < 90
    - Level 2: 60 <= 总分 < 80
    - Level 1: 总分 < 60
    
    Returns:
        (EvidenceLevel, score, explanation)
    """
    auth_score, auth_exp = _get_authority_score(source_url, source_name)
    rec_score, rec_exp = _get_recency_score(publication_date or "")
    doc_bonus, doc_exp = _get_doc_type_bonus(title, content)
    
    # 加权计算 (文档类型 bonus 按20分制折算)
    total = auth_score * 0.5 + rec_score * 0.3 + min(doc_bonus, 20) * 0.2
    
    if total >= 90:
        level = EvidenceLevel.HIGH
    elif total >= 80:
        level = EvidenceLevel.MEDIUM
    elif total >= 60:
        level = EvidenceLevel.LOW
    else:
        level = EvidenceLevel.VERY_LOW
    
    explanation = f"证据等级 {level.name}(Level {level.value}): {auth_exp}; {rec_exp}; {doc_exp}"
    
    return level, round(total, 2), explanation
