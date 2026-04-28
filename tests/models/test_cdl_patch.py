"""
Tests for CDL Patch/Diff System

测试覆盖：
1. PatchOperation 的创建和不可变性
2. CDLPatch 的序列化和反序列化
3. PatchValidator 的冲突检测
4. PatchApplicator 的应用和回滚
5. GraphDiffer 的差异计算
6. 便捷函数
"""

import pytest

from udify.models.content_graph import (
    ContentAsset,
    ContentEdge,
    ContentGraph,
    ContentNode,
    ContentSemantics,
    EdgeType,
    GameEngine,
    MediaType,
    NodeType,
)
from udify.models.cdl_patch import (
    CDLPatch,
    ConflictType,
    GraphDiffer,
    OpType,
    PatchApplicator,
    PatchConflict,
    PatchOperation,
    PatchValidator,
    create_add_asset_op,
    create_add_edge_op,
    create_add_node_op,
    create_modify_property_op,
    create_remove_asset_op,
    create_remove_edge_op,
    create_remove_node_op,
)


class TestPatchOperation:
    """PatchOperation 测试"""
    
    def test_create_operation(self):
        """测试创建操作"""
        op = PatchOperation(
            op_type=OpType.ADD_NODE,
            target_id="node_1",
            payload={"name": "Test Node"},
        )
        
        assert op.op_type == OpType.ADD_NODE
        assert op.target_id == "node_1"
        assert op.payload["name"] == "Test Node"
    
    def test_operation_immutability(self):
        """测试操作不可变性"""
        op = PatchOperation(
            op_type=OpType.ADD_NODE,
            target_id="node_1",
            payload={"name": "Test"},
        )
        
        # frozen=True 应该阻止修改
        with pytest.raises(AttributeError):
            op.target_id = "node_2"
    
    def test_operation_hashable(self):
        """测试操作可作为字典键"""
        op1 = PatchOperation(OpType.ADD_NODE, "node_1")
        op2 = PatchOperation(OpType.ADD_NODE, "node_1")
        
        # 相同内容应该相等
        assert op1 == op2
        assert hash(op1) == hash(op2)


class TestCDLPatch:
    """CDLPatch 测试"""
    
    def test_create_empty_patch(self):
        """测试创建空 patch"""
        patch = CDLPatch(intent="Test intent")
        
        assert patch.is_empty()
        assert patch.intent == "Test intent"
        assert not patch.has_conflicts()
    
    def test_add_operations(self):
        """测试添加操作"""
        patch = CDLPatch()
        
        op1 = create_add_node_op("node_1", NodeType.CHARACTER, "Hero")
        op2 = create_modify_property_op("node_1", "health", 100)
        
        patch.add_operation(op1).add_operation(op2)
        
        assert len(patch.operations) == 2
        assert not patch.is_empty()
    
    def test_patch_summary(self):
        """测试 patch 摘要"""
        patch = CDLPatch(intent="Add characters")
        patch.add_operation(create_add_node_op("n1", NodeType.CHARACTER, "A"))
        patch.add_operation(create_add_node_op("n2", NodeType.CHARACTER, "B"))
        patch.add_operation(create_modify_property_op("n1", "hp", 100))
        
        summary = patch.summary()
        assert "CDLPatch" in summary
        assert "ADD_NODE: 2" in summary
        assert "MODIFY_PROPERTY: 1" in summary
    
    def test_serialization_roundtrip(self):
        """测试序列化往返"""
        original = CDLPatch(
            intent="Test serialization",
            author="test_user",
        )
        original.add_operation(create_add_node_op("n1", NodeType.ITEM, "Sword"))
        original.add_operation(create_modify_property_op("n1", "damage", 50))
        
        data = original.to_dict()
        restored = CDLPatch.from_dict(data)
        
        assert restored.intent == original.intent
        assert restored.author == original.author
        assert len(restored.operations) == len(original.operations)
        assert restored.operations[0].op_type == OpType.ADD_NODE
        assert restored.operations[1].op_type == OpType.MODIFY_PROPERTY
    
    def test_patch_with_conflicts(self):
        """测试带冲突的 patch"""
        patch = CDLPatch()
        patch.conflicts.append(PatchConflict(
            conflict_type=ConflictType.SAME_PROPERTY_MODIFY,
            operation_a=None,
            operation_b=None,
            description="Test conflict",
            severity="error",
        ))
        
        assert patch.has_conflicts()


class TestPatchValidator:
    """PatchValidator 测试"""
    
    @pytest.fixture
    def sample_graph(self):
        """创建示例图"""
        graph = ContentGraph(media_type=MediaType.GAME)
        
        # 添加节点
        node1 = ContentNode(id="node_1", type=NodeType.CHARACTER, name="Hero")
        node2 = ContentNode(id="node_2", type=NodeType.ITEM, name="Sword")
        graph.add_node(node1)
        graph.add_node(node2)
        
        # 添加边
        edge = ContentEdge(source="node_1", target="node_2", type=EdgeType.DEPENDS_ON)
        graph.add_edge(edge)
        
        return graph
    
    def test_valid_patch(self, sample_graph):
        """测试有效 patch"""
        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("node_1", "health", 100))
        patch.add_operation(create_add_node_op("node_3", NodeType.CHARACTER, "Mage"))
        
        validator = PatchValidator()
        conflicts = validator.validate(patch, sample_graph)
        
        assert len(conflicts) == 0
    
    def test_duplicate_node_id(self, sample_graph):
        """测试重复节点 ID"""
        patch = CDLPatch()
        patch.add_operation(create_add_node_op("node_1", NodeType.CHARACTER, "Duplicate"))
        
        validator = PatchValidator()
        conflicts = validator.validate(patch, sample_graph)
        
        assert any(c.conflict_type == ConflictType.DUPLICATE_NODE_ID for c in conflicts)
    
    def test_remove_nonexistent_node(self, sample_graph):
        """测试删除不存在的节点"""
        patch = CDLPatch()
        patch.add_operation(create_remove_node_op("nonexistent"))
        
        validator = PatchValidator()
        conflicts = validator.validate(patch, sample_graph)
        
        assert any(c.conflict_type == ConflictType.SAME_NODE_REMOVE_VS_MODIFY for c in conflicts)
    
    def test_modify_removed_node(self, sample_graph):
        """测试修改已删除的节点"""
        patch = CDLPatch()
        patch.add_operation(create_remove_node_op("node_1"))
        patch.add_operation(create_modify_property_op("node_1", "health", 100))
        
        validator = PatchValidator()
        conflicts = validator.validate(patch, sample_graph)
        
        assert any(
            c.conflict_type == ConflictType.SAME_NODE_REMOVE_VS_MODIFY 
            and "removed node" in c.description
            for c in conflicts
        )
    
    def test_edge_to_removed_node(self, sample_graph):
        """测试指向已删除节点的边"""
        patch = CDLPatch()
        patch.add_operation(create_remove_node_op("node_2"))
        patch.add_operation(create_add_edge_op("node_1", "node_2"))
        
        validator = PatchValidator()
        conflicts = validator.validate(patch, sample_graph)
        
        assert any(c.conflict_type == ConflictType.EDGE_TARGET_REMOVED for c in conflicts)


class TestPatchApplicator:
    """PatchApplicator 测试"""
    
    @pytest.fixture
    def sample_graph(self):
        """创建示例图"""
        graph = ContentGraph(media_type=MediaType.GAME)
        
        node1 = ContentNode(id="node_1", type=NodeType.CHARACTER, name="Hero")
        node2 = ContentNode(id="node_2", type=NodeType.ITEM, name="Sword")
        graph.add_node(node1)
        graph.add_node(node2)
        
        edge = ContentEdge(source="node_1", target="node_2", type=EdgeType.DEPENDS_ON)
        graph.add_edge(edge)
        
        return graph
    
    def test_apply_add_node(self, sample_graph):
        """测试应用添加节点"""
        patch = CDLPatch()
        patch.add_operation(create_add_node_op("node_3", NodeType.CHARACTER, "Mage"))
        
        applicator = PatchApplicator()
        success, conflicts = applicator.apply(patch, sample_graph)
        
        assert success
        assert len(conflicts) == 0
        assert sample_graph.get_node("node_3") is not None
        assert sample_graph.get_node("node_3").name == "Mage"
    
    def test_apply_modify_property(self, sample_graph):
        """测试应用修改属性"""
        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("node_1", "health", 100))
        
        applicator = PatchApplicator()
        success, _ = applicator.apply(patch, sample_graph)
        
        assert success
        assert sample_graph.get_node("node_1").properties["health"] == 100
    
    def test_apply_remove_node(self, sample_graph):
        """测试应用删除节点"""
        patch = CDLPatch()
        patch.add_operation(create_remove_node_op("node_2"))
        
        applicator = PatchApplicator()
        success, _ = applicator.apply(patch, sample_graph)
        
        assert success
        assert sample_graph.get_node("node_2") is None
        # 相关边也应该被删除
        assert len(sample_graph.edges) == 0
    
    def test_apply_add_edge(self, sample_graph):
        """测试应用添加边"""
        # 先添加一个新节点
        node3 = ContentNode(id="node_3", type=NodeType.CHARACTER, name="Mage")
        sample_graph.add_node(node3)
        
        patch = CDLPatch()
        patch.add_operation(create_add_edge_op("node_1", "node_3", EdgeType.SIMILAR_TO))
        
        applicator = PatchApplicator()
        success, _ = applicator.apply(patch, sample_graph)
        
        assert success
        assert len(sample_graph.edges) == 2
    
    def test_apply_add_asset(self, sample_graph):
        """测试应用添加资源"""
        patch = CDLPatch()
        patch.add_operation(create_add_asset_op("asset_1", "textures/sword.png", "texture", "png"))
        
        applicator = PatchApplicator()
        success, _ = applicator.apply(patch, sample_graph)
        
        assert success
        assert len(sample_graph.assets) == 1
        assert sample_graph.assets[0].path == "textures/sword.png"
    
    def test_rollback(self, sample_graph):
        """测试回滚"""
        original_node_count = len(sample_graph.nodes)
        
        patch = CDLPatch()
        patch.add_operation(create_add_node_op("node_3", NodeType.CHARACTER, "Mage"))
        patch.add_operation(create_modify_property_op("node_1", "health", 100))
        
        applicator = PatchApplicator()
        success, _ = applicator.apply(patch, sample_graph)
        
        assert success
        assert len(sample_graph.nodes) == original_node_count + 1
        assert sample_graph.get_node("node_1").properties.get("health") == 100
        
        # 回滚
        rollback_success = applicator.rollback(patch, sample_graph)
        
        assert rollback_success
        assert len(sample_graph.nodes) == original_node_count
        assert "health" not in sample_graph.get_node("node_1").properties
    
    def test_atomic_failure(self, sample_graph):
        """测试原子性失败（部分操作失败后回滚）"""
        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("node_1", "health", 100))
        patch.add_operation(create_modify_property_op("nonexistent", "health", 100))  # 会失败
        
        applicator = PatchApplicator()
        success, conflicts = applicator.apply(patch, sample_graph, atomic=True)
        
        assert not success
        # 由于原子性，第一个操作也应该被回滚
        assert "health" not in sample_graph.get_node("node_1").properties
    
    def test_non_atomic_partial_apply(self, sample_graph):
        """测试非原子性部分应用"""
        patch = CDLPatch()
        patch.add_operation(create_modify_property_op("node_1", "health", 100))
        patch.add_operation(create_modify_property_op("nonexistent", "health", 100))
        
        applicator = PatchApplicator()
        success, conflicts = applicator.apply(patch, sample_graph, atomic=False)
        
        assert not success
        # 非原子性，第一个操作应该保留
        assert sample_graph.get_node("node_1").properties.get("health") == 100


class TestGraphDiffer:
    """GraphDiffer 测试"""
    
    def test_diff_add_node(self):
        """测试检测新增节点"""
        old_graph = ContentGraph(media_type=MediaType.GAME)
        old_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        
        new_graph = ContentGraph(media_type=MediaType.GAME)
        new_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        new_graph.add_node(ContentNode(id="n2", type=NodeType.CHARACTER, name="Mage"))
        
        differ = GraphDiffer()
        patch = differ.diff(old_graph, new_graph, intent="Add mage")
        
        assert len(patch.operations) == 1
        assert patch.operations[0].op_type == OpType.ADD_NODE
        assert patch.operations[0].payload["node_id"] == "n2"
    
    def test_diff_remove_node(self):
        """测试检测删除节点"""
        old_graph = ContentGraph(media_type=MediaType.GAME)
        old_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        old_graph.add_node(ContentNode(id="n2", type=NodeType.CHARACTER, name="Mage"))
        
        new_graph = ContentGraph(media_type=MediaType.GAME)
        new_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        
        differ = GraphDiffer()
        patch = differ.diff(old_graph, new_graph)
        
        assert len(patch.operations) == 1
        assert patch.operations[0].op_type == OpType.REMOVE_NODE
        assert patch.operations[0].target_id == "n2"
    
    def test_diff_modify_property(self):
        """测试检测属性修改"""
        old_graph = ContentGraph(media_type=MediaType.GAME)
        old_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero", properties={"hp": 100}))
        
        new_graph = ContentGraph(media_type=MediaType.GAME)
        new_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero", properties={"hp": 150}))
        
        differ = GraphDiffer()
        patch = differ.diff(old_graph, new_graph)
        
        assert len(patch.operations) == 1
        assert patch.operations[0].op_type == OpType.MODIFY_PROPERTY
        assert patch.operations[0].payload["key"] == "hp"
        assert patch.operations[0].payload["value"] == 150
    
    def test_diff_add_edge(self):
        """测试检测新增边"""
        old_graph = ContentGraph(media_type=MediaType.GAME)
        old_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        old_graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        
        new_graph = ContentGraph(media_type=MediaType.GAME)
        new_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        new_graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        new_graph.add_edge(ContentEdge(source="n1", target="n2", type=EdgeType.DEPENDS_ON))
        
        differ = GraphDiffer()
        patch = differ.diff(old_graph, new_graph)
        
        assert len(patch.operations) == 1
        assert patch.operations[0].op_type == OpType.ADD_EDGE
    
    def test_diff_complex(self):
        """测试复杂差异"""
        old_graph = ContentGraph(media_type=MediaType.GAME)
        old_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero", properties={"hp": 100}))
        old_graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        old_graph.add_edge(ContentEdge(source="n1", target="n2", type=EdgeType.DEPENDS_ON))
        
        new_graph = ContentGraph(media_type=MediaType.GAME)
        new_graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero", properties={"hp": 150}))
        new_graph.add_node(ContentNode(id="n3", type=NodeType.CHARACTER, name="Mage"))
        new_graph.add_edge(ContentEdge(source="n1", target="n3", type=EdgeType.SIMILAR_TO))
        
        differ = GraphDiffer()
        patch = differ.diff(old_graph, new_graph)
        
        # 应该有：修改属性 + 删除 n2 + 删除边 + 添加 n3 + 添加边
        assert len(patch.operations) == 5
        
        op_types = [op.op_type for op in patch.operations]
        assert OpType.MODIFY_PROPERTY in op_types
        assert OpType.REMOVE_NODE in op_types
        assert OpType.REMOVE_EDGE in op_types
        assert OpType.ADD_NODE in op_types
        assert OpType.ADD_EDGE in op_types


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_create_add_node_op(self):
        """测试创建添加节点操作"""
        op = create_add_node_op("n1", NodeType.CHARACTER, "Hero", {"hp": 100})
        
        assert op.op_type == OpType.ADD_NODE
        assert op.target_id == "n1"
        assert op.payload["node_type"] == "CHARACTER"
        assert op.payload["name"] == "Hero"
        assert op.payload["properties"]["hp"] == 100
    
    def test_create_remove_node_op(self):
        """测试创建删除节点操作"""
        op = create_remove_node_op("n1")
        
        assert op.op_type == OpType.REMOVE_NODE
        assert op.target_id == "n1"
    
    def test_create_modify_property_op(self):
        """测试创建修改属性操作"""
        op = create_modify_property_op("n1", "hp", 200)
        
        assert op.op_type == OpType.MODIFY_PROPERTY
        assert op.payload["key"] == "hp"
        assert op.payload["value"] == 200
    
    def test_create_add_edge_op(self):
        """测试创建添加边操作"""
        op = create_add_edge_op("n1", "n2", EdgeType.SIMILAR_TO, 0.8)
        
        assert op.op_type == OpType.ADD_EDGE
        assert op.payload["source"] == "n1"
        assert op.payload["target"] == "n2"
        assert op.payload["edge_type"] == "SIMILAR_TO"
        assert op.payload["weight"] == 0.8
    
    def test_create_remove_edge_op(self):
        """测试创建删除边操作"""
        op = create_remove_edge_op("n1", "n2", EdgeType.SIMILAR_TO)
        
        assert op.op_type == OpType.REMOVE_EDGE
        assert op.payload["source"] == "n1"
        assert op.payload["target"] == "n2"
    
    def test_create_add_asset_op(self):
        """测试创建添加资源操作"""
        op = create_add_asset_op("a1", "textures/sword.png", "texture", "png", size=1024)
        
        assert op.op_type == OpType.ADD_ASSET
        assert op.payload["path"] == "textures/sword.png"
        assert op.payload["size"] == 1024
    
    def test_create_remove_asset_op(self):
        """测试创建删除资源操作"""
        op = create_remove_asset_op("a1")
        
        assert op.op_type == OpType.REMOVE_ASSET
        assert op.target_id == "a1"
