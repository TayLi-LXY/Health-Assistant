"""构建健康知识库向量索引"""
import sys
from pathlib import Path

# 将 backend 加入 path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    import os
    os.chdir(backend_dir)
    print("正在构建知识库，首次运行将下载 embedding 模型，请稍候...")
    from knowledge_base.builder import build_vector_store
    persist_dir = str(backend_dir / "knowledge_base" / "chroma_db")
    build_vector_store(persist_dir=persist_dir)
    print("知识库构建完成！")
