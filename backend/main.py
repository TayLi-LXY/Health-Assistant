"""
在线健康问答助手 - 后端 API
FastAPI 主入口
"""
import uuid
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import ChatRequest, ChatMessage, MessageRole, EvidenceItem, EvidenceLevel
from dialogue_manager import DialogueManager
from rag_pipeline import run_rag_pipeline

app = FastAPI(
    title="在线健康问答助手 API",
    description="基于证据分级与多轮澄清的健康问答系统",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

dm = DialogueManager()


@app.get("/")
def root():
    return {"message": "在线健康问答助手 API", "status": "ok"}


@app.get("/health")
def health():
    return {"status": "healthy"}


def _serialize_evidence(ev: EvidenceItem) -> dict:
    return {
        "content": ev.content,
        "source_url": ev.source_url,
        "source_name": ev.source_name,
        "publication_date": ev.publication_date,
        "title": ev.title,
        "evidence_level": ev.evidence_level.value,
        "evidence_level_name": ev.evidence_level.name,
        "evidence_score": ev.evidence_score,
        "level_explanation": ev.level_explanation,
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    核心聊天接口
    - 若需要澄清，返回 clarification_question
    - 否则执行 RAG 并返回 answer + evidences
    """
    session_id = req.session_id or str(uuid.uuid4())
    
    # 判断是否为澄清轮次的回答：当前会话正在等待用户回答澄清问题
    state = dm.get_or_create_session(session_id)
    is_follow_up = (
        state.get("clarification_turns", 0) >= 1
        and len(state.get("clarification_answers", [])) < state.get("clarification_turns", 0)
    )
    
    needs_clarification, clarification_q, resolved_query = dm.process_user_input(
        session_id, req.message, is_follow_up=is_follow_up
    )
    
    if needs_clarification and clarification_q:
        return {
            "session_id": session_id,
            "needs_clarification": True,
            "clarification_question": clarification_q,
            "answer": None,
            "evidences": [],
            "disclaimer": "本系统为课程设计原型，其提供的信息仅供学术研究和参考，不能作为专业的医疗诊断和治疗建议。如有任何健康问题，请务必咨询执业医师。",
        }
    
    # 执行 RAG
    answer, evidences = run_rag_pipeline(resolved_query or req.message, top_k=5)
    
    return {
        "session_id": session_id,
        "needs_clarification": False,
        "clarification_question": None,
        "answer": answer,
        "evidences": [_serialize_evidence(e) for e in evidences],
        "disclaimer": "本系统为课程设计原型，其提供的信息仅供学术研究和参考，不能作为专业的医疗诊断和治疗建议。如有任何健康问题，请务必咨询执业医师。",
    }


@app.post("/api/chat/simple")
def chat_simple(message: str, session_id: str = None):
    """
    简化版聊天接口（方便测试）
    """
    sid = session_id or str(uuid.uuid4())
    req = ChatRequest(session_id=sid, message=message)
    return chat(req)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
