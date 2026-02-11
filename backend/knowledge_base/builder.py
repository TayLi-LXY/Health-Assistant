"""
健康知识库构建与预处理
- 数据源选择与获取
- 数据清洗与结构化
- 向量化与索引
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# 使用轻量级中文embedding模型
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


def load_sample_health_data() -> List[Dict[str, Any]]:
    """
    加载示例健康数据（项目内置）
    实际项目中可替换为爬虫或API获取的数据
    """
    data_path = Path(__file__).parent.parent / "data" / "health_knowledge.json"
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # 内置示例数据 - 模拟从WHO、CDC、Mayo Clinic等来源
    return [
        {
            "content": "高血压患者的饮食建议：减少钠盐摄入，每日不超过5克；增加钾的摄入，多吃蔬菜水果；控制体重，保持BMI在正常范围；限制饮酒；采用DASH饮食（多吃全谷物、蔬菜、水果、低脂奶制品）。世界卫生组织建议成年人每日钠摄入量应低于2克。",
            "source_url": "https://www.who.int/health-topics/hypertension",
            "source_name": "世界卫生组织 WHO",
            "publication_date": "2024-01-15",
            "title": "高血压预防与饮食指南",
            "document_type": "guideline"
        },
        {
            "content": "发烧的常见原因包括感染（病毒或细菌）、炎症、药物反应等。一般建议：体温38.5°C以下可物理降温；38.5°C以上可考虑服用退热药如对乙酰氨基酚或布洛芬。儿童用药需按体重计算剂量。如持续高热超过3天或伴有严重症状，应及时就医。",
            "source_url": "https://www.mayoclinic.org/fever",
            "source_name": "Mayo Clinic",
            "publication_date": "2023-08-20",
            "title": "发烧的症状与治疗",
            "document_type": "health_article"
        },
        {
            "content": "头痛的常见类型：紧张性头痛（头周箍紧感）、偏头痛（单侧搏动性痛）、丛集性头痛（眼周剧烈疼痛）。太阳穴附近跳痛常与偏头痛或紧张性头痛相关。缓解方法：休息、冷敷、避免强光噪音；可服用非处方止痛药。反复发作或剧烈头痛应就医检查。",
            "source_url": "https://www.cdc.gov/headaches",
            "source_name": "美国疾控中心 CDC",
            "publication_date": "2023-06-10",
            "title": "头痛类型与自我管理",
            "document_type": "fact sheet"
        },
        {
            "content": "腹痛可能由消化不良、肠胃炎、便秘等引起。轻度腹痛可先观察：避免油腻辛辣食物，少量多餐，适当补充水分。若伴发热、持续加重、呕吐、便血等应尽快就医。儿童腹痛需特别谨慎，不明原因腹痛不建议自行用药。",
            "source_url": "https://www.healthline.com/abdominal-pain",
            "source_name": "Healthline",
            "publication_date": "2023-05-01",
            "title": "腹痛的常见原因与应对",
            "document_type": "health_article"
        },
        {
            "content": "感冒是上呼吸道病毒感染，多为自限性疾病。建议：多休息、多饮水；可服用对症药物如退热药、止咳药；抗生素对病毒无效，切勿滥用。一般7-10天可自愈。若出现高热不退、呼吸困难、持续咳嗽超过2周应就医。",
            "source_url": "https://www.cdc.gov/flu",
            "source_name": "美国疾控中心 CDC",
            "publication_date": "2024-01-01",
            "title": "感冒与流感指南",
            "document_type": "guideline"
        },
        {
            "content": "糖尿病患者饮食管理要点：控制总热量，均衡营养；选择低血糖指数食物；定时定量进餐；限制精制糖和饱和脂肪。WHO建议成年人游离糖摄入不超过总能量的10%。规律运动有助于血糖控制。",
            "source_url": "https://www.who.int/diabetes",
            "source_name": "世界卫生组织 WHO",
            "publication_date": "2023-11-20",
            "title": "糖尿病饮食建议",
            "document_type": "guideline"
        },
        {
            "content": "失眠的应对策略：建立规律作息；睡前避免咖啡因和屏幕；营造适宜睡眠环境；可尝试放松技巧如深呼吸。短期失眠可考虑非处方助眠产品，但不宜长期使用。慢性失眠建议咨询医生，排除躯体或心理疾病。",
            "source_url": "https://www.mayoclinic.org/sleep",
            "source_name": "Mayo Clinic",
            "publication_date": "2023-09-15",
            "title": "失眠与睡眠卫生",
            "document_type": "health_article"
        },
        {
            "content": "咳嗽分为急性（3周内）和慢性。急性咳嗽多由感冒引起，可多饮水、蜂蜜水缓解。止咳药需根据是否有痰选择。咳嗽超过3周或伴咯血、发热、气促应就医。儿童咳嗽需谨慎使用镇咳药，应遵医嘱。",
            "source_url": "https://www.medlineplus.gov/cough.html",
            "source_name": "MedlinePlus",
            "publication_date": "2023-04-01",
            "title": "咳嗽的自我管理",
            "document_type": "health_article"
        },
    ]


def chunk_documents(docs: List[Dict], chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
    """将文档切分为chunk"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )
    chunks = []
    for doc in docs:
        content = doc.get("content", "")
        if not content:
            continue
        pieces = splitter.split_text(content)
        for p in pieces:
            if len(p.strip()) < 20:
                continue
            chunks.append({
                **{k: v for k, v in doc.items() if k != "content"},
                "content": p.strip(),
            })
    return chunks


def build_vector_store(
    persist_dir: str = "knowledge_base/chroma_db",
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
) -> Chroma:
    """构建并持久化向量知识库"""
    os.makedirs(persist_dir, exist_ok=True)
    
    docs = load_sample_health_data()
    chunks = chunk_documents(docs)
    
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
    )
    
    texts = [c["content"] for c in chunks]
    metadatas = [
        {
            "source_url": c.get("source_url", ""),
            "source_name": c.get("source_name", ""),
            "publication_date": c.get("publication_date", ""),
            "title": c.get("title", ""),
            "document_type": c.get("document_type", ""),
        }
        for c in chunks
    ]
    
    vector_store = Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        persist_directory=persist_dir,
    )
    return vector_store


def get_vector_store(persist_dir: str = None) -> Chroma:
    """获取已存在的向量库，若不存在则构建"""
    from langchain_community.embeddings import HuggingFaceEmbeddings
    
    if persist_dir is None:
        persist_dir = str(Path(__file__).parent.parent / "knowledge_base" / "chroma_db")
    
    embedding_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"},
    )
    
    if Path(persist_dir).exists() and any(Path(persist_dir).iterdir()):
        return Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
        )
    
    return build_vector_store(persist_dir=persist_dir, embedding_model=embedding_model)
