"""数据模型定义"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class EvidenceLevel(int, Enum):
    """证据等级 - 参考GRADE简化模型"""
    HIGH = 4          # 高证据强度: WHO, CDC等顶级权威机构
    MEDIUM = 3        # 中等证据强度: Mayo Clinic等知名机构
    LOW = 2           # 低证据强度: 信誉良好的健康资讯网站
    VERY_LOW = 1      # 极低证据强度: 来源不明或商业推广


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """聊天消息"""
    role: MessageRole
    content: str


class EvidenceItem(BaseModel):
    """单条证据"""
    content: str
    source_url: str = ""
    source_name: str = ""
    publication_date: Optional[str] = None
    title: str = ""
    evidence_level: EvidenceLevel = EvidenceLevel.LOW
    evidence_score: float = 0
    level_explanation: str = ""  # 可解释性：为什么被评为该等级


class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: str = ""
    message: str
    conversation_history: List[ChatMessage] = []
    is_clarification_response: bool = False  # 是否为对澄清问题的回答


class ClarificationResponse(BaseModel):
    """澄清响应 - 需要追问时返回"""
    needs_clarification: bool = True
    clarification_question: str
    session_state: dict


class AnswerResponse(BaseModel):
    """最终回答响应"""
    needs_clarification: bool = False
    answer: str
    evidences: List[EvidenceItem] = []
    disclaimer: str = "本系统为课程设计原型，其提供的信息仅供学术研究和参考，不能作为专业的医疗诊断和治疗建议。如有任何健康问题，请务必咨询执业医师。"
    session_state: dict = {}
