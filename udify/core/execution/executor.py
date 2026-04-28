"""
Patch Executor Module

Main entry point for executing CDLPatch operations.
Coordinates the entire execution pipeline:
1. Validation
2. Planning (if needed)
3. Execution via scheduler
4. Post-execution validation
5. Result reporting
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import time

from ...models.cdl_patch import CDLPatch
from ...models.content_graph import ContentGraph
from .tool_registry import ToolRegistry
from .sandbox import SandboxManager, SandboxConfig
from .scheduler import ExecutionScheduler, ExecutionConfig, ExecutionResult
from .mcp_server import UdifyMCPServer

logger = logging.getLogger(__name__)


@dataclass
class ExecutorConfig:
    """Configuration for the patch executor."""
    # Execution settings
    execution_config: Optional[ExecutionConfig] = None
    
    # MCP settings
    enable_mcp: bool = True
    mcp_port: int = 8080
    
    # Sandbox settings
    use_sandbox: bool = True
    sandbox_config: Optional[SandboxConfig] = None
    
    # Validation
    validate_before_execution: bool = True
    validate_after_execution: bool = True
    
    # Rollback
    enable_rollback: bool = True
    
    # Logging
    log_level: str = "info"


class PatchExecutor:
    """
    Main executor for CDLPatch operations.
    
    This class provides the primary interface for executing patches,
    handling all aspects of the execution pipeline.
    """
    
    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        sandbox_manager: Optional[SandboxManager] = None,
        config: Optional[ExecutorConfig] = None
    ):
        """
        Initialize patch executor.
        
        Args:
            tool_registry: Optional tool registry (creates new if None)
            sandbox_manager: Optional sandbox manager (creates new if None)
            config: Executor configuration
        """
        self.config = config or ExecutorConfig()
        
        # Initialize tool registry
        self.tool_registry = tool_registry or ToolRegistry()
        
        # Initialize sandbox manager
        self.sandbox_manager = sandbox_manager or SandboxManager()
        
        # Initialize execution scheduler
        execution_config = self.config.execution_config or ExecutionConfig(
            use_sandbox=self.config.use_sandbox,
            enable_rollback=self.config.enable_rollback
        )
        self.scheduler = ExecutionScheduler(
            tool_registry=self.tool_registry,
            sandbox_manager=self.sandbox_manager,
            config=execution_config
        )
        
        # Initialize MCP server if enabled
        self.mcp_server: Optional[UdifyMCPServer] = None
        if self.config.enable_mcp:
            self.mcp_server = UdifyMCPServer(
                tool_registry=self.tool_registry,
                sandbox_manager=self.sandbox_manager,
                use_sandbox=self.config.use_sandbox
            )
        
        logger.info("PatchExecutor initialized")
    
    def execute_patch(
        self,
        patch: CDLPatch,
        target_graph: ContentGraph,
        validate: bool = True
    ) -> ExecutionResult:
        """
        Execute a CDLPatch on a target ContentGraph.
        
        This is the main entry point for patch execution.
        
        Args:
            patch: The CDLPatch to execute
            target_graph: The target content graph
            validate: Whether to perform validation
            
        Returns:
            ExecutionResult with execution details
        """
        logger.info(f"Starting patch execution: {patch.patch_id}")
        
        # Log patch details
        logger.debug(f"Patch operations: {len(patch.operations)}")
        logger.debug(f"Patch intent: {patch.intent}")
        
        # Execute via scheduler
        result = self.scheduler.execute_patch(
            patch=patch,
            target_graph=target_graph,
            validate=validate
        )
        
        # Log result
        if result.success:
            logger.info(f"Patch execution successful: {len(result.executed_operations)} operations executed")
        else:
            logger.error(f"Patch execution failed: {len(result.failed_operations)} operations failed")
            for error in result.errors:
                logger.error(f"  Error: {error}")
        
        return result
    
    def execute_patch_with_retry(
        self,
        patch: CDLPatch,
        target_graph: ContentGraph,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> ExecutionResult:
        """
        Execute a patch with retry logic.
        
        Args:
            patch: The CDLPatch to execute
            target_graph: The target content graph
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            ExecutionResult with execution details
        """
        import time
        
        last_result = None
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(f"Retry attempt {attempt}/{max_retries}")
                time.sleep(retry_delay)
            
            result = self.execute_patch(patch, target_graph, validate=True)
            last_result = result
            
            if result.success:
                logger.info(f"Patch execution succeeded on attempt {attempt + 1}")
                return result
            
            # Check if retry is appropriate
            if not self._should_retry(result):
                logger.info("Retry not recommended, stopping")
                break
        
        logger.warning(f"Patch execution failed after {max_retries + 1} attempts")
        return last_result or ExecutionResult(
            success=False,
            patch=patch,
            executed_operations=[],
            failed_operations=patch.operations,
            rollback_operations=[],
            execution_time=0,
            errors=["Max retries exceeded"],
            warnings=[]
        )
    
    def _should_retry(self, result: ExecutionResult) -> bool:
        """
        Determine if a failed execution should be retried.
        
        Args:
            result: The execution result
            
        Returns:
            True if retry is recommended
        """
        # Don't retry if validation failed
        if any("validation" in error.lower() for error in result.errors):
            return False
        
        # Don't retry if rollback failed
        if any("rollback" in error.lower() for error in result.errors):
            return False
        
        # Retry for transient errors
        transient_indicators = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "unavailable"
        ]
        
        return any(
            indicator in error.lower()
            for error in result.errors
            for indicator in transient_indicators
        )
    
    def validate_patch(
        self,
        patch: CDLPatch,
        target_graph: ContentGraph
    ) -> Dict[str, Any]:
        """
        Validate a patch without executing it.
        
        Args:
            patch: The CDLPatch to validate
            target_graph: The target content graph
            
        Returns:
            Validation result
        """
        errors = []
        warnings = []
        
        # Check for duplicate operations
        target_operations = {}
        for i, operation in enumerate(patch.operations):
            target_id = getattr(operation, 'target_id', None)
            if target_id:
                if target_id in target_operations:
                    errors.append(
                        f"Duplicate operation on target {target_id}: "
                        f"operations {target_operations[target_id]} and {i}"
                    )
                target_operations[target_id] = i
        
        # Check for circular dependencies
        if self._has_circular_dependencies(patch):
            errors.append("Circular dependency detected in patch operations")
        
        # Check for missing required fields
        for i, operation in enumerate(patch.operations):
            if not operation.op_type:
                errors.append(f"Operation {i} missing op_type")
            if not operation.target_id and operation.op_type.value != "add_node":
                warnings.append(f"Operation {i} missing target_id")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "operation_count": len(patch.operations)
        }
    
    def _has_circular_dependencies(self, patch: CDLPatch) -> bool:
        """
        Check if patch operations have circular dependencies.
        
        Args:
            patch: The CDLPatch to check
            
        Returns:
            True if circular dependencies exist
        """
        # Build adjacency list
        graph = {}
        for i, operation in enumerate(patch.operations):
            target_id = getattr(operation, 'target_id', None)
            if target_id:
                if target_id not in graph:
                    graph[target_id] = []
                # Find operations that depend on this target
                for j, other_op in enumerate(patch.operations):
                    if i != j:
                        other_target = getattr(other_op, 'target_id', None)
                        if other_target == target_id:
                            graph[target_id].append(j)
        
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: int) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    return True
        
        return False
    
    def start_mcp_server(self, port: Optional[int] = None) -> bool:
        """
        Start the MCP server for tool execution.
        
        Args:
            port: Port to listen on (uses config default if None)
            
        Returns:
            True if server started successfully
        """
        if not self.mcp_server:
            logger.error("MCP server not initialized")
            return False
        
        try:
            # Note: This is a simplified implementation
            # In production, you would use a proper async server
            import threading
            import socket
            
            port = port or self.config.mcp_port
            
            def run_server():
                # Create a simple TCP server for MCP
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind(('localhost', port))
                server_socket.listen(5)
                
                logger.info(f"MCP server listening on port {port}")
                
                while True:
                    client_socket, addr = server_socket.accept()
                    logger.info(f"MCP connection from {addr}")
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_mcp_client,
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
            
            server_thread = threading.Thread(target=run_server)
            server_thread.daemon = True
            server_thread.start()
            
            logger.info(f"MCP server started on port {port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            return False
    
    def _handle_mcp_client(self, client_socket):
        """Handle MCP client connection."""
        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break
                
                request = data.decode('utf-8')
                response = self.mcp_server.handle_request(request)
                client_socket.send(response.encode('utf-8'))
        
        except Exception as e:
            logger.error(f"MCP client error: {e}")
        finally:
            client_socket.close()
    
    def register_custom_tool(
        self,
        name: str,
        description: str,
        executor: callable,
        parameters: list,
        category: str = "custom"
    ) -> bool:
        """
        Register a custom tool with the executor.
        
        Args:
            name: Tool name
            description: Tool description
            executor: Tool executor function
            parameters: Tool parameters
            category: Tool category
            
        Returns:
            True if registration successful
        """
        try:
            from .tool_registry import ToolType, ToolCategory, ToolParameter
            
            tool_type = ToolType.CUSTOM
            tool_category = ToolCategory.UTILITY  # Default category
            
            # Try to find matching category
            for cat in ToolCategory:
                if cat.value == category:
                    tool_category = cat
                    break
            
            # Convert parameters to ToolParameter objects
            tool_params = []
            for param in parameters:
                if isinstance(param, ToolParameter):
                    tool_params.append(param)
                else:
                    tool_params.append(ToolParameter(
                        name=param.get("name", ""),
                        type=param.get("type", "string"),
                        description=param.get("description", ""),
                        required=param.get("required", True),
                        default=param.get("default"),
                        constraints=param.get("constraints")
                    ))
            
            # Register tool
            self.tool_registry.register_tool(
                name=name,
                description=description,
                tool_type=tool_type,
                category=tool_category,
                parameters=tool_params,
                executor=executor,
                safe_mode=False  # Custom tools are not safe by default
            )
            
            logger.info(f"Custom tool registered: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register custom tool: {e}")
            return False
    
    def get_execution_status(self) -> Dict[str, Any]:
        """
        Get current execution status.
        
        Returns:
            Status information
        """
        return {
            "scheduler_active_operations": len(self.scheduler.operation_nodes),
            "active_sandboxes": len(self.sandbox_manager.list_sandboxes()),
            "registered_tools": len(self.tool_registry),
            "mcp_server_active": self.mcp_server is not None
        }
    
    def cleanup(self) -> None:
        """Clean up executor resources."""
        logger.info("Cleaning up PatchExecutor...")
        
        # Clean up sandboxes
        self.sandbox_manager.cleanup()
        
        # Clear operation nodes
        self.scheduler.operation_nodes.clear()
        
        logger.info("PatchExecutor cleanup complete")