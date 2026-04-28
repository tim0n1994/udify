"""
意图分类器 (Intent Classifier)

将自然语言输入分类为结构化意图类型，并提取关键信息。
参考: ARCHITECTURE-v2.md §4.2 认知层状态机 + §5.3 意图到目标映射
"""

import re
import json
from typing import Optional, Dict, Any, List, Tuple
from udify.core.cognition.intent import (
    Intent, IntentType, StructuredIntent, Constraint, ConstraintType
)
from udify.core.llm_client import LLMClient


class IntentClassifier:
    """意图分类器 - 将自然语言转化为结构化意图
    
    状态机流程:
    PARSING → CLASSIFYING → EXTRACTING → RESOLVING → ENRICHING → VALIDATING → DONE
    """
    
    # 意图类型关键词映射（用于快速分类）
    INTENT_KEYWORDS = {
        IntentType.DIFFICULTY_ADJUSTMENT: [
            "难", "简单", "容易", "简单", "困难", "难度", "boss", "敌人", "伤害",
            "hard", "easy", "difficulty", "damage", "enemy", "boss"
        ],
        IntentType.CONTENT_EXPANSION: [
            "新增", "添加", "扩展", "更多", "额外", "内容", "关卡", "任务",
            "add", "new", "more", "extra", "content", "level", "quest"
        ],
        IntentType.VISUAL_STYLE: [
            "画质", "纹理", "模型", "特效", "光照", "阴影", "视觉", "美化",
            "texture", "model", "effect", "lighting", "visual", "graphics", "beautify"
        ],
        IntentType.GAMEPLAY_MECHANIC: [
            "机制", "战斗", "技能", "系统", "玩法", "操作",
            "mechanic", "combat", "skill", "system", "gameplay"
        ],
        IntentType.NARRATIVE_CHANGE: [
            "剧情", "对话", "故事", "结局", "分支", "叙事",
            "story", "dialogue", "narrative", "ending", "plot"
        ],
    }
    
    # 方向和程度关键词
    DIRECTION_KEYWORDS = {
        "increase": ["增加", "提高", "加强", "增强", "提升", "变大",
                    "increase", "raise", "boost", "enhance", "improve"],
        "decrease": ["减少", "降低", "削弱", "减弱", "变小",
                    "decrease", "reduce", "lower", "weaken"],
        "change": ["改变", "修改", "调整", "变成",
                  "change", "modify", "adjust", "turn into"]
    }
    
    MAGNITUDE_KEYWORDS = {
        "slight": ["轻微", "一点点", "稍微", "小幅", "slight", "little", "slightly"],
        "moderate": ["中等", "适中", "一般", "moderate", "medium"],
        "significant": ["显著", "大幅", "明显", "很多", "significant", "dramatic", "much"],
        "extreme": ["极端", "非常", "超级", "极其", "extreme", "super", "ultra"]
    }
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client
        self.confidence_threshold = 0.6
    
    def classify(self, text: str, language: str = "zh") -> Intent:
        """分类用户的自然语言输入
        
        Args:
            text: 用户输入的自然语言
            language: 语言代码 ('zh' or 'en')
            
        Returns:
            Intent: 分类后的意图对象
        """
        # 1. 尝试基于关键词快速分类
        intent_type, keyword_confidence = self._classify_by_keywords(text, language)
        
        # 2. 如果置信度低且LLM可用，使用LLM增强
        if keyword_confidence < self.confidence_threshold and self.llm:
            intent_type, llm_confidence = self._classify_by_llm(text, language)
            if llm_confidence > keyword_confidence:
                intent_type = intent_type
                keyword_confidence = llm_confidence
        
        # 3. 提取核心目标
        primary_goal = self._extract_primary_goal(text, intent_type)
        
        # 4. 提取子目标
        sub_goals = self._extract_sub_goals(text, intent_type)
        
        # 5. 检测约束条件
        constraints = self._extract_constraints(text)
        
        # 6. 计算整体置信度
        confidence = self._calculate_confidence(text, intent_type, keyword_confidence)
        
        # 7. 检测歧义
        ambiguity_flags = self._detect_ambiguity(text, intent_type)
        
        intent = Intent(
            raw_text=text,
            language=language,
            intent_type=intent_type,
            primary_goal=primary_goal,
            sub_goals=sub_goals,
            parsing_confidence=confidence,
            ambiguity_flags=ambiguity_flags
        )
        
        return intent
    
    def to_structured(self, intent: Intent) -> StructuredIntent:
        """将Intent转换为StructuredIntent"""
        return StructuredIntent.from_intent(intent)
    
    def _classify_by_keywords(self, text: str, language: str) -> Tuple[IntentType, float]:
        """基于关键词分类"""
        text_lower = text.lower()
        scores = {}
        
        for intent_type, keywords in self.INTENT_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            if score > 0:
                scores[intent_type] = score / len(keywords)
        
        if not scores:
            return IntentType.UNKNOWN, 0.0
        
        # 返回得分最高的类型
        best_type = max(scores.keys(), key=lambda t: scores[t])
        return best_type, scores[best_type]
    
    def _classify_by_llm(self, text: str, language: str) -> Tuple[IntentType, float]:
        """使用LLM进行分类"""
        if not self.llm or not self.llm.is_available():
            return IntentType.UNKNOWN, 0.0
        
        prompt = f"""
Classify the following user input into one of these intent types:
- difficulty_adjustment: Adjusting game difficulty
- content_expansion: Adding new content
- visual_style: Changing visual appearance
- gameplay_mechanic: Modifying game mechanics
- narrative_change: Changing story/dialogue

User input: "{text}"
Language: {language}

Return JSON format:
{{
    "intent_type": "one of the above types",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}

Only return JSON, no other text.
"""
        
        try:
            response = self.llm.complete(prompt, temperature=0.3)
            if response:
                result = json.loads(response)
                intent_str = result.get("intent_type", "unknown")
                
                # 映射到IntentType
                type_map = {
                    "difficulty_adjustment": IntentType.DIFFICULTY_ADJUSTMENT,
                    "content_expansion": IntentType.CONTENT_EXPANSION,
                    "visual_style": IntentType.VISUAL_STYLE,
                    "gameplay_mechanic": IntentType.GAMEPLAY_MECHANIC,
                    "narrative_change": IntentType.NARRATIVE_CHANGE
                }
                
                intent_type = type_map.get(intent_str, IntentType.UNKNOWN)
                confidence = float(result.get("confidence", 0.5))
                return intent_type, confidence
        except Exception as e:
            print(f"LLM classification error: {e}")
        
        return IntentType.UNKNOWN, 0.0
    
    def _extract_primary_goal(self, text: str, intent_type: IntentType) -> str:
        """提取主要目标描述"""
        # 简化的提取逻辑 - 在实际应用中可增强
        if intent_type == IntentType.DIFFICULTY_ADJUSTMENT:
            # 提取难度相关目标
            if any(word in text.lower() for word in ["boss", "首领", "敌人"]):
                return "adjust_enemy_difficulty"
            return "adjust_overall_difficulty"
        elif intent_type == IntentType.CONTENT_EXPANSION:
            return "expand_game_content"
        elif intent_type == IntentType.VISUAL_STYLE:
            return "modify_visual_style"
        elif intent_type == IntentType.GAMEPLAY_MECHANIC:
            return "modify_gameplay_mechanic"
        elif intent_type == IntentType.NARRATIVE_CHANGE:
            return "change_narrative"
        return "unknown_goal"
    
    def _extract_sub_goals(self, text: str, intent_type: IntentType) -> List[str]:
        """提取子目标"""
        sub_goals = []
        text_lower = text.lower()
        
        # 根据意图类型提取特定子目标
        if intent_type == IntentType.DIFFICULTY_ADJUSTMENT:
            if any(word in text_lower for word in ["血", "hp", "生命", "health"]):
                sub_goals.append("modify_health")
            if any(word in text_lower for word in ["攻击", "伤害", "attack", "damage"]):
                sub_goals.append("modify_damage")
            if any(word in text_lower for word in ["经验", "升级", "exp", "level"]):
                sub_goals.append("modify_exp")
        
        return sub_goals
    
    def _extract_constraints(self, text: str) -> List[Constraint]:
        """提取约束条件"""
        constraints = []
        
        # 检测难度约束
        if any(word in text.lower() for word in ["不要太难", "别太难", "适中", "not too hard"]):
            constraints.append(Constraint(
                type=ConstraintType.DIFFICULTY,
                expression="difficulty < threshold",
                hard=False,
                weight=0.8
            ))
        
        # 检测平衡约束
        if any(word in text.lower() for word in ["平衡", "合理", "balanced"]):
            constraints.append(Constraint(
                type=ConstraintType.BALANCE,
                expression="all_parameters_within_reasonable_range",
                hard=True
            ))
        
        return constraints
    
    def _calculate_confidence(self, text: str, intent_type: IntentType, 
                                 keyword_confidence: float) -> float:
        """计算整体置信度"""
        base_confidence = keyword_confidence
        
        # 如果有LLM且置信度低，降低整体置信度
        if intent_type == IntentType.UNKNOWN:
            base_confidence *= 0.5
        
        # 文本长度影响置信度
        if len(text) < 5:
            base_confidence *= 0.8
        
        return min(1.0, base_confidence)
    
    def _detect_ambiguity(self, text: str, intent_type: IntentType) -> List[str]:
        """检测歧义"""
        flags = []
        
        # 检测矛盾意图
        has_increase = any(word in text.lower() for word in 
                        self.DIRECTION_KEYWORDS["increase"])
        has_decrease = any(word in text.lower() for word in 
                        self.DIRECTION_KEYWORDS["decrease"])
        
        if has_increase and has_decrease:
            flags.append("conflicting_directions")
        
        # 检测模糊参考
        if "那个" in text or "那个" in text:
            flags.append("vague_reference")
        
        return flags