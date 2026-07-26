"""
Udify 证据链原语（v3 数据地基）。

对应 ITERATION-PLAN-2026-07.md §4.1「数据模型（证据链先行）」与任务
`DATA-CG-01..05`。这些原语让每个 ContentNode / PatchOperation 都能回溯到
来源文件位置、提取工具与置信度——这是成功判据 #2「每个 PatchOperation 能
回溯到 SourceSpan 和 planning reason」的基础。

设计约束（来自计划）：
- 全部作为现有 dataclass 的 optional 字段兼容挂载，不做大搬家；
- ``to_dict`` / ``from_dict`` 向后兼容，旧 session 可读；
- 未知显式标记为 ``unknown``，不留隐式 None。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceSpan:
    """内容在原始来源中的位置。

    一个 SourceSpan 唯一定位"这段内容来自哪里"：哪个文件、哪个字节/行列范围、
    （若是归档内文件）归档路径、内容哈希、由哪个工具运行提取。

    Attributes:
        file_path: 相对 game_root 的路径。
        byte_start/byte_end: 字节范围（可选，二进制资源用）。
        line_start/line_end: 行范围（可选，文本用，1-based）。
        col_start/col_end: 列范围（可选，1-based）。
        ast_path: AST/结构化路径（如 ``["section","Boss","MaxLife"]``）。
        archive_path: 若来自归档内的文件，归档内相对路径。
        content_hash: 该 span 内容的 sha256（前 16 字符），用于回滚一致性校验。
        extractor: 提取该 span 的 ToolRunRef（哪个工具、哪次运行）。
    """

    file_path: str
    byte_start: int | None = None
    byte_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    col_start: int | None = None
    col_end: int | None = None
    ast_path: tuple[str, ...] = field(default_factory=tuple)
    archive_path: str | None = None
    content_hash: str | None = None
    extractor: ToolRunRef | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "col_start": self.col_start,
            "col_end": self.col_end,
            "ast_path": list(self.ast_path),
            "archive_path": self.archive_path,
            "content_hash": self.content_hash,
            "extractor": self.extractor.to_dict() if self.extractor else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceSpan:
        ext = data.get("extractor")
        return cls(
            file_path=data["file_path"],
            byte_start=data.get("byte_start"),
            byte_end=data.get("byte_end"),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            col_start=data.get("col_start"),
            col_end=data.get("col_end"),
            ast_path=tuple(data.get("ast_path", [])),
            archive_path=data.get("archive_path"),
            content_hash=data.get("content_hash"),
            extractor=ToolRunRef.from_dict(ext) if ext else None,
        )


@dataclass(frozen=True)
class ToolRunRef:
    """对一次工具运行的引用（溯源用）。

    Attributes:
        tool_id: 工具标识（如 ``miu2d_converter``、``ini_parser``）。
        version: 工具版本（未知显式 ``unknown``）。
        args_hash: 调用参数的哈希（前 16 字符），用于可重放。
        input_hash: 输入内容的哈希（前 16 字符）。
    """

    tool_id: str
    version: str = "unknown"
    args_hash: str | None = None
    input_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "version": self.version,
            "args_hash": self.args_hash,
            "input_hash": self.input_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolRunRef:
        return cls(
            tool_id=data["tool_id"],
            version=data.get("version", "unknown"),
            args_hash=data.get("args_hash"),
            input_hash=data.get("input_hash"),
        )


@dataclass(frozen=True)
class Provenance:
    """数据来源溯源（provenance）。

    记录一个节点/属性是"被哪个工具、以什么参数、从什么输入"提取出来的，
    让每次工具调用都可回放（对应 §7.3 供应链审计）。

    Attributes:
        tool: 提取它的工具运行引用。
        extracted_at: 提取时间（ISO 8601，未知 ``unknown``）。
        method: 提取方法描述（如 ``ini_section_parse``）。
    """

    tool: ToolRunRef
    extracted_at: str = "unknown"
    method: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool.to_dict(),
            "extracted_at": self.extracted_at,
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        return cls(
            tool=ToolRunRef.from_dict(data["tool"]),
            extracted_at=data.get("extracted_at", "unknown"),
            method=data.get("method", "unknown"),
        )


@dataclass(frozen=True)
class Confidence:
    """置信度。

    一个数值 + 产生方法 + 支撑证据引用，避免"裸分数无法解释"。

    Attributes:
        score: 0.0–1.0。
        method: 产生方法（``heuristic`` / ``llm`` / ``parser`` / ``unknown``）。
        evidence_refs: 支撑该分数的证据 ID 列表。
    """

    score: float = 0.0
    method: str = "unknown"
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            object.__setattr__(self, "score", max(0.0, min(1.0, self.score)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "method": self.method,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Confidence:
        return cls(
            score=float(data.get("score", 0.0)),
            method=data.get("method", "unknown"),
            evidence_refs=tuple(data.get("evidence_refs", [])),
        )


@dataclass(frozen=True)
class Evidence:
    """一条证据。

    把"为什么这样判定"显式化：一条文字描述 + 来源 span + 可选原始数据。

    Attributes:
        evidence_id: 唯一标识。
        description: 人类可读描述。
        span: 相关来源位置（可选）。
        payload: 原始证据数据（如解析出的原始行、工具原始输出片段）。
    """

    evidence_id: str
    description: str
    span: SourceSpan | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "description": self.description,
            "span": self.span.to_dict() if self.span else None,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        span = data.get("span")
        return cls(
            evidence_id=data["evidence_id"],
            description=data["description"],
            span=SourceSpan.from_dict(span) if span else None,
            payload=data.get("payload", {}),
        )


__all__ = [
    "Confidence",
    "Evidence",
    "Provenance",
    "SourceSpan",
    "ToolRunRef",
]
