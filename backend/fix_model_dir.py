"""
修复模型目录结构
"""

import os
import shutil

# 模型信息
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")
MODEL_DIR = os.path.join(CACHE_DIR, f"models--sentence-transformers--{MODEL_NAME}")
SNAPSHOT_DIR = os.path.join(MODEL_DIR, "snapshots")


def main():
    print(f"开始修复模型目录结构: {MODEL_NAME}")
    
    # 检查当前快照目录
    if os.path.exists(SNAPSHOT_DIR):
        files = os.listdir(SNAPSHOT_DIR)
        print(f"当前快照目录内容: {files}")
        
        # 检查是否有 config.json 文件直接在 snapshots 目录中
        if "config.json" in files:
            # 创建一个新的快照子目录
            new_snapshot_dir = os.path.join(SNAPSHOT_DIR, "main")
            os.makedirs(new_snapshot_dir, exist_ok=True)
            
            # 移动所有文件到新目录
            for file_name in files:
                src_path = os.path.join(SNAPSHOT_DIR, file_name)
                dst_path = os.path.join(new_snapshot_dir, file_name)
                
                if os.path.isfile(src_path):
                    print(f"移动文件: {file_name} -> {new_snapshot_dir}")
                    shutil.move(src_path, dst_path)
            
            # 更新 latest 链接
            latest_dir = os.path.join(MODEL_DIR, "refs", "main")
            os.makedirs(os.path.dirname(latest_dir), exist_ok=True)
            
            with open(latest_dir, 'w', encoding='utf-8') as f:
                f.write(new_snapshot_dir)
            
            print(f"\n目录结构已修复！")
            print(f"新的模型路径: {new_snapshot_dir}")
        else:
            print("目录结构已经正确，无需修复")
    else:
        print(f"快照目录不存在: {SNAPSHOT_DIR}")
    
    print("\n现在可以运行知识库构建脚本:")
    print("python knowledge_base/builder.py")


if __name__ == "__main__":
    main()
