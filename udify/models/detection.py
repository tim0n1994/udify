"""
引擎识别结果模型（iter4 M1，T1-ENGINE-AUTO 研究落地）。

字段级引擎指纹（不靠单一文件），支持 RPG Maker MV/MZ、Godot、Unity、miu2d。
DetectionResult 携带证据链与置信度，未知引擎返回 unknown + diagnostics，不臆测。

设计原则（T1 研究结论）：
- 纯数据（frozen），可序列化。
- 区分 syntactically_writable 与 semantically_verified。
- DetectionBudget 防 OOM（max_files/max_bytes）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EngineId(StrEnum):
    RPG_MAKER_MV = "rpg_maker_mv"
    RPG_MAKER_MZ = "rpg_maker_mz"
    GODOT = "godot"
    UNITY = "unity"
    MIU2D = "miu2d"
    UNKNOWN = "unknown"


class EvidenceStrength(StrEnum):
    DEFINITIVE = "definitive"  # 确凿指纹（如 RPGMV 的 nwjs + www/data）
    STRONG = "strong"
    WEAK = "weak"


@dataclass(frozen=True, slots=True)
class DetectionEvidence:
    """单条识别证据。"""

    kind: str  # 文件指纹类型
    source_path: str  # 相对路径
    field: str = ""  # 具体字段（如 package.json.chgamename）
    expected: str = ""  # 期望值/模式
    actual: str = ""  # 实际值
    strength: EvidenceStrength = EvidenceStrength.WEAK

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source_path": self.source_path,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
            "strength": self.strength.value,
        }


@dataclass(frozen=True, slots=True)
class DetectionBudget:
    """识别预算（防 OOM）。"""

    max_files: int = 5000
    max_bytes: int = 200 * 1024 * 1024  # 200MB


@dataclass(frozen=True, slots=True)
class DetectionDiagnostic:
    """识别诊断（未知/冲突/不完整）。"""

    code: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """引擎识别结果。"""

    engine_id: EngineId
    confidence: float  # 0-1
    evidence: tuple[DetectionEvidence, ...] = ()
    diagnostics: tuple[DetectionDiagnostic, ...] = ()
    root_path: str = ""

    @property
    def has_definitive_evidence(self) -> bool:
        return any(e.strength == EvidenceStrength.DEFINITIVE for e in self.evidence)

    @property
    def is_unknown(self) -> bool:
        return self.engine_id == EngineId.UNKNOWN

    def to_dict(self) -> dict:
        return {
            "engine_id": self.engine_id.value,
            "confidence": self.confidence,
            "has_definitive_evidence": self.has_definitive_evidence,
            "evidence": [e.to_dict() for e in self.evidence],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "root_path": self.root_path,
        }


def unknown_result(
    root_path: str, diagnostics: tuple[DetectionDiagnostic, ...] = ()
) -> DetectionResult:
    """未知引擎的安全结果。"""
    return DetectionResult(
        engine_id=EngineId.UNKNOWN,
        confidence=0.0,
        evidence=(),
        diagnostics=diagnostics or (DetectionDiagnostic("UNKNOWN_ENGINE", "无法确凿识别引擎类型"),),
        root_path=root_path,
    )
