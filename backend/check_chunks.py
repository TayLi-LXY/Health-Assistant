"""
检查预处理后的 chunks 文件
"""

import json


def main():
    print("正在检查预处理后的 chunks 文件...")
    
    try:
        with open('data/processed_kb_chunks.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"预处理后的 chunks 数量: {len(data)}")
        
        if data:
            print(f"第一个 chunk 的长度: {len(data[0].get('content', ''))}")
            print(f"第一个 chunk 的内容预览:")
            print(data[0].get('content', '')[:200] + '...')
            print(f"\n前 5 个 chunk 的标题:")
            for i, chunk in enumerate(data[:5]):
                title = chunk.get('title', '无标题')
                print(f'{i+1}. {title[:50]}...')
        
    except Exception as e:
        print(f"检查过程中出现错误: {e}")


if __name__ == "__main__":
    main()
