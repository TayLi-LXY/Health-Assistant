"""
验证知识库是否成功构建
"""

from knowledge_base.builder import get_vector_store


def main():
    print("正在验证知识库...")
    
    try:
        # 尝试加载向量库
        vector_store = get_vector_store()
        
        if vector_store:
            # 获取向量库中的文档数量
            count = vector_store._collection.count()
            print(f"✅ 知识库验证成功！")
            print(f"📚 向量库中包含 {count} 个文档")
        else:
            print("❌ 无法加载向量库")
    
    except Exception as e:
        print(f"❌ 验证过程中出现错误: {e}")


if __name__ == "__main__":
    main()
