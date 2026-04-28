"""
工具链集成模块 (Toolchain Integration)

集成社区Mod制作工具、反编译工具、移植工具等全套工具链。
参考: COMMUNITY-RESEARCH-v2.md + ARCHITECTURE-GAME-MOD-v1.md
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import subprocess
import json


class ToolchainManager:
    """工具链管理器
    
    管理反编译工具、Mod生成工具、移植工具等。
    支持工具自动发现、版本管理、调用封装。
    """
    
    # 已知社区工具映射
    KNOWN_TOOLS = {
        # Unity 工具
        "assetstudio": {
            "name": "AssetStudio",
            "description": "Unity 资源提取和反编译工具",
            "command": "AssetStudio.CLI",
            "supported_games": ["Unity"],
            "output_formats": ["prefab", "texture", "mesh", "audio"],
            "download_url": "https://github.com/Perfare/AssetStudio"
        },
        "uabe": {
            "name": "UABE (Unity Assets Bundle Extractor)",
            "description": "Unity Asset Bundle 解包工具",
            "command": "UABE",
            "supported_games": ["Unity"],
            "output_formats": ["assets", "bundles"],
            "download_url": "https://github.com/SeriousCache/UABE"
        },
        
        # Unreal 工具
        "ue_viewer": {
            "name": "UE Viewer (umodel)",
            "description": "Unreal Engine 资源查看器和提取器",
            "command": "umodel",
            "supported_games": ["Unreal"],
            "output_formats": ["mesh", "texture", "animation", "sound"],
            "download_url": "https://github.com/gildor/umodel"
        },
        "fmodel": {
            "name": "FModel",
            "description": "Unreal Engine 资源浏览器和提取器",
            "command": "FModel",
            "supported_games": ["Unreal"],
            "output_formats": ["mesh", "texture", "audio", "blueprint"],
            "download_url": "https://github.com/4sval/FModel"
        },
        
        # 通用工具
        "quickbms": {
            "name": "QuickBMS",
            "description": "通用游戏资源解包脚本工具",
            "command": "quickbms",
            "supported_games": ["Generic"],
            "output_formats": ["various"],
            "download_url": "https://aluigi.altervista.org/quickbms.htm"
        },
        
        # miu2d 特化工具
        "miu2d_converter": {
            "name": "miu2d Converter",
            "description": "miu2d 二进制格式转换工具（Rust CLI）",
            "command": "miu2d-converter",
            "supported_games": ["miu2d"],
            "output_formats": ["json", "png", "wav"],
            "download_url": "https://github.com/luckyyyyy/miu2d"
        }
    }
    
    def __init__(self, tools_config: Optional[Dict] = None):
        self.tools = tools_config or self.KNOWN_TOOLS
        self._check_tools_availability()
    
    def _check_tools_availability(self):
        """检查工具是否可用"""
        for tool_id, tool_info in self.tools.items():
            tool_info["available"] = self._is_tool_available(tool_info["command"])
    
    def _is_tool_available(self, command: str) -> bool:
        """检查命令是否可用"""
        try:
            subprocess.run(
                [command, "--version"],
                capture_output=True,
                timeout=5
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def get_tool_for_game(self, game_engine: str) -> List[Dict]:
        """根据游戏引擎获取可用工具"""
        available_tools = []
        
        for tool_id, tool_info in self.tools.items():
            if game_engine in tool_info["supported_games"] or "Generic" in tool_info["supported_games"]:
                if tool_info.get("available", False):
                    available_tools.append({
                        "id": tool_id,
                        **tool_info
                    })
        
        return available_tools
    
    def extract_assets(
        self,
        game_engine: str,
        game_path: Path,
        output_path: Path,
        asset_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """提取游戏资源
        
        Args:
            game_engine: 游戏引擎类型
            game_path: 游戏目录路径
            output_path: 输出目录
            asset_types: 要提取的资源类型（可选）
            
        Returns:
            Dict: 提取结果
        """
        tools = self.get_tool_for_game(game_engine)
        
        if not tools:
            return {
                "success": False,
                "error": f"No tools available for {game_engine}",
                "tools_needed": [t["name"] for t in self.tools.values() 
                           if game_engine in t["supported_games"]]
            }
        
        results = {
            "success": True,
            "extracted_files": [],
            "failed_files": [],
            "tool_used": None
        }
        
        # 尝试使用第一个可用工具
        for tool in tools:
            tool_id = tool["id"]
            
            if tool_id == "assetstudio":
                result = self._run_assetstudio(game_path, output_path, asset_types)
            elif tool_id == "uabe":
                result = self._run_uabe(game_path, output_path, asset_types)
            elif tool_id == "ue_viewer":
                result = self._run_ue_viewer(game_path, output_path, asset_types)
            elif tool_id == "fmodel":
                result = self._run_fmodel(game_path, output_path, asset_types)
            elif tool_id == "miu2d_converter":
                result = self._run_miu2d_converter(game_path, output_path, asset_types)
            else:
                continue
            
            if result["success"]:
                results.update(result)
                results["tool_used"] = tool["name"]
                break
        
        return results
    
    def _run_assetstudio(
        self,
        game_path: Path,
        output_path: Path,
        asset_types: Optional[List[str]]
    ) -> Dict[str, Any]:
        """运行 AssetStudio CLI"""
        try:
            cmd = ["AssetStudio.CLI", str(game_path), "-o", str(output_path)]
            
            if asset_types:
                cmd.extend(["-t", ",".join(asset_types)])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "extracted_files": self._list_output_files(output_path),
                "tool_used": "AssetStudio"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_used": "AssetStudio"
            }
    
    def _run_uabe(
        self,
        game_path: Path,
        output_path: Path,
        asset_types: Optional[List[str]]
    ) -> Dict[str, Any]:
        """运行 UABE"""
        try:
            cmd = ["UABE", "-export", str(game_path), str(output_path)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "extracted_files": self._list_output_files(output_path),
                "tool_used": "UABE"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_used": "UABE"
            }
    
    def _run_ue_viewer(
        self,
        game_path: Path,
        output_path: Path,
        asset_types: Optional[List[str]]
    ) -> Dict[str, Any]:
        """运行 UE Viewer (umodel)"""
        try:
            cmd = ["umodel", "-path", str(game_path), "-out", str(output_path)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "extracted_files": self._list_output_files(output_path),
                "tool_used": "UE Viewer"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_used": "UE Viewer"
            }
    
    def _run_miu2d_converter(
        self,
        game_path: Path,
        output_path: Path,
        asset_types: Optional[List[str]]
    ) -> Dict[str, Any]:
        """运行 miu2d Converter"""
        try:
            cmd = ["miu2d-converter", str(game_path), str(output_path)]
            
            if asset_types:
                cmd.extend(asset_types)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "extracted_files": self._list_output_files(output_path),
                "tool_used": "miu2d Converter"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "tool_used": "miu2d Converter"
            }
    
    def _list_output_files(self, output_path: Path) -> List[str]:
        """列出输出文件"""
        if not output_path.exists():
            return []
        
        return [str(p) for p in output_path.rglob("*") if p.is_file()]
    
    def check_mod_compatibility(
        self,
        mod_path: Path,
        game_version: str
    ) -> Dict[str, Any]:
        """检查 Mod 兼容性
        
        检查 Mod 是否兼容特定游戏版本。
        基于文件格式、依赖库、 API 调用等。
        """
        # 简化的兼容性检查
        result = {
            "compatible": True,
            "warnings": [],
            "errors": [],
            "game_version": game_version,
            "mod_version": "unknown"
        }
        
        # 检查常见 Mod 文件
        if (mod_path / "manifest.json").exists():
            manifest = json.loads((mod_path / "manifest.json").read_text())
            result["mod_version"] = manifest.get("version", "unknown")
            
            # 检查支持的游戏版本
            supported = manifest.get("supported_versions", [])
            if supported and game_version not in supported:
                result["compatible"] = False
                result["errors"].append(
                    f"Mod does not support game version {game_version}"
                )
        
        # 检查依赖
        if (mod_path / "requirements.txt").exists():
            reqs = (mod_path / "requirements.txt").read_text().splitlines()
            result["dependencies"] = reqs
        
        return result
    
    def migrate_mod(
        self,
        mod_path: Path,
        from_version: str,
        to_version: str
    ) -> Dict[str, Any]:
        """迁移 Mod 到新游戏版本
        
        尝试自动迁移 Mod 以兼容新游戏版本。
        包括更新 API 调用、替换废弃资源引用等。
        """
        # 这是一个复杂的功能，这里只是框架
        return {
            "success": False,
            "message": "Mod migration not yet implemented",
            "from_version": from_version,
            "to_version": to_version,
            "mod_path": str(mod_path)
        }