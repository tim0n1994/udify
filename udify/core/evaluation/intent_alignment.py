"""
意图对齐评估器 (Intent Alignment Evaluator)

评估改造结果是否符合用户原始意图。
参考: ARCHITECTURE-v2.md §4.5 评估层 + §5.3 意图到目标映射
"""

from typing import Dict, Any, List
from udify.core.cognition.intent import StructuredIntent, Intent
from udify.core.llm_client import LLMClient
from udify.models.cdl_patch import CDLPatch


class AlignmentMetric:
    """对齐度指标"""
    
    def __init__(self, name: str, weight: float, description: str = ""):
        self.name = name
        self.weight = weight
        self.description = description
        self.score = 0.0
        self.details = ""


class IntentAlignmentEvaluator:
    """意图对齐评估器
    
    评估维度：
    1. 目标达成度：意图中的主要目标是否实现
    2. 约束满足度：所有约束是否得到满足
    3. 参考匹配度：是否体现了参考案例的特征
    4. 范围控制度：是否过度修改或不足
    """
    
    # 默认评估指标
    DEFAULT_METRICS = [
        ("goal_achievement", 0.35, "主要目标是否实现"),
        ("constraint_satisfaction", 0.25, "约束条件是否满足"),
        ("reference_match", 0.20, "是否体现参考特征"),
        ("scope_control", 0.20, "修改范围是否合理"),
    ]
    
    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client
        self.metrics = [
            AlignmentMetric(name, weight, desc)
            for name, weight, desc in self.DEFAULT_METRICS
        ]
    
    def evaluate(
        self,
        original_intent: Intent,
        structured_intent: StructuredIntent,
        patch: CDLPatch,
        modified_graph: Any = None
    ) -> Dict[str, Any]:
        """评估改造结果与意图的对齐度"""
        # 重置分数
        for metric in self.metrics:
            metric.score = 0.0
            metric.details = ""
        
        # 1. 评估目标达成度
        goal_score = self._evaluate_goal_achievement(
            original_intent, structured_intent, patch
        )
        self._update_metric("goal_achievement", goal_score)
    
        # 2. 评估约束满足度
        constraint_score = self._evaluate_constraint_satisfaction(
            structured_intent, patch
        )
        self._update_metric("constraint_satisfaction", constraint_score)
    
        # 3. 评估参考匹配度
        reference_score = self._evaluate_reference_match(
            structured_intent, patch
        )
        self._update_metric("reference_match", reference_score)
    
        # 4. 评估范围控制度
        scope_score = self._evaluate_scope_control(
            original_intent, patch
        )
        self._update_metric("scope_control", scope_score)
    
        # 5. 使用LLM进行综合评估（如果可用）
        if self.llm and self.llm.is_available():
            llm_score = self._evaluate_with_llm(
                original_intent, structured_intent, patch
            )
            # LLM分数作为额外参考，调整总分
            if llm_score > 0:
                self._adjust_with_llm(llm_score)
    
        # 计算总分
        total_score = sum(m.weight * m.score for m in self.metrics)
        total_score = min(1.0, max(0.0, total_score))
    
        return {
            "total_score": total_score,
            "passed": total_score >= 0.6,  # 及格线60%
            "metrics": {
                m.name: {
                    "score": m.score,
                    "weight": m.weight,
                    "details": m.details
                }
                for m in self.metrics
            },
            "summary": self._generate_summary(total_score)
        }
    
    def _update_metric(self, name: str, score: float):
        """更新指标分数"""
        for metric in self.metrics:
            if metric.name == name:
                metric.score = score
                break
    
    def _evaluate_goal_achievement(
        self,
        intent: Intent,
        structured: StructuredIntent,
        patch: CDLPatch
    ) -> float:
        """评估主要目标是否实现"""
        score = 0.0
        details = []
    
        # 检查是否有对应的补丁操作
        operations = patch.operations if hasattr(patch, "operations") else []
    
        if intent.intent_type.name == "DIFFICULTY_ADJUSTMENT":
            # 检查是否有数值修改操作
            has_numeric_mod = any(
                op.get("type") in ["modify_node", "modify_asset"]
                for op in operations
            )
            if has_numeric_mod:
                score += 0.6
                details.append("Found numeric modification operations")
        
            # 检查是否修改了关键属性（HP、攻击等）
            has_key_mod = any(
                any(kw in str(op).lower() for kw in ["health", "damage", "hp", "attack"])
                for op in operations
            )
            if has_key_mod:
                score += 0.4
                details.append("Modified key difficulty attributes")
    
        elif intent.intent_type.name == "CONTENT_EXPANSION":
            # 检查是否有新增操作
            has_add = any(
                op.get("type") in ["add_node", "add_asset"]
                for op in operations
            )
            if has_add:
                score = 1.0
                details.append("Found content addition operations")
            else:
                score = 0.3
                details.append("No content addition found")
    
        else:
            # 通用评估：有操作就给基础分
            if operations:
                score = 0.5
                details.append("Found some operations")
            else:
                score = 0.0
                details.append("No operations found")
    
        return min(1.0, score)
    
    def _evaluate_constraint_satisfaction(
        self,
        structured: StructuredIntent,
        patch: CDLPatch
    ) -> float:
        """评估约束条件是否满足"""
        constraints = structured.constraints
        if not constraints:
            return 1.0  # 无约束，默认满足
    
        satisfied = 0
        for constraint in constraints:
            # 简化的约束检查
            if constraint.hard:
                # 硬约束必须满足
                if self._check_constraint(constraint, patch):
                    satisfied += 1
            else:
                # 软约束尽量满足
                if self._check_constraint(constraint, patch):
                    satisfied += 1
    
        return satisfied / len(constraints) if constraints else 1.0
    
    def _check_constraint(self, constraint: Any, patch: CDLPatch) -> bool:
        """检查单个约束是否满足"""
        expr = constraint.expression.lower()
    
        # 简单的关键词检查
        if "difficulty" in expr and "not too" in expr:
            # 检查是否没有极端数值修改
            operations = patch.operations if hasattr(patch, "operations") else []
            for op in operations:
                if "new_value" in op:
                    try:
                        val = float(op["new_value"])
                        if val > 1000000:  # 假设极端值
                            return False
                    except:
                        pass
            return True
    
        return True  # 默认通过
    
    def _evaluate_reference_match(
        self,
        structured: StructuredIntent,
        patch: CDLPatch
    ) -> float:
        """评估是否体现参考特征"""
        references = structured.references
        if not references:
            return 1.0  # 无参考，默认满足
    
        # 检查补丁是否包含参考特征相关的修改
        operations = patch.operations if hasattr(patch, "operations") else []
        patch_str = str(operations).lower()
    
        matched_features = 0
        total_features = 0
    
        for ref in references:
            for feature in ref.features:
                total_features += 1
                # 检查特征是否在补丁中体现
                if any(feat_kw in patch_str for feat_kw in feature.lower().split('_')):
                    matched_features += 1
    
        return matched_features / total_features if total_features > 0 else 1.0
    
    def _evaluate_scope_control(
        self,
        intent: Intent,
        patch: CDLPatch
    ) -> float:
        """评估修改范围是否合理"""
        operations = patch.operations if hasattr(patch, "operations") else []
        num_ops = len(operations)
    
        # 根据意图类型判断合理范围
        if intent.intent_type.name == "DIFFICULTY_ADJUSTMENT":
            # 难度调整：1-10个操作合理
            if 1 <= num_ops <= 10:
                return 1.0
            elif num_ops < 1:
                return 0.3  # 操作太少，可能没改到位
            else:
                return 0.5  # 操作太多，可能过度修改
    
        elif intent.intent_type.name == "CONTENT_EXPANSION":
            # 内容扩展：5-30个操作合理
            if 5 <= num_ops <= 30:
                return 1.0
            elif num_ops < 5:
                return 0.5
            else:
                return 0.4
    
        else:
            # 通用：1-50个操作
            if 1 <= num_ops <= 50:
                return 1.0
            else:
                return 0.6
    
    def _evaluate_with_llm(
        self,
        intent: Intent,
        structured: StructuredIntent,
        patch: CDLPatch
    ) -> float:
        """使用LLM进行综合评估"""
        if not self.llm or not self.llm.is_available():
            return 0.0
    
        # 构建操作类型列表
        op_types = []
        if hasattr(patch, "operations"):
            for op in patch.operations[:5]:
                if isinstance(op, dict):
                    op_types.append(op.get('type', ''))
        
        prompt = f"""
Evaluate how well the modification patch aligns with the user's intent.

User Intent:
- Raw text: {intent.raw_text}
- Primary goal: {structured.primary_goal}
- Sub-goals: {structured.sub_goals}

Patch Summary:
- Number of operations: {len(patch.operations) if hasattr(patch, "operations") else 0}
- Operation types: {op_types}

Rate the alignment from 0.0 to 1.0:
- 1.0: Perfect alignment, all goals achieved
- 0.7-0.9: Good alignment, most goals achieved
- 0.5-0.6: Partial alignment, some goals missing
- 0.3-0.4: Poor alignment, major goals missing
- 0.0-0.2: No alignment, irrelevant modifications.

Return only a float number.
"""
    
        try:
            response = self.llm.complete(prompt, temperature=0.0)
            if response:
                return float(response.strip())
        except Exception as e:
            print(f"LLM alignment evaluation error: {e}")
    
        return 0.0
    
    def _adjust_with_llm(self, llm_score: float):
        """使用LLM分数调整总分"""
        # LLM分数权重20%，其他指标80%
        total = sum(m.weight * m.score for m in self.metrics)
        adjusted = 0.8 * total + 0.2 * llm_score
    
        # 更新各指标分数（按比例缩放）
        if total > 0:
            scale = adjusted / total
            for m in self.metrics:
                m.score *= scale
    
    def _generate_summary(self, total_score: float) -> str:
        """生成评估摘要"""
        if total_score >= 0.8:
            return "Excellent alignment with user intent"
        elif total_score >= 0.6:
            return "Good alignment with minor gaps"
        elif total_score >= 0.4:
            return "Partial alignment, significant gaps"
        else:
            return "Poor alignment, major revision needed"