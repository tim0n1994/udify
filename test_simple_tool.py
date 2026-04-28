#!/usr/bin/env python3
"""简单测试工具执行"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from udify.models.content_graph import ContentGraph, ContentNode, NodeType, ContentMetadata, GameEngine
from udify.core.execution.tool_registry import ToolRegistry, ToolType, ToolCategory, ToolParameter

# 创建图
metadata = ContentMetadata(title="Test", engine=GameEngine.UNITY, version="1.0")
graph = ContentGraph(media_type="game", metadata=metadata)
node = ContentNode(id="player-001", type=NodeType.CHARACTER, name="Player", properties={"health": 100, "damage": 10})
graph.add_node(node)

print(f"Before: {graph.get_node('player-001').properties}")

# 定义工具执行器
def graph_modify_node(graph: ContentGraph, node_id: str, property_changes: dict) -> dict:
    """修改节点属性"""
    print(f"graph_modify_node called: node_id={node_id}, property_changes={property_changes}")
    try:
        node = graph.get_node(node_id)
        if not node:
            print(f"Node not found: {node_id}")
            return {"success": False, "error": f"Node {node_id} not found"}
        
        # 应用属性修改
        for prop, change in property_changes.items():
            print(f"Modifying {prop}: {change}")
            if prop in node.properties or True:  # 允许添加新属性
                new_val = change.get("new", node.properties.get(prop))
                print(f"  {prop}: {node.properties.get(prop)} -> {new_val}")
                node.properties[prop] = new_val
        
        print(f"After modification: {node.properties}")
        return {"success": True, "node_id": node_id, "changes": property_changes}
    except Exception as e:
        print(f"Exception: {e}")
        return {"success": False, "error": str(e)}

# 注册工具
registry = ToolRegistry()
registry.register_tool(
    name="graph_modify_node",
    description="Modify node properties in content graph",
    tool_type=ToolType.CUSTOM,
    category=ToolCategory.DATA_MANIPULATION,
    parameters=[
        ToolParameter("graph", "object", "Content graph", required=True),
        ToolParameter("node_id", "string", "Node ID to modify", required=True),
        ToolParameter("property_changes", "object", "Property changes", required=True)
    ],
    executor=graph_modify_node,
    safe_mode=False
)

# 执行工具
print("\nExecuting tool...")
result = registry.execute_tool("graph_modify_node", {
    "graph": graph,
    "node_id": "player-001",
    "property_changes": {"health": {"old": 100, "new": 150}}
})

print(f"\nResult: {result}")
print(f"After: {graph.get_node('player-001').properties}")

if graph.get_node("player-001").properties.get("health") == 150:
    print("\n✓ Test PASSED: Graph was modified correctly")
else:
    print("\n✗ Test FAILED: Graph was not modified")