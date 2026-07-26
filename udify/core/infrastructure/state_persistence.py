"""
Udify State Persistence

会话和图谱的持久化存储。
支持 JSON 格式，便于人工检查和版本控制。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from udify.core.session.session_manager import ModSession, SessionManager, SessionStatus
from udify.models.cdl_patch import CDLPatch
from udify.models.content_graph import (
    ContentEdge,
    ContentGraph,
    ContentNode,
    EdgeType,
    MediaType,
    NodeType,
)


class GraphSerializer:
    """图谱序列化器"""

    @staticmethod
    def to_dict(graph: ContentGraph) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "version": "1.0",
            "media_type": graph.media_type.value if graph.media_type else None,
            "metadata": graph.metadata.to_dict() if graph.metadata else {},
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type.name,
                    "name": n.name,
                    "properties": n.properties,
                    "media_type": n.media_type.value,
                    "source_path": n.source_path,
                    "source_offset": n.source_offset,
                }
                for n in graph.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "type": e.type.value if isinstance(e.type, EdgeType) else str(e.type),
                    "weight": e.weight,
                    "properties": e.properties,
                }
                for e in graph.edges
            ],
            "assets": [
                {
                    "id": a.id,
                    "path": a.path,
                    "type": a.type,
                    "format": a.format,
                    "metadata": a.metadata,
                }
                for a in graph.assets
            ],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ContentGraph:
        """从字典反序列化"""
        graph = ContentGraph(
            media_type=MediaType(data.get("media_type", "unknown")),
        )

        # 添加节点
        for node_data in data.get("nodes", []):
            node = ContentNode(
                id=node_data["id"],
                type=NodeType[node_data.get("type", "RESOURCE")],
                name=node_data.get("name", ""),
                properties=node_data.get("properties", {}),
                media_type=MediaType(node_data.get("media_type", "unknown")),
                source_path=node_data.get("source_path"),
                source_offset=node_data.get("source_offset"),
            )
            graph.add_node(node)

        # 添加边
        for edge_data in data.get("edges", []):
            edge = ContentEdge(
                source=edge_data["source"],
                target=edge_data["target"],
                type=EdgeType(edge_data.get("type", "depends_on")),
                weight=edge_data.get("weight", 1.0),
                properties=edge_data.get("properties", {}),
            )
            graph.add_edge(edge)

        return graph


class SessionSerializer:
    """会话序列化器"""

    @staticmethod
    def to_dict(session: ModSession) -> dict[str, Any]:
        """序列化会话"""
        return {
            "version": "1.0",
            "session_id": session.session_id,
            "user_id": session.user_id,
            "game_id": session.game_id,
            "status": session.status.name,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "intents": session.intents,
            "current_intent": session.current_intent,
            "patches": [p.to_dict() for p in session.patches],
            "checkpoints": [
                {
                    "name": cp.name,
                    "timestamp": cp.timestamp.isoformat(),
                    "graph": GraphSerializer.to_dict(cp.graph_snapshot),
                }
                for cp in session.checkpoints
            ],
            "feedback_history": session.feedback_history,
            "cost_spent": session.cost_spent,
            "llm_calls": session.llm_calls,
            "metadata": session.metadata,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ModSession:
        """反序列化会话"""
        session = ModSession(
            session_id=data["session_id"],
            user_id=data["user_id"],
            game_id=data["game_id"],
            status=SessionStatus[data["status"]],
        )

        session.intents = data.get("intents", [])
        session.current_intent = data.get("current_intent", "")
        session.cost_spent = data.get("cost_spent", 0.0)
        session.llm_calls = data.get("llm_calls", 0)
        session.metadata = data.get("metadata", {})
        session.feedback_history = data.get("feedback_history", [])

        # 反序列化 patches
        for patch_data in data.get("patches", []):
            session.patches.append(CDLPatch.from_dict(patch_data))

        return session


class StatePersistence:
    """
    状态持久化

    保存/加载:
    - 会话状态
    - ContentGraph
    - 系统配置
    """

    def __init__(self, base_dir: Path = Path(".udify/state")) -> None:
        self.base_dir = base_dir
        self.sessions_dir = base_dir / "sessions"
        self.graphs_dir = base_dir / "graphs"

        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.graphs_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: ModSession) -> Path:
        """保存会话"""
        path = self.sessions_dir / f"{session.session_id}.json"
        data = SessionSerializer.to_dict(session)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def load_session(self, session_id: str) -> ModSession | None:
        """加载会话"""
        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionSerializer.from_dict(data)

    def list_sessions(self) -> list[str]:
        """列出所有保存的会话 ID"""
        return [p.stem for p in self.sessions_dir.glob("*.json")]

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        path = self.sessions_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def save_graph(self, graph: ContentGraph, name: str) -> Path:
        """保存图谱"""
        path = self.graphs_dir / f"{name}.json"
        data = GraphSerializer.to_dict(graph)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def load_graph(self, name: str) -> ContentGraph | None:
        """加载图谱"""
        path = self.graphs_dir / f"{name}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        return GraphSerializer.from_dict(data)

    def list_graphs(self) -> list[str]:
        """列出所有保存的图谱"""
        return [p.stem for p in self.graphs_dir.glob("*.json")]

    def save_session_manager(self, manager: SessionManager) -> None:
        """保存所有会话"""
        for session in manager._sessions.values():
            self.save_session(session)

    def load_session_manager(self) -> SessionManager:
        """加载所有会话"""
        manager = SessionManager()
        for session_id in self.list_sessions():
            session = self.load_session(session_id)
            if session:
                manager._sessions[session_id] = session
                manager._user_sessions.setdefault(session.user_id, []).append(session_id)
        return manager

    def clear_all(self) -> None:
        """清除所有持久化数据"""
        for path in self.sessions_dir.glob("*.json"):
            path.unlink()
        for path in self.graphs_dir.glob("*.json"):
            path.unlink()
