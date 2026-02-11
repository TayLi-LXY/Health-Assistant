"""
多轮澄清对话管理模块
负责：判断是否需要澄清、生成澄清问题、维护对话状态、查询重写
"""
import re
from typing import Optional, Tuple, List
from models import ChatMessage, MessageRole


# 模糊/宽泛问题关键词
VAGUE_PATTERNS = [
    r"怎么办", r"怎么(样)?(办|做)", r"如何(保持|改善|治疗)",
    r"有什么(建议|办法|方法)", r"该(怎么|如何)", r"帮(我)?看看",
    r"不舒服", r"有问题", r"出(了)?问题", r"疼", r"痛", r"难受",
]

# 缺少关键信息：涉及用药/治疗但无具体症状
MISSING_CONTEXT_PATTERNS = [
    (r"(吃|用|服).*药", ["症状", "年龄", "过敏史"]),
    (r"能(不能)?吃", ["具体症状", "用药史"]),
    (r"治疗", ["具体病症", "病程"]),
    (r"发烧", ["体温", "伴随症状", "持续时间"]),
    (r"头疼", ["头痛类型", "持续时间", "部位"]),
    (r"肚子", ["具体症状", "持续时间", "饮食"]),
]

# 澄清问题模板
CLARIFICATION_TEMPLATES = {
    "symptom_vague": "为了更好地帮助您，您能具体描述一下{topic}的情况吗？例如：症状持续时间、严重程度、伴随的其他不适等。",
    "symptom_type": "您提到的{topic}，具体是哪种类型？例如：{options}",
    "missing_context": "为了给出更精准的建议，请问：{question}",
    "headache": "为了更好地帮助您，您能描述一下是哪种类型的头痛吗？比如是刺痛、胀痛、跳痛还是其他？头痛主要在哪个部位？持续多久了？",
    "stomach": "您说的肚子不舒服，具体是什么感觉？是腹痛、腹胀、恶心还是其他？这种情况持续多久了？",
    "fever": "请问您的体温大概多少度？发烧持续多长时间了？有没有其他伴随症状，比如咳嗽、喉咙痛等？",
    "medication": "在给出用药建议之前，请问您目前有哪些具体症状？是否有已知的药物过敏史？",
    "general": "您的问题比较宽泛。能否具体说一下您最关心的是哪方面？例如：预防措施、饮食建议、运动建议或具体症状的应对方法？",
}


def _check_vague_intent(query: str) -> bool:
    """检测意图是否模糊"""
    query_lower = query.strip().lower()
    if len(query_lower) < 5:
        return True
    for pattern in VAGUE_PATTERNS:
        if re.search(pattern, query):
            return True
    return False


def _check_missing_context(query: str) -> Optional[Tuple[str, str]]:
    """
    检测是否缺少关键信息
    返回: (模板key, 补充参数) 或 None
    """
    query_lower = query.strip()
    for pattern, missing in MISSING_CONTEXT_PATTERNS:
        if re.search(pattern, query_lower):
            if "头疼" in query_lower or "头痛" in query_lower:
                return ("headache", {})
            if "肚子" in query_lower or "胃" in query_lower or "腹痛" in query_lower:
                return ("stomach", {})
            if "发烧" in query_lower or "发热" in query_lower:
                return ("fever", {})
            if re.search(r"(吃|用|服).*药", query_lower):
                return ("medication", {})
    return None


def _needs_clarification(query: str, turn_count: int) -> bool:
    """
    判断是否需要澄清
    限制最多2-3轮澄清
    """
    if turn_count >= 3:
        return False
    if _check_vague_intent(query):
        return True
    if _check_missing_context(query):
        return True
    return False


def generate_clarification_question(query: str, session_state: dict) -> str:
    """
    基于模板生成澄清问题
    进阶可改为调用LLM生成
    """
    turn_count = session_state.get("clarification_turns", 0)
    
    # 头疼相关
    if any(kw in query for kw in ["头疼", "头痛", "头昏"]):
        return CLARIFICATION_TEMPLATES["headache"]
    
    # 肚子/胃相关
    if any(kw in query for kw in ["肚子", "胃", "腹痛", "腹泻"]):
        return CLARIFICATION_TEMPLATES["stomach"]
    
    # 发烧相关
    if any(kw in query for kw in ["发烧", "发热"]):
        return CLARIFICATION_TEMPLATES["fever"]
    
    # 用药相关
    if re.search(r"(吃|用|服).*药", query):
        return CLARIFICATION_TEMPLATES["medication"]
    
    # 宽泛问题
    if _check_vague_intent(query) and len(query.strip()) < 20:
        return CLARIFICATION_TEMPLATES["general"]
    
    return CLARIFICATION_TEMPLATES["symptom_vague"].format(topic="您的症状")


def rewrite_query(original_query: str, clarification_answers: List[str]) -> str:
    """
    查询重写：将原始问题与澄清轮次中收集的信息整合成更明确的查询
    """
    if not clarification_answers:
        return original_query.strip()
    
    combined = original_query
    for ans in clarification_answers:
        if ans and ans.strip():
            combined += "。补充信息：" + ans.strip()
    
    return combined


class DialogueManager:
    """对话管理器 - 使用简单状态机"""
    
    def __init__(self):
        self.sessions: dict = {}
    
    def get_or_create_session(self, session_id: str) -> dict:
        """获取或创建会话状态"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "original_query": "",
                "clarification_answers": [],
                "clarification_turns": 0,
                "resolved_query": "",
                "conversation": [],
            }
        return self.sessions[session_id]
    
    def process_user_input(
        self,
        session_id: str,
        message: str,
        is_follow_up: bool = False
    ) -> Tuple[bool, Optional[str], str]:
        """
        处理用户输入
        
        Returns:
            (needs_clarification, clarification_question, resolved_query)
            - 若 needs_clarification=True, clarification_question 有值
            - 若 needs_clarification=False, resolved_query 为可用于检索的明确查询
        """
        state = self.get_or_create_session(session_id)
        
        if not is_follow_up:
            # 新问题，重置或初始化
            state["original_query"] = message
            state["clarification_answers"] = []
            state["clarification_turns"] = 0
            state["conversation"] = [{"role": "user", "content": message}]
            
            if _needs_clarification(message, 0):
                q = generate_clarification_question(message, state)
                state["clarification_turns"] = 1
                return True, q, ""
            else:
                state["resolved_query"] = message.strip()
                return False, None, state["resolved_query"]
        
        else:
            # 澄清轮次的回答
            state["clarification_answers"].append(message)
            state["conversation"].append({"role": "user", "content": message})
            turn_count = state["clarification_turns"]
            
            if _needs_clarification(state["original_query"], turn_count + 1):
                q = generate_clarification_question(
                    state["original_query"],
                    {**state, "clarification_turns": turn_count + 1}
                )
                state["clarification_turns"] = turn_count + 1
                return True, q, ""
            else:
                state["resolved_query"] = rewrite_query(
                    state["original_query"],
                    state["clarification_answers"]
                )
                return False, None, state["resolved_query"]
    
    def is_clarification_round(self, session_id: str) -> bool:
        """判断当前是否为澄清轮次（有原始问题且已有澄清）"""
        state = self.sessions.get(session_id, {})
        return len(state.get("clarification_answers", [])) > 0
    
    def get_resolved_query(self, session_id: str) -> str:
        return self.sessions.get(session_id, {}).get("resolved_query", "")
