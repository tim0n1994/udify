"""
MCP Server Module

Implements Model Context Protocol (MCP) server for tool execution.
Provides standardized interface for LLMs to discover and invoke tools.

Based on MCP specification: https://github.com/modelcontextprotocol/servers
"""

import logging
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from .tool_registry import ToolRegistry, ToolDefinition
from .sandbox import SandboxManager, SandboxConfig

logger = logging.getLogger(__name__)


class McpErrorCodes:
    """MCP error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


class McpMessageTypes(Enum):
    """MCP message types."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


@dataclass
class McpRequest:
    """MCP request message."""
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


@dataclass
class McpResponse:
    """MCP response message."""
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


@dataclass
class McpTool:
    """MCP tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class McpListToolsResult:
    """MCP list_tools result."""
    tools: List[McpTool]


class UdifyMCPServer:
    """
    MCP Server for Udify tool execution.
    
    Provides MCP-compliant interface for tool discovery and execution,
    enabling LLMs to interact with Udify's execution engine.
    """
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        sandbox_manager: Optional[SandboxManager] = None,
        use_sandbox: bool = True
    ):
        """
        Initialize MCP server.
        
        Args:
            tool_registry: Tool registry instance
            sandbox_manager: Optional sandbox manager
            use_sandbox: Whether to use sandbox for tool execution
        """
        self.tool_registry = tool_registry
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self.use_sandbox = use_sandbox
        self.request_id_counter = 0
        logger.info("UdifyMCPServer initialized")
    
    def handle_request(self, request_data: str) -> str:
        """
        Handle incoming MCP request.
        
        Args:
            request_data: JSON string containing MCP request
            
        Returns:
            JSON string containing MCP response
        """
        try:
            request_dict = json.loads(request_data)
            request = McpRequest(**request_dict)
            
            # Validate JSON-RPC version
            if request.jsonrpc != "2.0":
                return self._error_response(
                    request.id,
                    McpErrorCodes.INVALID_REQUEST,
                    "Invalid JSON-RPC version"
                )
            
            # Route request based on method
            if request.method == "tools/list":
                return self._handle_list_tools(request.id)
            elif request.method == "tools/call":
                return self._handle_call_tool(request.id, request.params)
            else:
                return self._error_response(
                    request.id,
                    McpErrorCodes.METHOD_NOT_FOUND,
                    f"Method not found: {request.method}"
                )
        
        except json.JSONDecodeError as e:
            return self._error_response(
                None,
                McpErrorCodes.PARSE_ERROR,
                f"Invalid JSON: {e}"
            )
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return self._error_response(
                None,
                McpErrorCodes.INTERNAL_ERROR,
                f"Internal server error: {e}"
            )
    
    def _handle_list_tools(self, request_id: Optional[int]) -> str:
        """Handle tools/list request."""
        try:
            # Get all registered tools
            all_tools = self.tool_registry.list_tools()
            
            # Convert to MCP tool format
            mcp_tools = []
            for tool in all_tools:
                # Build JSON schema for tool parameters
                properties = {}
                required = []
                
                for param in tool["parameters"]:
                    param_schema = {
                        "type": param["type"],
                        "description": param["description"]
                    }
                    
                    if param["required"]:
                        required.append(param["name"])
                    
                    if "default" in param and param["default"] is not None:
                        param_schema["default"] = param["default"]
                    
                    properties[param["name"]] = param_schema
                
                input_schema = {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
                
                mcp_tool = McpTool(
                    name=tool["name"],
                    description=tool["description"],
                    inputSchema=input_schema
                )
                mcp_tools.append(asdict(mcp_tool))
            
            result = asdict(McpListToolsResult(tools=mcp_tools))
            return self._success_response(request_id, result)
        
        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return self._error_response(
                request_id,
                McpErrorCodes.INTERNAL_ERROR,
                f"Failed to list tools: {e}"
            )
    
    def _handle_call_tool(self, request_id: Optional[int], params: Optional[Dict[str, Any]]) -> str:
        """Handle tools/call request."""
        try:
            if not params:
                return self._error_response(
                    request_id,
                    McpErrorCodes.INVALID_PARAMS,
                    "Missing parameters"
                )
            
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            
            if not tool_name:
                return self._error_response(
                    request_id,
                    McpErrorCodes.INVALID_PARAMS,
                    "Missing tool name"
                )
            
            # Get tool definition
            tool_def = self.tool_registry.get_tool(tool_name)
            if not tool_def:
                return self._error_response(
                    request_id,
                    McpErrorCodes.INVALID_PARAMS,
                    f"Tool not found: {tool_name}"
                )
            
            # Execute tool
            if self.use_sandbox and tool_def.metadata.safe_mode:
                # Execute in sandbox
                config = SandboxConfig(
                    timeout=tool_def.metadata.timeout,
                    memory_limit="512m",
                    cpu_limit=1.0
                )
                
                # Create Python script to execute tool
                script = self._generate_tool_script(tool_name, tool_args)
                result = self.sandbox_manager.run_python_script(
                    script=script,
                    config=config
                )
                
                if result.success:
                    # Parse result from stdout
                    try:
                        output = json.loads(result.stdout.strip())
                        return self._success_response(request_id, output)
                    except json.JSONDecodeError:
                        return self._success_response(request_id, {
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "exit_code": result.exit_code
                        })
                else:
                    return self._error_response(
                        request_id,
                        McpErrorCodes.INTERNAL_ERROR,
                        f"Tool execution failed: {result.stderr}"
                    )
            else:
                # Execute directly
                execution_result = self.tool_registry.execute_tool(tool_name, tool_args)
                
                if execution_result["success"]:
                    return self._success_response(request_id, execution_result)
                else:
                    return self._error_response(
                        request_id,
                        McpErrorCodes.INTERNAL_ERROR,
                        execution_result.get("error", "Tool execution failed")
                    )
        
        except Exception as e:
            logger.error(f"Error calling tool: {e}")
            return self._error_response(
                request_id,
                McpErrorCodes.INTERNAL_ERROR,
                f"Failed to call tool: {e}"
            )
    
    def _generate_tool_script(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Generate Python script to execute tool in sandbox."""
        # Import necessary modules
        script = """
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
    tool_name="{}",
    parameters={}
)

# Output result as JSON
print(json.dumps(result))
""".format(tool_name, json.dumps(tool_args))
        
        return script
    
    def _success_response(self, request_id: Optional[int], result: Any) -> str:
        """Create success response."""
        response = McpResponse(
            id=request_id,
            result=result
        )
        return json.dumps(asdict(response))
    
    def _error_response(
        self,
        request_id: Optional[int],
        code: int,
        message: str,
        data: Optional[Any] = None
    ) -> str:
        """Create error response."""
        error = {
            "code": code,
            "message": message
        }
        if data is not None:
            error["data"] = data
        
        response = McpResponse(
            id=request_id,
            error=error
        )
        return json.dumps(asdict(response))
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools (convenience method)."""
        return self.tool_registry.list_tools()
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool (convenience method)."""
        request = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        response_data = self.handle_request(json.dumps(request))
        response = json.loads(response_data)
        
        if "error" in response:
            raise Exception(f"MCP error: {response['error']}")
        
        return response.get("result", {})
    
    def _next_request_id(self) -> int:
        """Get next request ID."""
        self.request_id_counter += 1
        return self.request_id_counter