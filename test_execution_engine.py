#!/usr/bin/env python3
"""
Test script for the Execution Engine.

This script demonstrates the complete execution pipeline:
1. Create a sample ContentGraph
2. Create a CDLPatch with operations
3. Execute the patch using the Execution Engine
4. Verify the results
"""

import sys
import json
from pathlib import Path

# Add the project to the path
sys.path.insert(0, str(Path(__file__).parent))

from udify.models.content_graph import ContentGraph, ContentNode, ContentEdge, NodeType
from udify.models.cdl_patch import CDLPatch, PatchOperation, OpType
from udify.core.execution.executor import PatchExecutor
from udify.core.execution.tool_registry import ToolRegistry, ToolType, ToolCategory, ToolParameter


def create_sample_graph() -> ContentGraph:
    """Create a sample game content graph for testing."""
    from udify.models.content_graph import ContentMetadata, GameEngine
    
    metadata = ContentMetadata(
        title="Test Game",
        engine=GameEngine.UNITY,
        version="1.0"
    )
    
    graph = ContentGraph(
        media_type="game",
        metadata=metadata
    )
    
    # Add player node
    player_node = ContentNode(
        id="player-001",
        type=NodeType.CHARACTER,
        name="Player",
        properties={
            "health": 100,
            "damage": 10,
            "speed": 5.0
        }
    )
    graph.add_node(player_node)
    
    # Add enemy node
    enemy_node = ContentNode(
        id="enemy-001",
        type=NodeType.CHARACTER,
        name="Enemy",
        properties={
            "health": 50,
            "damage": 5,
            "speed": 3.0
        }
    )
    graph.add_node(enemy_node)
    
    # Add weapon node
    weapon_node = ContentNode(
        id="weapon-001",
        type=NodeType.ITEM,
        name="Sword",
        properties={
            "damage": 15,
            "durability": 100
        }
    )
    graph.add_node(weapon_node)
    
    # Add relationships
    graph.add_edge(ContentEdge(
        source="player-001",
        target="weapon-001",
        type="equipped",
        weight=1.0
    ))
    
    graph.add_edge(ContentEdge(
        source="enemy-001",
        target="player-001",
        type="hostile_to",
        weight=0.8
    ))
    
    return graph


def create_difficulty_patch() -> CDLPatch:
    """Create a patch that increases game difficulty."""
    patch = CDLPatch(
        intent="Make the game harder like Dark Souls"
    )
    
    # Increase player health (modify property)
    patch.add_operation(
        op_type=OpType.MODIFY_PROPERTY,
        target_id="player-001",
        payload={
            "property_changes": {
                "health": {"old": 100, "new": 150},
                "damage": {"old": 10, "new": 12}
            }
        }
    )
    
    # Increase enemy health and damage
    patch.add_operation(
        op_type=OpType.MODIFY_PROPERTY,
        target_id="enemy-001",
        payload={
            "property_changes": {
                "health": {"old": 50, "new": 100},
                "damage": {"old": 5, "new": 15},
                "speed": {"old": 3.0, "new": 4.0}
            }
        }
    )
    
    # Add a new challenging enemy
    patch.add_operation(
        op_type=OpType.ADD_NODE,
        payload={
            "node": {
                "id": "enemy-002",
                "type": NodeType.CHARACTER,
                "name": "Mini-Boss",
                "properties": {
                    "health": 200,
                    "damage": 25,
                    "speed": 3.5,
                    "special_attack": "fire_breath"
                }
            }
        }
    )
    
    # Add relationship between new enemy and player
    patch.add_operation(
        op_type=OpType.ADD_EDGE,
        payload={
            "edge": {
                "source": "enemy-002",
                "target": "player-001",
                "type": "hostile_to",
                "weight": 0.9
            }
        }
    )
    
    return patch


def create_custom_tools(registry: ToolRegistry):
    """Register custom tools for graph manipulation."""
    
    def graph_add_node(graph: ContentGraph, node_data: dict) -> dict:
        """Add a node to the content graph."""
        try:
            node = ContentNode(
                id=node_data["id"],
                type=NodeType(node_data["type"]),
                name=node_data["name"],
                properties=node_data.get("properties", {}),
                confidence=node_data.get("confidence", 0.8)
            )
            graph.add_node(node)
            return {"success": True, "node_id": node.id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def graph_remove_node(graph: ContentGraph, node_id: str) -> dict:
        """Remove a node from the content graph."""
        try:
            if graph.remove_node(node_id):
                return {"success": True, "node_id": node_id}
            else:
                return {"success": False, "error": f"Node {node_id} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def graph_modify_node(graph: ContentGraph, node_id: str, property_changes: dict) -> dict:
        """Modify node properties."""
        try:
            node = graph.get_node(node_id)
            if not node:
                return {"success": False, "error": f"Node {node_id} not found"}
            
            for prop, change in property_changes.items():
                if prop in node.properties:
                    node.properties[prop] = change.get("new", node.properties[prop])
            
            return {"success": True, "node_id": node_id, "changes": property_changes}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def graph_add_edge(graph: ContentGraph, edge_data: dict) -> dict:
        """Add an edge to the content graph."""
        try:
            edge = ContentEdge(
                id=edge_data["id"],
                source=edge_data["source"],
                target=edge_data["target"],
                type=edge_data["type"],
                weight=edge_data.get("weight", 1.0)
            )
            graph.add_edge(edge)
            return {"success": True, "edge_id": edge.id}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def graph_remove_edge(graph: ContentGraph, edge_id: str) -> dict:
        """Remove an edge from the content graph."""
        try:
            if graph.remove_edge(edge_id):
                return {"success": True, "edge_id": edge_id}
            else:
                return {"success": False, "error": f"Edge {edge_id} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def graph_modify_edge(graph: ContentGraph, edge_id: str, property_changes: dict) -> dict:
        """Modify edge properties."""
        try:
            edge = graph.get_edge(edge_id)
            if not edge:
                return {"success": False, "error": f"Edge {edge_id} not found"}
            
            for prop, change in property_changes.items():
                if hasattr(edge, prop):
                    setattr(edge, prop, change.get("new", getattr(edge, prop)))
            
            return {"success": True, "edge_id": edge_id, "changes": property_changes}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # Register graph manipulation tools
    registry.register_tool(
        name="graph_add_node",
        description="Add a node to the content graph",
        tool_type=ToolType.CUSTOM,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("graph", "object", "Content graph", required=True),
            ToolParameter("node_data", "object", "Node data", required=True)
        ],
        executor=graph_add_node,
        safe_mode=False
    )
    
    registry.register_tool(
        name="graph_remove_node",
        description="Remove a node from the content graph",
        tool_type=ToolType.CUSTOM,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("graph", "object", "Content graph", required=True),
            ToolParameter("node_id", "string", "Node ID to remove", required=True)
        ],
        executor=graph_remove_node,
        safe_mode=False
    )
    
    registry.register_tool(
        name="graph_modify_node",
        description="Modify node properties",
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
    
    registry.register_tool(
        name="graph_add_edge",
        description="Add an edge to the content graph",
        tool_type=ToolType.CUSTOM,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("graph", "object", "Content graph", required=True),
            ToolParameter("edge_data", "object", "Edge data", required=True)
        ],
        executor=graph_add_edge,
        safe_mode=False
    )
    
    registry.register_tool(
        name="graph_remove_edge",
        description="Remove an edge from the content graph",
        tool_type=ToolType.CUSTOM,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("graph", "object", "Content graph", required=True),
            ToolParameter("edge_id", "string", "Edge ID to remove", required=True)
        ],
        executor=graph_remove_edge,
        safe_mode=False
    )
    
    registry.register_tool(
        name="graph_modify_edge",
        description="Modify edge properties",
        tool_type=ToolType.CUSTOM,
        category=ToolCategory.DATA_MANIPULATION,
        parameters=[
            ToolParameter("graph", "object", "Content graph", required=True),
            ToolParameter("edge_id", "string", "Edge ID to modify", required=True),
            ToolParameter("property_changes", "object", "Property changes", required=True)
        ],
        executor=graph_modify_edge,
        safe_mode=False
    )


def main():
    """Run the execution engine test."""
    print("=" * 80)
    print("Udify Execution Engine Test")
    print("=" * 80)
    
    # Create sample graph
    print("\n1. Creating sample content graph...")
    graph = create_sample_graph()
    print(f"   Created graph with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
    
    # Create patch
    print("\n2. Creating difficulty patch...")
    patch = create_difficulty_patch()
    print(f"   Created patch with {len(patch.operations)} operations")
    
    # Create executor and register tools
    print("\n3. Setting up execution engine...")
    executor = PatchExecutor()
    create_custom_tools(executor.tool_registry)
    print(f"   Registered {len(executor.tool_registry)} tools")
    
    # Execute patch
    print("\n4. Executing patch...")
    result = executor.execute_patch(patch, graph, validate=True)
    
    # Display results
    print("\n5. Execution Results:")
    print(f"   Success: {result.success}")
    print(f"   Execution time: {result.execution_time:.3f}s")
    print(f"   Operations executed: {len(result.executed_operations)}")
    print(f"   Operations failed: {len(result.failed_operations)}")
    
    if result.errors:
        print("\n   Errors:")
        for error in result.errors:
            print(f"     - {error}")
    
    if result.warnings:
        print("\n   Warnings:")
        for warning in result.warnings:
            print(f"     - {warning}")
    
    # Display final graph state
    print("\n6. Final Graph State:")
    print(f"   Nodes: {len(graph.nodes)}")
    for node in graph.nodes:
        print(f"     - {node.name} ({node.type.value}): {node.properties}")
    
    print(f"\n   Edges: {len(graph.edges)}")
    for edge in graph.edges:
        print(f"     - {edge.source} --{edge.type}--> {edge.target}")
    
    # Verify changes
    print("\n7. Verification:")
    
    # Check player health increased
    player = graph.get_node("player-001")
    if player and player.properties.get("health") == 150:
        print("   ✓ Player health increased to 150")
    else:
        print("   ✗ Player health not updated correctly")
    
    # Check enemy stats increased
    enemy = graph.get_node("enemy-001")
    if enemy and enemy.properties.get("health") == 100:
        print("   ✓ Enemy health increased to 100")
    else:
        print("   ✗ Enemy health not updated correctly")
    
    # Check new enemy added
    mini_boss = graph.get_node("enemy-002")
    if mini_boss:
        print("   ✓ Mini-boss added to graph")
    else:
        print("   ✗ Mini-boss not found")
    
    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())