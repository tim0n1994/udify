"""
Tests for Planning Engine

测试覆盖：
1. PlanState 的创建、拷贝和应用动作
2. Intent 和 PlanContext
3. ActionSpace 的动作生成
4. ValueFunction 评估
5. MCTSNode 和 MCTSTree
6. Planner 集成测试
"""

import pytest

from udify.core.planning import (
    ActionSpace,
    MCTSConfig,
    MCTSNode,
    MCTSTree,
    PlanResult,
    PlanState,
    Planner,
)
from udify.core.planning.state import Intent, PlanContext
from udify.core.planning.value_function import HeuristicValueFunction
from udify.models.content_graph import (
    ContentEdge,
    ContentGraph,
    ContentNode,
    EdgeType,
    MediaType,
    NodeType,
)
from udify.models.cdl_patch import (
    OpType,
    PatchOperation,
    create_add_node_op,
    create_modify_property_op,
)


class TestIntent:
    """Intent 测试"""

    def test_create_intent(self):
        """测试创建意图"""
        intent = Intent(
            description="增加游戏难度",
            target_media_type="game",
            priority_nodes=["boss_1"],
            constraints=["不要修改玩家属性"],
        )
        assert intent.description == "增加游戏难度"
        assert intent.target_media_type == "game"
        assert "boss_1" in intent.priority_nodes

    def test_intent_serialization(self):
        """测试意图序列化"""
        intent = Intent(description="Test", style_hints={"theme": "dark"})
        data = intent.to_dict()
        assert data["description"] == "Test"
        assert data["style_hints"]["theme"] == "dark"


class TestPlanContext:
    """PlanContext 测试"""

    def test_default_context(self):
        """测试默认上下文"""
        ctx = PlanContext()
        assert ctx.max_operations == 50
        assert ctx.max_depth == 10
        assert ctx.risk_tolerance == 0.5
        assert ctx.preservative_bias == 0.7

    def test_custom_context(self):
        """测试自定义上下文"""
        ctx = PlanContext(max_operations=20, risk_tolerance=0.2, preservative_bias=0.9)
        assert ctx.max_operations == 20
        assert ctx.risk_tolerance == 0.2


class TestPlanState:
    """PlanState 测试"""

    @pytest.fixture
    def sample_graph(self):
        """创建示例图"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        graph.add_edge(ContentEdge(source="n1", target="n2", type=EdgeType.DEPENDS_ON))
        return graph

    def test_create_state(self, sample_graph):
        """测试创建状态"""
        intent = Intent(description="Test intent")
        context = PlanContext()
        state = PlanState(graph=sample_graph, intent=intent, context=context)
        assert state.depth == 0
        assert len(state.action_history) == 0
        assert state._cached_value is None

    def test_state_copy(self, sample_graph):
        """测试状态拷贝"""
        intent = Intent(description="Test")
        state = PlanState(graph=sample_graph, intent=intent, context=PlanContext())
        copied = state.copy()
        assert copied.graph is not state.graph
        assert len(copied.graph.nodes) == len(state.graph.nodes)

    def test_apply_action(self, sample_graph):
        """测试应用动作"""
        state = PlanState(
            graph=sample_graph,
            intent=Intent(description="Test"),
            context=PlanContext(),
        )
        action = create_modify_property_op("n1", "health", 100)
        state.apply_action(action)
        assert state.depth == 1
        assert len(state.action_history) == 1
        assert state.graph.get_node("n1").properties["health"] == 100

    def test_is_terminal(self, sample_graph):
        """测试终止状态判断"""
        state = PlanState(
            graph=sample_graph,
            intent=Intent(description="Test"),
            context=PlanContext(max_depth=3),
        )
        assert not state.is_terminal()
        state.depth = 3
        assert state.is_terminal()

    def test_state_hash(self, sample_graph):
        """测试状态哈希"""
        state = PlanState(
            graph=sample_graph,
            intent=Intent(description="Test"),
            context=PlanContext(),
        )
        hash1 = state.get_hash()
        state.apply_action(create_modify_property_op("n1", "health", 100))
        hash2 = state.get_hash()
        assert hash1 != hash2


class TestActionSpace:
    """ActionSpace 测试"""

    @pytest.fixture
    def sample_state(self):
        """创建示例状态"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        return PlanState(
            graph=graph,
            intent=Intent(description="add new characters"),
            context=PlanContext(),
        )

    def test_generate_actions(self, sample_state):
        """测试动作生成"""
        action_space = ActionSpace(max_candidates=10)
        actions = action_space.generate_actions(sample_state)
        assert len(actions) > 0
        assert len(actions) <= 10

    def test_action_types(self, sample_state):
        """测试生成的动作类型"""
        action_space = ActionSpace(max_candidates=20)
        actions = action_space.generate_actions(sample_state)
        assert any(op.op_type.name == "ADD_NODE" for op in actions)

    def test_intent_driven_actions(self):
        """测试意图驱动的动作生成"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        state = PlanState(
            graph=graph,
            intent=Intent(description="remove unnecessary items"),
            context=PlanContext(),
        )
        action_space = ActionSpace(max_candidates=20)
        actions = action_space.generate_actions(state)
        assert any("REMOVE" in op.op_type.name for op in actions)

    def test_modify_actions(self):
        """测试修改动作生成"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero", properties={"difficulty": "normal"}))
        state = PlanState(
            graph=graph,
            intent=Intent(description="increase difficulty"),
            context=PlanContext(),
        )
        action_space = ActionSpace(max_candidates=20)
        actions = action_space.generate_actions(state)
        modify_actions = [op for op in actions if op.op_type.name == "MODIFY_PROPERTY"]
        assert len(modify_actions) > 0


class TestValueFunction:
    """ValueFunction 测试"""

    @pytest.fixture
    def sample_state(self):
        """创建示例状态"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        graph.add_edge(ContentEdge(source="n1", target="n2", type=EdgeType.DEPENDS_ON))
        return PlanState(
            graph=graph,
            intent=Intent(description="Test intent"),
            context=PlanContext(),
        )

    def test_heuristic_evaluation(self, sample_state):
        """测试启发式评估"""
        vf = HeuristicValueFunction()
        value = vf.evaluate(sample_state)
        assert -1.0 <= value <= 1.0

    def test_evaluation_caching(self, sample_state):
        """测试评估缓存"""
        vf = HeuristicValueFunction()
        value1 = vf.evaluate(sample_state)
        value2 = vf.evaluate(sample_state)
        assert value1 == value2
        assert sample_state._cached_value == value1

    def test_terminal_good(self, sample_state):
        """测试终止状态判断"""
        vf = HeuristicValueFunction()
        assert not vf.is_terminal_good(sample_state)

    def test_structure_evaluation(self):
        """测试结构完整性评估"""
        graph = ContentGraph(media_type=MediaType.GAME)
        for i in range(10):
            graph.add_node(ContentNode(id=f"n{i}", type=NodeType.CHARACTER, name=f"NPC{i}"))
        state = PlanState(
            graph=graph,
            intent=Intent(description="Test"),
            context=PlanContext(),
        )
        vf = HeuristicValueFunction()
        value = vf.evaluate(state)
        assert value < 0.8

    def test_preservative_evaluation(self):
        """测试保守性评估"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        state = PlanState(
            graph=graph,
            intent=Intent(description="Test"),
            context=PlanContext(preservative_bias=0.9),
        )
        state.action_history.append(PatchOperation(OpType.REMOVE_NODE, "n1"))
        vf = HeuristicValueFunction()
        value = vf.evaluate(state)
        assert value < 1.0


class TestMCTSNode:
    """MCTSNode 测试"""

    @pytest.fixture
    def root_state(self):
        """创建根状态"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        return PlanState(
            graph=graph,
            intent=Intent(description="Test"),
            context=PlanContext(),
        )

    def test_node_creation(self, root_state):
        """测试节点创建"""
        node = MCTSNode(state=root_state)
        assert node.visit_count == 0
        assert node.value_sum == 0.0
        assert not node.is_expanded
        assert node.parent is None

    def test_node_update(self, root_state):
        """测试节点更新"""
        node = MCTSNode(state=root_state)
        node.update(0.5)
        assert node.visit_count == 1
        assert node.value_sum == 0.5

    def test_best_child(self, root_state):
        """测试选择最佳子节点"""
        root = MCTSNode(state=root_state)
        root.visit_count = 1000
        
        # 创建子节点
        child1 = MCTSNode(
            state=root_state.copy(), parent=root,
            action=create_add_node_op("c1", NodeType.CHARACTER, "A"),
        )
        child1.visit_count = 500
        child1.value_sum = 450.0  # avg = 0.9
        
        child2 = MCTSNode(
            state=root_state.copy(), parent=root,
            action=create_add_node_op("c2", NodeType.CHARACTER, "B"),
        )
        child2.visit_count = 400
        child2.value_sum = 120.0  # avg = 0.3
        
        root.children = [child1, child2]
        
        # child1 有更高的平均价值且已被充分探索，应该被选中
        best = root.best_child(exploration_constant=1.414)
        assert best == child1

    def test_get_path(self, root_state):
        """测试获取路径"""
        root = MCTSNode(state=root_state)
        action1 = create_add_node_op("c1", NodeType.CHARACTER, "A")
        child1 = MCTSNode(state=root_state.copy(), parent=root, action=action1)
        action2 = create_modify_property_op("c1", "hp", 100)
        child2 = MCTSNode(state=root_state.copy(), parent=child1, action=action2)
        path = child2.get_path()
        assert len(path) == 2
        assert path[0] == action1
        assert path[1] == action2


class TestMCTSTree:
    """MCTSTree 测试"""

    @pytest.fixture
    def simple_tree(self):
        """创建简单 MCTS 树"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        initial_state = PlanState(
            graph=graph,
            intent=Intent(description="add characters"),
            context=PlanContext(max_depth=3),
        )
        config = MCTSConfig(num_iterations=10, max_depth=3)
        action_space = ActionSpace(max_candidates=5)
        value_function = HeuristicValueFunction()
        tree = MCTSTree(config, action_space, value_function)
        return tree, initial_state

    def test_search(self, simple_tree):
        """测试搜索"""
        tree, initial_state = simple_tree
        best_node = tree.search(initial_state)
        assert best_node is not None
        assert tree.root is not None
        assert tree.root.visit_count > 0

    def test_tree_stats(self, simple_tree):
        """测试树统计信息"""
        tree, initial_state = simple_tree
        tree.search(initial_state)
        stats = tree.get_tree_stats()
        assert stats["nodes"] > 0
        assert stats["root_visits"] > 0

    def test_get_best_path(self, simple_tree):
        """测试获取最佳路径"""
        tree, initial_state = simple_tree
        tree.search(initial_state)
        path = tree.get_best_path()
        assert isinstance(path, list)


class TestPlanner:
    """Planner 集成测试"""

    @pytest.fixture
    def sample_graph(self):
        """创建示例图"""
        graph = ContentGraph(media_type=MediaType.GAME)
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Hero"))
        graph.add_node(ContentNode(id="n2", type=NodeType.ITEM, name="Sword"))
        return graph

    def test_plan(self, sample_graph):
        """测试基本规划"""
        planner = Planner(
            config=MCTSConfig(num_iterations=10, max_depth=3),
            action_space=ActionSpace(max_candidates=5),
        )
        result = planner.plan(sample_graph, intent="add new content")
        assert isinstance(result, PlanResult)
        assert result.estimated_value >= -1.0
        assert result.estimated_value <= 1.0

    def test_plan_with_structured_intent(self, sample_graph):
        """测试使用结构化意图规划"""
        planner = Planner(
            config=MCTSConfig(num_iterations=10, max_depth=3),
            action_space=ActionSpace(max_candidates=5),
        )
        intent = Intent(
            description="increase difficulty",
            priority_nodes=["n1"],
        )
        result = planner.plan_with_intent(sample_graph, intent=intent)
        assert isinstance(result, PlanResult)

    def test_plan_result_to_patch(self, sample_graph):
        """测试规划结果转换为 patch"""
        planner = Planner(
            config=MCTSConfig(num_iterations=10, max_depth=3),
            action_space=ActionSpace(max_candidates=5),
        )
        result = planner.plan(sample_graph, intent="add new content")
        patch = result.to_patch()
        assert patch.intent is not None
        assert patch.author == "planner"

    def test_plan_result_summary(self, sample_graph):
        """测试规划结果摘要"""
        planner = Planner(
            config=MCTSConfig(num_iterations=5, max_depth=2),
            action_space=ActionSpace(max_candidates=3),
        )
        result = planner.plan(sample_graph, intent="test")
        summary = result.summary()
        assert "PlanResult" in summary
        assert "Estimated Value" in summary
