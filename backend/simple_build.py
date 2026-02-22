"""
简化的知识库构建脚本
使用基本的向量化方法，避免复杂的模型下载问题
"""

import json
import os
from pathlib import Path
from tqdm import tqdm

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# 设置国内镜像源
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 模型选择
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_STORE_DIR = "knowledge_base/chroma_db_small"


def load_processed_chunks():
    """加载预处理后的 chunks"""
    chunks_path = Path("data/processed_kb_chunks.json")
    if not chunks_path.exists():
        print(f"错误：找不到预处理文件 {chunks_path}")
        return []
    
    print(f"加载预处理文件：{chunks_path}")
    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    
    print(f"成功加载 {len(chunks)} 个 chunks")
    return chunks


def build_vector_store():
    """构建向量库"""
    print("开始构建向量库...")
    
    # 1. 加载数据
    chunks = load_processed_chunks()
    if not chunks:
        print("错误：没有数据可处理")
        return None
    
    # 2. 创建向量存储目录
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
    
    # 3. 初始化 Embeddings
    print(f"初始化嵌入模型：{EMBEDDING_MODEL}")
    print("注意：首次运行会下载模型，可能需要一些时间...")
    
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        print("嵌入模型初始化成功！")
    except Exception as e:
        print(f"初始化嵌入模型时出错：{e}")
        print("尝试使用备用方法...")
        return None
    
    # 4. 初始化 Chroma
    print(f"初始化 Chroma 向量库：{VECTOR_STORE_DIR}")
    vector_store = Chroma(
        persist_directory=VECTOR_STORE_DIR,
        embedding_function=embeddings,
        collection_name="health_kb"
    )
    
    # 5. 分批处理
    batch_size = 32
    total_chunks = len(chunks)
    print(f"开始批量插入向量库，共 {total_chunks} 个 chunks，批大小：{batch_size}")
    
    for i in tqdm(range(0, total_chunks, batch_size), desc="向量化进度"):
        batch = chunks[i : i + batch_size]
        
        batch_texts = [c["content"] for c in batch]
        batch_metadatas = []
        
        for c in batch:
            batch_metadatas.append({
                "source_url": c.get("source_url", ""),
                "title": c.get("title", ""),
                "chunk_id": c.get("chunk_id", ""),
                "chunk_index": c.get("chunk_index", 0),
                "document_type": c.get("document_type", "unknown")
            })
        
        try:
            vector_store.add_texts(texts=batch_texts, metadatas=batch_metadatas)
        except Exception as e:
            print(f"插入批次 {i//batch_size + 1} 时出错：{e}")
            continue
    
    # 6. 持久化
    vector_store.persist()
    print(f"✅ 向量库构建完成！")
    print(f"📁 向量库保存位置：{VECTOR_STORE_DIR}")
    
    # 7. 验证
    count = vector_store._collection.count()
    print(f"📊 向量库中包含 {count} 个文档")
    
    return vector_store


def main():
    print("=== 健康知识库构建脚本 ===")
    print("使用国内镜像源下载模型，带进度条显示")
    print("=" * 50)
    
    vector_store = build_vector_store()
    
    if vector_store:
        print("\n🎉 构建成功！")
        print("\n如何使用知识库：")
        print("1. 启动后端服务：python -m uvicorn main:app --reload")
        print("2. 访问前端：http://localhost:5173")
        print("3. 测试检索功能：在前端输入健康问题")
    else:
        print("\n❌ 构建失败，请检查错误信息")


if __name__ == "__main__":
    main()
