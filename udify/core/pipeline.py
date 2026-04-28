"""
Udify Core - End-to-End Pipeline

端到端管道：协调所有模块，完成从用户意图到 Mod 生成的完整流程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from udify.core.execution.patch_executor import PatchExecutor
from udify.core.execution.vfs import VirtualFileSystem
from udify.core.infrastructure.event_bus import EventBus, EventType, emit_event
from udify.core.knowledge.knowledge_graph import GameKnowledgeGraph
from udify.core.perception.incremental_perception import IncrementalPerception
from udify.core.planning.cost_controller import CostController
from udify.core.planning.planner import Planner
from udify.core.security.sanitizer import InputSanitizer, OutputValidator
from udify.core.session.session_manager import ModSession, SessionManager, SessionStatus
from udify.core.validation.enhanced_validator import EnhancedValidator
from udify.models.cdl_patch import CDLPatch
from udify.models.content_graph import ContentGraph


@dataclass
class PipelineResult:
    """管道执行结果"""
    success: bool
    session_id: str
    intent: str
    patch: Optional[CDLPatch] = None
    vfs_diffs: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

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
    """
    Udify 端到端管道

    完整流程：
    1. 输入消毒
    2. 创建会话
    3. 感知游戏目录（增量）
    4. 规划修改方案
    5. 成本检查
    6. 验证 Patch
    7. 知识验证
    8. VFS 预览执行
    9. 生成 Diff 报告
    10. 等待用户确认
    11. 应用到实际文件系统
    """

    def __init__(
        self,
        game_root: Path,
        event_bus: Optional[EventBus] = None,
        session_manager: Optional[SessionManager] = None,
    ) -> None:
        self.game_root = game_root
        self.event_bus = event_bus or EventBus()
        self.session_manager = session_manager or SessionManager()

        # 初始化各模块
        self.sanitizer = InputSanitizer()
        self.output_validator = OutputValidator()
        self.perception = IncrementalPerception(game_root)
        self.planner = Planner()
        self.cost_controller = CostController()
        self.enhanced_validator = EnhancedValidator()
        self.knowledge_graph = GameKnowledgeGraph()

        self._vfs: Optional[VirtualFileSystem] = None

    async def process_intent(
        self,
        user_id: str,
        intent: str,
        preview_only: bool = True,
    ) -> PipelineResult:
        """
        处理用户意图

        Args:
            user_id: 用户 ID
            intent: 自然语言意图
            preview_only: 是否仅预览（不应用到实际文件系统）

        Returns:
            PipelineResult: 执行结果
        """
        errors = []
        warnings = []

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

        # 4. 规划修改方案（带成本控制）
        from udify.core.planning.state import Intent as PlanIntent, PlanContext, PlanState

        state = PlanState(
            graph=graph,
            intent=PlanIntent(description=sanitized_intent),
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
            )

        if not plan_result.success or not plan_result.actions:
            errors.append("无法生成有效的修改方案")
            return PipelineResult(
                success=False,
                session_id=session.session_id,
                intent=sanitized_intent,
                errors=errors,
            )

        session.set_status(SessionStatus.PLANNING)

        # 5. 转换为 Patch
        patch = plan_result.to_patch(author="udify_pipeline")
        patch.intent = sanitized_intent
        session.add_patch(patch)

        await emit_event(
            self.event_bus,
            EventType.PLANNING_COMPLETED,
            {"operations": len(patch.operations)},
            session_id=session.session_id,
        )

        # 6. 验证 Patch
        try:
            validation_report = await self.enhanced_validator.validate(patch, graph)
            if not validation_report.is_valid:
                errors.extend(validation_report.errors)
                warnings.extend(validation_report.warnings)

                # 如果有严重错误，返回失败
                if validation_report.errors:
                    return PipelineResult(
                        success=False,
                        session_id=session.session_id,
                        intent=sanitized_intent,
                        patch=patch,
                        errors=errors,
                        warnings=warnings,
                        stats=validation_report.stats,
                    )

            warnings.extend([w.message for w in validation_report.knowledge_warnings])
        except Exception as e:
            warnings.append(f"验证过程出错: {e}")

        # 7. 知识验证
        knowledge_warnings = self.knowledge_graph.validate_mod_against_knowledge(
            [op.to_dict() if hasattr(op, "to_dict") else {"op_type": op.op_type.name, "payload": op.payload}
             for op in patch.operations]
        )
        if knowledge_warnings:
            warnings.extend([w.message for w in knowledge_warnings])

        # 8. VFS 预览执行
        self._vfs = VirtualFileSystem(self.game_root)
        executor = PatchExecutor(self._vfs)

        try:
            exec_result = executor.execute(patch)
            if not exec_result["success"]:
                errors.extend([f["error"] for f in exec_result["failed"]])
        except Exception as e:
            errors.append(f"执行失败: {e}")

        # 9. 生成 Diff
        vfs_diffs = self._vfs.get_all_diffs() if self._vfs else []

        session.set_status(SessionStatus.EXECUTING)

        await emit_event(
            self.event_bus,
            EventType.EXECUTION_COMPLETED,
            {"modified_files": len(vfs_diffs)},
            session_id=session.session_id,
        )

        # 10. 如果不只是预览，应用到实际文件系统
        if not preview_only and not errors:
            try:
                apply_result = self._vfs.apply_to_filesystem()
                if apply_result["failed"]:
                    errors.extend([f"应用失败: {f['path']} - {f['error']}" for f in apply_result["failed"]])
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
        )

    async def apply_pending_mod(self, session_id: str) -> Dict[str, Any]:
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

    def get_preview(self) -> List[Dict[str, Any]]:
        """获取当前预览的 diff"""
        if not self._vfs:
            return []
        return self._vfs.get_all_diffs()

    def get_stats(self) -> Dict[str, Any]:
        """获取管道统计"""
        return {
            "sessions": self.session_manager.get_stats(),
            "events": self.event_bus.get_stats(),
            "perception": self.perception.get_stats(),
        }
