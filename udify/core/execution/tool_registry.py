"""
Tool Registry Module

Manages registration and discovery of execution tools.
Tools are the atomic operations that can be performed on content,
such as file operations, JSON modifications, text replacements, etc.

This module provides:
- Tool registration and metadata management
- Tool discovery and validation
- Tool execution context management
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """Types of tools that can be registered."""
    FILE_OPERATION = "file_operation"
    JSON_OPERATION = "json_operation"
    TEXT_OPERATION = "text_operation"
    SHELL_COMMAND = "shell_command"
    CUSTOM = "custom"


class ToolCategory(Enum):
    """Categories for organizing tools."""
    FILE_SYSTEM = "file_system"
    DATA_MANIPULATION = "data_manipulation"
    CONTENT_EXTRACTION = "content_extraction"
    VALIDATION = "validation"
    UTILITY = "utility"


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    name: str
    description: str
    tool_type: ToolType
    category: ToolCategory
    version: str = "1.0.0"
    author: str = "Udify"
    tags: List[str] = field(default_factory=list)
    timeout: int = 300  # 5 minutes default
    requires_approval: bool = False
    safe_mode: bool = True  # Whether tool is safe to run in sandbox


@dataclass
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    constraints: Optional[Dict[str, Any]] = None


@dataclass
class ToolDefinition:
    """Complete definition of a tool."""
    metadata: ToolMetadata
    parameters: List[ToolParameter]
    executor: Callable
    validation_fn: Optional[Callable] = None


class ToolRegistry:
    """Registry for managing execution tools."""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._categories: Dict[ToolCategory, List[str]] = {}
        logger.info("ToolRegistry initialized")
    
    def register_tool(
        self,
        name: str,
        description: str,
        tool_type: ToolType,
        category: ToolCategory,
        parameters: List[ToolParameter],
        executor: Callable,
        validation_fn: Optional[Callable] = None,
        **metadata_kwargs
    ) -> None:
        """
        Register a new tool.
        
        Args:
            name: Unique tool identifier
            description: Human-readable description
            tool_type: Type of tool operation
            category: Tool category for organization
            parameters: List of parameter definitions
            executor: Callable that executes the tool
            validation_fn: Optional validation function
            **metadata_kwargs: Additional metadata (version, author, tags, etc.)
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        
        metadata = ToolMetadata(
            name=name,
            description=description,
            tool_type=tool_type,
            category=category,
            **metadata_kwargs
        )
        
        tool_def = ToolDefinition(
            metadata=metadata,
            parameters=parameters,
            executor=executor,
            validation_fn=validation_fn
        )
        
        self._tools[name] = tool_def
        
        if category not in self._categories:
            self._categories[category] = []
        self._categories[category].append(name)
        
        logger.info(f"Tool registered: {name} (type: {tool_type.value}, category: {category.value})")
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get tool definition by name."""
        return self._tools.get(name)
    
    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        tool_type: Optional[ToolType] = None,
        safe_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List available tools with optional filtering.
        
        Args:
            category: Filter by category
            tool_type: Filter by tool type
            safe_only: Only include safe tools
            
        Returns:
            List of tool metadata dictionaries
        """
        tools = []
        
        for name, tool_def in self._tools.items():
            if category and tool_def.metadata.category != category:
                continue
            if tool_type and tool_def.metadata.tool_type != tool_type:
                continue
            if safe_only and not tool_def.metadata.safe_mode:
                continue
            
            tools.append({
                "name": name,
                "description": tool_def.metadata.description,
                "type": tool_def.metadata.tool_type.value,
                "category": tool_def.metadata.category.value,
                "version": tool_def.metadata.version,
                "safe_mode": tool_def.metadata.safe_mode,
                "parameters": [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "description": p.description
                    }
                    for p in tool_def.parameters
                ]
            })
        
        return tools
    
    def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate parameters for a tool.
        
        Args:
            tool_name: Name of the tool
            parameters: Parameters to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        tool_def = self.get_tool(tool_name)
        if not tool_def:
            return False, [f"Tool '{tool_name}' not found"]
        
        errors = []
        
        # Check required parameters
        for param in tool_def.parameters:
            if param.required and param.name not in parameters:
                errors.append(f"Missing required parameter: {param.name}")
        
        # Check parameter types and constraints
        for param_name, param_value in parameters.items():
            param_def = next((p for p in tool_def.parameters if p.name == param_name), None)
            if not param_def:
                errors.append(f"Unknown parameter: {param_name}")
                continue
            
            # Type checking (basic)
            if param_def.type == "string" and not isinstance(param_value, str):
                errors.append(f"Parameter '{param_name}' must be a string")
            elif param_def.type == "integer" and not isinstance(param_value, int):
                errors.append(f"Parameter '{param_name}' must be an integer")
            elif param_def.type == "boolean" and not isinstance(param_value, bool):
                errors.append(f"Parameter '{param_name}' must be a boolean")
            elif param_def.type == "array" and not isinstance(param_value, list):
                errors.append(f"Parameter '{param_name}' must be an array")
            elif param_def.type == "object" and not isinstance(param_value, (dict, object)):
                errors.append(f"Parameter '{param_name}' must be an object")
            
            # Constraint checking
            if param_def.constraints:
                if "min" in param_def.constraints and param_value < param_def.constraints["min"]:
                    errors.append(f"Parameter '{param_name}' must be >= {param_def.constraints['min']}")
                if "max" in param_def.constraints and param_value > param_def.constraints["max"]:
                    errors.append(f"Parameter '{param_name}' must be <= {param_def.constraints['max']}")
                if "enum" in param_def.constraints and param_value not in param_def.constraints["enum"]:
                    errors.append(f"Parameter '{param_name}' must be one of {param_def.constraints['enum']}")
        
        return len(errors) == 0, errors
    
    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool with given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            
        Returns:
            Execution result dictionary
        """
        tool_def = self.get_tool(tool_name)
        if not tool_def:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found",
                "tool_name": tool_name
            }
        
        # Validate parameters
        is_valid, errors = self.validate_parameters(tool_name, parameters)
        if not is_valid:
            return {
                "success": False,
                "error": "Parameter validation failed",
                "errors": errors,
                "tool_name": tool_name
            }
        
        # Run validation function if provided
        if tool_def.validation_fn:
            try:
                validation_result = tool_def.validation_fn(parameters)
                if not validation_result.get("valid", True):
                    return {
                        "success": False,
                        "error": "Validation failed",
                        "validation_errors": validation_result.get("errors", []),
                        "tool_name": tool_name
                    }
            except Exception as e:
                logger.warning(f"Validation function failed for tool {tool_name}: {e}")
        
        # Execute the tool
        try:
            result = tool_def.executor(**parameters)
            return {
                "success": True,
                "result": result,
                "tool_name": tool_name,
                "metadata": tool_def.metadata
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {
                "success": False,
                "error": str(e),
                "tool_name": tool_name,
                "metadata": tool_def.metadata
            }
    
    def get_tools_by_category(self, category: ToolCategory) -> List[str]:
        """Get tool names for a specific category."""
        return self._categories.get(category, [])
    
    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools
    
    def __len__(self) -> int:
        """Get number of registered tools."""
        return len(self._tools)