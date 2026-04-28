"""
Built-in Tools Module

Provides standard execution tools for common operations needed by the
planning and execution engine. These tools are registered in the ToolRegistry
and can be invoked by CDLPatch operations.

Tools include:
- File system operations (read, write, delete, copy, move)
- JSON operations (read, write, modify)
- Text operations (read, write, replace)
- Shell command execution
- Content validation
"""

import json
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .tool_registry import ToolRegistry, ToolType, ToolCategory, ToolParameter

logger = logging.getLogger(__name__)


def _create_file_tool(registry: ToolRegistry) -> None:
    """Register file system operation tools."""
    
    def read_file(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Read file content."""
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return {
                "path": path,
                "content": content,
                "size": len(content),
                "encoding": encoding
            }
        except Exception as e:
            raise RuntimeError(f"Failed to read file {path}: {e}")
    
    def write_file(path: str, content: str, encoding: str = "utf-8", create_dirs: bool = True) -> Dict[str, Any]:
        """Write content to file."""
        try:
            file_path = Path(path)
            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "w", encoding=encoding) as f:
                f.write(content)
            
            return {
                "path": path,
                "size": len(content),
                "encoding": encoding,
                "created": not file_path.exists()
            }
        except Exception as e:
            raise RuntimeError(f"Failed to write file {path}: {e}")
    
    def delete_file(path: str) -> Dict[str, Any]:
        """Delete a file."""
        try:
            file_path = Path(path)
            if not file_path.exists():
                return {"path": path, "existed": False}
            
            file_path.unlink()
            return {"path": path, "deleted": True}
        except Exception as e:
            raise RuntimeError(f"Failed to delete file {path}: {e}")
    
    def copy_file(source: str, destination: str) -> Dict[str, Any]:
        """Copy a file."""
        try:
            shutil.copy2(source, destination)
            return {
                "source": source,
                "destination": destination,
                "copied": True
            }
        except Exception as e:
            raise RuntimeError(f"Failed to copy file {source} to {destination}: {e}")
    
    def move_file(source: str, destination: str) -> Dict[str, Any]:
        """Move/rename a file."""
        try:
            shutil.move(source, destination)
            return {
                "source": source,
                "destination": destination,
                "moved": True
            }
        except Exception as e:
            raise RuntimeError(f"Failed to move file {source} to {destination}: {e}")
    
    def list_files(directory: str, recursive: bool = False, pattern: str = "*") -> Dict[str, Any]:
        """List files in a directory."""
        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                return {"directory": directory, "exists": False, "files": []}
            
            files = []
            if recursive:
                for file_path in dir_path.rglob(pattern):
                    if file_path.is_file():
                        files.append(str(file_path.relative_to(dir_path)))
            else:
                for file_path in dir_path.glob(pattern):
                    if file_path.is_file():
                        files.append(file_path.name)
            
            return {
                "directory": directory,
                "exists": True,
                "recursive": recursive,
                "pattern": pattern,
                "files": files,
                "count": len(files)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to list files in {directory}: {e}")
    
    # Register file tools
    registry.register_tool(
        name="file_read",
        description="Read content from a file",
        tool_type=ToolType.FILE_OPERATION,
        category=ToolCategory.FILE_SYSTEM,
        parameters=[
            ToolParameter("path", "string", "Path to the file to read", required=True),
            ToolParameter("encoding", "string", "File encoding (default: utf-8)", required=False, default="utf-8")
        ],
        executor=read_file,
        safe_mode=True
    )
    
    registry.register_tool(
        name="file_write",
        description="Write content to a file",
        tool_type=ToolType.FILE_OPERATION,
        category=ToolCategory.FILE_SYSTEM,
        parameters=[
            ToolParameter("path", "string", "Path to write the file to", required=True),
            ToolParameter("content", "string", "Content to write", required=True),
            ToolParameter("encoding", "string", "File encoding (default: utf-8)", required=False, default="utf-8"),
            ToolParameter("create_dirs", "boolean", "Create parent directories if they don't exist", required=False, default=True)
        ],
        executor=write_file,
        safe_mode=True
    )
    
    registry.register_tool(
        name="file_delete",
        description="Delete a file",
        tool_type=ToolType.FILE_OPERATION,
        category=ToolCategory.FILE_SYSTEM,
        parameters=[
            ToolParameter("path", "string", "Path to the file to delete", required=True)
        ],
        executor=delete_file,
        safe_mode=False  # Deletion is not safe
    )
    
    registry.register_tool(
        name="file_copy",
        description="Copy a file to a new location",
        tool_type=ToolType.FILE_OPERATION,
        category=ToolCategory.FILE_SYSTEM,
        parameters=[
            ToolParameter("source", "string", "Source file path", required=True),
            ToolParameter("destination", "string", "Destination file path", required=True)
        ],
        executor=copy_file,
        safe_mode=True
    )
    
    registry.register_tool(
        name="file_move",
        description="Move or rename a file",
        tool_type=ToolType.FILE_OPERATION,
        category=ToolCategory.FILE_SYSTEM,
        parameters=[
            ToolParameter("source", "string", "Source file path", required=True),
            ToolParameter("destination", "string", "Destination file path", required=True)
        ],
        executor=move_file,
        safe_mode=False  # Moving is not safe
    )
    
    registry.register_tool(
        name="file_list",
        description="List files in a directory",
        tool_type=ToolType.FILE_OPERATION,
        category=ToolCategory.FILE_SYSTEM,
        parameters=[
            ToolParameter("directory", "string", "Directory to list", required=True),
            ToolParameter("recursive", "boolean", "List recursively", required=False, default=False),
            ToolParameter("pattern", "string", "File pattern to match (default: *)", required=False, default="*")
        ],
        executor=list_files,
        safe_mode=True
    )


def _create_json_tool(registry: ToolRegistry) -> None:
    """Register JSON operation tools."""
    
    def read_json(path: str) -> Dict[str, Any]:
        """Read JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to read JSON file {path}: {e}")
    
    def write_json(path: str, data: Dict[str, Any], indent: int = 2) -> Dict[str, Any]:
        """Write JSON file."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            return {"path": path, "written": True}
        except Exception as e:
            raise RuntimeError(f"Failed to write JSON file {path}: {e}")
    
    def modify_json(
        path: str,
        operations: List[Dict[str, Any]],
        create_if_missing: bool = False
    ) -> Dict[str, Any]:
        """
        Modify JSON file using JSON Patch operations.
        
        Operations format:
        [
            {"op": "add", "path": "/key", "value": "value"},
            {"op": "replace", "path": "/key", "value": "new_value"},
            {"op": "remove", "path": "/key"}
        ]
        """
        try:
            # Read existing data or create empty dict
            if Path(path).exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            elif create_if_missing:
                data = {}
            else:
                raise RuntimeError(f"File {path} does not exist and create_if_missing is False")
            
            # Apply operations
            for op in operations:
                op_type = op.get("op")
                op_path = op.get("path", "")
                value = op.get("value")
                
                if not op_type or not op_path:
                    raise ValueError(f"Invalid operation: {op}")
                
                # Parse path (simple implementation, supports /key/subkey)
                keys = [k for k in op_path.split("/") if k]
                
                if op_type == "add":
                    target = data
                    for key in keys[:-1]:
                        if key not in target:
                            target[key] = {}
                        target = target[key]
                    target[keys[-1]] = value
                
                elif op_type == "replace":
                    target = data
                    for key in keys[:-1]:
                        if key not in target:
                            raise KeyError(f"Path not found: {'/'.join(keys[:keys.index(key)+1])}")
                        target = target[key]
                    target[keys[-1]] = value
                
                elif op_type == "remove":
                    target = data
                    for key in keys[:-1]:
                        if key not in target:
                            raise KeyError(f"Path not found: {'/'.join(keys[:keys.index(key)+1])}")
                        target = target[key]
                    if keys[-1] in target:
                        del target[keys[-1]]
                
                else:
                    raise ValueError(f"Unsupported operation: {op_type}")
            
            # Write back
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return {
                "path": path,
                "operations_applied": len(operations),
                "modified": True
            }
        except Exception as e:
            raise RuntimeError(f"Failed to modify JSON file {path}: {e}")
    
    # Register JSON tools
    registry.register_tool(
        name="json_read",
        description="Read and parse JSON file",
        tool_type=ToolType.JSON_OPERATION,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("path", "string", "Path to JSON file", required=True)
        ],
        executor=read_json,
        safe_mode=True
    )
    
    registry.register_tool(
        name="json_write",
        description="Write data as JSON file",
        tool_type=ToolType.JSON_OPERATION,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("path", "string", "Path to write JSON file", required=True),
            ToolParameter("data", "object", "JSON data to write", required=True),
            ToolParameter("indent", "integer", "Indentation spaces (default: 2)", required=False, default=2)
        ],
        executor=write_json,
        safe_mode=True
    )
    
    registry.register_tool(
        name="json_modify",
        description="Modify JSON file using JSON Patch operations",
        tool_type=ToolType.JSON_OPERATION,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("path", "string", "Path to JSON file", required=True),
            ToolParameter("operations", "array", "JSON Patch operations", required=True),
            ToolParameter("create_if_missing", "boolean", "Create file if it doesn't exist", required=False, default=False)
        ],
        executor=modify_json,
        safe_mode=False  # Modifications are not safe
    )


def _create_text_tool(registry: ToolRegistry) -> None:
    """Register text operation tools."""
    
    def read_text(path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Read text file."""
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            return {
                "path": path,
                "content": content,
                "lines": content.count("\n") + 1,
                "size": len(content)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to read text file {path}: {e}")
    
    def write_text(path: str, content: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Write text file."""
        try:
            with open(path, "w", encoding=encoding) as f:
                f.write(content)
            return {
                "path": path,
                "size": len(content),
                "written": True
            }
        except Exception as e:
            raise RuntimeError(f"Failed to write text file {path}: {e}")
    
    def replace_text(
        path: str,
        search: str,
        replace: str,
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """Replace text in file."""
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            
            original_content = content
            new_content = content.replace(search, replace)
            replacements = content.count(search)
            
            if replacements > 0:
                with open(path, "w", encoding=encoding) as f:
                    f.write(new_content)
            
            return {
                "path": path,
                "search": search,
                "replace": replace,
                "replacements": replacements,
                "modified": replacements > 0
            }
        except Exception as e:
            raise RuntimeError(f"Failed to replace text in {path}: {e}")
    
    # Register text tools
    registry.register_tool(
        name="text_read",
        description="Read text file",
        tool_type=ToolType.TEXT_OPERATION,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("path", "string", "Path to text file", required=True),
            ToolParameter("encoding", "string", "File encoding (default: utf-8)", required=False, default="utf-8")
        ],
        executor=read_text,
        safe_mode=True
    )
    
    registry.register_tool(
        name="text_write",
        description="Write text file",
        tool_type=ToolType.TEXT_OPERATION,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("path", "string", "Path to write text file", required=True),
            ToolParameter("content", "string", "Text content to write", required=True),
            ToolParameter("encoding", "string", "File encoding (default: utf-8)", required=False, default="utf-8")
        ],
        executor=write_text,
        safe_mode=True
    )
    
    registry.register_tool(
        name="text_replace",
        description="Replace text in file",
        tool_type=ToolType.TEXT_OPERATION,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("path", "string", "Path to text file", required=True),
            ToolParameter("search", "string", "Text to search for", required=True),
            ToolParameter("replace", "string", "Text to replace with", required=True),
            ToolParameter("encoding", "string", "File encoding (default: utf-8)", required=False, default="utf-8")
        ],
        executor=replace_text,
        safe_mode=False  # Modifications are not safe
    )


def _create_shell_tool(registry: ToolRegistry) -> None:
    """Register shell command execution tool."""
    
    def execute_shell(command: str, cwd: Optional[str] = None, timeout: int = 300) -> Dict[str, Any]:
        """Execute shell command."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "command": command,
                "cwd": cwd,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out after {timeout} seconds: {command}")
        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {command} - {e}")
    
    # Register shell tool
    registry.register_tool(
        name="shell_execute",
        description="Execute shell command",
        tool_type=ToolType.SHELL_COMMAND,
        category=ToolCategory.UTILITY,
        parameters=[
            ToolParameter("command", "string", "Shell command to execute", required=True),
            ToolParameter("cwd", "string", "Working directory (optional)", required=False),
            ToolParameter("timeout", "integer", "Timeout in seconds (default: 300)", required=False, default=300)
        ],
        executor=execute_shell,
        safe_mode=False,  # Shell commands are not safe
        requires_approval=True
    )


def _create_validation_tool(registry: ToolRegistry) -> None:
    """Register validation tools."""
    
    def validate_json_schema(path: str, schema_path: str) -> Dict[str, Any]:
        """Validate JSON file against schema."""
        try:
            # Simple validation - check if JSON is valid
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)
            
            # Load schema if provided
            if Path(schema_path).exists():
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
            else:
                schema = None
            
            return {
                "path": path,
                "schema_path": schema_path,
                "valid_json": True,
                "schema_valid": schema is not None,
                "errors": []
            }
        except json.JSONDecodeError as e:
            return {
                "path": path,
                "schema_path": schema_path,
                "valid_json": False,
                "schema_valid": False,
                "errors": [str(e)]
            }
        except Exception as e:
            raise RuntimeError(f"Failed to validate JSON file {path}: {e}")
    
    # Register validation tools
    registry.register_tool(
        name="validate_json",
        description="Validate JSON file syntax",
        tool_type=ToolType.VALIDATION,
        category=ToolCategory.VALIDATION,
        parameters=[
            ToolParameter("path", "string", "Path to JSON file", required=True),
            ToolParameter("schema_path", "string", "Path to JSON schema file (optional)", required=False, default="")
        ],
        executor=validate_json_schema,
        safe_mode=True
    )


def register_all_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools in the registry."""
    logger.info("Registering built-in tools...")
    
    _create_file_tool(registry)
    _create_json_tool(registry)
    _create_text_tool(registry)
    _create_shell_tool(registry)
    _create_validation_tool(registry)
    
    logger.info(f"Registered {len(registry)} built-in tools")
    
    # Log registered tools
    for category in ToolCategory:
        tools = registry.get_tools_by_category(category)
        if tools:
            logger.info(f"  {category.value}: {', '.join(tools)}")