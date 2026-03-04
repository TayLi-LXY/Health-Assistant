## 在线健康问答助手（Health-Assistant）

基于 **RAG 检索增强生成、证据分级机制与多轮澄清对话** 的智能健康问答系统。  
系统能够理解用户的健康相关问题，通过多轮交互进行澄清，检索本地健康知识库中的相关证据，并调用大语言模型生成 **附有明确证据来源、证据等级与溯源链接** 的回答。

---

### 核心特性

- **证据分级机制（Level 1–4）**：在后端对每条检索到的证据进行来源权威性、时效性、文档类型等多维评分，并映射为 4 个等级；前端通过徽章与解释文本展示。
- **多轮澄清对话**：通过增强版对话管理器检测问题是否模糊、关键信息是否缺失，并以结构化选项（A/B/C 等）继续追问，最终生成更精确的“重写问题”送入 RAG 流水线。
- **RAG 检索增强生成**：从本地 ChromaDB 向量库中检索最相关的健康知识块，附上证据等级后交给 LLM 生成回答，避免“凭空编造”。
- **可追溯证据展示**：每条回答对应的证据在前端以卡片形式展示，包含来源网站、标题、发布日期、证据等级及“查看来源”链接。
- **对话记录与多会话管理**：前端支持侧边栏展示历史对话，点击即可恢复聊天内容与证据列表。

---

### 技术栈概览

- **后端**
  - Python 3.10+
  - FastAPI
  - LangChain + ChromaDB
  - 自定义证据分级模块与多轮澄清对话管理器
  - Deepseek / OpenAI 兼容 LLM 接入

- **前端**
  - React + Vite
  - ReactMarkdown + remark-gfm（渲染 Markdown 回答）
  - 自定义聊天 UI、证据面板、对话历史侧边栏等

- **知识库与向量检索**
  - 多源健康数据（百度医疗百科、CDC、WHO fact sheets、Wikipedia、WebMD、贴吧等）
  - 本地 ChromaDB 向量库（约 4 万个文本块，384 维向量）

---

### 目录结构（简要）

```text
Health-Assistant/
├── backend/                     # 后端服务与知识库构建
│   ├── main.py                  # FastAPI 入口，定义 /chat 等接口
│   ├── config.py                # 配置（API Key、向量库路径等）
│   ├── models.py                # Pydantic 数据模型与 EvidenceItem
│   ├── evidence_grading.py      # 证据评分与 Level 1–4 分级逻辑
│   ├── dialogue_manager.py      # 多轮澄清对话管理（EnhancedDialogueManager）
│   ├── rag_pipeline.py          # RAG 检索 + LLM 生成整体流程
│   ├── knowledge_base/
│   │   ├── builder.py           # 知识库构建与 get_vector_store
│   │   └── chroma_db_small/     # 向量存储目录
│   ├── data/                    # 原始与预处理后的健康知识数据
│   ├── tests/                   # 证据分级相关单元测试
│   └── requirements.txt
├── frontend/                    # 前端单页应用
│   ├── src/
│   │   ├── App.jsx              # 主界面与对话逻辑
│   │   └── 样式与入口文件
│   ├── index.html
│   └── package.json
├── data/                        # 爬取/整理后的多源健康数据
├── docs/                        # 证据分级标准等文档
└── scripts/                     # 快速运行/构建脚本
```

---

### 快速开始

#### 1. 环境准备

- Python 3.10+
- Node.js 18+

#### 2. 启动后端

```bash
cd backend

# （推荐）创建并激活虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# 或 source venv/bin/activate  # Linux / macOS

# 安装依赖
pip install -r requirements.txt

# 配置 LLM API Key
copy .env.example .env  # Windows，也可手动新建 .env
# 在 .env 中至少设置：
# DEEPSEEK_API_KEY=你的密钥

# 启动服务
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问开发服务器地址（通常为 `http://localhost:5173`），即可使用在线健康问答助手。

---

### 常见使用场景示例

- 输入「高血压患者的饮食建议」：系统直接检索相关指南/百科内容，返回带证据等级与来源链接的回答。
- 输入「我头疼」：系统先通过多轮澄清询问头痛部位、性质、持续时间等，再根据补充信息给出更精准建议并附上证据。
- 当问题中出现「胸痛、呼吸困难、昏迷、高烧不退」等紧急症状关键词时：系统优先给出“立即就医”安全提醒。

---

### 免责声明

本系统为课程/训练营场景下的教学原型，其提供的信息仅供学术研究和健康科普参考，**不构成医疗诊断或治疗建议**。  
如有任何健康问题，请务必线下咨询执业医师或前往正规医疗机构就诊。

