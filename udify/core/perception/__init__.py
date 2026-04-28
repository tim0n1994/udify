"""
Udify Core - Perception Engine

主感知引擎，协调引擎检测、资源提取和机制分析，
将原始内容转换为结构化的内容图谱（Content Graph）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from udify.models.content_graph import (
    ContentGraph,
    ContentSemantics,
    GameEngine,
    MediaType,
    NodeType,
)
from udify.core.perception.engine_detector import (
    CompositeEngineDetector,
    EngineDetectionResult,
)
from udify.core.perception.resource_extractor import (
    CompositeResourceExtractor,
    ExtractionResult,
)
from udify.core.perception.mechanism_analyzer import (
    CompositeMechanismAnalyzer,
)

logger = logging.getLogger(__name__)


class PerceptionEngine:
    """
    感知引擎
    
    负责将原始内容（游戏、音乐、视频、小说）解析为结构化的内容图谱。
    处理流程：
    1. 引擎检测（如果是游戏）
    2. 资源提取
    3. 机制分析（如果是游戏）
    4. 语义理解
    5. 质量评估
    
    Example:
        >>> engine = PerceptionEngine()
        >>> graph = engine.perceive("/path/to/game")
        >>> print(graph.summary())
    """
    
    def __init__(
        self,
        engine_detector: Optional[CompositeEngineDetector] = None,
        resource_extractor: Optional[CompositeResourceExtractor] = None,
        mechanism_analyzer: Optional[CompositeMechanismAnalyzer] = None,
    ):
        self.engine_detector = engine_detector or CompositeEngineDetector()
        self.resource_extractor = resource_extractor or CompositeResourceExtractor()
        self.mechanism_analyzer = mechanism_analyzer or CompositeMechanismAnalyzer()
    
    def perceive(self, path: str | Path, media_type: Optional[MediaType] = None) -> ContentGraph:
        """
        感知内容，生成内容图谱
        
        Args:
            path: 内容文件或目录路径
            media_type: 媒介类型（如果已知）。如果为 None，会自动检测
            
        Returns:
            内容图谱
        """
        path = Path(path)
        logger.info(f"Perceiving content at: {path}")
        
        # 初始化图谱
        graph = ContentGraph(
            source_path=str(path.absolute()),
            media_type=media_type or MediaType.UNKNOWN,
        )
        
        if not path.exists():
            logger.error(f"Path does not exist: {path}")
            graph.confidence = 0.0
            return graph
        
        try:
            # 步骤 1: 检测媒介类型和引擎（如果是游戏）
            if media_type is None or media_type == MediaType.UNKNOWN:
                media_type = self._detect_media_type(path)
                graph.media_type = media_type
            
            # 如果是游戏，检测引擎
            engine_result: Optional[EngineDetectionResult] = None
            if media_type == MediaType.GAME:
                engine_result = self.engine_detector.detect(path)
                graph.metadata.engine = engine_result.engine
                graph.metadata.engine_version = engine_result.version
                graph.confidence = engine_result.confidence
                
                logger.info(
                    f"Detected engine: {engine_result.engine.value} "
                    f"(confidence={engine_result.confidence:.2f})"
                )
            
            # 步骤 2: 提取资源
            if media_type == MediaType.GAME and engine_result:
                extraction_result = self.resource_extractor.extract(
                    path, engine_result.engine
                )
            else:
                # 通用资源提取
                extraction_result = self._generic_extraction(path, media_type)
            
            for asset in extraction_result.assets:
                graph.add_asset(asset)
            
            logger.info(f"Extracted {len(graph.assets)} assets")
            
            # 步骤 3: 分析机制（如果是游戏）
            if media_type == MediaType.GAME:
                self.mechanism_analyzer.analyze(graph)
                logger.info(
                    f"Analyzed mechanisms: "
                    f"{len(graph.get_nodes_by_type(NodeType.MECHANIC))} mechanics, "
                    f"{len(graph.get_nodes_by_type(NodeType.CHARACTER))} characters, "
                    f"{len(graph.get_nodes_by_type(NodeType.LEVEL))} levels"
                )
            
            # 步骤 4: 语义理解
            self._extract_semantics(graph, media_type)
            
            # 步骤 5: 计算总体置信度
            graph.confidence = self._calculate_overall_confidence(graph, engine_result)
            
        except Exception as e:
            logger.exception(f"Perception failed for {path}: {e}")
            graph.confidence *= 0.5  # 降低置信度
        
        logger.info(f"Perception complete. Confidence: {graph.confidence:.2f}")
        return graph
    
    def _detect_media_type(self, path: Path) -> MediaType:
        """检测媒介类型"""
        if path.is_file():
            suffix = path.suffix.lower()
            
            # 音频文件
            if suffix in ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma']:
                return MediaType.MUSIC
            
            # 视频文件
            if suffix in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv']:
                return MediaType.VIDEO
            
            # 文本/小说
            if suffix in ['.txt', '.epub', '.mobi', '.pdf', '.docx']:
                return MediaType.NOVEL
            
            # 压缩包/可执行文件 = 可能是游戏
            if suffix in ['.zip', '.rar', '.7z', '.exe', '.apk', '.ipa', '.app']:
                return MediaType.GAME
        
        elif path.is_dir():
            # 检查目录内容来判断类型
            files = list(path.iterdir())
            
            # 检查是否有可执行文件或数据目录
            exe_files = [f for f in files if f.suffix in ['.exe', '.app', '.sh']]
            data_dirs = [f for f in files if f.is_dir() and 
                        any(x in f.name for x in ['Data', 'data', 'Content', 'Resources'])]
            
            if exe_files or data_dirs:
                return MediaType.GAME
            
            # 检查是否有大量文本文件
            text_files = [f for f in files if f.suffix in ['.txt', '.md', '.docx']]
            if text_files:
                return MediaType.NOVEL
            
            # 检查是否有音频文件
            audio_files = [f for f in files if f.suffix in ['.mp3', '.wav', '.ogg']]
            if audio_files:
                return MediaType.MUSIC
            
            # 检查是否有视频文件
            video_files = [f for f in files if f.suffix in ['.mp4', '.avi', '.mov']]
            if video_files:
                return MediaType.VIDEO
        
        # 默认假设为游戏（最常见的情况）
        return MediaType.GAME
    
    def _generic_extraction(self, path: Path, media_type: MediaType) -> ExtractionResult:
        """通用资源提取（适用于未知引擎或非游戏媒介）"""
        from udify.core.perception.resource_extractor import ResourceExtractor
        
        class GenericExtractor(ResourceExtractor):
            @property
            def supported_engine(self) -> GameEngine:
                return GameEngine.UNKNOWN
            
            def extract(self, path: Path) -> ExtractionResult:
                assets = []
                errors = []
                
                if path.is_file():
                    # 单个文件
                    asset = self._create_asset_from_file(path, path.parent)
                    if asset:
                        assets.append(asset)
                
                elif path.is_dir():
                    # 扫描目录
                    for file_path in self._scan_directory(path):
                        try:
                            asset = self._create_asset_from_file(file_path, path)
                            if asset:
                                assets.append(asset)
                        except Exception as e:
                            errors.append(str(e))
                
                return ExtractionResult(
                    assets=assets,
                    success=len(errors) == 0,
                    errors=errors,
                )
            
            def _create_asset_from_file(self, file_path: Path, base_dir: Path) -> Optional[ContentAsset]:
                from udify.models.content_graph import ContentAsset
                
                suffix = file_path.suffix
                file_type = self._get_file_type(suffix)
                
                if file_type == 'unknown':
                    return None
                
                try:
                    rel_path = file_path.relative_to(base_dir)
                except ValueError:
                    rel_path = file_path.name
                
                return ContentAsset(
                    path=str(rel_path),
                    type=file_type,
                    format=suffix.lstrip('.') if suffix else '',
                    size=file_path.stat().st_size,
                )
        
        extractor = GenericExtractor()
        return extractor.extract(path)
    
    def _extract_semantics(self, graph: ContentGraph, media_type: MediaType) -> None:
        """提取语义信息"""
        semantics = ContentSemantics()
        
        if media_type == MediaType.GAME:
            # 基于机制推断游戏类型
            mechanics = graph.get_nodes_by_type(NodeType.MECHANIC)
            mechanic_names = [m.name for m in mechanics]
            
            # 推断游戏类型
            if any('战斗' in m or 'combat' in m for m in mechanic_names):
                if any('rpg' in m.lower() or '角色' in m for m in mechanic_names):
                    semantics.game_genre = 'RPG'
                elif any('fps' in m.lower() or '射击' in m for m in mechanic_names):
                    semantics.game_genre = 'FPS'
                else:
                    semantics.game_genre = 'Action'
            
            if any('inventory' in m.lower() or '背包' in m for m in mechanic_names):
                semantics.game_genre = semantics.game_genre or 'RPG'
            
            if any('quest' in m.lower() or '任务' in m for m in mechanic_names):
                semantics.game_genre = semantics.game_genre or 'Adventure'
            
            # 推断视角
            if any('first_person' in m.lower() for m in mechanic_names):
                semantics.perspective = 'first_person'
            elif any('top_down' in m.lower() for m in mechanic_names):
                semantics.perspective = 'top_down'
            else:
                # 基于资源推断
                model_count = len(graph.get_assets_by_type('model'))
                texture_count = len(graph.get_assets_by_type('texture'))
                
                if model_count > 10:
                    semantics.perspective = 'third_person'  # 3D 游戏通常默认第三人称
                elif texture_count > 50:
                    semantics.perspective = 'top_down'  # 大量 2D 纹理可能是俯视角
            
            # 生成摘要
            summary_parts = []
            if graph.metadata.engine != GameEngine.UNKNOWN:
                summary_parts.append(f"{graph.metadata.engine.value} engine")
            if semantics.game_genre:
                summary_parts.append(f"{semantics.game_genre} genre")
            if graph.metadata.title:
                summary_parts.append(f"titled '{graph.metadata.title}'")
            
            summary_parts.append(f"with {len(graph.assets)} assets")
            summary_parts.append(f"and {len(mechanics)} detected mechanics")
            
            semantics.summary = " ".join(summary_parts)
        
        graph.semantics = semantics
    
    def _calculate_overall_confidence(
        self, 
        graph: ContentGraph, 
        engine_result: Optional[EngineDetectionResult]
    ) -> float:
        """计算总体置信度"""
        scores = []
        
        # 引擎检测置信度
        if engine_result:
            scores.append(engine_result.confidence)
        
        # 资源提取置信度（基于提取到的资产数量）
        if graph.assets:
            # 有资产 = 至少 0.3 基础分
            asset_score = min(0.3 + len(graph.assets) * 0.01, 0.5)
            scores.append(asset_score)
        
        # 机制分析置信度（基于检测到的机制数量）
        mechanic_count = len(graph.get_nodes_by_type(NodeType.MECHANIC))
        if mechanic_count > 0:
            mechanism_score = min(0.3 + mechanic_count * 0.02, 0.5)
            scores.append(mechanism_score)
        
        if not scores:
            return 0.0
        
        return sum(scores) / len(scores)


# 便捷函数
def perceive_content(path: str | Path, media_type: Optional[MediaType] = None) -> ContentGraph:
    """
    便捷函数：感知内容
    
    Example:
        >>> graph = perceive_content("/path/to/game")
        >>> print(graph.summary())
    """
    engine = PerceptionEngine()
    return engine.perceive(path, media_type)
