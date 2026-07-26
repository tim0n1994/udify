"""
静态验证器 v3（VAL-STATIC-01..05）。

MODULE-ATTACK-MAP-v3 §9 VAL-STATIC：
- VAL-STATIC-01: schema validation（patch/file schema）
- VAL-STATIC-02: reference integrity（悬空引用）
- VAL-STATIC-03: numeric range（engine-specific range）
- VAL-STATIC-04: syntax reparse（修改后重新解析）
- VAL-STATIC-05: dangerous API scan（Lua/DSL）

输出统一 ValidationReportV3（§5.3）：
passed / blocking_errors / warnings / evidence / confidence / recommended_action
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from udify.core.perception.parsers.lua_ts_parser import DANGEROUS_APIS, TreeSitterLuaParser
from udify.models.cdl_patch import CDLPatch, ExecutionMode, OpType
from udify.models.content_graph import ContentGraph


@dataclass
class ValidationFinding:
    """单条验证发现。"""

    check: str  # 哪个检查（VAL-STATIC-01..05）
    severity: str  # error / warning
    message: str
    target_id: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReportV3:
    """v3 统一验证报告（§5.3）。"""

    passed: bool = True
    blocking_errors: list[ValidationFinding] = field(default_factory=list)
    warnings: list[ValidationFinding] = field(default_factory=list)
    evidence: list[ValidationFinding] = field(default_factory=list)
    confidence: float = 1.0
    recommended_action: str = "proceed"

    def add_error(self, finding: ValidationFinding) -> None:
        self.blocking_errors.append(finding)
        self.passed = False
        self.recommended_action = "fix_blocking_errors"

    def add_warning(self, finding: ValidationFinding) -> None:
        self.warnings.append(finding)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blocking_errors": [f.__dict__ for f in self.blocking_errors],
            "warnings": [f.__dict__ for f in self.warnings],
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "error_count": len(self.blocking_errors),
            "warning_count": len(self.warnings),
        }


# miu2d 数值范围（VAL-STATIC-03：engine-specific range）
_NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "health": (0, 999999),
    "offense": (0, 99999),
    "defense": (0, 99999),
    "mana": (0, 99999),
    "speed": (0, 1000),
    "critical": (0, 1.0),
    "drop": (0, 1.0),
    "experience": (0, 9999999),
    "currency": (0, 9999999),
    "level": (1, 999),
}


class StaticValidatorV3:
    """静态验证器 v3。"""

    def __init__(self) -> None:
        self.lua_parser = TreeSitterLuaParser()

    def validate(
        self,
        patch: CDLPatch,
        graph: ContentGraph,
        vfs_diffs: list[dict[str, Any]] | None = None,
    ) -> ValidationReportV3:
        """运行全部 P0 静态检查。"""
        report = ValidationReportV3()

        # VAL-STATIC-01: schema validation
        self._check_schema(patch, report)
        # VAL-STATIC-02: reference integrity
        self._check_references(patch, graph, report)
        # VAL-STATIC-03: numeric range
        self._check_numeric_range(patch, graph, report)
        # VAL-STATIC-04: syntax reparse（检查 patch 后文件仍可解析）
        if vfs_diffs:
            self._check_syntax_reparse(vfs_diffs, report)
        # VAL-STATIC-05: dangerous API scan
        self._check_dangerous_apis(patch, vfs_diffs, report)

        return report

    def _check_schema(self, patch: CDLPatch, report: ValidationReportV3) -> None:
        """VAL-STATIC-01: patch 操作 schema 校验。"""
        for op in patch.operations:
            if not op.target_id:
                report.add_error(
                    ValidationFinding(
                        check="VAL-STATIC-01",
                        severity="error",
                        message=f"operation {op.op_type.name} missing target_id",
                        target_id=op.target_id,
                    )
                )
            # file_patch 必须有 emitter 或 key
            if op.execution_mode == ExecutionMode.FILE_PATCH:
                payload = op.payload
                if not payload.get("emitter") and not payload.get("key"):
                    report.add_error(
                        ValidationFinding(
                            check="VAL-STATIC-01",
                            severity="error",
                            message="file_patch operation missing 'emitter' or 'key'",
                            target_id=op.target_id,
                        )
                    )

    def _check_references(
        self, patch: CDLPatch, graph: ContentGraph, report: ValidationReportV3
    ) -> None:
        """VAL-STATIC-02: 引用完整性（悬空引用）。"""
        node_ids = {n.id for n in graph.nodes}
        for op in patch.operations:
            # MODIFY_PROPERTY / REMOVE_NODE 的 target 必须存在
            if op.op_type in (OpType.MODIFY_PROPERTY, OpType.REMOVE_NODE, OpType.MODIFY_ASSET):
                if op.target_id not in node_ids:
                    # 除非是 file_patch emitter 模式（target 可能是合成的）
                    if op.payload.get("emitter") in ("ini", "generic"):
                        continue
                    report.add_error(
                        ValidationFinding(
                            check="VAL-STATIC-02",
                            severity="error",
                            message=f"dangling reference: target '{op.target_id}' not in graph",
                            target_id=op.target_id,
                        )
                    )

    def _check_numeric_range(
        self, patch: CDLPatch, graph: ContentGraph, report: ValidationReportV3
    ) -> None:
        """VAL-STATIC-03: 数值范围（engine-specific）。"""
        from udify.core.perception.semantic_lifter import _NUMERIC_ATTRIBUTES, _norm

        for op in patch.operations:
            if op.op_type != OpType.MODIFY_PROPERTY:
                continue
            key = op.payload.get("key", "")
            value = op.payload.get("value")
            if value is None or not isinstance(value, (int, float)):
                continue
            kind = _NUMERIC_ATTRIBUTES.get(_norm(key))
            if kind and kind in _NUMERIC_RANGES:
                lo, hi = _NUMERIC_RANGES[kind]
                if value < lo or value > hi:
                    report.add_error(
                        ValidationFinding(
                            check="VAL-STATIC-03",
                            severity="error",
                            message=f"{key}={value} out of range [{lo}, {hi}] for {kind}",
                            target_id=op.target_id,
                            evidence={"key": key, "value": value, "range": [lo, hi]},
                        )
                    )

    def _check_syntax_reparse(
        self, vfs_diffs: list[dict[str, Any]], report: ValidationReportV3
    ) -> None:
        """VAL-STATIC-04: 修改后重新解析（INi 仍可解析、Lua 仍可解析）。"""
        for diff in vfs_diffs:
            path = diff.get("path", "")
            new_content = diff.get("new_content", "")
            if not new_content:
                continue
            if path.endswith(".ini"):
                # INI：每个非空非注释行要么是 [section] 要么含 =
                from udify.core.text_normalize import is_valid_ini_line

                for i, line in enumerate(new_content.splitlines(), 1):
                    stripped = line.strip()
                    if is_valid_ini_line(stripped):
                        continue
                    report.add_warning(
                        ValidationFinding(
                            check="VAL-STATIC-04",
                            severity="warning",
                            message=f"{path}:{i} not valid INI (no '='): {stripped[:40]}",
                        )
                    )
            elif path.endswith(".lua"):
                analysis = self.lua_parser.analyze(new_content)
                if not analysis.available:
                    continue
                # 粗略：括号配平
                if new_content.count("(") != new_content.count(")"):
                    report.add_warning(
                        ValidationFinding(
                            check="VAL-STATIC-04",
                            severity="warning",
                            message=f"{path} unbalanced parens after patch",
                        )
                    )

    def _check_dangerous_apis(
        self,
        patch: CDLPatch,
        vfs_diffs: list[dict[str, Any]] | None,
        report: ValidationReportV3,
    ) -> None:
        """VAL-STATIC-05: 危险 API 扫描（Lua/DSL）。"""
        # 检查 patch 引入的 Lua body
        for op in patch.operations:
            body = op.payload.get("body", "")
            if isinstance(body, str) and body:
                danger = self._scan_dangerous(body)
                if danger:
                    report.add_error(
                        ValidationFinding(
                            check="VAL-STATIC-05",
                            severity="error",
                            message=f"patch introduces dangerous API ({danger})",
                            target_id=op.target_id,
                            evidence={"category": danger},
                        )
                    )
        # 检查 VFS diff 中新写入的 Lua
        if vfs_diffs:
            for diff in vfs_diffs:
                path = diff.get("path", "")
                content = diff.get("new_content", "")
                if path.endswith(".lua") and content:
                    danger = self._scan_dangerous(content)
                    if danger:
                        report.add_error(
                            ValidationFinding(
                                check="VAL-STATIC-05",
                                severity="error",
                                message=f"{path} contains dangerous API ({danger})",
                                evidence={"category": danger},
                            )
                        )

    def _scan_dangerous(self, text: str) -> str | None:
        """扫描文本中的危险 API（归一化匹配）。"""
        from udify.core.text_normalize import normalize_identifier

        normalized = normalize_identifier(text)
        for api, category in DANGEROUS_APIS.items():
            api_norm = normalize_identifier(api)
            if api_norm and api_norm in normalized:
                return category
        return None


__all__ = ["StaticValidatorV3", "ValidationFinding", "ValidationReportV3"]
