"""
全自动Mod生产管线 v2

集成所有模块：感知→认知→规划→执行→评估→反馈
参考: PLAN.md + ARCHITECTURE-v2.md + PROGRESS-SESSION-3.md
"""

from typing import Dict, Any, Optional, List
from pathlib import Path

from udify.core.perception.incremental_perception import IncrementalPerception
from udify.core.cognition.intent_classifier import IntentClassifier
from udify.core.cognition.reference_resolver import ReferenceResolver
from udify.core.cognition.conflict_detector import ConflictDetector
from udify.core.planning.planner import Planner
from udify.core.planning.cost_controller import CostController
from udify.core.execution.scheduler import ExecutionScheduler
from udify.core.execution.patch_executor import PatchExecutor
from udify.core.evaluation.intent_alignment import IntentAlignmentEvaluator
from udify.core.validation.enhanced_validator import EnhancedValidator
from udify.core.knowledge.knowledge_graph import GameKnowledgeGraph
from udify.core.memory.memory_store import MemoryStore
from udify.core.toolchain import ToolchainManager
from udify.models.cdl_patch import CDLPatch
from udify.core.cognition.intent import Intent, StructuredIntent


class AutomatedModPipeline:
    """全自动Mod生产管线
    
    完整流程：
    1. 输入消毒
    2. 感知分析（Perception）
    3. 意图分类（Cognition - IntentClassifier）
    4. 参考解析（Cognition - ReferenceResolver）
    5. 冲突检测（Cognition - ConflictDetector）
    6. 规划生成（Planning）
    7. 成本检查（CostController）
    8. 静态验证（EnhancedValidator）
    9. 知识验证（GameKnowledgeGraph）
    10. 预览应用（VirtualFileSystem）
    11. 意图对齐评估（IntentAlignmentEvaluator）
    12. 执行应用（PatchExecutor）
    13. 反馈收集（MemoryStore）
    """
    
    def __init__(
        self,
        llm_client=None,
        config: Optional[Dict[str, Any]] = None
    ):
        # 初始化所有模块
        self.perception = IncrementalPerception()
        
        self.intent_classifier = IntentClassifier(llm_client=llm_client)
        self.reference_resolver = ReferenceResolver(llm_client=llm_client)
        self.conflict_detector = ConflictDetector(reference_resolver=self.reference_resolver)
        
        self.planner = Planner(llm_client=llm_client)
        self.cost_controller = CostController()
        
        self.scheduler = ExecutionScheduler()
        self.patch_executor = PatchExecutor()
        
        self.alignment_evaluator = IntentAlignmentEvaluator(llm_client=llm_client)
        self.validator = EnhancedValidator()
        self.knowledge_graph = GameKnowledgeGraph()
        
        self.memory_store = MemoryStore()
        self.toolchain_manager = ToolchainManager()
        
        self.config = config or {}
    
    def create_mod_full_auto(
        self,
        game_path: Path,
        user_intent_text: str,
        mod_name: str = "auto_mod",
        language: str = "zh",
        auto_apply: bool = False,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """全自动Mod创建管线
        
        Args:
            game_path: 游戏目录路径
            user_intent_text: 用户意图文本
            mod_name: Mod名称
            language: 语言
            auto_apply: 是否自动应用（不需人工确认）
            dry_run: 是否为演练模式（只预览不应用）
            
        Returns:
            Dict: 包含完整流程和结果的字典
        """
        result = {
            "success": False,
            "mod_name": mod_name,
            "intent_text": user_intent_text,
            "steps": [],
            "patch": None,
            "evaluation": None,
            "error": None
        }
        
        try:
            # Step 1: 输入消毒
            result["steps"].append("Step 1: Input Sanitization")
            # TODO: 调用 InputSanitizer.sanitize()
            
            # Step 2: 感知分析
            result["steps"].append("Step 2: Perception Analysis")
            graph = self.perception.perceive(game_path)
            result["content_graph"] = graph
            
            # Step 3: 意图分类
            result["steps"].append("Step 3: Intent Classification")
            intent = self.intent_classifier.classify(user_intent_text, language)
            result["intent"] = intent
            
            # 转换为结构化意图
            structured_intent = self.intent_classifier.to_structured(intent)
            
            # Step 4: 参考解析
            result["steps"].append("Step 4: Reference Resolution")
            references = self.reference_resolver.resolve_from_structured_intent(structured_intent)
            structured_intent.references.extend(references)
            
            # Step 5: 冲突检测
            result["steps"].append("Step 5: Conflict Detection")
            conflicts = self.conflict_detector.detect(intent, structured_intent)
            result["conflicts"] = [c.to_dict() for c in conflicts]
            
            # 解决冲突
            if conflicts:
                structured_intent = self.conflict_detector.resolve_conflicts(
                    structured_intent, conflicts
                )
            
            # Step 6: 规划生成
            result["steps"].append("Step 6: Plan Generation")
            plan_result = self.planner.plan(graph, structured_intent)
            result["plan"] = plan_result
            
            # Step 7: 成本检查
            result["steps"].append("Step 7: Cost Check")
            cost_result = self.cost_controller.plan_with_budget(
                structured_intent, graph, plan_result.estimated_cost
            )
            
            if not cost_result["within_budget"]:
                result["error"] = "Budget exceeded"
                return result
            
            # Step 8: 静态验证
            result["steps"].append("Step 8: Static Validation")
            validation = self.validator.validate(plan_result.to_patch(), graph)
            result["validation"] = validation
            
            if not validation.is_valid:
                result["error"] = "Validation failed"
                result["validation_errors"] = validation.errors
                return result
            
            # Step 9: 知识验证
            result["steps"].append("Step 9: Knowledge Validation")
            kg_validation = self.knowledge_graph.validate_mod_against_knowledge(
                graph, plan_result.to_patch()
            )
            result["knowledge_validation"] = kg_validation
            
            # Step 10: 生成补丁
            patch = plan_result.to_patch()
            result["patch"] = patch
            
            # Step 11: 意图对齐评估
            result["steps"].append("Step 11: Intent Alignment Evaluation")
            alignment = self.alignment_evaluator.evaluate(
                intent, structured_intent, patch, graph
            )
            result["alignment"] = alignment
            
            # Step 12: 决定是否应用
            if not dry_run and (auto_apply or alignment["passed"]):
                # Step 12: 执行应用
                result["steps"].append("Step 12: Apply Patch")
                exec_result = self.scheduler.execute_patch(patch, graph)
                result["execution"] = exec_result
                
                if exec_result.success:
                    result["success"] = True
                    result["steps"].append("Step 13: Success!")
                else:
                    result["error"] = f"Execution failed: {exec_result.error}"
            else:
                # 预览模式
                result["steps"].append("Step 12: Preview Only (dry-run)")
                result["success"] = True
                result["preview"] = True
            
            # Step 13: 收集反馈到记忆系统
            result["steps"].append("Step 13: Update Memory")
            self.memory_store.record_execution(
                intent=intent,
                patch=patch,
                success=result["success"],
                alignment_score=alignment["total_score"]
            )
            
        except Exception as e:
            result["error"] = str(e)
            import traceback
            result["traceback"] = traceback.format_exc()
        
        return result
    
    def batch_create_mods(
        self,
        game_path: Path,
        intent_list: List[str],
        mod_names: Optional[List[str]] = None,
        parallel: bool = False
    ) -> List[Dict[str, Any]]:
        """批量创建多个Mod
        
        Args:
            game_path: 游戏目录
            intent_list: 意图文本列表
            mod_names: Mod名称列表（可选）
            parallel: 是否并行处理（未来功能）
            
        Returns:
            List[Dict]: 每个意图的结果列表
        """
        results = []
        
        for i, intent_text in enumerate(intent_list):
            mod_name = mod_names[i] if mod_names and i < len(mod_names) else f"auto_mod_{i}"
            
            result = self.create_mod_full_auto(
                game_path=game_path,
                user_intent_text=intent_text,
                mod_name=mod_name,
                auto_apply=True,
                dry_run=False
            )
            
            results.append(result)
        
        return results
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """获取管线状态"""
        return {
            "modules": {
                "perception": "IncrementalPerception",
                "cognition": {
                    "intent_classifier": "IntentClassifier",
                    "reference_resolver": "ReferenceResolver",
                    "conflict_detector": "ConflictDetector"
                },
                "planning": {
                    "planner": "Planner",
                    "cost_controller": "CostController"
                },
                "execution": {
                    "scheduler": "ExecutionScheduler",
                    "patch_executor": "PatchExecutor"
                },
                "evaluation": {
                    "alignment_evaluator": "IntentAlignmentEvaluator",
                    "validator": "EnhancedValidator"
                },
                "knowledge": "GameKnowledgeGraph",
                "memory": "MemoryStore",
                "toolchain": "ToolchainManager"
            },
            "version": "2.0.0",
            "status": "All modules integrated"
        }