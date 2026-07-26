"""
参考解析器 (Reference Resolver)

将模糊参考（如"像魂系"）解析为具体特征向量。
参考: ARCHITECTURE-GAME-MOD-v1.md §5.2 影响分析器 + §6.3 规划器使用示例
"""

import re
from typing import Any

from udify.core.cognition.intent import Reference, StructuredIntent
from udify.core.llm_client import LLMClient


class ReferenceResolver:
    """参考解析器 - 将模糊参考解析为具体特征

    参考解析流程:
    1. 在知识库中查找匹配
    2. 用LLM评估匹配度
    3. 提取特征向量
    4. 返回解析后的参考对象
    """

    # 预定义的知识库（游戏系列/风格的特征映射）
    KNOWLEDGE_BASE = {
        "魂系": {
            "name": "Dark Souls Series",
            "type": "game_series",
            "features": [
                "gradual_power_progression",
                "high_death_penalty",
                "environmental_storytelling",
                "methodical_combat_pacing",
                "punishing_difficulty",
                "bonfire_checkpoint_system",
                "interconnected_world_design",
                "minimal_tutorial",
                "die_and_learn_gameplay_loop",
            ],
            "confidence": 0.95,
        },
        "dark souls": {
            "name": "Dark Souls Series",
            "type": "game_series",
            "features": [
                "gradual_power_progression",
                "high_death_penalty",
                "environmental_storytelling",
                "methodical_combat_pacing",
            ],
            "confidence": 0.95,
        },
        "塞尔达": {
            "name": "The Legend of Zelda Series",
            "type": "game_series",
            "features": [
                "open_world_exploration",
                "puzzle_dungeons",
                "item_progression",
                "heart_container_upgrades",
                "divine_beasts_shrines",
                "hyrule_field_open_ending",
            ],
            "confidence": 0.92,
        },
        "zelda": {
            "name": "The Legend of Zelda Series",
            "type": "game_series",
            "features": ["open_world_exploration", "puzzle_dungeons", "item_progression"],
            "confidence": 0.92,
        },
        "武侠": {
            "name": "Wuxia Style",
            "type": "genre_style",
            "features": [
                "martial_arts_combat",
                "chi_energy_system",
                "sect_faction_system",
                "chinese_ancient_setting",
                "flying_sword_arts",
                "internal_external_cultivation",
            ],
            "confidence": 0.88,
        },
        "仙侠": {
            "name": "Xianxia Style",
            "type": "genre_style",
            "features": [
                "immortal_cultivation",
                "flying_sword",
                "pill_alchemy",
                "tribulation_system",
                "spirit_root_system",
                "ascension_immortal_realm",
            ],
            "confidence": 0.88,
        },
        "roguelike": {
            "name": "Roguelike Genre",
            "type": "genre",
            "features": [
                "permadeath",
                "procedural_generation",
                "high_difficulty",
                "run_based_progress",
                "meta_progression",
                "randomized_loadouts",
            ],
            "confidence": 0.90,
        },
        "metroidvania": {
            "name": "Metroidvania Genre",
            "type": "genre",
            "features": [
                "interconnected_world",
                "ability_gating",
                "backtracking",
                "map_exploration",
                "character_progression",
                "hidden_secrets",
            ],
            "confidence": 0.89,
        },
    }

    def __init__(self, llm_client: LLMClient | None = None, knowledge_base: dict | None = None):
        self.llm = llm_client
        self.knowledge_base = knowledge_base or self.KNOWLEDGE_BASE
        self.confidence_threshold = 0.6

    def resolve(self, reference_text: str, context: str | None = None) -> Reference:
        """解析参考文本

        Args:
            reference_text: 参考文本（如"像魂系"）
            context: 上下文（可选，用于LLM增强）

        Returns:
            Reference: 解析后的参考对象
        """
        # 1. 在知识库中查找匹配
        best_match = self._search_knowledge_base(reference_text)

        # 2. 如果找到匹配且置信度高，直接返回
        if best_match and best_match.confidence >= self.confidence_threshold:
            return best_match

        # 3. 如果置信度低或LLM可用，使用LLM增强
        if self.llm and self.llm.is_available():
            llm_result = self._resolve_by_llm(reference_text, context)
            if llm_result and llm_result.confidence > (best_match.confidence if best_match else 0):
                return llm_result

        # 4. 返回最佳匹配或空参考
        return best_match or Reference(name="unknown", type="unknown", features=[], confidence=0.0)

    def resolve_from_structured_intent(self, intent: StructuredIntent) -> list[Reference]:
        """从结构化意图中解析所有参考"""
        resolved_references = []

        # 从raw_input中提取可能的参考
        text = intent.raw_input.get("text", "")

        # 使用正则表达式识别常见参考模式
        patterns = [
            r"像(.+?)那样",
            r"类似(.+?)",
            r"参考(.+?)",
            r"like (.+?)",
            r"similar to (.+?)",
            r"in the style of (.+?)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                ref = self.resolve(match, context=text)
                if ref.confidence > 0:
                    resolved_references.append(ref)

        return resolved_references

    def _search_knowledge_base(self, text: str) -> Reference | None:
        """在知识库中搜索匹配"""
        text_lower = text.lower()
        best_score = 0
        best_match = None

        for key, data in self.knowledge_base.items():
            # 检查关键词是否出现在文本中
            if key.lower() in text_lower:
                score = data.get("confidence", 0.5)
                if score > best_score:
                    best_score = score
                    best_match = Reference(
                        name=data["name"],
                        type=data["type"],
                        features=data.get("features", []),
                        confidence=score,
                        metadata={"source": "knowledge_base", "key": key},
                    )

        return best_match

    def _resolve_by_llm(self, reference_text: str, context: str | None = None) -> Reference | None:
        """使用LLM解析参考"""
        if not self.llm or not self.llm.is_available():
            return None

        context_str = f"\nContext: {context}" if context else ""

        prompt = f"""
Analyze the following reference in a gaming context and extract key features.

Reference: "{reference_text}"{context_str}

Return JSON format:
{{
    "name": "canonical name of the referenced game/series/style",
    "type": "game_series|game_title|genre|style|mechanic",
    "features": ["feature1", "feature2", "feature3", ...],
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}

Focus on gameplay mechanics, art style, difficulty, progression systems, and unique features.
Only return JSON, no other text.
"""

        try:
            response = self.llm.complete(prompt, temperature=0.3)
            if response:
                import json

                result = json.loads(response)

                return Reference(
                    name=result.get("name", "unknown"),
                    type=result.get("type", "unknown"),
                    features=result.get("features", []),
                    confidence=float(result.get("confidence", 0.5)),
                    metadata={"source": "llm", "reason": result.get("reason", "")},
                )
        except Exception as e:
            print(f"LLM reference resolution error: {e}")

        return None

    def extract_features_for_planning(self, reference: Reference) -> dict[str, Any]:
        """将参考特征转换为规划可用的参数

        将特征列表转换为结构化的规划参数，
        用于指导Mod生成。
        """
        planning_params = {
            "difficulty_curve": "gradual",  # 默认渐进
            "death_penalty": "low",
            "progression_type": "linear",
            "combat_pacing": "normal",
            "storytelling": "direct",
        }

        features = reference.features

        # 根据特征调整参数
        if "gradual_power_progression" in features or "gradual" in str(features).lower():
            planning_params["difficulty_curve"] = "gradual"

        if "high_death_penalty" in features or "punishing" in str(features).lower():
            planning_params["death_penalty"] = "high"

        if "methodical_combat_pacing" in features or "slow_paced" in str(features).lower():
            planning_params["combat_pacing"] = "methodical"

        if "environmental_storytelling" in features:
            planning_params["storytelling"] = "environmental"

        if "permadeath" in features:
            planning_params["death_penalty"] = "permadeath"

        if "open_world_exploration" in features:
            planning_params["progression_type"] = "open_world"

        return planning_params
