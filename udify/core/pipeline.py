"""
Udify Core - End-to-End Pipeline (unified)

合并后的单一编排门面：感知 → 认知 → 规划 → 验证 → 评估 → 执行。

本模块取代旧的两个并存管线（``pipeline.py`` 的 ``UdifyPipeline`` 与
``pipeline_v2.py`` 的 ``AutomatedModPipeline``）。``AutomatedModPipeline`` 保留为
向后兼容别名，指向同一类。

设计参考：
- ITERATION-PLAN-2026-07.md §5.1（统一 pipeline，先还债）
- PROJECT-RESTRUCTURING-IMPLEMENTATION-MAP-v1.md §2（pipeline 作为编排门面）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.cognition.conflict_detector import ConflictDetector
from udify.core.cognition.intent import Intent, StructuredIntent
from udify.core.cognition.intent_classifier import IntentClassifier
from udify.core.cognition.reference_resolver import ReferenceResolver
from udify.core.evaluation.intent_alignment import IntentAlignmentEvaluator
from udify.core.execution.patch_executor import PatchExecutor
from udify.core.execution.vfs import VirtualFileSystem
from udify.core.infrastructure.event_bus import EventBus, EventType, emit_event
from udify.core.knowledge.knowledge_graph import GameKnowledgeGraph
from udify.core.memory.memory_store import MemoryStore
from udify.core.perception.incremental_perception import IncrementalPerception
from udify.core.planning.cost_controller import CostController
from udify.core.planning.planner import Planner
from udify.core.security.sanitizer import InputSanitizer, OutputValidator
from udify.core.session.session_manager import SessionManager, SessionStatus
from udify.core.validation.enhanced_validator import EnhancedValidator
from udify.models.cdl_patch import CDLPatch


@dataclass
class PipelineResult:
    """管道执行结果"""

    success: bool
    session_id: str
    intent: str
    patch: CDLPatch | None = None
    vfs_diffs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    # 认知层产物（让 Session 4 的 cognition/evaluation 第一次成为可被触达的真实资产）
    structured_intent: StructuredIntent | None = None
    alignment: dict[str, Any] | None = None

    def summary(self) -> str:
        lines = [
            f"PipelineResult: success={self.success}",
            f"  Session: {self.session_id}",
            f"  Intent: {self.intent}",
        ]
        if self.patch:
            lines.append(f"  Operations: {len(self.patch.operations)}")
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
        if self.vfs_diffs:
            lines.append(f"  Modified Files: {len(self.vfs_diffs)}")
        return "\n".join(lines)


class UdifyPipeline:
    """Udify 统一端到端管道。

    完整流程：
    1. 输入消毒
    2. 创建会话
    3. 感知游戏目录（增量）
    4. 认知层：意图分类 → 参考解析 → 冲突检测
    5. 规划修改方案（带成本控制）
    6. 转换为 Patch
    7. 静态验证
    8. 知识验证
    9. VFS 预览执行 + 生成 Diff
    10. 意图对齐评估
    11. 反馈记录
    12. （可选）应用到实际文件系统
    """

    def __init__(
        self,
        game_root: Path | None = None,
        event_bus: EventBus | None = None,
        session_manager: SessionManager | None = None,
        llm_client: Any = None,
    ) -> None:
        self.game_root = game_root or Path(".")
        self.event_bus = event_bus or EventBus()
        self.session_manager = session_manager or SessionManager()

        # 安全 / 感知 / 规划 / 验证
        self.sanitizer = InputSanitizer()
        self.output_validator = OutputValidator()
        self.perception = IncrementalPerception(self.game_root)
        self.planner = Planner()
        self.cost_controller = CostController()
        self.enhanced_validator = EnhancedValidator()
        self.knowledge_graph = GameKnowledgeGraph()

        # 认知层（Session 4，首次接入主流程）
        self.intent_classifier = IntentClassifier(llm_client=llm_client)
        self.reference_resolver = ReferenceResolver(llm_client=llm_client)
        self.conflict_detector = ConflictDetector(reference_resolver=self.reference_resolver)

        # 评估层
        self.alignment_evaluator = IntentAlignmentEvaluator(llm_client=llm_client)

        # 记忆系统
        self.memory_store = MemoryStore()

        self._vfs: VirtualFileSystem | None = None

    async def process_intent(
        self,
        user_id: str,
        intent: str,
        preview_only: bool = True,
        language: str = "zh",
    ) -> PipelineResult:
        """处理用户意图。

        Args:
            user_id: 用户 ID
            intent: 自然语言意图
            preview_only: 是否仅预览（不应用到实际文件系统）
            language: 意图语言（``zh``/``en``）

        Returns:
            PipelineResult: 执行结果
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. 输入消毒
        sanitize_result = self.sanitizer.sanitize(intent)
        if not sanitize_result.is_valid:
            return PipelineResult(
                success=False,
                session_id="",
                intent=intent,
                errors=sanitize_result.violations,
            )

        sanitized_intent = sanitize_result.sanitized_input

        # 2. 创建会话
        session = self.session_manager.create_session(user_id, "game")
        session.add_intent(sanitized_intent)

        await emit_event(
            self.event_bus,
            EventType.INTENT_RECEIVED,
            {"intent": sanitized_intent, "user_id": user_id},
            session_id=session.session_id,
        )

        # 3. 感知游戏目录
        try:
            graph = await self.perception.perceive()
            session.set_graph(graph)
        except Exception as e:
            errors.append(f"感知失败: {e}")
            return PipelineResult(
                success=False,
                session_id=session.session_id,
                intent=sanitized_intent,
                errors=errors,
            )

        await emit_event(
            self.event_bus,
            EventType.PERCEPTION_COMPLETED,
            {"node_count": len(graph.nodes), "edge_count": len(graph.edges)},
            session_id=session.session_id,
        )

        # 4. 认知层：意图分类 → 结构化 → 参考解析 → 冲突检测
        classified: Intent = self.intent_classifier.classify(sanitized_intent, language)
        structured_intent = self.intent_classifier.to_structured(classified)
        references = self.reference_resolver.resolve_from_structured_intent(structured_intent)
        structured_intent.references.extend(references)
        conflicts = self.conflict_detector.detect(classified, structured_intent)
        if conflicts:
            structured_intent = self.conflict_detector.resolve_conflicts(
                structured_intent, conflicts
            )
            for c in conflicts:
                warnings.append(f"{c.type}: {c.description}")

        await emit_event(
            self.event_bus,
            EventType.INTENT_PARSED,
            {"intent_type": classified.intent_type.value, "references": len(references)},
            session_id=session.session_id,
        )

        # 5. 规划修改方案（带成本控制）。
        # 把原始意图与结构化目标拼接，既保留关键词（如"血量"）供 planner/LocalModel
        # 启发式匹配，又把结构化目标作为上下文。Batch 2 的 miu2d adapter 接入后，
        # 这里会改为传入带 SourceSpan 的结构化目标 + acceptance_probes。
        from udify.core.planning.state import Intent as PlanIntent
        from udify.core.planning.state import PlanContext, PlanState

        structured_target = structured_intent.primary_goal.get("target") or ""
        plan_input = (
            f"{sanitized_intent} [goal: {structured_target}]"
            if structured_target
            else sanitized_intent
        )
        state = PlanState(
            graph=graph,
            intent=PlanIntent(description=plan_input),
            context=PlanContext(),
        )

        try:
            plan_result = await self.cost_controller.plan_with_budget(
                state,
                lambda s: self.planner.plan(s.graph, s.intent.description),
            )
        except Exception as e:
            errors.append(f"规划失败: {e}")
            return PipelineResult(
                success=False,
                session_id=session.session_id,
                intent=sanitized_intent,
                errors=errors,
                structured_intent=structured_intent,
            )

        if not plan_result.success or not plan_result.actions:
            errors.append("无法生成有效的修改方案")
            return PipelineResult(
                success=False,
                session_id=session.session_id,
                intent=sanitized_intent,
                errors=errors,
                structured_intent=structured_intent,
            )

        session.set_status(SessionStatus.PLANNING)

        # 6. 转换为 Patch
        patch = plan_result.to_patch(author="udify_pipeline")
        patch.intent = sanitized_intent
        session.add_patch(patch)

        await emit_event(
            self.event_bus,
            EventType.PLANNING_COMPLETED,
            {"operations": len(patch.operations)},
            session_id=session.session_id,
        )

        # 7. 静态验证
        try:
            validation_report = await self.enhanced_validator.validate(patch, graph)
            if not validation_report.is_valid:
                errors.extend(validation_report.errors)
                warnings.extend(validation_report.warnings)

                if validation_report.errors:
                    return PipelineResult(
                        success=False,
                        session_id=session.session_id,
                        intent=sanitized_intent,
                        patch=patch,
                        errors=errors,
                        warnings=warnings,
                        stats=validation_report.stats,
                        structured_intent=structured_intent,
                    )

            warnings.extend([w.message for w in validation_report.knowledge_warnings])
        except Exception as e:
            warnings.append(f"验证过程出错: {e}")

        # 8. 知识验证
        knowledge_warnings = self.knowledge_graph.validate_mod_against_knowledge(
            [
                op.to_dict()
                if hasattr(op, "to_dict")
                else {"op_type": op.op_type.name, "payload": op.payload}
                for op in patch.operations
            ]
        )
        if knowledge_warnings:
            warnings.extend([w.message for w in knowledge_warnings])

        # 9. VFS 预览执行
        self._vfs = VirtualFileSystem(self.game_root)
        executor = PatchExecutor(self._vfs)

        try:
            exec_result = executor.execute(patch)
            if not exec_result["success"]:
                errors.extend([f["error"] for f in exec_result["failed"]])
        except Exception as e:
            errors.append(f"执行失败: {e}")

        vfs_diffs = self._vfs.get_all_diffs() if self._vfs else []

        session.set_status(SessionStatus.EXECUTING)

        await emit_event(
            self.event_bus,
            EventType.EXECUTION_COMPLETED,
            {"modified_files": len(vfs_diffs)},
            session_id=session.session_id,
        )

        # 10. 意图对齐评估
        alignment: dict[str, Any] | None = None
        try:
            alignment = self.alignment_evaluator.evaluate(
                classified, structured_intent, patch, graph
            )
        except Exception as e:
            warnings.append(f"意图对齐评估出错: {e}")

        # 11. 反馈记录
        try:
            from udify.core.memory.memory_store import ExecutionRecord

            self.memory_store.add_execution_record(
                ExecutionRecord(
                    record_id=session.session_id,
                    session_id=session.session_id,
                    intent=sanitized_intent,
                    patch_id=patch.patch_id,
                    operations_count=len(patch.operations),
                    success=len(errors) == 0,
                )
            )
        except Exception:
            # 记忆系统失败不应阻塞主管线
            pass

        # 12. 如果不只是预览，应用到实际文件系统
        if not preview_only and not errors:
            try:
                apply_result = self._vfs.apply_to_filesystem()
                if apply_result["failed"]:
                    errors.extend(
                        [f"应用失败: {f['path']} - {f['error']}" for f in apply_result["failed"]]
                    )
            except Exception as e:
                errors.append(f"应用到文件系统失败: {e}")

        # 收集成本
        cost_report = self.cost_controller.get_report()
        session.record_cost(cost_report.spent, llm_call=cost_report.llm_calls > 0)

        stats = {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "operations": len(patch.operations),
            "modified_files": len(vfs_diffs),
            "cost_spent": cost_report.spent,
            "llm_calls": cost_report.llm_calls,
            "intent_type": classified.intent_type.value,
            "alignment_score": alignment["total_score"] if alignment else None,
        }

        success = len(errors) == 0

        if success:
            session.set_status(SessionStatus.COMPLETED)
        else:
            session.set_status(SessionStatus.FAILED)

        return PipelineResult(
            success=success,
            session_id=session.session_id,
            intent=sanitized_intent,
            patch=patch,
            vfs_diffs=vfs_diffs,
            errors=errors,
            warnings=warnings,
            stats=stats,
            structured_intent=structured_intent,
            alignment=alignment,
        )

    async def apply_pending_mod(self, session_id: str) -> dict[str, Any]:
        """应用待确认的 Mod"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}

        if not self._vfs:
            return {"success": False, "error": "No pending modifications"}

        result = self._vfs.apply_to_filesystem()
        session.set_status(SessionStatus.COMPLETED)

        await emit_event(
            self.event_bus,
            EventType.MOD_CREATED,
            {"session_id": session_id, "files": len(result.get("applied", []))},
            session_id=session_id,
        )

        return result

    def rollback_session(self, session_id: str) -> bool:
        """回滚会话"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return False

        if self._vfs:
            self._vfs.rollback()

        return session.rollback_to_last()

    def get_preview(self) -> list[dict[str, Any]]:
        """获取当前预览的 diff"""
        if not self._vfs:
            return []
        return self._vfs.get_all_diffs()

    def get_stats(self) -> dict[str, Any]:
        """获取管道统计"""
        return {
            "sessions": self.session_manager.get_stats(),
            "events": self.event_bus.get_stats(),
            "perception": self.perception.get_stats(),
        }


# 向后兼容别名：旧 pipeline_v2.AutomatedModPipeline 指向统一管线。
AutomatedModPipeline = UdifyPipeline
