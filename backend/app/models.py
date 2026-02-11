"""数据模型定义"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class EvidenceLevel(str, Enum):
    """证据等级定义 (参考GRADE简化版)"""
    LEVEL_4 = "Level 4"  # 高证据强度
    LEVEL_3 = "Level 3"  # 中等证据强度
    LEVEL_2 = "Level 2"  # 低证据强度
    LEVEL_1 = "Level 1"  # 极低证据强度/仅供参考


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """聊天消息"""
    role: MessageRole
    content: str
    evidence_list: Optional[List[dict]] = None  # 回答附带证据


class EvidenceItem(BaseModel):
    """单条证据"""
    content: str
    source_url: str
    source_name: str
    evidence_level: str
    title: Optional[str] = None
    publication_date: Optional[str] = None
    explanation: Optional[str] = None  # 可解释性：为何评定为该等级


class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: str
    message: str
    conversation_history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    """聊天响应"""
    message: str
    need_clarification: bool = False
    clarification_question: Optional[str] = None
    evidence_list: List[EvidenceItem] = []
    disclaimer: str = "本系统为课程设计原型，其提供的信息仅供学术研究和参考，不能作为专业的医疗诊断和治疗建议。如有任何健康问题，请务必咨询执业医师。"
