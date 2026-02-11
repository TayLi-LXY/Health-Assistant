# 在线健康问答助手

基于证据分级与多轮澄清机制的智能健康问答系统。系统能够理解用户的健康相关问题，通过多轮交互进行澄清，最终提供附有明确证据来源和证据等级的回答。

## 项目特性

- **证据分级机制**：参考 GRADE 系统，根据来源权威性、时效性、文档类型对检索到的健康信息进行分级（Level 1-4）
- **多轮澄清对话**：识别模糊问题，通过澄清式追问引导用户提供更多信息
- **RAG 架构**：检索增强生成，结合向量知识库与大语言模型
- **可追溯证据**：每条回答均附来源链接与证据等级，支持可解释性展示

## 技术栈

- **后端**：Python + FastAPI
- **前端**：React + Vite
- **RAG**：LangChain + ChromaDB
- **嵌入模型**：paraphrase-multilingual-MiniLM-L12-v2（本地）
- **LLM**：Deepseek API（或 OpenAI 兼容接口）

## 项目结构

```
在线健康问答助手/
├── backend/                 # 后端服务
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # 配置
│   ├── models.py           # 数据模型
│   ├── evidence_grading.py # 证据分级模块
│   ├── dialogue_manager.py # 多轮澄清对话管理
│   ├── rag_pipeline.py     # RAG 检索与生成
│   ├── knowledge_base/     # 知识库构建
│   ├── data/               # 健康知识数据
│   └── requirements.txt
├── frontend/               # 前端
│   ├── src/
│   │   ├── App.jsx
│   │   └── ...
│   └── package.json
└── README.md
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+

### 2. 后端启动

```bash
cd backend

# 创建虚拟环境（推荐）
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
# source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置 LLM API Key（必需）
# 复制 .env.example 为 .env，填入 Deepseek API Key
copy .env.example .env
# 编辑 .env，设置 DEEPSEEK_API_KEY=你的密钥

# 首次运行会构建知识库（下载 embedding 模型，约需几分钟）
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 前端启动

```bash
cd frontend

npm install
npm run dev
```

浏览器访问 http://localhost:5173

### 4. 预构建知识库（可选）

若希望提前构建向量知识库，可运行：

```bash
cd backend
python -c "from knowledge_base.builder import build_vector_store; build_vector_store()"
```

## 配置说明

在 `backend/.env` 中配置：

| 变量 | 说明 |
|------|------|
| DEEPSEEK_API_KEY | Deepseek API 密钥 |
| DEEPSEEK_BASE_URL | API 地址，默认 https://api.deepseek.com |

也可使用 OpenAI 兼容接口，设置 `OPENAI_API_KEY` 和相应 `BASE_URL`。

## 演示场景

1. **简单查询**：输入「高血压患者的饮食建议」，系统直接返回带证据来源和等级的回答。
2. **澄清查询**：输入「我头疼」，系统会追问头痛类型、部位、持续时间等，再基于补充信息给出精准建议。

## 免责声明

本系统为课程设计原型，其提供的信息仅供学术研究和参考，不能作为专业的医疗诊断和治疗建议。如有任何健康问题，请务必咨询执业医师。

## 许可证

本项目仅供学习交流使用。
