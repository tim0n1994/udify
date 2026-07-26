"""
Udify Validation - Enhanced Validator

增强验证器：结合静态验证、知识验证、运行时验证。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from udify.core.execution.sandbox import SafetyReport, SandboxExecutor
from udify.core.knowledge.knowledge_graph import GameKnowledgeGraph, KnowledgeWarning
from udify.core.security.sanitizer import OutputValidator
from udify.models.cdl_patch import CDLPatch


@dataclass
class ValidationReport:
    """验证报告"""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    knowledge_warnings: list[KnowledgeWarning]
    safety_report: SafetyReport | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "knowledge_warning_count": len(self.knowledge_warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "knowledge_warnings": [
                {"level": w.level, "message": w.message} for w in self.knowledge_warnings
            ],
            "safety_report": self.safety_report.to_dict() if self.safety_report else None,
            "stats": self.stats,
        }


class EnhancedValidator:
    """
    增强验证器

    三级验证：
    1. 静态验证（引用完整性、数值范围、格式合法）
    2. 知识验证（基于游戏知识图谱）
    3. 安全验证（沙箱静态分析）
    """

    def __init__(self) -> None:
        self.knowledge_graph = GameKnowledgeGraph()
        self.sandbox = SandboxExecutor()
        self.output_validator = OutputValidator()

    async def validate(self, patch: CDLPatch, graph: Any = None) -> ValidationReport:
        """
        全面验证 Patch
        """
        errors = []
        warnings = []
        knowledge_warnings = []
        safety_report = None

        # 1. 输出格式验证
        patch_dict = patch.to_dict()
        format_valid, format_errors = self.output_validator.validate_patch(patch_dict)
        errors.extend(format_errors)

        # 2. 引用完整性验证
        ref_errors = self._validate_references(patch, graph)
        errors.extend(ref_errors)

        # 3. 数值范围验证
        numeric_warnings = self._validate_numeric_ranges(patch)
        warnings.extend(numeric_warnings)

        # 4. 知识验证
        knowledge_warnings = self.knowledge_graph.validate_mod_against_knowledge(
            [
                op.to_dict()
                if hasattr(op, "to_dict")
                else {"op_type": op.op_type.name, "payload": op.payload}
                for op in patch.operations
            ]
        )

        # 5. 安全验证（脚本）
        for op in patch.operations:
            has_code = "code" in op.payload
            is_script_op = op.op_type.name in ["INSERT_SCRIPT", "MODIFY_SCRIPT"]
            if is_script_op or has_code:
                code = op.payload.get("code", "")
                language = op.payload.get("language", "lua")
                if code:
                    safety_report = self.sandbox.validate_script_safety(code, language)
                    if not safety_report.is_safe:
                        errors.extend(
                            [
                                f"安全警告: {v['message']}"
                                for v in safety_report.vulnerabilities
                                if v["level"] == "critical"
                            ]
                        )
                        warnings.extend(
                            [
                                f"安全警告: {v['message']}"
                                for v in safety_report.vulnerabilities
                                if v["level"] in ["high", "warning"]
                            ]
                        )

        # 6. 路径安全验证
        path_errors = self._validate_paths(patch)
        errors.extend(path_errors)

        # 7. 检查点验证
        checkpoint_warnings = self._validate_checkpoints(patch)
        warnings.extend(checkpoint_warnings)

        is_valid = len(errors) == 0 and not any(
            w.level in ["error", "critical"] for w in knowledge_warnings
        )

        stats = {
            "total_operations": len(patch.operations),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "knowledge_warnings": len(knowledge_warnings),
            "critical_safety_issues": (
                sum(1 for v in safety_report.vulnerabilities if v["level"] == "critical")
                if safety_report
                else 0
            ),
        }

        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            knowledge_warnings=knowledge_warnings,
            safety_report=safety_report,
            stats=stats,
        )

    def _validate_references(self, patch: CDLPatch, graph: Any) -> list[str]:
        """验证引用完整性"""
        errors = []

        for op in patch.operations:
            target_id = op.target_id

            # 检查目标是否存在
            if graph and hasattr(graph, "get_node"):
                node = graph.get_node(target_id)
                if node is None and op.op_type.name not in ["ADD_NODE", "ADD_ASSET"]:
                    errors.append(f"操作引用不存在的节点: {target_id}")

            # 检查脚本引用
            if "script" in op.payload:
                script_path = op.payload["script"]
                # 这里应该检查文件是否存在
                # 简化版：只检查路径格式
                if not script_path.endswith(".txt") and not script_path.endswith(".lua"):
                    errors.append(f"脚本路径格式不正确: {script_path}")

            # 检查资源引用
            if "asset" in op.payload:
                asset_path = op.payload["asset"]
                valid, msg = self.output_validator.validate_asset_path(asset_path)
                if not valid:
                    errors.append(f"资源路径无效: {asset_path} - {msg}")

        return errors

    def _validate_numeric_ranges(self, patch: CDLPatch) -> list[str]:
        """验证数值范围"""
        warnings = []

        for op in patch.operations:
            if op.op_type.name in ["MODIFY_INI", "MODIFY_PROPERTY"]:
                key = op.payload.get("key", "")
                new_value = op.payload.get("value")

                if isinstance(new_value, (int, float)):
                    # 检查极端值
                    if abs(new_value) > 999999:
                        warnings.append(f"属性 {key} 的数值极大 ({new_value})，可能影响平衡")
                    elif abs(new_value) > 100000:
                        warnings.append(f"属性 {key} 的数值很大 ({new_value})，建议检查")

                    # 检查负数（主要属性）
                    if new_value < 0 and key in ["MaxLife", "MaxMana", "Strength", "Dexterity"]:
                        warnings.append(f"属性 {key} 不能为负数: {new_value}")

                    # 检查小数
                    if isinstance(new_value, float) and key in ["MaxLife", "MaxMana", "Strength"]:
                        if new_value != int(new_value):
                            warnings.append(
                                f"属性 {key} 使用了小数 ({new_value})，INI 格式可能不支持"
                            )

        return warnings

    def _validate_paths(self, patch: CDLPatch) -> list[str]:
        """验证路径安全"""
        errors = []

        for op in patch.operations:
            # 检查所有包含路径的 payload
            for key in ["file_path", "path", "source_path", "target_path"]:
                if key in op.payload:
                    path = op.payload[key]
                    valid, msg = self.output_validator.validate_asset_path(path)
                    if not valid:
                        errors.append(f"路径验证失败 [{key}={path}]: {msg}")

        return errors

    def _validate_checkpoints(self, patch: CDLPatch) -> list[str]:
        """验证检查点（确保操作序列合理）"""
        warnings = []

        # 检查重复操作
        seen = {}
        for i, op in enumerate(patch.operations):
            key = f"{op.op_type.name}:{op.target_id}"
            if key in seen:
                warnings.append(
                    f"操作 {i} 重复了操作 {seen[key]}: {op.op_type.name} on {op.target_id}"
                )
            seen[key] = i

        # 检查修改已删除的节点
        removed_nodes = set()
        for op in patch.operations:
            if op.op_type.name == "REMOVE_NODE":
                removed_nodes.add(op.target_id)

        for i, op in enumerate(patch.operations):
            if op.op_type.name in ["MODIFY_PROPERTY", "MODIFY_EDGE"]:
                if op.target_id in removed_nodes:
                    warnings.append(f"操作 {i} 尝试修改已删除的节点: {op.target_id}")

        return warnings

    def get_knowledge_summary(self) -> dict[str, Any]:
        """获取知识验证摘要"""
        return self.knowledge_graph.get_knowledge_summary()
