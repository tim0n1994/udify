#!/usr/bin/env python3
"""
简化的执行引擎测试脚本 - 修正版
"""

import sys
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

from udify.models.content_graph import ContentGraph, ContentNode, NodeType, ContentMetadata, GameEngine
from udify.models.cdl_patch import CDLPatch, PatchOperation, OpType
from udify.core.execution.executor import PatchExecutor
from udify.core.execution.tool_registry import ToolRegistry, ToolType, ToolCategory, ToolParameter


def create_simple_graph() -> ContentGraph:
    """创建简单的测试图"""
    metadata = ContentMetadata(
        title="Test Game",
        engine=GameEngine.UNITY,
        version="1.0"
    )
    
    graph = ContentGraph(
        media_type="game",
        metadata=metadata
    )
    
    # 添加节点
    player = ContentNode(
        id="player-001",
        type=NodeType.CHARACTER,
        name="Player",
        properties={"health": 100, "damage": 10}
    )
    graph.add_node(player)
    
    enemy = ContentNode(
        id="enemy-001", 
        type=NodeType.CHARACTER,
        name="Enemy",
        properties={"health": 50, "damage": 5}
    )
    graph.add_node(enemy)
    
    return graph


def create_test_patch() -> CDLPatch:
    """创建测试patch"""
    patch = CDLPatch(intent="Test difficulty increase")
    
    # 创建操作1: 修改玩家属性
    op1 = PatchOperation(
        op_type=OpType.MODIFY_PROPERTY,
        target_id="player-001",
        payload={
            "property_changes": {
                "health": {"old": 100, "new": 150}
            }
        }
    )
    patch.add_operation(op1)
    
    # 创建操作2: 修改敌人属性
    op2 = PatchOperation(
        op_type=OpType.MODIFY_PROPERTY,
        target_id="enemy-001",
        payload={
            "property_changes": {
                "health": {"old": 50, "new": 100}
            }
        }
    )
    patch.add_operation(op2)
    
    return patch


def register_graph_tools(registry: ToolRegistry):
    """注册图操作工具（与scheduler.py期望的一致）"""
    
    def graph_modify_node(graph: ContentGraph, node_id: str, property_changes: dict) -> dict:
        """修改节点属性"""
        try:
            node = graph.get_node(node_id)
            if not node:
                return {"success": False, "error": f"Node {node_id} not found"}
            
            # 应用属性修改
            for prop, change in property_changes.items():
                if prop in node.properties or True:  # 允许添加新属性
                    node.properties[prop] = change.get("new", node.properties.get(prop))
            
            return {"success": True, "node_id": node_id, "changes": property_changes}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # 注册工具 - 工具名必须与scheduler.py中的_convert_to_tool_call返回的一致
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


def main():
    """主测试函数"""
    print("=" * 60)
    print("Udify Execution Engine - Simple Test (Fixed)")
    print("=" * 60)
    
    # 1. 创建图
    print("\n1. Creating test graph...")
    graph = create_simple_graph()
    print(f"   Created graph: {len(graph.nodes)} nodes")
    
    # 显示初始状态
    print("\n   Initial state:")
    for node in graph.nodes:
        print(f"     - {node.name}: {node.properties}")
    
    # 2. 创建patch
    print("\n2. Creating test patch...")
    patch = create_test_patch()
    print(f"   Created patch with {len(patch.operations)} operations")
    
    # 3. 设置执行器
    print("\n3. Setting up executor...")
    executor = PatchExecutor()
    
    # 注册工具
    register_graph_tools(executor.tool_registry)
    print(f"   Registered {len(executor.tool_registry)} tools")
    
    # 4. 执行patch
    print("\n4. Executing patch...")
    try:
        result = executor.execute_patch(patch, graph, validate=True)
        
        print(f"\n5. Results:")
        print(f"   Success: {result.success}")
        print(f"   Execution time: {result.execution_time:.3f}s")
        print(f"   Executed: {len(result.executed_operations)}")
        print(f"   Failed: {len(result.failed_operations)}")
        
        if result.errors:
            print("\n   Errors:")
            for error in result.errors:
                print(f"     - {error}")
    except Exception as e:
        print(f"\n   ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # 5. 显示最终状态
    print("\n6. Final state:")
    for node in graph.nodes:
        print(f"     - {node.name}: {node.properties}")
    
    # 6. 验证
    print("\n7. Verification:")
    player = graph.get_node("player-001")
    if player and player.properties.get("health") == 150:
        print("   ✓ Player health updated to 150")
    else:
        print(f"   ✗ Player health not updated correctly: {player.properties if player else 'Node not found'}")
    
    enemy = graph.get_node("enemy-001")
    if enemy and enemy.properties.get("health") == 100:
        print("   ✓ Enemy health updated to 100")
    else:
        print(f"   ✗ Enemy health not updated correctly: {enemy.properties if enemy else 'Node not found'}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())