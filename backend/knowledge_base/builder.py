"""
健康知识库构建与预处理
- 数据清洗与结构化切分（chunk）
- 向量化与索引（Chroma）
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from tqdm import tqdm  # 引入进度条库

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# 【模型选择】默认改用更轻量的多语言 MiniLM，加载更快、内存占用更低
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 简单缓存，避免每次请求都重新加载 Embedding 模型和 Chroma 索引
_VECTOR_STORE_CACHE: Optional[Chroma] = None


def load_crawled_health_data(kb_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    从爬虫合并后的 KB 加载原始文档列表。
    默认路径：backend/data/crawled_knowledge_base.json
    """
    if kb_path is None:
        kb_path = Path(__file__).parent.parent / "data" / "crawled_knowledge_base.json"
    if not kb_path.exists() or kb_path.stat().st_size <= 0:
        return []
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_processed_kb_chunks(chunks_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    加载已清洗切分好的 chunk 文件（若存在）。
    默认路径：backend/data/processed_kb_chunks.json
    """
    if chunks_path is None:
        chunks_path = Path(__file__).parent.parent / "data" / "processed_kb_chunks.json"
    if not chunks_path.exists() or chunks_path.stat().st_size <= 0:
        return []
    try:
        with open(chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


# 参考文献/脚注标记（兼容缺失右括号的异常格式，如 "[2 按摩..." 或 "[2"）
_REF_MARK_PAT = re.compile(r"[\[\［]\s*\d+(?:\s*-\s*\d+)?\s*[\]\］]?")
_BAIKE_NOISE_PATTERNS = [
    # 百度百科/百科类常见噪声
    re.compile(r"\b播报\s*编辑\b"),
    re.compile(r"\b展开\b"),
    re.compile(r"\b目录\b"),
    re.compile(r"\b参考来源\b[:：]?"),
]


def clean_kb_content(text: str) -> str:
    """
    对 KB 内容做“轻量但有效”的清洗：
    - 复用爬虫侧 clean_text_strict
    - 去掉百科常见噪声短语
    - 去掉脚注引用标记
    """
    if not text or not str(text).strip():
        return ""

    # 延迟导入，避免在不使用爬虫工具时引入额外依赖
    # 如果运行报错找不到 crawler，请确保 crawler 文件夹在 python path 中，
    # 或者简单起见，这里可以将 import 放在 try-except 块中，或直接复制 clean_text_strict 函数过来
    try:
        from crawler.utils import clean_text_strict
        cleaned = clean_text_strict(str(text))
    except ImportError:
        # 如果找不到模块，做一个简单的清洗兜底
        cleaned = str(text).strip()

    cleaned = _REF_MARK_PAT.sub("", cleaned)
    for pat in _BAIKE_NOISE_PATTERNS:
        cleaned = pat.sub("", cleaned)

    # 再做一次空白归一化
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def chunk_documents(docs: List[Dict], chunk_size: int = 500, overlap: int = 50) -> List[Dict]:
    """将文档切分为chunk"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )
    chunks = []
    print(f"正在切分文档，共 {len(docs)} 篇...")
    for doc in tqdm(docs, desc="文档切分"):
        content = clean_kb_content(doc.get("content", ""))
        if not content:
            continue
        pieces = splitter.split_text(content)
        source_url = str(doc.get("source_url", "") or "")
        title = str(doc.get("title", "") or "")
        base_key = f"{source_url}||{title}".encode("utf-8", errors="ignore")
        base_hash = hashlib.sha1(base_key).hexdigest()

        for idx, p in enumerate(pieces):
            if len(p.strip()) < 20: # 过滤太短的碎片
                continue
            chunks.append({
                **{k: v for k, v in doc.items() if k != "content"},
                "chunk_index": idx,
                "chunk_id": f"{base_hash}#{idx}",
                "content": p.strip(),
            })
    return chunks


def build_vector_store(
    persist_dir: str = "knowledge_base/chroma_db_small",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Chroma:
    """构建并持久化向量知识库（改进版：带进度条+分批写入）"""
    os.makedirs(persist_dir, exist_ok=True)

    print(f"准备构建向量库，使用模型: {embedding_model}")

    # 1. 加载数据
    chunks = load_processed_kb_chunks()

    # 可选：通过环境变量 KB_CHUNK_LIMIT 控制只使用前 N 条，用于测试/调试
    limit = os.getenv("KB_CHUNK_LIMIT")
    if limit:
        try:
            n = int(limit)
            if n > 0:
                chunks = chunks[:n]
                print(f"⚠ KB_CHUNK_LIMIT={n}，当前仅使用前 {n} 个 chunk 进行向量化。")
        except ValueError:
            print(f"⚠ KB_CHUNK_LIMIT={limit} 非法，忽略该限制，按全量数据构建。")

    if not chunks:
        print("未发现预处理chunk，正在加载原始数据并切分...")
        docs = load_crawled_health_data()
        if not docs:
            print("❌ 错误：没有找到原始数据 (crawled_knowledge_base.json)")
            return None
            
        from config import get_settings
        settings = get_settings()
        chunks = chunk_documents(docs, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)
    
    print(f"数据准备完毕，共 {len(chunks)} 个文本块，准备向量化...")

    # 2. 初始化 Embeddings（轻量模型，加载速度更快）
    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu"}, # 如果有显卡，改成 "cuda" 速度会起飞
        encode_kwargs={"normalize_embeddings": True},
    )
    
    # 3. 初始化 Chroma (连接本地数据库)
    vector_store = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
        collection_name="health_kb"
    )

    # 4. 分批处理（Batch Processing）
    batch_size = 64  # 每次处理64条，稳健不卡顿
    total_chunks = len(chunks)
    
    print("开始批量插入向量库...")
    for i in tqdm(range(0, total_chunks, batch_size), desc="向量化进度"):
        batch = chunks[i : i + batch_size]
        
        batch_texts = [c["content"] for c in batch]
        
        # 构造 metadata
        batch_metadatas = []
        for c in batch:
            batch_metadatas.append({
                "source_url": c.get("source_url", "") or "",
                "title": c.get("title", "") or "",
                "chunk_id": c.get("chunk_id", "") or "",
                "chunk_index": c.get("chunk_index", 0),
                "document_type": c.get("document_type", "unknown")
            })
        
        # 写入当前批次
        vector_store.add_texts(texts=batch_texts, metadatas=batch_metadatas)

    print(f"✅ 恭喜！向量库构建完成！数据已保存至: {persist_dir}")
    return vector_store


def get_vector_store(
    persist_dir: str = "knowledge_base/chroma_db_small",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Chroma:
    """
    加载已构建好的向量知识库（带进程内缓存）。
    - 若尚未构建，请先运行本模块的 main（或调用 build_vector_store）生成向量库。
    """
    global _VECTOR_STORE_CACHE
    if _VECTOR_STORE_CACHE is not None:
        return _VECTOR_STORE_CACHE

    os.makedirs(persist_dir, exist_ok=True)

    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={"device": "cpu",
        },
        encode_kwargs={"normalize_embeddings": True},
    )

    vector_store = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
        collection_name="health_kb",
    )
    _VECTOR_STORE_CACHE = vector_store
    return vector_store


if __name__ == "__main__":
    # 直接运行此文件即可构建
    build_vector_store()