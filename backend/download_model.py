"""
手动下载模型到本地，使用国内镜像源和进度条
"""

import os
import requests
from tqdm import tqdm
import zipfile
import shutil

# 模型信息
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MODEL_URL = f"https://hf-mirror.com/sentence-transformers/{MODEL_NAME}/resolve/main"
CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")
MODEL_DIR = os.path.join(CACHE_DIR, f"models--sentence-transformers--{MODEL_NAME}")
SNAPSHOT_DIR = os.path.join(MODEL_DIR, "snapshots")

# 必要的文件列表
FILES_TO_DOWNLOAD = [
    "config.json",
    "pytorch_model.bin",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "vocab.txt",
    "tokenizer.model"
]


def download_file(url, save_path):
    """下载文件并显示进度条"""
    print(f"正在下载: {os.path.basename(save_path)}")
    
    # 确保目录存在
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    # 发送请求
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    
    # 获取文件大小
    total_size = int(response.headers.get('content-length', 0))
    
    # 下载文件
    with open(save_path, 'wb') as file, tqdm(
        desc=os.path.basename(save_path),
        total=total_size,
        unit='B',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)
    
    print(f"下载完成: {os.path.basename(save_path)}")


def main():
    print(f"开始下载模型: sentence-transformers/{MODEL_NAME}")
    print(f"目标目录: {MODEL_DIR}")
    
    # 创建必要的目录
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    
    # 下载每个文件
    for file_name in FILES_TO_DOWNLOAD:
        try:
            file_url = f"{MODEL_URL}/{file_name}"
            save_path = os.path.join(SNAPSHOT_DIR, file_name)
            
            # 检查文件是否已存在
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                print(f"文件已存在，跳过: {file_name}")
                continue
            
            download_file(file_url, save_path)
        except Exception as e:
            print(f"下载 {file_name} 时出错: {e}")
            continue
    
    # 创建指向快照的链接
    latest_dir = os.path.join(MODEL_DIR, "refs", "main")
    os.makedirs(os.path.dirname(latest_dir), exist_ok=True)
    
    # 获取快照目录的实际路径
    snapshot_name = os.listdir(SNAPSHOT_DIR)[0] if len(os.listdir(SNAPSHOT_DIR)) > 1 else ""
    if snapshot_name:
        actual_snapshot_dir = os.path.join(SNAPSHOT_DIR, snapshot_name)
    else:
        actual_snapshot_dir = SNAPSHOT_DIR
    
    # 创建链接文件
    with open(latest_dir, 'w', encoding='utf-8') as f:
        f.write(actual_snapshot_dir)
    
    print("\n模型下载完成！")
    print(f"模型路径: {actual_snapshot_dir}")
    print("\n现在可以运行知识库构建脚本:")
    print("python knowledge_base/builder.py")


if __name__ == "__main__":
    main()
