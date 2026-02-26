"""
多轮澄清对话管理模块 - 触发条件增强版
负责：判断是否需要澄清、生成澄清问题、维护对话状态、查询重写
主要改进：增强意图模糊性检测、实体/术语歧义识别、关键信息缺失检测、紧急症状响应
修复内容：
1. 修复正则表达式字符集错误（如意识[不模糊]清 → 意识(不清|模糊)）
2. 补全未闭合的CLARIFICATION_TEMPLATES字典
3. 修复置信度未定义、轮次限制逻辑漏洞
4. 优化去重逻辑、异常处理、变量命名一致性
5. 增强正则匹配边界处理、紧急症状优先级
"""
import re
from typing import Optional, Tuple, List, Dict
import random

# =========================== 1. 意图模糊性检测 ===========================
# 模糊/宽泛问题关键词（增强版）
VAGUE_PATTERNS = {
    # 通用模糊表达
    "general_action": [
        r"怎么办$", r"怎么(样)?(办|做)", r"如何(保持|改善|治疗|处理|解决)", 
        r"有什么(建议|办法|方法|主意)", r"该(怎么|如何|怎样)", r"帮(我)?(看看|看一下|分析一下)",
        r"给点(建议|意见)", r"请(问)?指教", r"请(问)?帮助"
    ],
    # 过于宽泛的健康问题
    "too_broad": [
        r"健康", r"养生", r"锻炼", r"饮食", r"生活(习惯|方式)", r"身体(状况|情况)",
        r"亚健康", r"保健", r"养生", r"怎么(变|保持)健康", r"如何养生"
    ],
    # 模糊症状描述
    "vague_symptom": [
        r"不舒服$", r"难受$", r"有问题$", r"出(了)?问题$", r"(不|没)好$", r"异常$",
        r"有点(不舒服|难受|不对)", r"感觉(不舒服|难受|不对)", r"不太对劲"
    ],
    # 缺乏细节的症状
    "vague_pain": [
        r"疼$", r"痛$", r"痒$", r"肿$", r"红$", r"难受$",
        r"(这里|那里|某个地方)(疼|痛|痒|肿|红)"
    ],
    # 缺乏具体部位的描述
    "vague_location": [
        r"身体", r"全身", r"某(个|处)", r"那里", r"这里", r"一个地方", r"某些地方",
        r"局部", r"部分区域", r"某些部位"
    ]
}

# =========================== 2. 实体/术语歧义识别 ===========================
# 健康领域的多义词/歧义词典
AMBIGUOUS_TERMS = {
    "苹果": {
        "contexts": ["水果", "公司产品"],
        "health_relevant": True,
        "default_sense": "水果",
        "clarification": "您是指水果苹果还是电子产品苹果？"
    },
    "血压": {
        "contexts": ["血压值", "血压状况"],
        "health_relevant": True,
        "default_sense": "血压值",
        "clarification": "您是想咨询血压的测量值还是血压相关的健康状况？"
    },
    "低血糖": {
        "contexts": ["病症", "检测值"],
        "health_relevant": True,
        "default_sense": "病症",
        "clarification": "您是指低血糖症状还是检测到的血糖值偏低？"
    },
    "过敏": {
        "contexts": ["免疫反应", "药物反应", "食物不耐受"],
        "health_relevant": True,
        "default_sense": "免疫反应",
        "clarification": "您是指什么类型的过敏？食物过敏、药物过敏还是其他过敏？"
    },
    "营养": {
        "contexts": ["营养素", "饮食", "营养补充"],
        "health_relevant": True,
        "default_sense": "营养素",
        "clarification": "您是想了解营养素的补充还是饮食营养？"
    },
    "锻炼": {
        "contexts": ["运动", "康复训练", "特定锻炼"],
        "health_relevant": True,
        "default_sense": "运动",
        "clarification": "您是指一般的体育锻炼还是针对性的康复训练？"
    },
    "治疗": {
        "contexts": ["医疗治疗", "自我调理", "物理治疗"],
        "health_relevant": True,
        "default_sense": "医疗治疗",
        "clarification": "您是指医疗机构的治疗还是自我调理的方法？"
    },
    "药": {
        "contexts": ["处方药", "非处方药", "中药", "草药"],
        "health_relevant": True,
        "default_sense": "药物",
        "clarification": "您是指处方药、非处方药、中药还是其他类型的药物？"
    },
    "检查": {
        "contexts": ["体检", "专项检查", "自我检查"],
        "health_relevant": True,
        "default_sense": "体检",
        "clarification": "您是指医院的专业检查还是自我检查？"
    },
    "炎症": {
        "contexts": ["病理状态", "局部红肿"],
        "health_relevant": True,
        "default_sense": "病理状态",
        "clarification": "您是指身体内部的炎症反应还是局部红肿炎症？"
    }
}

# =========================== 3. 关键信息缺失检测 ===========================
# 症状-必需信息映射表
SYMPTOM_REQUIRED_INFO = {
    "headache": {
        "required": ["位置", "类型", "持续时间", "严重程度"],
        "optional": ["诱因", "缓解方式", "伴随症状"],
        "triggers": ["头疼", "头痛", "头昏", "头晕"]
    },
    "stomach": {
        "required": ["具体感觉", "位置", "持续时间", "饮食关联"],
        "optional": ["排便情况", "呕吐", "食欲变化"],
        "triggers": ["肚子", "胃", "腹痛", "胃痛", "肠胃不适"]
    },
    "fever": {
        "required": ["体温", "持续时间", "伴随症状"],
        "optional": ["发热时间", "退烧情况", "其他症状"],
        "triggers": ["发烧", "发热", "体温高"]
    },
    "cough": {
        "required": ["咳嗽类型", "持续时间", "痰液情况"],
        "optional": ["咳痰时间", "诱发因素", "其他症状"],
        "triggers": ["咳嗽", "咳", "嗽"]
    },
    "medication": {
        "required": ["具体症状", "年龄", "过敏史"],
        "optional": ["用药史", "基础疾病", "特殊人群"],
        "triggers": ["吃药", "用药", "服药", "药"]
    },
    "treatment": {
        "required": ["具体病症", "持续时间", "严重程度"],
        "optional": ["已尝试治疗", "就医经历", "检查结果"],
        "triggers": ["治疗", "处理", "解决", "办法"]
    }
}

# 关键信息检测模式
MISSING_INFO_PATTERNS = [
    # 症状描述不完整
    (r"(头疼|头痛|头昏|头晕)(?!.*(位置|哪里|部位|太阳穴|额头|后脑|头顶|枕部))", 
     "headache", ["位置"], 0.9),
    (r"(肚子|胃|腹部)(?!.*(哪种|什么感觉|怎么疼|什么位置|哪个部位))", 
     "stomach", ["具体感觉", "位置"], 0.9),
    (r"(发烧|发热)(?!.*(多少度|体温|几度|温度))", 
     "fever", ["体温"], 0.9),
    (r"(咳嗽)(?!.*(有痰|干咳|什么时候|咳多久|痰液))", 
     "cough", ["咳嗽类型", "痰液情况"], 0.8),
    
    # 用药相关缺少关键信息
    (r"(吃|用|服).*药(?!.*(什么症状|哪不舒服|过敏|多大|几岁|年龄|病史))", 
     "medication", ["具体症状", "年龄", "过敏史"], 1.0),
    (r"能(不能)?吃.*药(?!.*(症状|年龄|过敏|病史))", 
     "medication", ["具体症状", "年龄", "过敏史"], 0.9),
    (r"(应该|要|需要)吃.*药", 
     "medication", ["具体症状", "年龄", "过敏史"], 0.8),
    
    # 治疗建议缺少上下文
    (r"(治疗|处理|解决).*(?!.*(什么病|什么症状|多久|时间))", 
     "treatment", ["具体病症", "持续时间"], 0.8),
    (r"(应该|要|需要)(怎么|如何)(治疗|处理)(?!.*(具体|详细|情况))", 
     "treatment", ["具体病症"], 0.7),
    
    # 缺乏个人信息
    (r"(我|本人|患者).*(病|不舒服|有问题)(?!.*(多大|几岁|年龄|性别|男|女|[\d一二三四五六七八九十]+岁))", 
 "general", ["年龄", "性别"], 0.7),
    (r"(小孩|孩子|儿童|宝宝|幼儿|婴儿).*(?!.*(多大|几岁|几月|月龄|[\d一二三四五六七八九十]+岁|[\d一二三四五六七八九十]+个月|[\d一二三四五六七八九十]+月大))", 
 "child", ["确切年龄"], 0.9),
    (r"(老人|老年|长辈|长者).*(?!.*(多大|年龄|病史|基础病|[\d一二三四五六七八九十]+岁|高龄))", 
 "elderly", ["年龄", "基础疾病"], 0.9),
    (r"(孕妇|怀孕|孕妈|准妈妈).*(?!.*(孕周|孕期|几月|[\d一二三四五六七八九十]+[个]?月|[\d一二三四五六七八九十]+周))", 
 "pregnancy", ["孕周"], 0.9),
    
    # 缺乏症状细节
    (r"(疼|痛|痒|肿|红)(?!.*(多久|怎么个|什么样|程度|级别|性质))", 
     "general", ["持续时间", "性质描述", "严重程度"], 0.7),
]

# 特殊人群关键词（需要额外澄清）
SPECIAL_POPULATION_KEYWORDS = {
    "child_related": ["小孩", "孩子", "儿童", "宝宝", "幼儿", "婴儿", "新生儿", "婴幼儿"],
    "elderly_related": ["老人", "老年", "长辈", "长者", "高龄", "年长"],
    "pregnancy_related": ["孕妇", "怀孕", "孕期", "孕妈", "准妈妈", "哺乳期", "月子"],
    "chronic_patient": ["高血压", "糖尿病", "心脏病", "哮喘", "肾病", "肝病", "慢阻肺"],
    "emergency_signals": ["剧痛", "吐血", "昏迷", "呼吸困难", "高烧不退", "意识不清", "胸痛"]
}

# 紧急症状关键词
EMERGENCY_KEYWORDS = [
    "胸痛", "呼吸困难", "昏迷", "意识不清", "大出血", "吐血", "抽搐", 
    "高烧不退", "持续高烧", "剧烈头痛", "剧烈腹痛"
]

# =========================== 检测函数 ===========================
def _detect_vague_intent(query: str) -> Tuple[bool, List[Dict]]:
    """
    检测意图模糊性
    返回：(是否需要澄清, 检测结果列表)
    修复：增加空值处理、边界匹配优化
    """
    # 空值/空字符串处理
    if not query:
        return True, [{
            "type": "empty_query",
            "confidence": 1.0,
            "message": "问题描述为空，无法理解具体需求",
            "suggestion": "请详细描述您或者病人的情况或问题"
        }]
    
    query_lower = query.strip().lower()
    results = []
    
    # 1. 文本长度检测
    if len(query_lower) < 5:
        results.append({
            "type": "too_short",
            "confidence": 0.9,
            "message": "问题描述过于简短，无法理解具体需求",
            "suggestion": "请详细描述您或者病人的情况"
        })
    
    # 2. 模糊意图模式匹配
    for intent_type, patterns in VAGUE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                results.append({
                    "type": "vague_intent",
                    "intent_type": intent_type,
                    "confidence": 0.8,
                    "message": f"检测到模糊意图类型: {intent_type}",
                    "suggestion": "请具体描述您的问题"
                })
                break
    
    # 3. 检查是否包含具体的症状描述
    # 如果问题中包含模糊词汇但不包含具体症状，认为是模糊意图
    vague_words = ["怎么办", "怎么", "如何", "什么", "建议", "帮助", "不舒服", "难受"]
    symptom_words = ["头疼", "头痛", "发烧", "咳嗽", "肚子", "胃", "腹泻", "便秘", "呕吐", "头晕"]
    
    has_vague = any(word in query_lower for word in vague_words)
    has_symptom = any(word in query_lower for word in symptom_words)
    
    if has_vague and not has_symptom and len(query_lower) < 15:
        results.append({
            "type": "vague_without_symptom",
            "confidence": 0.7,
            "message": "问题包含模糊词汇但缺乏具体症状描述",
            "suggestion": "请具体描述您或病人的症状"
        })
    
    # 4. 检查是否缺乏疑问词（对于陈述句）
    question_words = ["吗", "什么", "怎么", "如何", "为什么", "哪", "谁", "多少", "几", "？", "?"]
    if not any(word in query_lower for word in question_words) and len(query_lower) < 20:
        results.append({
            "type": "missing_question_word",
            "confidence": 0.6,
            "message": "问题陈述不够明确",
            "suggestion": "请明确表达您的疑问"
        })
    
    return len(results) > 0, results

def _detect_ambiguity(query: str) -> Tuple[bool, List[Dict]]:
    """
    检测实体/术语歧义
    返回：(是否需要澄清, 歧义词列表)
    """
    # 空值处理
    if not query:
        return False, []
    
    results = []
    query_lower = query.strip().lower()
    
    # 检查是否有歧义术语
    for term, info in AMBIGUOUS_TERMS.items():
        if term in query_lower:
            # 检查是否有足够的上下文来确定词义
            has_context = False
            # 可以根据术语的具体情况添加更多上下文检查逻辑
            
            if not has_context:
                results.append({
                    "type": "ambiguous_term",
                    "term": term,
                    "possible_meanings": info["contexts"],
                    "health_relevant": info["health_relevant"],
                    "clarification_template": info["clarification"],
                    "confidence": 0.8 if info["health_relevant"] else 0.5,
                    "message": f"术语'{term}'可能有多种含义",
                    "suggestion": info["clarification"]
                })
    
    # 检查健康领域的其他常见歧义
    health_ambiguities = [
        ("血压", ["血压值", "血压状况"]),
        ("血糖", ["血糖值", "血糖状况"]),
        ("血脂", ["血脂值", "血脂状况"]),
        ("营养", ["营养补充", "营养状况", "营养学"]),
        ("运动", ["体育锻炼", "康复运动", "日常活动"]),
        ("治疗", ["医疗治疗", "自我调理", "辅助治疗"])
    ]
    
    for term, meanings in health_ambiguities:
        if term in query_lower:
            # 简单上下文检查
            context_clues = {
                "血压": ["多少", "高不高", "正常吗", "测量"],
                "血糖": ["多少", "高不高", "正常吗", "测量"],
                "血脂": ["多少", "高不高", "正常吗", "测量"],
                "营养": ["补充", "缺乏", "丰富", "摄入"],
                "运动": ["做", "进行", "锻炼", "康复"],
                "治疗": ["方法", "方式", "手段", "措施"]
            }
            
            clues = context_clues.get(term, [])
            has_context = any(clue in query_lower for clue in clues)
            
            if not has_context:
                results.append({
                    "type": "health_ambiguity",
                    "term": term,
                    "possible_meanings": meanings,
                    "confidence": 0.7,
                    "message": f"健康术语'{term}'可能有不同含义",
                    "suggestion": f"您是指{meanings[0]}还是{meanings[1]}？"
                })
    
    return len(results) > 0, results

def _detect_missing_info(query: str, conversation_history: List = None, 
                        symptom_context: str = None , user_profile: dict = None) -> Tuple[bool, List[Dict]]:
    """
    检测关键信息缺失
    返回：(是否需要澄清, 缺失信息列表)
    参数：symptom_context - 当前对话的症状上下文
    修复：
    1. 正则表达式字符集错误修复
    2. 置信度初始化，解决UnboundLocalError
    3. 优化去重逻辑（增加type字段）
    4. 异常处理（空值、非列表类型历史记录）
    """
    # 空值处理
    if not query:
        return False, []
    
    # 初始化默认值，避免非列表类型报错
    if conversation_history is None:
        conversation_history = []
    
    query_lower = query.strip().lower()
    results = []
    
    # 1. 模式匹配检测 - 添加症状上下文权重
    for pattern, detected_symptom_type, missing_info_list, confidence in MISSING_INFO_PATTERNS:
        if re.search(pattern, query_lower):
            for info in missing_info_list:
                # 初始化置信度，修复未定义问题
                adjusted_confidence = confidence
                
                # 如果当前有症状上下文，且检测到的症状类型与上下文匹配，提高置信度
                if symptom_context and detected_symptom_type == symptom_context:
                    adjusted_confidence = min(confidence + 0.2, 1.0)  # 最高1.0
                
                # 如果当前有症状上下文，但检测到的症状类型与上下文不匹配，降低置信度
                elif symptom_context and detected_symptom_type != symptom_context:
                    # 通用类型不降低置信度
                    if detected_symptom_type not in ["general", "child", "elderly", "pregnancy", "medication", "treatment"]:
                        adjusted_confidence = confidence * 0.3
                
                results.append({
                    "type": "pattern_missing",
                    "symptom_type": detected_symptom_type,
                    "missing_info": info,
                    "confidence": adjusted_confidence,
                    "message": f"检测到缺失信息: {info}",
                    "suggestion": f"请补充{info}信息"
                })
    
    # 2. 症状类型推断和必需信息检查
    detected_symptoms = []
    for symptom_type, info in SYMPTOM_REQUIRED_INFO.items():
        for trigger in info["triggers"]:
            if trigger in query_lower:
                # 如果当前有症状上下文，优先匹配
                if symptom_context and symptom_type == symptom_context:
                    detected_symptoms.insert(0, (symptom_type, info))  # 插入到开头
                else:
                    detected_symptoms.append((symptom_type, info))
                break
    
    for symptom_type, info in detected_symptoms:
        required_infos = info["required"]
        
        # 检查每个必需信息是否在查询中提及
        for req_info in required_infos:
            info_keywords = {
                "位置": ["哪里", "位置", "部位", "什么地方", "区域", "部位"],
                "类型": ["什么感觉", "什么样", "怎么个", "哪种", "类型", "性质"],
                "持续时间": ["多久", "几天", "多长时间", "持续", "时间", "有多久"],
                "严重程度": ["程度", "严重", "厉害", "级别", "强度", "多严重"],
                "体温": ["体温", "多少度", "几度", "温度", "发热", "发烧"],
                "具体感觉": ["感觉", "感受", "症状", "表现", "什么样"],
                "饮食关联": ["吃饭", "饮食", "吃什么", "喝什么", "饭后", "饭前"],
                "具体症状": ["症状", "表现", "不舒服", "难受", "什么病"],
                "年龄": ["多大", "几岁", "年龄", "岁数", "年纪"],
                "性别": ["性别", "男", "女", "男性", "女性"],
                "过敏史": ["过敏", "过敏史", "过敏反应", "过敏体质"],
                "确切年龄": ["多大", "几岁", "几个月", "几岁零", "月龄", "年龄"],
                "孕周": ["孕周", "孕期", "怀孕几周", "几个月", "预产期"],
                "基础疾病": ["病史", "慢性病", "基础病", "有什么病", "疾病史"],
                "痰液情况": ["痰", "咯痰", "吐痰", "有痰", "没痰", "痰液"],
                "咳嗽类型": ["干咳", "湿咳", "咳嗽类型", "怎么咳"],
                "已尝试治疗": ["看过", "用过", "吃过", "治疗过", "处理过"]
            }
            
            # 检查该信息是否被提及
            keywords = info_keywords.get(req_info, [req_info])
            info_mentioned = any(keyword in query_lower for keyword in keywords)
            
            # 进一步检查是否已经在历史对话中提及
            if not info_mentioned:
                # 只检查最近5条，且处理非列表类型
                try:
                    recent_history = conversation_history[-5:] if len(conversation_history) >=5 else conversation_history
                    for message in recent_history:
                        msg_content = message.get("content", "").lower() if isinstance(message, dict) else str(message).lower()
                        if any(keyword in msg_content for keyword in keywords):
                            info_mentioned = True
                            break
                except Exception:
                    # 历史记录格式异常时跳过
                    pass
            
            if not info_mentioned:
                # 初始化基础置信度
                base_confidence = 0.8
                
                # 如果当前症状上下文匹配，提高置信度
                if symptom_context and symptom_type == symptom_context:
                    base_confidence = min(base_confidence + 0.15, 1.0)
                
                # 如果当前症状上下文存在但不匹配，降低置信度
                elif symptom_context and symptom_type != symptom_context:
                    if symptom_type not in ["general", "child", "elderly", "pregnancy"]:
                        base_confidence = base_confidence * 0.4
                
                results.append({
                    "type": "symptom_required",
                    "symptom_type": symptom_type,
                    "missing_info": req_info,
                    "confidence": base_confidence,
                    "message": f"对于{symptom_type}症状，需要补充信息: {req_info}",
                    "suggestion": f"请提供{req_info}信息"
                })
    
    # 3. 特殊人群关键词检测
    for category, keywords in SPECIAL_POPULATION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in query_lower:
                # 根据症状上下文调整置信度
                if symptom_context and symptom_context not in ["general", "medication", "treatment"]:
                    adjusted_confidence = 0.7  # 降低置信度
                else:
                    adjusted_confidence = 0.9  # 保持高置信度
                
                # 根据不同类别检查额外信息
                if category == "child_related":
                    age_keywords = ["多大", "几岁", "年龄", "月龄", "几个月"]
                    if not any(word in query_lower for word in age_keywords):
                        results.append({
                            "type": "special_population",
                            "category": category,
                            "keyword": keyword,
                            "missing_info": "年龄",
                            "confidence": adjusted_confidence,
                            "message": f"涉及{keyword}，需要提供年龄信息",
                            "suggestion": "请提供孩子的具体年龄"
                        })
                
                elif category == "pregnancy_related":
                    pregnancy_keywords = ["孕周", "孕期", "怀孕几周", "几个月"]
                    if not any(word in query_lower for word in pregnancy_keywords):
                        results.append({
                            "type": "special_population",
                            "category": category,
                            "keyword": keyword,
                            "missing_info": "孕周",
                            "confidence": adjusted_confidence,
                            "message": f"涉及{keyword}，需要提供孕周信息",
                            "suggestion": "请提供怀孕周数"
                        })
                
                elif category == "chronic_patient":
                    condition_keywords = ["病史", "有什么病", "基础病", "慢性病"]
                    if not any(word in query_lower for word in condition_keywords):
                        results.append({
                            "type": "special_population",
                            "category": category,
                            "keyword": keyword,
                            "missing_info": "基础疾病",
                            "confidence": adjusted_confidence,
                            "message": f"涉及{keyword}患者，需要提供基础疾病信息",
                            "suggestion": "请提供基础疾病情况"
                        })
    
    # 4. 紧急症状检测（增强版）
    # 修复正则表达式字符集错误
    emergency_patterns = [
        (r"胸[口部]?剧痛", "胸痛"), 
        (r"呼吸(困难|不畅|喘不上气|急促)", "呼吸困难"),
        (r"昏迷|不省人事|失去意识", "昏迷"),
        (r"意识(不清|模糊)", "意识不清"),  # 修复：[不模糊] → (不清|模糊)
        (r"(大|大量)出血", "大出血"),
        (r"吐血|咯血", "吐血"),
        (r"抽搐|惊厥", "抽搐"),
        (r"高烧不退|持续高[烧热]|体温[超过]39[度°]C?", "高烧不退"),
         (r"(剧烈|强烈)(头痛|腹痛)", "剧痛"),
    ]
    
    for pattern, keyword in emergency_patterns:
        if re.search(pattern, query_lower):
            # 紧急症状始终高优先级，不受症状上下文影响
            results.append({
                "type": "emergency_symptom",
                "keyword": keyword,
                "pattern_matched": pattern,
                "confidence": 1.0,  # 置信度设为最高
                "message": f"检测到紧急症状关键词: {keyword}",
                "suggestion": "请立即寻求紧急医疗帮助"
            })
            # 提高其他缺失信息的置信度（紧急场景下更需要完整信息）
            for result in results:
                if result["type"] in ["pattern_missing", "symptom_required"]:
                    result["confidence"] = min(result["confidence"] + 0.1, 1.0)
    
    # 去重并排序（按置信度降序）
    if results:
        # 优化去重逻辑：增加type字段，避免不同类型结果误去重
        seen = set()
        unique_results = []
        for item in results:
            key = (item.get("type", ""), item.get("missing_info", ""), item.get("symptom_type", ""))
            if key not in seen:
                seen.add(key)
                unique_results.append(item)
        
        # 排序：优先当前症状上下文的缺失信息
        def sort_key(item):
            confidence = item.get("confidence", 0.5)
            item_symptom_type = item.get("symptom_type", "")
            item_type = item.get("type", "")
            
            # 1. 紧急症状优先级最高
            if item_type == "emergency_symptom":
                confidence += 0.5  # 大幅提高权重
            
            # 2. 如果症状类型匹配当前上下文，提高排序权重
            if symptom_context and item_symptom_type == symptom_context:
                confidence += 0.4
            
            # 3. 如果是特殊人群但当前有具体症状上下文，降低权重
            if item_type == "special_population" and symptom_context and symptom_context not in ["general", "medication", "treatment"]:
                confidence -= 0.3
            
            # 4. 不同信息类型的基准权重
            type_weights = {
                "emergency_symptom": 1.0,
                "special_population": 0.9,
                "symptom_required": 0.8,
                "pattern_missing": 0.7,
            }
            
            weight = type_weights.get(item_type, 0.6)
            confidence = confidence * weight
            
            return confidence
        
        unique_results.sort(key=sort_key, reverse=True)
        
        # 只返回最重要的3个，但如果当前症状上下文有结果，至少保留1个
        current_symptom_results = [r for r in unique_results if r.get("symptom_type") == symptom_context]
        other_results = [r for r in unique_results if r.get("symptom_type") != symptom_context]
        
        final_results = []
        if current_symptom_results:
            final_results.append(current_symptom_results[0])  # 至少包含1个当前症状结果
        
        # 添加其他高置信度结果，但不超过总数限制
        remaining_slots = 3 - len(final_results)
        for result in other_results:
            if result.get("confidence", 0) > 0.6 and remaining_slots > 0:
                final_results.append(result)
                remaining_slots -= 1
    # 去重并排序（按置信度降序）
    else:
        # 如果 results 为空，初始化为空列表
        final_results = []
    
    # ===================== 用户信息过滤逻辑（现在在正确的位置，总是执行） =====================
    if user_profile and final_results:  # 只有当有结果需要过滤时才执行
        filtered_results = []
        for item in final_results:
            missing_info_type = item.get("missing_info", "")
            item_symptom_type = item.get("symptom_type", "")
            
            # 标记此缺失项是否已在user_profile中被提供
            is_info_already_provided = False
            
            # 1. 检查"年龄"或"确切年龄"
            if missing_info_type in ["年龄", "确切年龄"] and user_profile.get("age"):
                is_info_already_provided = True
            # 2. 检查"性别"
            elif missing_info_type == "性别" and user_profile.get("gender"):
                is_info_already_provided = True
            # 3. 检查"孕周"（通常孕妇查询会触发）
            elif missing_info_type == "孕周" and user_profile.get("special_population") == "pregnancy_related":
                is_info_already_provided = True
            # 4. 检查"基础疾病"
            elif missing_info_type == "基础疾病" and user_profile.get("existing_conditions"):
                is_info_already_provided = True
            # 5. 检查"过敏史"
            elif missing_info_type == "过敏史" and user_profile.get("allergy_history"):
                is_info_already_provided = True
            
            # 如果这个信息尚未在user_profile中被记录，则保留此检测结果
            if not is_info_already_provided:
                filtered_results.append(item)
        
        final_results = filtered_results
    
    return len(final_results) > 0, final_results
        
        
    return False, []

def _needs_clarification(query: str, turn_count: int, conversation_history: List = None, 
                        symptom_context: str = None , user_profile: dict = None) -> Dict:
    """
    增强版澄清需求检测
    返回：澄清需求结果字典
    参数：
    - turn_count: 当前对话轮次
    - conversation_history: 对话历史
    - symptom_context: 当前症状上下文（统一变量命名）
    修复：
    1. 正则表达式错误修复
    2. 轮次限制逻辑优化（保留紧急症状优先级）
    3. 变量命名统一（current_symptom_type → symptom_context）
    4. 异常处理（空值、非列表类型）
    """
    # 空值处理
    if not query:
        return {
            "needs_clarification": True,
            "reasons": [{"type": "empty_query", "message": "查询内容为空"}],
            "priority": "medium",
            "clarification_type": "intent_clarification"
        }
    
    # 初始化默认值
    if conversation_history is None:
        conversation_history = []
    
    query_lower = query.strip().lower()
    
    # 第一步：紧急症状扫描（最高优先级）
    emergency_keywords_detected = []
    # 修复正则表达式字符集错误
    emergency_patterns = [
        (r"胸[口部]?[剧巨]痛", "胸痛"),
        (r"呼吸(困难|不畅|喘不上气|急促|上气不接下气)", "呼吸困难"),
        (r"昏迷|不省人事|失去意识", "昏迷"),
        (r"意识(不清|模糊)", "意识不清"),  # 修复字符集错误
        (r"(大|大量)出血", "大出血"),
        (r"吐血|咯血", "吐血"),
        (r"抽搐|惊厥", "抽搐"),
        (r"高烧不退|持续高[烧热]|体温[超过]39[度°]C?", "高烧不退"),
        (r"(剧烈|强烈)(头痛|腹痛)", "剧痛"),  # 修复字符集错误
    ]
    
    for pattern, keyword in emergency_patterns:
        if re.search(pattern, query_lower):
            emergency_keywords_detected.append(keyword)
    
    if emergency_keywords_detected:
        # 紧急症状不受轮次限制，始终需要澄清/告警
        return {
            "needs_clarification": True,
            "reasons": [{
                "type": "emergency_symptom",
                "keyword": "、".join(emergency_keywords_detected),
                "confidence": 1.0,
                "message": f"检测到紧急症状: {', '.join(emergency_keywords_detected)}"
            }],
            "priority": "highest",
            "clarification_type": "emergency_alert",
            "emergency_alert": True  # 新增字段，明确标记为紧急情况
        }
    
    # 轮次限制：超过3轮且无紧急症状时，停止澄清
    if turn_count >= 3:
        return {
            "needs_clarification": False,
            "reasons": [],
            "priority": "low",
            "clarification_type": "none"
        }
    
    # 执行所有检测
    vague_intent, vague_results = _detect_vague_intent(query)
    ambiguous, ambiguous_results = _detect_ambiguity(query)
    missing_info, missing_results = _detect_missing_info(query, conversation_history, symptom_context, user_profile)
    
    # 过滤无关的歧义检测（基于当前症状上下文）
    if symptom_context and ambiguous_results:
        # 定义症状相关的歧义术语白名单
        symptom_related_ambiguities = {
            "general": ["苹果", "血压", "低血糖", "过敏", "营养", "锻炼", "治疗", "药", "检查", "炎症"],  # 新增：通用健康咨询中的常见歧义词
            "headache": ["疼痛", "痛", "不适", "症状"],
            "stomach": ["肚子", "胃", "腹部", "腹泻", "便秘", "胀气"],
            "fever": ["发烧", "发热", "体温", "温度"],
            "cough": ["咳嗽", "咳", "痰", "喉咙"],
            "medication": ["药", "药物", "用药", "服药"],
            "treatment": ["治疗", "处理", "解决", "方法"]
        }
        
        # 获取当前症状相关的术语
        related_terms = symptom_related_ambiguities.get(symptom_context, [])
        
        # 过滤掉与当前症状无关的歧义检测结果
        filtered_ambiguous = []
        for result in ambiguous_results:
            term = result.get("term", "")
            if any(related_term in term for related_term in related_terms) or result.get("confidence", 0) < 0.3:
                filtered_ambiguous.append(result)
        
        ambiguous_results = filtered_ambiguous
        ambiguous = len(filtered_ambiguous) > 0
    
    # 添加症状类型上下文到检测结果
    if symptom_context and missing_results:
        symptom_specific_missing = []
        for result in missing_results:
            result_type = result.get("type", "")
            symptom_in_result = result.get("symptom_type", "")
            
            # 如果检测到的症状类型与当前上下文不符，降低优先级
            if symptom_in_result and symptom_in_result != symptom_context:
                result["confidence"] = result.get("confidence", 0.5) * 0.5
            
            # 如果检测类型与当前症状强相关，提高优先级
            if result_type == "symptom_required" and symptom_in_result == symptom_context:
                result["confidence"] = min(result.get("confidence", 0.7) + 0.2, 1.0)
                
            symptom_specific_missing.append(result)
        
        missing_results = symptom_specific_missing
        missing_info = len(symptom_specific_missing) > 0
    
    all_reasons = vague_results + ambiguous_results + missing_results
    
    if not all_reasons:
        return {
            "needs_clarification": False,
            "reasons": [],
            "priority": "low",
            "clarification_type": "none"
        }
    
    # 计算加权优先级分数
    priority_factors = {
        "emergency_symptom": 1.0,
        "special_population": 0.9,
        "symptom_required": 0.8,
        "pattern_missing": 0.7,
        "health_ambiguity": 0.6,
        "ambiguous_term": 0.5,
        "vague_intent": 0.4,
        "missing_question_word": 0.3,
        "too_short": 0.2
    }
    
    max_score = 0
    primary_reason_type = None
    
    for reason in all_reasons:
        reason_type = reason.get("type", "")
        confidence = reason.get("confidence", 0.5)
        factor = priority_factors.get(reason_type, 0.1)
        score = confidence * factor
        
        if score > max_score:
            max_score = score
            primary_reason_type = reason_type
    
    # 设置优先级
    if max_score >= 0.7:
        priority = "high"
    elif max_score >= 0.4:
        priority = "medium"
    else:
        priority = "low"
    
    # 确定澄清类型
    if primary_reason_type in ["ambiguous_term", "health_ambiguity"]:
        clarification_type = "ambiguity"
    elif primary_reason_type == "emergency_symptom":
        clarification_type = "emergency"
    elif primary_reason_type == "special_population":
        clarification_type = "population_specific"
    elif primary_reason_type in ["symptom_required", "pattern_missing"]:
        clarification_type = "info_completion"
    elif primary_reason_type in ["vague_intent", "missing_question_word", "too_short"]:
        clarification_type = "intent_clarification"
    else:
        clarification_type = "general"
    
    return {
        "needs_clarification": True,
        "reasons": all_reasons,
        "priority": priority,
        "clarification_type": clarification_type
    }

# =========================== 澄清问题模板 ===========================
CLARIFICATION_TEMPLATES = {
    # 头痛相关
    "headache": """请问您或病人的头痛是哪种感觉？您可以选择最接近的选项：
A. 一跳一跳的搏动性痛
B. 持续的胀痛或紧箍感  
C. 针扎或刀割样刺痛
D. 其他（请简单描述）

直接回复A/B/C/D，或描述您或病人的感受。""",
    
    "headache_location": """头痛主要在哪个位置？
A. 前额
B. 太阳穴
C. 头顶
D. 后脑勺
E. 整个头部
F. 其他位置（请说明）

请选择A-F，或告诉我具体位置。""",
    
    "headache_duration": """头痛持续多久了？
A. 几小时内
B. 1-2天
C. 3-7天
D. 一周以上
E. 反复发作

请选择A-E，或告诉我具体时间。""",
    
    # 肠胃相关
    "stomach": """肚子不舒服时，最明显的感觉是？请选择：
A. 腹痛（哪个位置最明显？）
B. 腹胀
C. 恶心/呕吐
D. 腹泻
E. 便秘

    可以多选（如AB），或直接描述您或病人的症状。""",
 # 补全字典闭合符

    
    "stomach_duration": """这种情况持续多久了？
A. 几小时内
B. 1-2天
C. 3-7天
D. 一周以上
E. 时好时坏

请选择A-E。""",
    
    "fever_temp": """请问您或病人的体温大概多少？
A. 低烧（37.3-38°C）
B. 中度发烧（38.1-39°C）
C. 高烧（39°C以上）
D. 不清楚具体温度

请选择A-D，或告诉我具体体温。""",
    
    "fever_accompany": """除了发烧，有没有其他症状？可以选择多项：
A. 咳嗽有痰
B. 喉咙痛
C. 全身酸痛
D. 发冷寒战
E. 其他（请说明）

可以直接回复字母（如AC），或描述症状。""",
    
    "medication_symptom": """您或病人目前最不舒服的症状是？
A. 发烧
B. 头痛
C. 咳嗽
D. 喉咙痛
E. 胃痛
F. 腹泻
G. 其他（请说明）

请选择A-G。""",
    
    "medication_allergy": """或病人过去对什么药物过敏？
A. 无过敏
B. 青霉素类
C. 头孢类
D. 阿司匹林
E. 布洛芬
F. 不清楚

请选择A-F。""",
    
    "general": """您最想了解哪方面？
A. 问题本身
B. 可能的原因
C. 需要警惕的危险信号
D. 就医时机
E. 预防措施

请选择A-E。""",
    
    "symptom_duration": """症状持续多久了？
A. 几小时内
B. 1-2天
C. 3-7天
D. 一周以上
E. 不清楚

请选择A-E。""",
    
    # 新增模板
    "child_age": """请问孩子的具体年龄是？
A. 0-1岁（婴儿）
B. 1-3岁（幼儿）
C. 3-6岁（学龄前）
D. 6-12岁（学龄期）
E. 12岁以上（青少年）

请选择A-E，或直接告诉我具体年龄。""",
    
    "pregnancy_week": """请问您现在怀孕几周了？
A. 早期（1-12周）
B. 中期（13-27周）
C. 晚期（28周以上）
D. 不清楚具体周数

请选择A-D，或直接告诉我孕周。""",
    
    "age_gender": """为了更好地为您或病人提供建议，请问：
1. 年龄是？
2. 性别是？

请分别回答年龄和性别。""",
    
    "chronic_conditions": """您或病人是否有以下基础疾病？（可多选）
A. 高血压
B. 糖尿病
C. 心脏病
D. 哮喘
E. 其他慢性病
F. 无

请选择A-F，或具体说明。""",
    
    "ambiguity_apple": """您是指：
A. 水果苹果（营养价值、健康益处）
B. 苹果公司产品（对健康的影响）

请选择A或B。""",
    
     "ambiguity_blood_pressure": """您是想了解：
A. 血压的测量值和正常范围
B. 高血压/低血压的健康管理
C. 血压相关的症状

请选择A-C。""",
    
}

# =========================== 智能澄清问题生成 ===========================
def generate_clarification_question(query: str, session_state: dict, detection_result: Dict = None) -> str:
    """
    基于检测结果生成澄清问题 或 紧急响应
    """
    if not detection_result:
        detection_result = _needs_clarification(query, session_state.get("clarification_turns", 0), 
                                              session_state.get("conversation_history", []),
                                              session_state.get("symptom_type", ""),
                                              user_profile=session_state.get("user_profile", {}))
                                                
    if detection_result.get("emergency_alert", False):
        # 返回空字符串，表示需要上游进行紧急响应
        return ""
    turn_count = session_state.get("clarification_turns", 0)
    clarification_answers = session_state.get("clarification_answers", [])
    symptom_type = session_state.get("symptom_type", "")
    
    # 开场白
    opening = ""
    if turn_count == 0:
        opening_templates = {
            "general": ["为了更好地帮您分析，", "为了给出更准确的建议，", "感谢您的提问，为了更准确地理解您的情况，"],
            "ambiguity": ["您提到的内容可能有不同的理解，", "为了更好地理解您的意思，", "您的问题中有些表述可能有多种含义，"],
            "emergency": ["您描述的情况需要特别注意，", "为了更好地评估您的情况，", "这种情况需要了解更多信息，"],
            "population_specific": ["为了提供适合的建议，", "考虑到您的特殊情况，", "为了更好地为您服务，"],
            "info_completion": ["为了更全面地了解您的情况，", "需要补充一些信息，", "为了更好地帮助您，"],
            "intent_clarification": ["您的问题比较广泛，", "为了更好地定位您的问题，", "您想了解的是哪个方面？"]
        }
        
        template_type = detection_result.get("clarification_type", "general")
        templates = opening_templates.get(template_type, opening_templates["general"])
        opening = random.choice(templates)
    
    # 进度提示
    progress_hint = ""
    if turn_count == 1:
        progress_hint = "再了解一点信息："
    elif turn_count == 2:
        progress_hint = "最后确认一下："
    
    # 根据澄清类型生成问题
    clarification_type = detection_result.get("clarification_type", "general")
    reasons = detection_result.get("reasons", [])
    
    # 1. 处理歧义术语
    if clarification_type == "ambiguity":
        ambiguous_terms = [r for r in reasons if r.get("type") in ["ambiguous_term", "health_ambiguity"]]
        if ambiguous_terms:
            term = ambiguous_terms[0].get("term", "")
            if term == "苹果":
                return f"{opening}{CLARIFICATION_TEMPLATES['ambiguity_apple']}"
            elif term == "血压":
                return f"{opening}{CLARIFICATION_TEMPLATES['ambiguity_blood_pressure']}"
            else:
                suggestion = ambiguous_terms[0].get("suggestion", "请明确您所指的具体含义")
                return f"{opening}{suggestion}"
    
    # 2. 处理紧急症状 (注：此分支现在被前面的 emergency_alert 拦截，保留原有逻辑用于非紧急情况)
    
    # 3. 处理特殊人群
    elif clarification_type == "population_specific":
        population_items = [r for r in reasons if r.get("type") == "special_population"]
        if population_items:
            category = population_items[0].get("category", "")
            if "child" in category:
                return f"{opening}{CLARIFICATION_TEMPLATES['child_age']}"
            elif "pregnancy" in category:
                return f"{opening}{CLARIFICATION_TEMPLATES['pregnancy_week']}"
            elif "chronic" in category:
                return f"{opening}{CLARIFICATION_TEMPLATES['chronic_conditions']}"
    
    # 4. 处理症状细节缺失
    elif clarification_type == "info_completion":
        missing_items = [r for r in reasons if r.get("type") in ["pattern_missing", "symptom_required"]]
        if missing_items:
            # 优先处理最重要的缺失信息
            primary_item = missing_items[0]
            missing_info = primary_item.get("missing_info", "")
            symptom_type = primary_item.get("symptom_type", "")
            
            # 根据症状类型和缺失信息选择模板
            if symptom_type == "headache":
                if "位置" in missing_info and turn_count == 0:
                    return f"{opening}{CLARIFICATION_TEMPLATES['headache']}"
                elif "位置" in missing_info:
                    return f"{progress_hint}{CLARIFICATION_TEMPLATES['headache_location']}"
                elif "持续时间" in missing_info:
                    return f"{progress_hint}{CLARIFICATION_TEMPLATES['headache_duration']}"
            
            elif symptom_type == "stomach":
                if turn_count == 0:
                    return f"{opening}{CLARIFICATION_TEMPLATES['stomach']}"
                else:
                    return f"{progress_hint}{CLARIFICATION_TEMPLATES['stomach_duration']}"
            
            elif symptom_type == "fever":
                if turn_count == 0:
                    return f"{opening}{CLARIFICATION_TEMPLATES['fever_temp']}"
                else:
                    return f"{progress_hint}{CLARIFICATION_TEMPLATES['fever_accompany']}"
            
            elif symptom_type == "medication":
                if turn_count == 0:
                    return f"{opening}{CLARIFICATION_TEMPLATES['medication_symptom']}"
                else:
                    return f"{progress_hint}{CLARIFICATION_TEMPLATES['medication_allergy']}"
            
            # 通用缺失信息处理
            info_questions = {
                "年龄": "请问您或病人的年龄是？",
                "性别": "请问您或病人的性别是？",
                "持续时间": "这种情况持续多久了？",
                "具体症状": "能具体描述一下您或病人的症状吗？",
                "过敏史": "您或病人有药物或食物过敏史吗？",
                "基础疾病": "您或病人有其他基础疾病吗？",
                "严重程度": "症状的严重程度如何？",
                "具体感觉": "具体是什么感觉？",
                "体温": "您或病人的体温是多少？",
                "孕周": "请问现在怀孕几周了？",
                "确切年龄": "请问具体年龄是？"
            }
            
            question = info_questions.get(missing_info, f"请提供{missing_info}信息")
            return f"{opening}{question}"
    
    # 5. 处理模糊意图
    elif clarification_type == "intent_clarification":
        if turn_count == 0:
            return f"{opening}{CLARIFICATION_TEMPLATES['general']}"
        else:
            # 根据上一轮回答调整
            last_answer = clarification_answers[-1] if clarification_answers else ""
            if last_answer and len(last_answer.strip()) <= 3:
                return "可以具体描述一下吗？比如具体症状或关注点？"
            else:
                return "还有其他需要补充的信息吗？"
    
    # 6. 通用处理 - 基于症状类型
    if symptom_type and turn_count == 0:
        if symptom_type == "headache":
            return f"{opening}{CLARIFICATION_TEMPLATES['headache']}"
        elif symptom_type == "stomach":
            return f"{opening}{CLARIFICATION_TEMPLATES['stomach']}"
        elif symptom_type == "fever":
            return f"{opening}{CLARIFICATION_TEMPLATES['fever_temp']}"
        elif symptom_type == "medication":
            return f"{opening}{CLARIFICATION_TEMPLATES['medication_symptom']}"
    
   # 7. 默认通用澄清
    if turn_count == 0:
        # 检查是否缺乏基本信息
        if any("年龄" in r.get("missing_info", "") for r in reasons) or any("性别" in r.get("missing_info", "") for r in reasons):
            return f"{opening}{CLARIFICATION_TEMPLATES['age_gender']}"
        else:
            return f"{opening}{CLARIFICATION_TEMPLATES['general']}"
    else:
        # 根据用户历史回答调整
        last_answer = clarification_answers[-1] if clarification_answers else ""
        if last_answer and len(last_answer.strip()) <= 3:
            return "可以具体描述一下吗？"
        else:
            return "还有其他需要补充的信息吗？"

# =========================== 增强版对话管理器 ===========================
class EnhancedDialogueManager:
    """增强版对话管理器，支持智能澄清检测和紧急响应"""
    
    def __init__(self):
        self.sessions: dict = {}
    
    def get_or_create_session(self, session_id: str) -> dict:
        """获取或创建会话状态"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "original_query": "",
                "conversation_history": [],
                "clarification_answers": [],
                "clarification_turns": 0,
                "clarification_history": [],
                "resolved_query": "",
                "symptom_type": "",
                "user_profile": {
                    "age": None,
                    "gender": None,
                    "allergy_history": None,
                    "existing_conditions": None,
                    "special_population": None
                },
                "detection_results": []
            }
        return self.sessions[session_id]
    
    def _extract_symptom_type(self, query: str) -> str:
        """提取症状类型"""
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["头疼", "头痛", "头昏", "头晕", "头沉", "头重"]):
            return "headache"
        elif any(kw in query_lower for kw in ["肚子", "胃", "腹部", "腹痛", "胃痛", "肠胃", "腹泻", "便秘"]):
            return "stomach"
        elif any(kw in query_lower for kw in ["发烧", "发热", "体温", "发冷", "怕冷"]):
            return "fever"
        elif any(kw in query_lower for kw in ["咳嗽", "咳", "嗽", "喉咙", "嗓子", "咽"]):
            return "cough"
        elif any(kw in query_lower for kw in ["皮疹", "疹子", "红点", "痒", "红肿", "疙瘩"]):
            return "rash"
        elif re.search(r"(吃|用|服).*药", query_lower):
            return "medication"
        elif "治疗" in query_lower or "处理" in query_lower or "解决" in query_lower:
            return "treatment"
        else:
            return "general"
    
    def _extract_user_info(self, query: str, session_state: dict):
        """从查询中提取用户信息"""
        query_lower = query.lower()
        
        age_patterns = [
            (r"(怀孕|孕)\s*(\d+)\s*个?月", "个月"), # 匹配“怀孕三个月”、“孕3个月”
            (r"(怀孕|孕)\s*(\d+)\s*周", "周"),     # 匹配“怀孕12周”、“孕12周”
            (r"(\d+)\s*岁半", "岁"),              # 匹配“3岁半”
            (r"(\d+)\s*岁多", "岁"),              # 匹配“3岁多”
            (r"(\d+)\s*岁[了]", "岁"),            # 匹配“3岁了”、“60岁了”
            (r"(\d+)[岁]", "岁"),                 # 匹配“3岁”、“60岁”
            (r"([零一二三四五六七八九十百]+)\s*岁", "岁"),  # 新增：匹配“六十岁”、“十二岁”
            (r"(\d+)[了]", "岁"),                 # 新增：匹配“60了”、“3了”等口语表达
            (r"(\d+)[个]?月大", "个月"),           # 匹配“3个月大”
            (r"(\d+)[个]?月", "个月"),            # 匹配“3个月”
            (r"(\d+)[天]大", "天"),               # 匹配“15天大”
            (r"我\s*(\d+)\s*岁", "岁"),           # 匹配“我60岁”
            (r"患者\s*(\d+)\s*岁", "岁"),         # 匹配“患者60岁”
            (r"老人\s*(\d+)\s*岁", "岁"),         # 匹配“老人60岁”
            (r"小孩\s*(\d+)\s*岁", "岁"),         # 匹配“小孩3岁”
            (r"(\d+)[年]龄", "岁"),               # 匹配“60年龄”（不常见但容错）
        ]
            
        
        for pattern, unit in age_patterns:
            match = re.search(pattern, query_lower)
            if match:
                try:
                    age_num = match.group(1)
                    session_state["user_profile"]["age"] = f"{age_num}{unit}"
                    break
                except:
                    pass
        
        # 提取性别
        if "男" in query_lower or "男性" in query_lower:
            session_state["user_profile"]["gender"] = "男"
        elif "女" in query_lower or "女性" in query_lower:
            session_state["user_profile"]["gender"] = "女"
        
        # 提取过敏史
        allergy_keywords = ["过敏", "青霉素", "头孢", "阿司匹林", "布洛芬", "过敏史"]
        for keyword in allergy_keywords:
            if keyword in query_lower:
                # 提取过敏相关内容
                start = max(0, query_lower.find(keyword) - 20)
                end = min(len(query_lower), query_lower.find(keyword) + 20)
                session_state["user_profile"]["allergy_history"] = query_lower[start:end]
                break
        
        # 提取基础疾病
        condition_keywords = ["高血压", "糖尿病", "心脏病", "哮喘", "肾病", "肝病", "胃病", "病史"]
        for keyword in condition_keywords:
            if keyword in query_lower:
                session_state["user_profile"]["existing_conditions"] = keyword
                break
        
        # 识别特殊人群
        for category, keywords in SPECIAL_POPULATION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    session_state["user_profile"]["special_population"] = category
                    break
    
    def _map_option_to_meaning(self, option: str, question_text: str, clarification_type: str) -> str:
        """
        将选项字母映射到其实际含义
        支持单个字母和多个字母（如"AB"、"A,B"、"A B"）
        
        Args:
            option: 用户输入的选项字母（如"A"、"AB"、"A,B"）
            question_text: 澄清问题的文本
            clarification_type: 澄清问题的类型
        
        Returns:
            选项对应的实际含义，如果不是选项则返回原输入
        """
        option = option.strip().upper()
        
        # 清理输入，移除逗号、空格等分隔符
        cleaned_option = re.sub(r'[\s,，、;]+', '', option)
        
        # 检查是否是选项字母组合
        if not re.match(r'^[A-G]+$', cleaned_option):
            return option
        
        # 分割多个选项
        options = list(cleaned_option)
        
        # 根据问题类型映射选项含义
        mapped_options = []
        
        for opt in options:
            mapped_meaning = self._map_single_option(opt, question_text, clarification_type)
            mapped_options.append(mapped_meaning)
        
        # 如果只有一个选项，直接返回
        if len(mapped_options) == 1:
            return mapped_options[0]
        
        # 多个选项用顿号连接
        return "、".join(mapped_options)
    
    def _map_single_option(self, option: str, question_text: str, clarification_type: str) -> str:
        """
        映射单个选项字母到实际含义
        """
        # 根据问题类型和选项映射到具体含义
        if "头痛是哪种感觉" in question_text or "头痛是哪种感觉" in str(question_text):
            # 头痛类型选项映射
            headache_mapping = {
                "A": "一跳一跳的搏动性痛",
                "B": "持续的胀痛或紧箍感",
                "C": "针扎或刀割样刺痛",
                "D": "其他类型的头痛"
            }
            return headache_mapping.get(option, f"选项{option}")
        
        elif "头痛主要在哪个位置" in question_text or "头痛主要在哪个位置" in str(question_text):
            # 头痛位置选项映射
            location_mapping = {
                "A": "前额",
                "B": "太阳穴", 
                "C": "头顶",
                "D": "后脑勺",
                "E": "整个头部",
                "F": "其他位置"
            }
            return location_mapping.get(option, f"选项{option}")
        
        elif "头痛持续多久了" in question_text or "头痛持续多久了" in str(question_text):
            # 头痛持续时间选项映射
            duration_mapping = {
                "A": "几小时内",
                "B": "1-2天",
                "C": "3-7天",
                "D": "一周以上",
                "E": "反复发作"
            }
            return duration_mapping.get(option, f"选项{option}")
        
        elif "血压的测量值和正常范围" in question_text or "血压相关的症状" in question_text:
            # 血压相关选项映射
            bp_mapping = {
                "A": "血压的测量值和正常范围",
                "B": "高血压/低血压的健康管理", 
                "C": "血压相关的症状"
            }
            return bp_mapping.get(option, f"选项{option}")
        
        elif "肚子不舒服时，最明显的感觉是" in question_text or "最明显的感觉是" in str(question_text):
            # 胃部症状选项映射
            stomach_mapping = {
                "A": "腹痛",
                "B": "腹胀",
                "C": "恶心/呕吐",
                "D": "腹泻",
                "E": "便秘"
            }
            return stomach_mapping.get(option, f"选项{option}")
        
        elif "体温大概多少" in question_text or "体温大概多少" in str(question_text):
            # 体温选项映射
            fever_mapping = {
                "A": "低烧（37.3-38°C）",
                "B": "中度发烧（38.1-39°C）",
                "C": "高烧（39°C以上）",
                "D": "不清楚具体温度"
            }
            return fever_mapping.get(option, f"选项{option}")
        
        elif "最不舒服的症状是" in question_text or "最不舒服的症状是" in str(question_text):
            # 症状选项映射
            symptom_mapping = {
                "A": "发烧",
                "B": "头痛",
                "C": "咳嗽",
                "D": "喉咙痛",
                "E": "胃痛",
                "F": "腹泻",
                "G": "其他症状"
            }
            return symptom_mapping.get(option, f"选项{option}")
        
        elif "您是想了解" in question_text and "血压" in question_text:
            # 血压澄清选项映射
            bp_mapping = {
                "A": "血压的测量值和正常范围",
                "B": "高血压/低血压的健康管理",
                "C": "血压相关的症状"
            }
            return bp_mapping.get(option, f"选项{option}")
        
        elif "除了发烧，有没有其他症状" in question_text or "除了发烧，有没有其他症状" in str(question_text):
            # 发烧伴随症状选项映射
            fever_accompany_mapping = {
                "A": "咳嗽有痰",
                "B": "喉咙痛",
                "C": "全身酸痛",
                "D": "发冷寒战",
                "E": "其他症状"
            }
            return fever_accompany_mapping.get(option, f"选项{option}")
        
        elif "您过去对什么药物过敏" in question_text or "药物过敏" in question_text:
            # 药物过敏选项映射
            allergy_mapping = {
                "A": "无药物过敏史",
                "B": "对青霉素类过敏",
                "C": "对头孢类过敏",
                "D": "对阿司匹林过敏",
                "E": "对布洛芬过敏",
                "F": "不清楚过敏史"
            }
            return allergy_mapping.get(option, f"选项{option}")
        
        elif "您是否有以下基础疾病" in question_text or "基础疾病" in question_text:
            # 基础疾病选项映射
            conditions_mapping = {
                "A": "高血压",
                "B": "糖尿病",
                "C": "心脏病",
                "D": "哮喘",
                "E": "其他慢性病",
                "F": "无"
            }
            return conditions_mapping.get(option, f"选项{option}")
        
        elif "孩子的具体年龄是" in question_text or "具体年龄" in question_text:
            # 孩子年龄选项映射
            child_age_mapping = {
                "A": "0-1岁（婴儿）",
                "B": "1-3岁（幼儿）",
                "C": "3-6岁（学龄前）",
                "D": "6-12岁（学龄期）",
                "E": "12岁以上（青少年）"
            }
            return child_age_mapping.get(option, f"选项{option}")
        
        # 默认情况下返回原选项，但可以进一步分析question_text来推断
        return self._general_option_mapping(option, question_text)
    
    def _general_option_mapping(self, option: str, question_text: str) -> str:
        """
        通用选项映射：从问题文本中提取选项含义
        
        Args:
            option: 选项字母
            question_text: 问题文本
        
        Returns:
            选项对应的含义
        """
        # 从问题文本中提取选项行
        lines = question_text.split('\n')
        for line in lines:
            line = line.strip()
            # 查找以"X. "开头的行
            if line.startswith(f"{option}.") or line.startswith(f"{option}．") or line.startswith(f"{option}、") or line.startswith(f"{option}："):
                # 提取选项内容
                content = line[2:].strip()
                # 移除可能的后缀
                if "（" in content:
                    content = content.split("（")[0].strip()
                if "(" in content:
                    content = content.split("(")[0].strip()
                if "：" in content:
                    content = content.split("：")[0].strip()
                if ":" in content:
                    content = content.split(":")[0].strip()
                return content
        
        return f"选项{option}"
    
    def process_user_input(self, session_id: str, message: str, is_follow_up: bool = False) -> Tuple[bool, Optional[str], str]:
        """处理用户输入，判断是否需要澄清，返回(是否需要澄清, 澄清问题或响应, 重写后的查询)"""
    
        # 获取会话状态
        state = self.get_or_create_session(session_id)
        clarification_history = state.get("clarification_history", [])
        clarification_turns = state.get("clarification_turns", 0)
        
        # 自动检测澄清回答（如果不是显式标记的 follow_up）
        if not is_follow_up and clarification_turns > 0 and clarification_history:
            user_input = message.strip()
            
            # 获取上一个澄清问题
            last_clarification = clarification_history[-1]
            last_question = last_clarification.get("question", "").lower()
            
            # 检测是否是澄清回答
            clarification_keywords = ["请选择", "选项", "a", "b", "c", "d", "e", "f", "g", "还是", "选择"]
            is_clarification_question = any(keyword in last_question for keyword in clarification_keywords)
            
            # 用户回答简短且不包含疑问词
            question_words = ["吗", "什么", "怎么", "为什么", "？", "?", "如何"]
            # 支持多个字母选项（如"AB"、"AC"等）
            cleaned_input = user_input.replace(' ', '').replace(',', '').replace('，', '').replace('、', '')
            is_multi_letter_answer = re.match(r'^[A-Ga-g]+$', cleaned_input)
            
            # 如果上一个问题是澄清问题，且用户回答是字母选项或简短回答，自动标记为澄清回答
            if is_clarification_question and (is_multi_letter_answer or (len(user_input) <= 10 and not any(word in user_input.lower() for word in question_words))):
                is_follow_up = True
        
        # 从查询中提取用户信息
        self._extract_user_info(message, state)
        
        if not is_follow_up:
            # 新问题 - 重置所有澄清状态
            state["original_query"] = message
            state["clarification_answers"] = []
            state["clarification_turns"] = 0
            state["clarification_history"] = []
            state["conversation_history"].append({"role": "user", "content": message})
            
            # 识别症状类型
            state["symptom_type"] = self._extract_symptom_type(message)
            
            # 检测是否需要澄清
            detection_result = _needs_clarification(
                message, 
                state["clarification_turns"],
                state["conversation_history"],
                state.get("symptom_type", ""),
                user_profile=state.get("user_profile", {})
            )
            
            state["detection_results"] = detection_result.get("reasons", [])
            
            # ===== 紧急情况早期处理 =====
            if detection_result.get("emergency_alert", False):
                # 直接生成紧急响应
                emergency_keywords = []
                for reason in detection_result.get("reasons", []):
                    if reason.get("type") == "emergency_symptom":
                        emergency_keywords.append(reason.get("keyword", "相关症状"))
                
                symptoms_text = "、".join(emergency_keywords)
                
                # 构建紧急安全指引
                emergency_response = f"""【重要安全提醒】

                    您描述的症状包含"{symptoms_text}"，这可能提示存在需要紧急医疗干预的情况。

                    ⚠️ **请立即采取以下行动：**
                    1.  **停止在线咨询**，立即前往最近医院的急诊科。
                    2.  或立即拨打急救电话（中国大陆拨打 120）。
                    3.  请勿自行用药或等待观察。

                    本健康助手无法处理急症或危重病情。在获得专业医疗人员诊治前，请不要依赖任何网络信息做决定。

                    健康与安全是第一位的，请立即寻求线下专业医疗帮助！"""
                
                # 更新会话状态
                state["resolved_query"] = "[紧急情况已响应，建议立即就医]"
                state["conversation_history"].append({"role": "assistant", "content": emergency_response})
                
                # 返回：不继续澄清、紧急响应、已处理的查询
                return False, emergency_response, state["resolved_query"]
            
            # 非紧急情况：继续原有逻辑
            if detection_result.get("needs_clarification", False):
                # 生成澄清问题
                q = generate_clarification_question(message, state, detection_result)
                
                if q:  # 生成器返回非空澄清问题
                    state["clarification_turns"] = 1
                    state["clarification_history"].append({
                        "type": detection_result.get("clarification_type", "general"),
                        "priority": detection_result.get("priority", "normal"),
                        "question": q,
                        "reasons": detection_result.get("reasons", [])
                    })
                    return True, q, ""
            
            # 不需要澄清，直接重写查询
            state["resolved_query"] = self._rewrite_query(message, [], state)
            return False, None, state["resolved_query"]
        
        else:
            # 处理澄清回答
            # 获取上一个澄清问题，用于选项映射
            last_clarification = None
            if state["clarification_history"]:
                last_clarification = state["clarification_history"][-1]
            
            # 处理用户回答：如果是选项字母，转换为对应含义
            processed_answer = message.strip()
            if last_clarification:
                question_text = last_clarification.get("question", "")
                clarification_type = last_clarification.get("type", "")
                processed_answer = self._map_option_to_meaning(message, question_text, clarification_type)
            
            # 记录澄清回答
            state["clarification_answers"].append(processed_answer)
            state["conversation_history"].append({"role": "user", "content": message})
            
            # 从回答中提取用户信息
            self._extract_user_info(message, state)
            
            turn_count = state["clarification_turns"]
            
            # 检查用户是否想结束澄清
            end_keywords = ["没有", "不知道", "不清楚", "没了", "就这样", "结束", "好了", "不用了", "没有其他"]
            if any(keyword in processed_answer.lower() for keyword in end_keywords) and turn_count >= 1:
                state["resolved_query"] = self._rewrite_query(
                    state["original_query"],
                    state["clarification_answers"],
                    state
                )
                return False, None, state["resolved_query"]
            
            # 构建包含澄清信息的查询，用于重新检测
            combined_query = self._rewrite_query(
                state["original_query"],
                state["clarification_answers"],
                state
            )
            
            # 使用包含澄清信息的查询重新检测
            detection_result = _needs_clarification(
                combined_query,
                turn_count + 1,
                state["conversation_history"],
                state.get("symptom_type", ""),
                user_profile=state.get("user_profile", {})
            )
            
            # ===== 在澄清过程中检测到紧急情况 =====
            if detection_result.get("emergency_alert", False):
                # 直接生成紧急响应
                emergency_keywords = []
                for reason in detection_result.get("reasons", []):
                    if reason.get("type") == "emergency_symptom":
                        emergency_keywords.append(reason.get("keyword", "相关症状"))
                
                symptoms_text = "、".join(emergency_keywords)
                
                emergency_response = f"""【重要安全提醒】

                    在进一步了解情况时，发现您描述的症状包含"{symptoms_text}"，这可能提示存在需要紧急医疗干预的情况。

                    ⚠️ **请立即采取以下行动：**
                    1.  **停止在线咨询**，立即前往最近医院的急诊科。
                    2.  或立即拨打急救电话（中国大陆拨打 120）。
                    3.  请勿自行用药或等待观察。

                    本健康助手无法处理急症或危重病情。在获得专业医疗人员诊治前，请不要依赖任何网络信息做决定。

                    健康与安全是第一位的，请立即寻求线下专业医疗帮助！"""
                
                state["resolved_query"] = "[在澄清过程中发现紧急情况，建议立即就医]"
                state["conversation_history"].append({"role": "assistant", "content": emergency_response})
                
                # 返回：终止对话、紧急响应、已处理的查询
                return False, emergency_response, state["resolved_query"]
            
            # 过滤掉已经澄清的歧义
            if detection_result.get("reasons", []):
                original_reasons = state.get("detection_results", [])
                clarified_terms = []
                
                # 检查是否有已经回答过的歧义
                for answer in state["clarification_answers"]:
                    if answer.upper() in ["A", "B", "C", "D", "E", "F", "G"]:
                        if state["clarification_history"]:
                            last_clarification = state["clarification_history"][-1]
                            if last_clarification.get("type") == "ambiguity":
                                for reason in original_reasons:
                                    if reason.get("type") == "ambiguous_term":
                                        clarified_terms.append(reason.get("term", ""))
                
                # 过滤掉已经澄清的歧义
                filtered_reasons = []
                for reason in detection_result.get("reasons", []):
                    term = reason.get("term", "")
                    if term not in clarified_terms:
                        filtered_reasons.append(reason)
                
                detection_result["reasons"] = filtered_reasons
                detection_result["needs_clarification"] = len(filtered_reasons) > 0
            
            # 检查是否已经有足够的症状信息
            current_symptom = state.get("symptom_type", "")
            if current_symptom:
                required_infos = SYMPTOM_REQUIRED_INFO.get(current_symptom, {}).get("required", [])
                collected_infos = []
                
                # 从澄清答案中提取已收集的信息
                for answer in state["clarification_answers"]:
                    answer_lower = answer.lower()
                    if answer_lower in ["a", "b", "c", "d", "e", "f", "g"]:
                        if current_symptom == "headache":
                            if len(state["clarification_answers"]) == 1:
                                collected_infos.append("类型")
                            elif len(state["clarification_answers"]) == 2:
                                collected_infos.append("位置")
                    elif "小时" in answer_lower or "天" in answer_lower or "周" in answer_lower or "月" in answer_lower:
                        collected_infos.append("持续时间")
                    elif "岁" in answer_lower or "年龄" in answer_lower or "月龄" in answer_lower:
                        collected_infos.append("年龄")
                    elif "男" in answer_lower or "女" in answer_lower:
                        collected_infos.append("性别")
                
                # 如果关键信息已收集，不再需要澄清
                missing_required = [info for info in required_infos if info not in collected_infos]
                if not missing_required and turn_count >= 1:
                    detection_result["needs_clarification"] = False
            
            # 判断是否还需要进一步澄清
            if detection_result.get("needs_clarification", False) and turn_count < 3:
                q = generate_clarification_question(
                    state["original_query"],
                    {**state, "clarification_turns": turn_count + 1},
                    detection_result
                )
                
                if not q or q.strip() == "":
                    # 生成器返回空，说明已获取足够信息
                    state["resolved_query"] = self._rewrite_query(
                        state["original_query"],
                        state["clarification_answers"],
                        state
                    )
                    return False, None, state["resolved_query"]
                
                state["clarification_turns"] = turn_count + 1
                state["clarification_history"].append({
                    "type": detection_result.get("clarification_type", "general"),
                    "priority": detection_result.get("priority", "normal"),
                    "question": q,
                    "reasons": detection_result.get("reasons", [])
                })
                state["detection_results"].extend(detection_result.get("reasons", []))
                
                return True, q, ""
            else:
                # 澄清完成，构建最终查询
                state["resolved_query"] = self._rewrite_query(
                    state["original_query"],
                    state["clarification_answers"],
                    state
                )
                return False, None, state["resolved_query"]
    def _rewrite_query(self, original_query: str, clarification_answers: List[str], session_state: dict) -> str:
        """内部查询重写方法"""
        if not clarification_answers:
            return original_query.strip()
        
        # 使用用户画像信息
        user_profile = session_state.get("user_profile", {})
        
        # 构建查询
        query_parts = [original_query]
        
        # 添加澄清信息 - 现在包含具体含义
        if clarification_answers:
            # 改进：将选项字母转换为更易读的描述
            formatted_answers = []
            for answer in clarification_answers:
                answer_str = str(answer)
                # 如果是简单的选项字母，尝试进一步解释
                if len(answer_str) <= 3 and all(c.upper() in "ABCDEFG" for c in answer_str):
                    # 根据上下文尝试解释
                    symptom_type = session_state.get("symptom_type", "")
                    if symptom_type == "headache":
                        if answer_str.upper() == "A":
                            formatted_answers.append("一跳一跳的搏动性头痛")
                        elif answer_str.upper() == "B":
                            formatted_answers.append("持续的胀痛或紧箍感头痛")
                        elif answer_str.upper() == "C":
                            formatted_answers.append("针扎或刀割样刺痛头痛")
                        elif answer_str.upper() in ["AB", "AC", "BC", "ABC", "ABD", "ACD", "BCD"]:
                            # 多选处理
                            meanings = []
                            for letter in answer_str.upper():
                                if letter == "A":
                                    meanings.append("搏动性痛")
                                elif letter == "B":
                                    meanings.append("胀痛或紧箍感")
                                elif letter == "C":
                                    meanings.append("刺痛")
                                elif letter == "D":
                                    meanings.append("其他类型")
                            formatted_answers.append("、".join(meanings))
                        else:
                            formatted_answers.append(answer_str)
                    elif symptom_type == "fever":
                        if answer_str.upper() == "A":
                            formatted_answers.append("低烧")
                        elif answer_str.upper() == "B":
                            formatted_answers.append("中度发烧")
                        elif answer_str.upper() == "C":
                            formatted_answers.append("高烧")
                        elif answer_str.upper() == "D":
                            formatted_answers.append("不清楚体温")
                        elif answer_str.upper() in ["AB", "AC", "AD", "BC", "BD", "CD", "ABC", "ABD", "ACD", "BCD"]:
                            # 发烧伴随症状多选
                            meanings = []
                            for letter in answer_str.upper():
                                if letter == "A":
                                    meanings.append("咳嗽有痰")
                                elif letter == "B":
                                    meanings.append("喉咙痛")
                                elif letter == "C":
                                    meanings.append("全身酸痛")
                                elif letter == "D":
                                    meanings.append("发冷寒战")
                                elif letter == "E":
                                    meanings.append("其他症状")
                            formatted_answers.append("伴随症状：" + "、".join(meanings))
                        else:
                            formatted_answers.append(answer_str)
                    elif symptom_type == "stomach":
                        if answer_str.upper() in ["A", "B", "C", "D", "E"]:
                            stomach_map = {
                                "A": "腹痛", "B": "腹胀", "C": "恶心呕吐", 
                                "D": "腹泻", "E": "便秘"
                            }
                            formatted_answers.append(stomach_map.get(answer_str.upper(), answer_str))
                        else:
                            formatted_answers.append(answer_str)
                    else:
                        formatted_answers.append(answer_str)
                else:
                    formatted_answers.append(answer_str)
            
            answers_text = "，".join([ans.strip() for ans in formatted_answers if ans.strip()])
            if answers_text:
                query_parts.append(f"补充信息：{answers_text}")
        
        # 添加用户画像信息
        profile_parts = []
        if user_profile.get("age"):
            profile_parts.append(f"年龄{user_profile['age']}")
        if user_profile.get("gender"):
            profile_parts.append(f"性别{user_profile['gender']}")
        if user_profile.get("allergy_history"):
            profile_parts.append(f"过敏史：{user_profile['allergy_history']}")
        if user_profile.get("existing_conditions"):
            profile_parts.append(f"基础疾病：{user_profile['existing_conditions']}")
        
        if profile_parts:
            query_parts.append(f"用户信息：{'，'.join(profile_parts)}")
        
        # 连接所有部分
        combined_query = "。".join([p for p in query_parts if p])
        
        # 限制长度
        if len(combined_query) > 500:
            combined_query = combined_query[:497] + "..."
        
        return combined_query
    
    def is_clarification_round(self, session_id: str) -> bool:
        """判断当前是否为澄清轮次"""
        state = self.sessions.get(session_id, {})
        return len(state.get("clarification_answers", [])) > 0
    
    def get_resolved_query(self, session_id: str) -> str:
        state = self.sessions.get(session_id, {})
        return state.get("resolved_query", "")
    
    def get_session_summary(self, session_id: str) -> Dict:
        """获取会话摘要"""
        state = self.sessions.get(session_id, {})
        return {
            "original_query": state.get("original_query", ""),
            "clarification_turns": state.get("clarification_turns", 0),
            "clarification_answers": state.get("clarification_answers", []),
            "clarification_history": state.get("clarification_history", []),
            "resolved_query": state.get("resolved_query", ""),
            "symptom_type": state.get("symptom_type", ""),
            "user_profile": state.get("user_profile", {}),
            "detection_results": state.get("detection_results", [])
        }