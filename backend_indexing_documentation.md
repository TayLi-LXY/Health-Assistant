# 健康助手知识库索引文档

## 1. 项目概述

健康助手是一个基于 RAG（检索增强生成）架构的智能健康问答系统，能够为用户提供基于证据的健康信息和建议。本文档详细说明其知识库的构建过程，包括数据源、预处理流程、字段设计和索引机制。

## 2. 数据源

健康助手整合了多个权威健康数据源，确保信息的全面性和可靠性：

| 数据源 | 文件位置 | 内容类型 | 来源说明 |
|-------|---------|---------|--------|
| 百度医疗百科 | `data/baidu_med_encyclopedia_*.json` | 医疗百科知识 | 百度百科医疗相关条目 |
| CDC 文章 | `data/cdc_articles.json` | 疾病防控指南 | 美国疾病控制与预防中心 |
| 贴吧帖子 | `data/tieba_posts.json` | 患者经验分享 | 百度贴吧健康相关讨论 |
| WebMD 数据 | `data/webmd_data.json` | 医疗资讯 | 国际知名医疗信息网站 |
| WHO  fact sheets | `data/who_fact_sheets_*.json` | 全球健康指南 | 世界卫生组织官方资料 |
| Wikipedia 数据 | `data/wikipedia_data.json` | 医学百科 | 维基百科医学相关条目 |

### 数据合并
所有数据源通过 `merge_data_to_kb.py` 脚本合并到 `backend/data/crawled_knowledge_base.json` 文件中，总文档数约为 3,480 个。

## 3. 预处理流程

预处理流程将原始健康数据转换为适合向量索引的结构化格式：

### 3.1 数据清洗
- 去除百科常见噪声短语（如"播报编辑"、"展开"、"目录"等）
- 移除脚注引用标记（如"[1]"、"[2-3]"等）
- 空白字符归一化
- 过滤过短内容（少于 20 字符）

### 3.2 文本切分
使用 `RecursiveCharacterTextSplitter` 进行智能切分：
- **切分大小**：500 字符
- **重叠部分**：50 字符
- **分隔符优先级**：`\n\n` > `\n` > `。` > `！` > `？` > `.` > `!` > `?` > ` ` > ``

### 3.3 结果文件
预处理结果存储在 `backend/data/processed_kb_chunks.json` 文件中，包含 40,089 个文本块（chunks），文件大小约 38.2 MB。

## 4. 字段设计

每个文本块（chunk）包含以下字段：

| 字段名 | 类型 | 描述 | 示例值 |
|-------|------|------|--------|
| `title` | 字符串 | 原始文档标题 | "高血压"
| `content` | 字符串 | 切分后的文本内容 | "高血压患者应减少钠盐摄入..."
| `source_url` | 字符串 | 原始文档来源 URL | "https://baike.baidu.com/item/高血压"
| `document_type` | 字符串 | 文档类型 | "encyclopedia"
| `chunk_index` | 整数 | 在原始文档中的序号 | 0
| `chunk_id` | 字符串 | 唯一标识符 | "a1b2c3d4#0"

### 字段用途
- **title**：用于显示和快速识别文档主题
- **content**：主要检索内容，包含详细健康信息
- **source_url**：用于溯源和提供证据链接
- **document_type**：用于证据分级和来源可信度评估
- **chunk_index**：用于在需要时重建原始文档
- **chunk_id**：确保每个文本块的唯一性

## 5. 索引机制

### 5.1 向量存储
- **存储引擎**：ChromaDB
- **存储位置**：`backend/knowledge_base/chroma_db_small`
- **索引大小**：约 285.9 MB
- **文档数量**：40,089 个 chunks

### 5.2 向量化方法
采用本地简单向量化方法（基于字符串哈希）：
- **向量维度**：384 维
- **计算方法**：基于文本内容的哈希值生成固定长度向量
- **优点**：无需网络下载，本地运行速度快，适合开发和测试环境

### 5.3 批处理策略
- **批大小**：100 条/批
- **处理速度**：约 6.25 批/秒
- **总处理时间**：约 1 分 04 秒

### 5.4 检索机制
- **相似度计算**：余弦相似度
- **默认返回数**：5 个最相关结果
- **检索速度**：毫秒级响应

## 6. 技术实现细节

### 6.1 核心组件
- **数据合并**：`merge_data_to_kb.py`
- **预处理**：`knowledge_base/builder.py` 中的 `chunk_documents` 函数
- **索引构建**：`minimal_build.py`
- **向量存储**：ChromaDB

### 6.2 关键参数
| 参数 | 值 | 说明 |
|------|-----|------|
| `chunk_size` | 500 | 文本切分大小（字符） |
| `chunk_overlap` | 50 | 切分重叠部分（字符） |
| `batch_size` | 100 | 批量处理大小 |
| `vector_dimension` | 384 | 向量维度 |
| `top_k` | 5 | 默认返回结果数 |

### 6.3 目录结构
```
backend/
├── data/
│   ├── crawled_knowledge_base.json    # 合并后的原始数据
│   └── processed_kb_chunks.json       # 预处理后的 chunks
├── knowledge_base/
│   ├── chroma_db_small/               # 向量索引存储
│   └── builder.py                     # 知识库构建脚本
└── minimal_build.py                   # 简化版索引构建脚本
```

## 7. 使用方法

### 7.1 构建知识库
```bash
# 1. 合并数据源
python merge_data_to_kb.py

# 2. 构建向量索引
python minimal_build.py
```

### 7.2 启动服务
```bash
# 启动后端服务
cd backend
python -m uvicorn main:app --reload

# 启动前端服务
cd frontend
npm install
npm run dev
```

### 7.3 测试检索
```python
from knowledge_base.builder import get_vector_store

# 加载向量库
vector_store = get_vector_store()

# 执行相似度搜索
results = vector_store.similarity_search(
    query="高血压患者的饮食建议",
    k=5
)

# 查看结果
for i, result in enumerate(results):
    print(f"结果 {i+1}:")
    print(f"内容: {result.page_content[:200]}...")
    print(f"来源: {result.metadata.get('source_url', '未知')}")
    print(f"标题: {result.metadata.get('title', '未知')}")
```

## 8. 总结

健康助手知识库构建过程体现了以下特点：

- **数据源多样性**：整合多个权威健康信息来源，确保内容全面性
- **预处理精细化**：通过智能切分和清洗，提高检索准确性
- **字段设计合理**：包含必要的元数据，支持多维度检索和溯源
- **索引机制高效**：采用批量处理和本地向量化，实现快速构建和检索
- **可扩展性强**：支持增量更新和新数据源添加

该知识库为健康助手提供了坚实的数据基础，使其能够为用户提供基于证据的健康信息和建议。

## 9. 后续优化方向

1. **模型升级**：网络条件允许时，切换到 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 模型以提高检索质量
2. **数据扩充**：持续添加最新健康研究成果和指南
3. **证据分级**：基于数据源可信度实现更精细的证据分级
4. **多语言支持**：扩展支持中英文双语检索
5. **性能优化**：针对大规模部署进行索引优化

---

*文档创建时间：2026-02-22*
*适用版本：健康助手 v1.0*
