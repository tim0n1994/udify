"""
意图数据结构定义

定义结构化意图、约束、参考等核心数据结构。
参考: ARCHITECTURE-v2.md §4.2 认知层状态机
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(Enum):
    """意图类型枚举"""

    # 游戏相关
    DIFFICULTY_ADJUSTMENT = "difficulty_adjustment"
    CONTENT_EXPANSION = "content_expansion"
    VISUAL_STYLE = "visual_style"
    GAMEPLAY_MECHANIC = "gameplay_mechanic"
    NARRATIVE_CHANGE = "narrative_change"

    # 通用
    UNKNOWN = "unknown"


class ConstraintType(Enum):
    """约束类型枚举"""

    BUDGET = "budget"
    TIME = "time"
    QUALITY = "quality"
    LEGAL = "legal"
    BALANCE = "balance"
    DIFFICULTY = "difficulty"
    FEEL = "feel"


@dataclass
class Constraint:
    """约束条件"""

    type: ConstraintType
    expression: str  # 机器可解析的约束表达式
    hard: bool = True  # 硬约束（必须满足）vs 软约束（尽量满足）
    weight: float = 1.0  # 权重（软约束时使用）


@dataclass
class Reference:
    """参考案例"""

    name: str
    type: str  # 参考类型：game_series, game_title, style, etc.
    features: list[str] = field(default_factory=list)  # 提取的特征列表
    confidence: float = 0.0  # 匹配置信度 0-1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Intent:
    """用户意图的基础表示"""

    raw_text: str  # 原始用户输入
    language: str = "zh"  # 语言
    timestamp: str = ""  # ISO 8601 时间戳

    # 解析后的信息
    intent_type: IntentType = IntentType.UNKNOWN
    primary_goal: str = ""  # 主要目标描述
    sub_goals: list[str] = field(default_factory=list)  # 子目标列表

    # 置信度
    parsing_confidence: float = 0.0
    ambiguity_flags: list[str] = field(default_factory=list)  # 歧义标记
    negative_preferences: list[str] = field(default_factory=list)  # v3 负向偏好（COG-INTENT-04）


@dataclass
class AcceptanceProbe:
    """验收探针建议（COG-INTENT-05）。

    连接"意图"和"运行时验证"：每个目标至少一个可验证探针建议。
    """

    goal_ref: str  # 对应 primary_goal.target 或 sub_goal id
    probe_kind: str  # read_state / assert / console_scan
    description: str = ""
    expect: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredIntent:
    """结构化意图 v3 - 机器可执行的意图表示（COG-INTENT-01..05）。

    v3 变更（参考 ITERATION-PLAN-2026-07.md §5.2）：
    - version 提升到 "3.0"
    - 新增 ``negative_preferences``：表达"不要数值膨胀"等禁止路径（COG-INTENT-04）
    - 新增 ``acceptance_probes``：每个目标至少一个可验证探针建议（COG-INTENT-05）
    - ``ambiguity`` 字段：模糊目标要求澄清或降级，不能硬猜（COG-INTENT-02）
    """

    version: str = "3.0"
    intent_id: str = ""  # UUID

    # 用户原始输入
    raw_input: dict[str, Any] = field(
        default_factory=lambda: {"text": "", "language": "zh", "timestamp": ""}
    )

    # 核心意图（分类结果）
    primary_goal: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "",
            "target": "",
            "direction": "",  # increase/decrease/change
            "magnitude": "",  # slight/moderate/significant/extreme
        }
    )

    # 子目标（分解结果）
    sub_goals: list[dict[str, Any]] = field(default_factory=list)
    # 每个子目标包含: type, target_mechanic, parameter, change

    # 参考案例（解析结果）
    references: list[Reference] = field(default_factory=list)

    # 约束条件
    constraints: list[Constraint] = field(default_factory=list)

    # v3 负向偏好：用户明确"不要"的实现路径（COG-INTENT-04，如"不要数值膨胀"）
    negative_preferences: list[str] = field(default_factory=list)

    # v3 验收探针建议：每个目标至少一个（COG-INTENT-05）
    acceptance_probes: list[AcceptanceProbe] = field(default_factory=list)

    # v3 歧义处理（COG-INTENT-02）：模糊目标要求澄清或降级，不能硬猜
    ambiguity: dict[str, Any] = field(
        default_factory=lambda: {
            "flags": [],  # 歧义标记
            "action": "none",  # none / clarify / degrade
            "clarification_question": "",  # action=clarify 时的提问
        }
    )

    # 用户偏好（从记忆系统注入）
    preferences: dict[str, Any] = field(
        default_factory=lambda: {
            "difficulty_baseline": "",
            "preferred_genres": [],
            "disliked_mechanics": [],
        }
    )

    # 元数据
    metadata: dict[str, Any] = field(
        default_factory=lambda: {
            "parsing_confidence": 0.0,
            "ambiguity_flags": [],
            "estimated_complexity": "medium",  # low/medium/high/extreme
        }
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "version": self.version,
            "intent_id": self.intent_id,
            "raw_input": self.raw_input,
            "primary_goal": self.primary_goal,
            "sub_goals": self.sub_goals,
            "references": [
                {
                    "name": r.name,
                    "type": r.type,
                    "features": r.features,
                    "confidence": r.confidence,
                    "metadata": r.metadata,
                }
                for r in self.references
            ],
            "constraints": [
                {
                    "type": c.type.value if isinstance(c.type, Enum) else c.type,
                    "expression": c.expression,
                    "hard": c.hard,
                    "weight": c.weight,
                }
                for c in self.constraints
            ],
            "negative_preferences": self.negative_preferences,
            "acceptance_probes": [
                {
                    "goal_ref": p.goal_ref,
                    "probe_kind": p.probe_kind,
                    "description": p.description,
                    "expect": p.expect,
                }
                for p in self.acceptance_probes
            ],
            "ambiguity": self.ambiguity,
            "preferences": self.preferences,
            "metadata": self.metadata,
        }

    @classmethod
    def from_intent(cls, intent: Intent) -> "StructuredIntent":
        """从基础 Intent 创建 StructuredIntent"""
        import uuid

        structured = cls(
            intent_id=str(uuid.uuid4()),
            raw_input={
                "text": intent.raw_text,
                "language": intent.language,
                "timestamp": intent.timestamp or "",
            },
        )

        # 映射 primary_goal
        if intent.intent_type != IntentType.UNKNOWN:
            structured.primary_goal["type"] = intent.intent_type.value

        structured.primary_goal["target"] = intent.primary_goal
        structured.primary_goal["direction"] = "change"  # 默认方向

        # 子目标
        for sub in intent.sub_goals:
            structured.sub_goals.append(
                {
                    "type": "generic",
                    "target_mechanic": sub,
                    "parameter": "",
                    "change": {"type": "set", "value": None},
                }
            )

        structured.metadata["parsing_confidence"] = intent.parsing_confidence
        structured.metadata["ambiguity_flags"] = intent.ambiguity_flags
        structured.negative_preferences = list(intent.negative_preferences)

        # v3 歧义处理（COG-INTENT-02）：有歧义标记时降级
        if intent.ambiguity_flags:
            structured.ambiguity["flags"] = list(intent.ambiguity_flags)
            structured.ambiguity["action"] = "degrade"
            structured.ambiguity["clarification_question"] = (
                f"意图含歧义标记 {intent.ambiguity_flags}，已降级置信度；如需精确结果请澄清。"
            )

        # v3 验收探针（COG-INTENT-05）：为 primary_goal 建议至少一个探针
        if structured.primary_goal.get("target"):
            structured.acceptance_probes.append(
                AcceptanceProbe(
                    goal_ref=structured.primary_goal["target"],
                    probe_kind="read_state",
                    description=f"验证目标「{structured.primary_goal['target']}」的修改后状态可读",
                )
            )

        return structured
