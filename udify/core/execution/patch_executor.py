"""
Udify Execution - Patch Executor

在 VFS 上执行 CDLPatch，将图谱级别的操作转换为文件级别的修改。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from udify.core.execution.vfs import VirtualFileSystem
from udify.models.cdl_patch import CDLPatch, OpType, PatchOperation


class PatchExecutionError(Exception):
    """Patch 执行错误"""
    pass


class PatchExecutor:
    """
    Patch 执行器

    将 CDLPatch 中的操作转换为 VFS 上的文件修改。
    支持：
    - INI 属性修改
    - 对象属性修改
    - 脚本插入/修改
    - 资源替换
    """

    def __init__(self, vfs: VirtualFileSystem) -> None:
        self.vfs = vfs
        self._operation_handlers = {
            OpType.MODIFY_PROPERTY: self._execute_modify_property,
            OpType.ADD_NODE: self._execute_add_node,
            OpType.REMOVE_NODE: self._execute_remove_node,
            OpType.ADD_ASSET: self._execute_add_asset,
            OpType.REMOVE_ASSET: self._execute_remove_asset,
        }

    def execute(self, patch: CDLPatch) -> Dict[str, Any]:
        """
        执行 Patch

        Returns:
            执行结果统计
        """
        results = {
            "success": True,
            "executed": [],
            "failed": [],
            "modified_files": set(),
        }

        for i, op in enumerate(patch.operations):
            handler = self._operation_handlers.get(op.op_type)
            if handler is None:
                results["failed"].append({
                    "index": i,
                    "op": op.op_type.name,
                    "error": "不支持的操作类型",
                })
                results["success"] = False
                continue

            try:
                modified_files = handler(op)
                results["executed"].append({
                    "index": i,
                    "op": op.op_type.name,
                    "files": modified_files,
                })
                results["modified_files"].update(modified_files)
            except Exception as e:
                results["failed"].append({
                    "index": i,
                    "op": op.op_type.name,
                    "error": str(e),
                })
                results["success"] = False

        results["modified_files"] = list(results["modified_files"])
        return results

    def _execute_modify_property(self, op: PatchOperation) -> List[str]:
        """执行属性修改"""
        node_id = op.target_id
        key = op.payload.get("key")
        value = op.payload.get("value")

        if not key:
            raise PatchExecutionError("Missing key in MODIFY_PROPERTY")

        # 从 node_id 解析文件路径和 section
        file_path, section_name = self._parse_node_id(node_id)

        if not file_path:
            raise PatchExecutionError(f"Cannot resolve file path from node ID: {node_id}")

        # 读取文件内容
        content = self.vfs.read_file(file_path)
        if content is None:
            raise PatchExecutionError(f"File not found: {file_path}")

        # 根据文件类型选择修改方式
        if file_path.endswith(".ini"):
            new_content = self._modify_ini(content, section_name, key, value)
        elif file_path.endswith(".obj"):
            new_content = self._modify_obj(content, section_name, key, value)
        else:
            raise PatchExecutionError(f"Unsupported file type for modification: {file_path}")

        # 写入修改后的内容
        self.vfs.write_file(file_path, new_content)

        return [file_path]

    def _execute_add_node(self, op: PatchOperation) -> List[str]:
        """执行添加节点（创建新文件条目）"""
        node_id = op.target_id
        payload = op.payload

        file_path = payload.get("source_path", "")
        if not file_path:
            # 从 node_id 推断
            file_path, _ = self._parse_node_id(node_id)

        if not file_path:
            raise PatchExecutionError(f"Cannot determine file path for ADD_NODE: {node_id}")

        section_name = payload.get("name", node_id)
        properties = payload.get("properties", {})

        content = self.vfs.read_file(file_path) or ""

        if file_path.endswith(".ini"):
            new_content = self._add_ini_section(content, section_name, properties)
        elif file_path.endswith(".obj"):
            new_content = self._add_obj_entry(content, section_name, properties)
        else:
            raise PatchExecutionError(f"Unsupported file type for ADD_NODE: {file_path}")

        self.vfs.write_file(file_path, new_content)
        return [file_path]

    def _execute_remove_node(self, op: PatchOperation) -> List[str]:
        """执行删除节点"""
        node_id = op.target_id
        file_path, section_name = self._parse_node_id(node_id)

        if not file_path:
            raise PatchExecutionError(f"Cannot resolve file path from node ID: {node_id}")

        content = self.vfs.read_file(file_path)
        if content is None:
            return []

        if file_path.endswith(".ini"):
            new_content = self._remove_ini_section(content, section_name)
        elif file_path.endswith(".obj"):
            new_content = self._remove_obj_entry(content, section_name)
        else:
            raise PatchExecutionError(f"Unsupported file type for REMOVE_NODE: {file_path}")

        self.vfs.write_file(file_path, new_content)
        return [file_path]

    def _execute_add_asset(self, op: PatchOperation) -> List[str]:
        """执行添加资源"""
        path = op.payload.get("path", "")
        if not path:
            raise PatchExecutionError("Missing path in ADD_ASSET")

        # 对于新资源，可能需要创建占位文件
        content = self.vfs.read_file(path)
        if content is None:
            self.vfs.write_file(path, "# New asset\n")

        return [path]

    def _execute_remove_asset(self, op: PatchOperation) -> List[str]:
        """执行删除资源"""
        path = op.payload.get("path", "")
        if not path:
            # 从 target_id 推断
            path = op.target_id

        self.vfs.delete_file(path)
        return [path]

    def _parse_node_id(self, node_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从节点 ID 解析文件路径和 section 名

        格式: file_path_section_name（路径中的 / 替换为 _）
        """
        # 尝试找到文件扩展名位置（支持 .ext_ 和 _ext_ 格式）
        patterns = [
            (r"^(.+?)\.ini_(.+)$", ".ini"),
            (r"^(.+?)\.obj_(.+)$", ".obj"),
            (r"^(.+?)\.txt_(.+)$", ".txt"),
            (r"^(.+?)\.npc_(.+)$", ".npc"),
            (r"^(.+?)\.lua_(.+)$", ".lua"),
            (r"^(.+?)_ini_(.+)$", ".ini"),
            (r"^(.+?)_obj_(.+)$", ".obj"),
            (r"^(.+?)_txt_(.+)$", ".txt"),
            (r"^(.+?)_npc_(.+)$", ".npc"),
            (r"^(.+?)_lua_(.+)$", ".lua"),
        ]

        for pattern, ext in patterns:
            match = re.match(pattern, node_id)
            if match:
                file_path = match.group(1).replace("_", "/") + ext
                section_name = match.group(2).replace("_", " ")
                return file_path, section_name

        # 如果找不到扩展名，尝试其他分隔符
        if "_" in node_id:
            parts = node_id.rsplit("_", 1)
            return parts[0].replace("_", "/") + ".ini", parts[1]

        return None, None

    def _modify_ini(self, content: str, section: str, key: str, value: Any) -> str:
        """修改 INI 文件中的属性"""
        lines = content.splitlines()
        in_section = False
        modified = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 检查 section
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1].strip()
                in_section = (current_section == section)
                continue

            # 在目标 section 中查找 key
            if in_section and "=" in line:
                current_key = line.split("=", 1)[0].strip()
                if current_key == key:
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[i] = f"{indent}{key}={value}"
                    modified = True
                    break

        if not modified:
            # Section 或 key 不存在，需要添加
            content = self._add_ini_section(content, section, {key: value})
            return content

        return "\n".join(lines)

    def _add_ini_section(self, content: str, section: str, properties: Dict[str, Any]) -> str:
        """在 INI 文件中添加新 section"""
        lines = content.splitlines() if content else []

        # 检查 section 是否已存在
        for line in lines:
            stripped = line.strip()
            if stripped == f"[{section}]":
                # Section 已存在，追加属性
                return self._modify_ini(content, section, list(properties.keys())[0], list(properties.values())[0])

        # 添加新 section
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        for key, value in properties.items():
            lines.append(f"{key}={value}")

        return "\n".join(lines)

    def _remove_ini_section(self, content: str, section: str) -> str:
        """从 INI 文件中删除 section"""
        lines = content.splitlines()
        result = []
        in_target_section = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1].strip()
                in_target_section = (current_section == section)
                if not in_target_section:
                    result.append(line)
                continue

            if not in_target_section:
                result.append(line)

        return "\n".join(result)

    def _modify_obj(self, content: str, entry: str, key: str, value: Any) -> str:
        """修改 OBJ 文件中的属性"""
        lines = content.splitlines()
        in_entry = False
        modified = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 检查条目开始
            if stripped.upper() == entry.upper() or \
               re.match(rf"^(?:Object|Define|Entry|@)\s+{re.escape(entry)}", stripped, re.IGNORECASE):
                in_entry = True
                continue

            # 检查条目结束（下一个条目或空行）
            if in_entry:
                if stripped == "" or \
                   (stripped.isupper() and len(stripped) > 1 and "=" not in stripped) or \
                   re.match(r"^(?:Object|Define|Entry|@)\s+", stripped, re.IGNORECASE):
                    in_entry = False
                    continue

                if "=" in line:
                    current_key = line.split("=", 1)[0].strip()
                    if current_key == key:
                        indent = line[:len(line) - len(line.lstrip())]
                        lines[i] = f"{indent}{key}={value}"
                        modified = True
                        break

        if not modified:
            # 添加属性到条目
            return self._add_obj_entry(content, entry, {key: value})

        return "\n".join(lines)

    def _add_obj_entry(self, content: str, entry: str, properties: Dict[str, Any]) -> str:
        """在 OBJ 文件中添加新条目"""
        lines = content.splitlines() if content else []

        if lines and lines[-1].strip():
            lines.append("")
        lines.append(entry)
        for key, value in properties.items():
            lines.append(f"    {key}={value}")

        return "\n".join(lines)

    def _remove_obj_entry(self, content: str, entry: str) -> str:
        """从 OBJ 文件中删除条目"""
        lines = content.splitlines()
        result = []
        in_target_entry = False

        for line in lines:
            stripped = line.strip()

            # 检查条目开始
            if stripped.upper() == entry.upper() or \
               re.match(rf"^(?:Object|Define|Entry|@)\s+{re.escape(entry)}", stripped, re.IGNORECASE):
                in_target_entry = True
                continue

            # 检查条目结束
            if in_target_entry:
                if stripped == "" or \
                   (stripped.isupper() and len(stripped) > 1 and "=" not in stripped) or \
                   re.match(r"^(?:Object|Define|Entry|@)\s+", stripped, re.IGNORECASE):
                    in_target_entry = False
                continue

            result.append(line)

        return "\n".join(result)
