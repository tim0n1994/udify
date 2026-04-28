"""
Execution Scheduler Module

Manages the execution of CDLPatch operations with support for:
- Parallel execution of independent operations
- Dependency resolution
- Error handling and rollback
- Progress tracking
"""

import json
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
import time

from .tool_registry import ToolRegistry
from .sandbox import SandboxManager, SandboxConfig
from ...models.cdl_patch import CDLPatch, PatchOperation
from ...models.content_graph import ContentGraph

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for patch execution."""
    # Execution settings
    max_parallel_operations: int = 5
    timeout_per_operation: int = 300
    retry_attempts: int = 3
    retry_delay: float = 1.0
    
    # Sandbox settings
    use_sandbox: bool = True
    sandbox_config: Optional[SandboxConfig] = None
    
    # Rollback settings
    enable_rollback: bool = True
    save_snapshots: bool = True
    
    # Validation
    validate_before_execute: bool = True
    validate_after_execute: bool = True


@dataclass
class ExecutionResult:
    """Result of patch execution."""
    success: bool
    patch: CDLPatch
    executed_operations: List[PatchOperation]
    failed_operations: List[PatchOperation]
    rollback_operations: List[PatchOperation]
    execution_time: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    graph_snapshot: Optional[ContentGraph] = None


@dataclass
class OperationNode:
    """Node in the execution dependency graph."""
    operation: PatchOperation
    dependencies: Set[str] = field(default_factory=set)
    dependents: Set[str] = field(default_factory=set)
    status: str = "pending"  # pending, executing, completed, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    original_state: Optional[Dict[str, Any]] = None  # 用于回滚的原始状态


class ExecutionScheduler:
    """
    Schedules and executes CDLPatch operations with dependency management.
    
    This class handles the execution of patch operations, ensuring that
    dependencies are respected and providing rollback capabilities.
    """
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        sandbox_manager: Optional[SandboxManager] = None,
        config: Optional[ExecutionConfig] = None
    ):
        """
        Initialize execution scheduler.
        
        Args:
            tool_registry: Tool registry for executing operations
            sandbox_manager: Optional sandbox manager
            config: Execution configuration
        """
        self.tool_registry = tool_registry
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self.config = config or ExecutionConfig()
        self.operation_nodes: Dict[str, OperationNode] = {}
        logger.info("ExecutionScheduler initialized")
    
    def execute_patch(
        self,
        patch: CDLPatch,
        target_graph: ContentGraph,
        validate: bool = True
    ) -> ExecutionResult:
        """
        Execute a CDLPatch on a target ContentGraph.
        
        Args:
            patch: The patch to execute
            target_graph: The target content graph
            validate: Whether to validate before execution
            
        Returns:
            ExecutionResult with execution details
        """
        start_time = time.time()
        executed_operations: List[PatchOperation] = []
        failed_operations: List[PatchOperation] = []
        rollback_operations: List[PatchOperation] = []
        errors: List[str] = []
        warnings: List[str] = []
        
        # Create snapshot for rollback if enabled
        graph_snapshot = None
        if self.config.save_snapshots:
            try:
                import copy
                graph_snapshot = copy.deepcopy(target_graph)
            except Exception as e:
                warnings.append(f"Failed to create snapshot: {e}")
        
        try:
            # Validate patch if requested
            if validate and self.config.validate_before_execute:
                validation_errors = self._validate_patch(patch, target_graph)
                if validation_errors:
                    return ExecutionResult(
                        success=False,
                        patch=patch,
                        executed_operations=[],
                        failed_operations=patch.operations,
                        rollback_operations=[],
                        execution_time=time.time() - start_time,
                        errors=validation_errors,
                        warnings=warnings,
                        graph_snapshot=graph_snapshot
                    )
            
            # Build dependency graph
            self._build_dependency_graph(patch)
            
            # Execute operations in topological order
            completed_operations = self._execute_operations(
                patch, target_graph, executed_operations, failed_operations, errors
            )
            
            # Check if all operations completed successfully
            if failed_operations:
                # Attempt rollback if enabled
                if self.config.enable_rollback:
                    rollback_errors = self._rollback_operations(
                        executed_operations, target_graph, rollback_operations
                    )
                    errors.extend(rollback_errors)
                
                return ExecutionResult(
                    success=False,
                    patch=patch,
                    executed_operations=executed_operations,
                    failed_operations=failed_operations,
                    rollback_operations=rollback_operations,
                    execution_time=time.time() - start_time,
                    errors=errors,
                    warnings=warnings,
                    graph_snapshot=graph_snapshot
                )
            
            # Validate after execution if requested
            if validate and self.config.validate_after_execute:
                validation_errors = self._validate_result(patch, target_graph)
                if validation_errors:
                    warnings.extend(validation_errors)
            
            return ExecutionResult(
                success=True,
                patch=patch,
                executed_operations=executed_operations,
                failed_operations=[],
                rollback_operations=rollback_operations,
                execution_time=time.time() - start_time,
                errors=[],
                warnings=warnings,
                graph_snapshot=graph_snapshot
            )
        
        except Exception as e:
            logger.error(f"Patch execution failed: {e}")
            
            # Attempt rollback on unexpected error
            if self.config.enable_rollback and executed_operations:
                rollback_errors = self._rollback_operations(
                    executed_operations, target_graph, rollback_operations
                )
                errors.extend(rollback_errors)
            
            return ExecutionResult(
                success=False,
                patch=patch,
                executed_operations=executed_operations,
                failed_operations=patch.operations[len(executed_operations):],
                rollback_operations=rollback_operations,
                execution_time=time.time() - start_time,
                errors=[str(e)] + errors,
                warnings=warnings,
                graph_snapshot=graph_snapshot
            )
    
    def _build_dependency_graph(self, patch: CDLPatch) -> None:
        """Build dependency graph from patch operations."""
        self.operation_nodes.clear()
        
        # Create nodes for all operations
        for i, operation in enumerate(patch.operations):
            node = OperationNode(operation=operation)
            
            # Determine dependencies based on target IDs
            target_id = getattr(operation, 'target_id', None)
            if target_id:
                # This operation depends on operations that modify the same target
                for other_id, other_node in self.operation_nodes.items():
                    other_target = getattr(other_node.operation, 'target_id', None)
                    if other_target == target_id:
                        node.dependencies.add(other_id)
                        other_node.dependents.add(i)
            
            # Check for asset dependencies
            asset_id = getattr(operation, 'asset_id', None)
            if asset_id:
                for other_id, other_node in self.operation_nodes.items():
                    other_asset = getattr(other_node.operation, 'asset_id', None)
                    if other_asset == asset_id:
                        node.dependencies.add(other_id)
                        other_node.dependents.add(i)
            
            self.operation_nodes[i] = node
    
    def _execute_operations(
        self,
        patch: CDLPatch,
        target_graph: ContentGraph,
        executed_operations: List[PatchOperation],
        failed_operations: List[PatchOperation],
        errors: List[str]
    ) -> List[PatchOperation]:
        """Execute operations respecting dependencies."""
        # Find operations with no dependencies (ready to execute)
        ready_queue = deque()
        for op_id, node in self.operation_nodes.items():
            if not node.dependencies and node.status == "pending":
                ready_queue.append(op_id)
        
        completed_count = 0
        total_operations = len(patch.operations)
        
        while ready_queue and completed_count < total_operations:
            # Execute operations in parallel where possible
            batch = []
            while ready_queue and len(batch) < self.config.max_parallel_operations:
                batch.append(ready_queue.popleft())
            
            # Execute batch
            for op_id in batch:
                node = self.operation_nodes[op_id]
                operation = node.operation
                
                try:
                    node.status = "executing"
                    logger.info(f"Executing operation {op_id}: {operation.op_type.value}")
                    
                    # 捕获原始状态（用于回滚）
                    node.original_state = self._capture_original_state(operation, target_graph)
                    
                    # Execute the operation
                    result = self._execute_operation(operation, target_graph)
                    node.status = "completed"
                    node.result = result
                    
                    executed_operations.append(operation)
                    completed_count += 1
                    
                    # Update dependents
                    for dependent_id in node.dependents:
                        dependent_node = self.operation_nodes[dependent_id]
                        dependent_node.dependencies.discard(op_id)
                        if not dependent_node.dependencies and dependent_node.status == "pending":
                            ready_queue.append(dependent_id)
                
                except Exception as e:
                    node.status = "failed"
                    node.error = str(e)
                    failed_operations.append(operation)
                    errors.append(f"Operation {op_id} failed: {e}")
                    logger.error(f"Operation {op_id} failed: {e}")
                    
                    # Mark dependents as failed due to dependency
                    self._mark_dependents_failed(op_id, failed_operations, errors)
        
        return executed_operations
    
    def _execute_operation(
        self,
        operation: PatchOperation,
        target_graph: ContentGraph
    ) -> Dict[str, Any]:
        """Execute a single patch operation."""
        # Convert patch operation to tool execution
        tool_name, tool_args = self._convert_to_tool_call(operation, target_graph)
        
        if self.config.use_sandbox and self.sandbox_manager:
            # Execute in sandbox (simplified - just use SandboxExecutor)
            try:
                # Convert tool call to script
                script = self._generate_execution_script(tool_name, tool_args)
                result = self.sandbox_manager.execute_lua(script)
                
                if not result.success:
                    raise Exception(f"Sandbox execution failed: {result.stderr}")
                
                # Parse result
                try:
                    return json.loads(result.stdout.strip())
                except json.JSONDecodeError:
                    return {"stdout": result.stdout, "stderr": result.stderr}
            
            except Exception as e:
                logger.warning(f"Sandbox execution failed, falling back to direct: {e}")
                # Fall through to direct execution
        
        # Execute directly
        return self.tool_registry.execute_tool(tool_name, tool_args)
    
    def _convert_to_tool_call(
        self,
        operation: PatchOperation,
        target_graph: ContentGraph
    ) -> tuple[str, Dict[str, Any]]:
        """
        Convert patch operation to tool call.
        
        Returns:
            Tuple of (tool_name, tool_arguments)
        """
        op_type = operation.op_type.value
        
        if op_type == "add_node":
            return "graph_add_node", {
                "graph": target_graph,
                "node_data": operation.payload.get("node", {})
            }
        
        elif op_type == "remove_node":
            return "graph_remove_node", {
                "graph": target_graph,
                "node_id": operation.target_id
            }
        
        elif op_type == "modify_property":
            return "graph_modify_node", {
                "graph": target_graph,
                "node_id": operation.target_id,
                "property_changes": operation.payload.get("property_changes", {})
            }
        
        elif op_type == "add_edge":
            return "graph_add_edge", {
                "graph": target_graph,
                "edge_data": operation.payload.get("edge", {})
            }
        
        elif op_type == "remove_edge":
            return "graph_remove_edge", {
                "graph": target_graph,
                "edge_id": operation.target_id
            }
        
        elif op_type == "modify_edge":
            return "graph_modify_edge", {
                "graph": target_graph,
                "edge_id": operation.target_id,
                "property_changes": operation.payload.get("property_changes", {})
            }
        
        elif op_type == "add_asset":
            return "asset_add", {
                "graph": target_graph,
                "asset_data": operation.payload.get("asset", {})
            }
        
        elif op_type == "remove_asset":
            return "asset_remove", {
                "graph": target_graph,
                "asset_id": operation.target_id
            }
        
        elif op_type == "modify_asset":
            return "asset_modify", {
                "graph": target_graph,
                "asset_id": operation.target_id,
                "file_patch": operation.payload.get("file_patch", {})
            }
        
        else:
            raise ValueError(f"Unknown operation type: {op_type}")
    
    def _generate_execution_script(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Generate Python script for sandbox execution."""
        import json
        
        script = f"""
import sys
import json
sys.path.insert(0, '/work')

from udify.core.execution.tool_registry import ToolRegistry
from udify.core.execution.builtin_tools import register_all_builtin_tools

# Create registry and register tools
registry = ToolRegistry()
register_all_builtin_tools(registry)

# Execute tool
result = registry.execute_tool(
    tool_name="{tool_name}",
    parameters={json.dumps(tool_args)}
)

# Output result as JSON
print(json.dumps(result))
"""
        return script
    
    def _validate_patch(self, patch: CDLPatch, target_graph: ContentGraph) -> List[str]:
        """Validate patch before execution."""
        errors = []
        
        # Check for duplicate operations on same target
        target_operations = {}
        for i, operation in enumerate(patch.operations):
            target_id = getattr(operation, 'target_id', None)
            if target_id:
                if target_id in target_operations:
                    errors.append(
                        f"Multiple operations on same target {target_id}: "
                        f"{target_operations[target_id]} and {i}"
                    )
                target_operations[target_id] = i
        
        return errors
    
    def _validate_result(self, patch: CDLPatch, target_graph: ContentGraph) -> List[str]:
        """Validate result after execution."""
        warnings = []
        
        # Check for orphaned nodes
        for node in target_graph.nodes:
            if not target_graph.edges and not any(
                edge.source == node.id or edge.target == node.id
                for edge in target_graph.edges
            ):
                warnings.append(f"Orphaned node detected: {node.id}")
        
        return warnings
    
    def _rollback_operations(
        self,
        executed_operations: List[PatchOperation],
        target_graph: ContentGraph,
        rollback_operations: List[PatchOperation]
    ) -> List[str]:
        """Rollback executed operations in reverse order."""
        errors = []

        for operation in reversed(executed_operations):
            try:
                # 找到对应的 OperationNode 获取 original_state
                original_state = None
                for node in self.operation_nodes.values():
                    if node.operation is operation:
                        original_state = node.original_state
                        break

                rollback_op = self._create_rollback_operation(operation, original_state)
                if rollback_op:
                    result = self._execute_operation(rollback_op, target_graph)
                    rollback_operations.append(rollback_op)
                    logger.info(f"Rolled back operation: {operation.op_type.value}")
                else:
                    logger.warning(f"No rollback available for: {operation.op_type.value}")

            except Exception as e:
                error_msg = f"Rollback failed for {operation.op_type.value}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

        return errors
    
    def _capture_original_state(self, operation: PatchOperation, target_graph: ContentGraph) -> Optional[Dict[str, Any]]:
        """Capture original state before executing an operation."""
        op_type = operation.op_type.value
        target_id = operation.target_id

        if op_type == "remove_node":
            node = target_graph.get_node(target_id)
            if node:
                return {"node": node.to_dict() if hasattr(node, "to_dict") else {"id": node.id, "name": getattr(node, "name", ""), "properties": getattr(node, "properties", {})}}

        elif op_type == "modify_property" or op_type == "modify_node":
            node = target_graph.get_node(target_id)
            if node:
                return {"properties": dict(getattr(node, "properties", {}))}

        elif op_type == "remove_edge":
            for edge in target_graph.edges:
                if getattr(edge, "id", None) == target_id or (getattr(edge, "source", None), getattr(edge, "target", None)) == target_id:
                    return {"edge": {"source": getattr(edge, "source", ""), "target": getattr(edge, "target", ""), "type": str(getattr(edge, "type", "")), "properties": getattr(edge, "properties", {})}}

        elif op_type == "modify_edge":
            for edge in target_graph.edges:
                if getattr(edge, "id", None) == target_id:
                    return {"edge": {"source": getattr(edge, "source", ""), "target": getattr(edge, "target", ""), "type": str(getattr(edge, "type", "")), "properties": dict(getattr(edge, "properties", {}))}}

        elif op_type == "remove_asset":
            for asset in target_graph.assets:
                if getattr(asset, "id", None) == target_id:
                    return {"asset": {"id": getattr(asset, "id", ""), "path": getattr(asset, "path", ""), "type": getattr(asset, "type", ""), "format": getattr(asset, "format", "")}}

        elif op_type == "modify_asset":
            for asset in target_graph.assets:
                if getattr(asset, "id", None) == target_id:
                    return {"asset": {"id": getattr(asset, "id", ""), "path": getattr(asset, "path", ""), "type": getattr(asset, "type", ""), "format": getattr(asset, "format", "")}}

        return None

    def _create_rollback_operation(self, operation: PatchOperation, original_state: Optional[Dict[str, Any]]) -> Optional[PatchOperation]:
        """Create rollback operation for given operation using captured original state."""
        op_type = operation.op_type.value

        if op_type == "add_node":
            return PatchOperation(
                op_type="remove_node",
                target_id=operation.target_id,
                payload={}
            )

        elif op_type == "remove_node":
            if original_state and "node" in original_state:
                return PatchOperation(
                    op_type="add_node",
                    target_id=operation.target_id,
                    payload={"node": original_state["node"]}
                )

        elif op_type == "modify_property" or op_type == "modify_node":
            if original_state and "properties" in original_state:
                return PatchOperation(
                    op_type="modify_property",
                    target_id=operation.target_id,
                    payload={"property_changes": original_state["properties"]}
                )

        elif op_type == "add_edge":
            return PatchOperation(
                op_type="remove_edge",
                target_id=operation.target_id,
                payload={}
            )

        elif op_type == "remove_edge":
            if original_state and "edge" in original_state:
                return PatchOperation(
                    op_type="add_edge",
                    target_id=operation.target_id,
                    payload={"edge": original_state["edge"]}
                )

        elif op_type == "modify_edge":
            if original_state and "edge" in original_state:
                return PatchOperation(
                    op_type="modify_edge",
                    target_id=operation.target_id,
                    payload={"property_changes": original_state["edge"].get("properties", {})}
                )

        elif op_type == "add_asset":
            return PatchOperation(
                op_type="remove_asset",
                target_id=operation.target_id,
                payload={}
            )

        elif op_type == "remove_asset":
            if original_state and "asset" in original_state:
                return PatchOperation(
                    op_type="add_asset",
                    target_id=operation.target_id,
                    payload={"asset": original_state["asset"]}
                )

        elif op_type == "modify_asset":
            if original_state and "asset" in original_state:
                return PatchOperation(
                    op_type="modify_asset",
                    target_id=operation.target_id,
                    payload={"asset_data": original_state["asset"]}
                )

        return None
    
    def _mark_dependents_failed(
        self,
        failed_op_id: str,
        failed_operations: List[PatchOperation],
        errors: List[str]
    ) -> None:
        """Mark all dependents of a failed operation as failed."""
        node = self.operation_nodes.get(failed_op_id)
        if not node:
            return
        
        for dependent_id in node.dependents:
            dependent_node = self.operation_nodes[dependent_id]
            if dependent_node.status == "pending":
                dependent_node.status = "failed"
                dependent_node.error = f"Dependency failed: {failed_op_id}"
                failed_operations.append(dependent_node.operation)
                errors.append(f"Operation {dependent_id} skipped due to dependency failure")
                
                # Recursively mark dependents
                self._mark_dependents_failed(dependent_id, failed_operations, errors)