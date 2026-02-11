"""
RAG 检索增强生成流程
- 向量检索
- 证据分级
- Prompt构建
- LLM生成
"""
import os
from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

from models import EvidenceItem, EvidenceLevel
from evidence_grading import compute_evidence_grade
from knowledge_base.builder import get_vector_store

# Prompt模板
SYSTEM_PROMPT = """你是一位专业的健康咨询助手。你的任务是基于用户问题和提供的参考资料，生成准确、有帮助的健康建议。

重要规则：
1. 你必须严格基于提供的参考资料回答，不得编造信息。
2. 如果参考资料不足以回答某方面，请明确说明"根据现有资料无法确定"。
3. 对于用药建议，务必提醒用户咨询医生，不可推荐具体处方药。
4. 回答要清晰、结构合理，适当分段。
5. 在回答末尾，引用你使用的证据来源（对应参考资料编号）。
"""

USER_PROMPT_TEMPLATE = """## 用户问题
{query}

## 参考资料（请基于以下内容回答，并注明引用来源编号）
{context}

请根据上述参考资料，为用户提供专业、负责任的健康建议。"""


def _get_llm():
    """获取LLM实例 - 支持Deepseek/OpenAI兼容API"""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    
    if not api_key:
        # 若无API Key，返回一个会提示配置的mock
        raise ValueError(
            "请配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY 环境变量。"
            "在 backend/.env 中设置，或导出环境变量。"
        )
    
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url=base_url.rstrip("/") + "/v1",
        temperature=0.3,
    )


def _format_context_with_evidence(chunks: List[dict], evidences: List[EvidenceItem]) -> str:
    """将检索结果和证据等级格式化为上下文"""
    lines = []
    for i, (chunk, ev) in enumerate(zip(chunks, evidences), 1):
        level_tag = f"[证据等级: Level {ev.evidence_level.value} - {ev.evidence_level.name}]"
        lines.append(f"[{i}] {level_tag}\n来源: {ev.source_name}\n{chunk.get('content', '')}\n")
    return "\n".join(lines)


def retrieve(query: str, top_k: int = 5) -> List[dict]:
    """从知识库检索相关文本块"""
    vs = get_vector_store()
    docs = vs.similarity_search(query, k=top_k)
    return [
        {
            "content": d.page_content,
            "metadata": d.metadata or {},
        }
        for d in docs
    ]


def grade_and_format_evidences(chunks: List[dict]) -> List[EvidenceItem]:
    """对检索结果进行证据分级并格式化为EvidenceItem"""
    evidences = []
    for c in chunks:
        meta = c.get("metadata", {}) or c
        level, score, explanation = compute_evidence_grade(
            content=meta.get("content", c.get("content", "")),
            source_url=meta.get("source_url", ""),
            source_name=meta.get("source_name", ""),
            publication_date=meta.get("publication_date"),
            title=meta.get("title", ""),
        )
        evidences.append(EvidenceItem(
            content=meta.get("content", c.get("content", "")),
            source_url=meta.get("source_url", ""),
            source_name=meta.get("source_name", ""),
            publication_date=meta.get("publication_date"),
            title=meta.get("title", ""),
            evidence_level=level,
            evidence_score=score,
            level_explanation=explanation,
        ))
    return evidences


def generate_answer(query: str, chunks: List[dict], evidences: List[EvidenceItem]) -> str:
    """调用LLM生成最终回答"""
    llm = _get_llm()
    context = _format_context_with_evidence(chunks, evidences)
    user_prompt = USER_PROMPT_TEMPLATE.format(query=query, context=context)
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    response = llm.invoke(messages)
    return response.content if hasattr(response, "content") else str(response)


def run_rag_pipeline(query: str, top_k: int = 5) -> tuple[str, List[EvidenceItem]]:
    """
    完整RAG流程
    Returns: (answer, evidences)
    """
    chunks = retrieve(query, top_k=top_k)
    if not chunks:
        return "抱歉，在知识库中未找到与您问题直接相关的内容。建议您咨询专业医生获取更准确的建议。", []
    
    evidences = grade_and_format_evidences(chunks)
    try:
        answer = generate_answer(query, chunks, evidences)
    except ValueError as e:
        return f"系统配置提示：{str(e)}", evidences
    except Exception as e:
        return f"生成回答时发生错误：{str(e)}。您可以先查看下方的参考资料。", evidences
    
    return answer, evidences
