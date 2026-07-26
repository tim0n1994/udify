"""
意图分类器 (Intent Classifier)

将自然语言输入分类为结构化意图类型，并提取关键信息。
参考: ARCHITECTURE-v2.md §4.2 认知层状态机 + §5.3 意图到目标映射
"""

from udify.core.cognition.intent import (
    Constraint,
    ConstraintType,
    Intent,
    IntentType,
    StructuredIntent,
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
            "难",
            "简单",
            "容易",
            "简单",
            "困难",
            "难度",
            "boss",
            "敌人",
            "伤害",
            "hard",
            "easy",
            "difficulty",
            "damage",
            "enemy",
            "boss",
        ],
        IntentType.CONTENT_EXPANSION: [
            "新增",
            "添加",
            "扩展",
            "更多",
            "额外",
            "内容",
            "关卡",
            "任务",
            "add",
            "new",
            "more",
            "extra",
            "content",
            "level",
            "quest",
        ],
        IntentType.VISUAL_STYLE: [
            "画质",
            "纹理",
            "模型",
            "特效",
            "光照",
            "阴影",
            "视觉",
            "美化",
            "texture",
            "model",
            "effect",
            "lighting",
            "visual",
            "graphics",
            "beautify",
        ],
        IntentType.GAMEPLAY_MECHANIC: [
            "机制",
            "战斗",
            "技能",
            "系统",
            "玩法",
            "操作",
            "mechanic",
            "combat",
            "skill",
            "system",
            "gameplay",
        ],
        IntentType.NARRATIVE_CHANGE: [
            "剧情",
            "对话",
            "故事",
            "结局",
            "分支",
            "叙事",
            "story",
            "dialogue",
            "narrative",
            "ending",
            "plot",
        ],
    }

    # 方向和程度关键词
    DIRECTION_KEYWORDS = {
        "increase": [
            "增加",
            "提高",
            "加强",
            "增强",
            "提升",
            "变大",
            "increase",
            "raise",
            "boost",
            "enhance",
            "improve",
        ],
        "decrease": [
            "减少",
            "降低",
            "削弱",
            "减弱",
            "变小",
            "decrease",
            "reduce",
            "lower",
            "weaken",
        ],
        "change": ["改变", "修改", "调整", "变成", "change", "modify", "adjust", "turn into"],
    }

    MAGNITUDE_KEYWORDS = {
        "slight": ["轻微", "一点点", "稍微", "小幅", "slight", "little", "slightly"],
        "moderate": ["中等", "适中", "一般", "moderate", "medium"],
        "significant": ["显著", "大幅", "明显", "很多", "significant", "dramatic", "much"],
        "extreme": ["极端", "非常", "超级", "极其", "extreme", "super", "ultra"],
    }

    def __init__(self, llm_client: LLMClient | None = None):
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
        self._extract_constraints(text)

        # 6. 计算整体置信度
        confidence = self._calculate_confidence(text, intent_type, keyword_confidence)

        # 7. 检测歧义
        ambiguity_flags = self._detect_ambiguity(text, intent_type)

        # 8. v3 负向偏好（COG-INTENT-04）
        negative_prefs = self._extract_negative_preferences(text)
        # 歧义降级：有歧义标记时降低置信度（COG-INTENT-02 不能硬猜）
        if ambiguity_flags:
            confidence *= 0.6

        intent = Intent(
            raw_text=text,
            language=language,
            intent_type=intent_type,
            primary_goal=primary_goal,
            sub_goals=sub_goals,
            parsing_confidence=confidence,
            ambiguity_flags=ambiguity_flags,
            negative_preferences=negative_prefs,
        )

        return intent

    def to_structured(self, intent: Intent) -> StructuredIntent:
        """将Intent转换为StructuredIntent"""
        return StructuredIntent.from_intent(intent)

    def _classify_by_keywords(self, text: str, language: str) -> tuple[IntentType, float]:
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

    # JSON schema 约束 LLM 输出（§5.2:201 必须走 schema 约束，禁止自由文本再正则解析）
    INTENT_SCHEMA: dict = {
        "type": "object",
        "properties": {
            "intent_type": {
                "type": "string",
                "enum": [
                    "difficulty_adjustment",
                    "content_expansion",
                    "visual_style",
                    "gameplay_mechanic",
                    "narrative_change",
                ],
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reason": {"type": "string"},
        },
        "required": ["intent_type", "confidence"],
        "additionalProperties": False,
    }

    def _classify_by_llm(self, text: str, language: str) -> tuple[IntentType, float]:
        """使用LLM进行分类（结构化输出，JSON schema 约束）。

        §5.2:201 强约束：LLM 输出必须走 schema 约束，禁止自由文本再正则解析；
        LLM 只能产出候选，不能越过 schema 写入 final（防注入）。
        """
        if not self.llm or not self.llm.is_available():
            return IntentType.UNKNOWN, 0.0

        import json as _json

        prompt = _json.dumps(
            {
                "task": "classify_intent",
                "schema": self.INTENT_SCHEMA,
                "user_input": text,
                "language": language,
                "instruction": "Return ONLY a JSON object matching the schema. Do not add any text outside the JSON.",
            },
            ensure_ascii=False,
        )

        try:
            response = self.llm.complete(prompt, temperature=0.3)
            if not response:
                return IntentType.UNKNOWN, 0.0

            # 结构化校验：必须符合 schema，否则拒绝（防注入）
            result = _json.loads(response)
            if not self._validate_against_schema(result, self.INTENT_SCHEMA):
                # LLM 越过 schema → 不信任，降级到 UNKNOWN
                return IntentType.UNKNOWN, 0.0

            intent_str = result.get("intent_type", "unknown")
            type_map = {
                "difficulty_adjustment": IntentType.DIFFICULTY_ADJUSTMENT,
                "content_expansion": IntentType.CONTENT_EXPANSION,
                "visual_style": IntentType.VISUAL_STYLE,
                "gameplay_mechanic": IntentType.GAMEPLAY_MECHANIC,
                "narrative_change": IntentType.NARRATIVE_CHANGE,
            }
            intent_type = type_map.get(intent_str, IntentType.UNKNOWN)
            confidence = float(result.get("confidence", 0.5))
            # LLM 只产出候选，置信度上限 0.9（不能越过 schema 直接写入 final）
            confidence = min(0.9, max(0.0, confidence))
            return intent_type, confidence
        except Exception as e:
            print(f"LLM classification error: {e}")

        return IntentType.UNKNOWN, 0.0

    def _validate_against_schema(self, obj: dict, schema: dict) -> bool:
        """轻量 JSON-schema 校验（type/enum/required/additionalProperties）。

        防注入：LLM 产出必须严格匹配 schema，否则拒绝。不依赖外部库。
        """
        if schema.get("type") == "object" and not isinstance(obj, dict):
            return False
        # required
        for req in schema.get("required", []):
            if req not in obj:
                return False
        # additionalProperties: False → 拒绝 schema 外的字段
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            if any(k not in allowed for k in obj):
                return False
        # 逐字段校验
        for key, subschema in schema.get("properties", {}).items():
            if key not in obj:
                continue
            val = obj[key]
            stype = subschema.get("type")
            if stype == "string" and not isinstance(val, str):
                return False
            if stype == "number" and not isinstance(val, (int, float)):
                return False
            if "enum" in subschema and val not in subschema["enum"]:
                return False
            if (
                "minimum" in subschema
                and isinstance(val, (int, float))
                and val < subschema["minimum"]
            ):
                return False
            if (
                "maximum" in subschema
                and isinstance(val, (int, float))
                and val > subschema["maximum"]
            ):
                return False
        return True

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

    def _extract_sub_goals(self, text: str, intent_type: IntentType) -> list[str]:
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

    def _extract_constraints(self, text: str) -> list[Constraint]:
        """提取约束条件"""
        constraints = []

        # 检测难度约束
        if any(word in text.lower() for word in ["不要太难", "别太难", "适中", "not too hard"]):
            constraints.append(
                Constraint(
                    type=ConstraintType.DIFFICULTY,
                    expression="difficulty < threshold",
                    hard=False,
                    weight=0.8,
                )
            )

        # 检测平衡约束
        if any(word in text.lower() for word in ["平衡", "合理", "balanced"]):
            constraints.append(
                Constraint(
                    type=ConstraintType.BALANCE,
                    expression="all_parameters_within_reasonable_range",
                    hard=True,
                )
            )

        return constraints

    def _calculate_confidence(
        self, text: str, intent_type: IntentType, keyword_confidence: float
    ) -> float:
        """计算整体置信度"""
        base_confidence = keyword_confidence

        # 如果有LLM且置信度低，降低整体置信度
        if intent_type == IntentType.UNKNOWN:
            base_confidence *= 0.5

        # 文本长度影响置信度
        if len(text) < 5:
            base_confidence *= 0.8

        return min(1.0, base_confidence)

    def _detect_ambiguity(self, text: str, intent_type: IntentType) -> list[str]:
        """检测歧义（COG-INTENT-02）。"""
        flags = []
        text_lower = text.lower()

        # 检测矛盾意图
        has_increase = any(word in text_lower for word in self.DIRECTION_KEYWORDS["increase"])
        has_decrease = any(word in text_lower for word in self.DIRECTION_KEYWORDS["decrease"])

        if has_increase and has_decrease:
            flags.append("conflicting_directions")

        # 检测模糊参考（中英文指示词）
        vague_refs = ["那个", "这个", "那些", "某某", "that one", "that", "the thing", "something"]
        if any(ref in text_lower for ref in vague_refs):
            flags.append("vague_reference")

        # 检测无明确目标
        if intent_type == IntentType.UNKNOWN:
            flags.append("no_clear_target")

        # 检测缺少数值/程度
        has_magnitude = any(
            word in text_lower for words in self.MAGNITUDE_KEYWORDS.values() for word in words
        )
        has_direction_word = has_increase or has_decrease
        if intent_type != IntentType.UNKNOWN and not has_magnitude and not has_direction_word:
            flags.append("missing_magnitude")

        return flags

    def _extract_negative_preferences(self, text: str) -> list[str]:
        """提取负向偏好（COG-INTENT-04）：用户明确"不要"的实现路径。"""
        negatives: list[str] = []
        text_lower = text.lower()
        # "不要 X" / "别 X" / "no X" / "without X"
        import re

        # 中文：不要/别/禁止 + 后续词
        for m in re.finditer(r"(?:不要|别|禁止|不能)([^\s，。,!]{2,})", text):
            negatives.append(m.group(1))
        # "不要单纯翻倍" 这类
        for m in re.finditer(r"不要(单纯|直接|只是)(翻倍|数值|堆数值)", text):
            negatives.append(f"no_{m.group(2)}")
        # 英文：no X / without X
        for m in re.finditer(r"\b(?:no|without|don't)\s+(\w+)", text_lower):
            negatives.append(f"no_{m.group(1)}")
        return negatives
