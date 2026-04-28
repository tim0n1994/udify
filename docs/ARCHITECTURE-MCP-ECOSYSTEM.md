# Udify MCP 工具生态设计

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: MCP Protocol 实现、工具注册发现、执行隔离、版本管理、工具市场、第三方扩展

---

## 目录

1. [MCP 协议在 Udify 中的定位](#1-mcp-协议在-udify-中的定位)
2. [MCP Server 架构](#2-mcp-server-架构)
3. [工具注册与发现](#3-工具注册与发现)
4. [工具执行隔离](#4-工具执行隔离)
5. [工具版本管理](#5-工具版本管理)
6. [内置工具集](#6-内置工具集)
7. [第三方工具市场](#7-第三方工具市场)
8. [LLM 与工具的交互协议](#8-llm-与工具的交互协议)

---

## 1. MCP 协议在 Udify 中的定位

### 1.1 架构层次

```
Udify 工具架构
    │
    ├──→ LLM 层（导演）
    │       └──→ 决定调用哪个工具、传递什么参数
    │
    ├──→ MCP Client 层（调度员）
    │       ├──→ 维护 Server 连接池
    │       ├──→ 路由工具调用请求
    │       ├──→ 处理并发/超时/重试
    │       └──→ 结果聚合与格式化
    │
    ├──→ MCP Server 层（演员）
    │       ├──→ 内置 Servers（Udify 官方）
    │       ├──→ 第三方 Servers（社区/商业）
    │       └──→ 用户自定义 Servers
    │
    └──→ 执行层（沙箱）
            ├──→ gVisor 容器
            ├──→ 资源限制
            └──→ 输出捕获
```

### 1.2 与标准 MCP 的关系

```yaml
mcp_compliance:
  version: "2024-11-05"  # MCP Protocol 版本
  
  supported_transports:
    - stdio              # 本地进程通信
    - sse                # Server-Sent Events（HTTP）
    - websocket          # 扩展（非标准，用于实时场景）
  
  extensions:
    - name: "udify-execution-context"
      description: "传递执行上下文（项目ID、用户ID、沙箱配置）"
    - name: "udify-resource-streaming"
      description: "支持大文件流式传输"
    - name: "udify-batch-execution"
      description: "批量工具调用优化"
```

---

## 2. MCP Server 架构

### 2.1 Server 基类

```python
# udify/tools/mcp/server.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncGenerator
from pydantic import BaseModel
import asyncio

class MCPToolParameter(BaseModel):
    name: str
    type: str  # string, number, boolean, array, object
    description: str
    required: bool = True
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None

class MCPToolDefinition(BaseModel):
    name: str
    description: str
    parameters: List[MCPToolParameter]
    returns: Dict[str, Any]
    dangerous: bool = False  # 是否需要人类确认
    estimated_cost_usd: float = 0.0  # 估算成本
    average_latency_ms: int = 1000
    
class MCPToolResult(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    logs: List[str] = []
    artifacts: List[ArtifactRef] = []  # 生成的文件引用
    
class MCPResourceDefinition(BaseModel):
    uri: str
    name: str
    mimeType: str
    description: str

class UdifyMCPServer(ABC):
    """Udify MCP Server 基类"""
    
    def __init__(self, server_id: str, version: str):
        self.server_id = server_id
        self.version = version
        self.tools: Dict[str, MCPToolDefinition] = {}
        self.resources: Dict[str, MCPResourceDefinition] = {}
        self._register_capabilities()
    
    @abstractmethod
    def _register_capabilities(self):
        """注册本 Server 支持的工具和资源"""
        pass
    
    def register_tool(self, definition: MCPToolDefinition, handler: callable):
        """注册工具"""
        self.tools[definition.name] = {
            "definition": definition,
            "handler": handler,
        }
    
    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> MCPToolResult:
        """执行工具"""
        if tool_name not in self.tools:
            return MCPToolResult(success=False, error=f"Tool '{tool_name}' not found")
        
        tool = self.tools[tool_name]
        
        # 1. 参数验证
        validation_error = self._validate_parameters(tool["definition"], parameters)
        if validation_error:
            return MCPToolResult(success=False, error=validation_error)
        
        # 2. 权限检查
        if tool["definition"].dangerous and not context.approved:
            return MCPToolResult(
                success=False,
                error=f"Tool '{tool_name}' requires human approval",
                requires_approval=True
            )
        
        # 3. 执行
        try:
            result = await tool["handler"](parameters, context)
            return MCPToolResult(success=True, data=result)
        except Exception as e:
            return MCPToolResult(success=False, error=str(e))
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取 Server 能力清单（用于 LLM 工具选择）"""
        return {
            "server_id": self.server_id,
            "version": self.version,
            "tools": [
                {
                    "name": t["definition"].name,
                    "description": t["definition"].description,
                    "parameters": [
                        {"name": p.name, "type": p.type, "description": p.description, "required": p.required}
                        for p in t["definition"].parameters
                    ],
                    "dangerous": t["definition"].dangerous,
                    "estimated_cost_usd": t["definition"].estimated_cost_usd,
                }
                for t in self.tools.values()
            ],
            "resources": [
                {"uri": r.uri, "name": r.name, "mimeType": r.mimeType}
                for r in self.resources.values()
            ],
        }
    
    def _validate_parameters(self, definition: MCPToolDefinition, params: Dict[str, Any]) -> Optional[str]:
        """验证参数"""
        for param in definition.parameters:
            if param.required and param.name not in params:
                return f"Missing required parameter: {param.name}"
            
            if param.name in params and param.enum and params[param.name] not in param.enum:
                return f"Invalid value for {param.name}: must be one of {param.enum}"
        
        return None
```

### 2.2 Server 生命周期管理

```python
# udify/tools/mcp/server_manager.py

class MCPServerManager:
    """MCP Server 生命周期管理器"""
    
    def __init__(self):
        self.servers: Dict[str, UdifyMCPServer] = {}
        self.processes: Dict[str, asyncio.subprocess.Process] = {}
        self.health_checks: Dict[str, asyncio.Task] = {}
    
    async def start_server(self, server_config: ServerConfig) -> UdifyMCPServer:
        """启动 MCP Server"""
        
        if server_config.transport == "stdio":
            # 启动本地进程
            process = await asyncio.create_subprocess_exec(
                server_config.command,
                *server_config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            self.processes[server_config.server_id] = process
            
            # 等待初始化完成
            init_response = await self._read_jsonrpc(process.stdout)
            if init_response.get("result", {}).get("protocolVersion") != "2024-11-05":
                raise MCPProtocolError("Incompatible MCP protocol version")
        
        elif server_config.transport == "sse":
            # HTTP SSE 连接
            # ...
            pass
        
        # 获取能力清单
        capabilities = await self._request_capabilities(server_config.server_id)
        
        # 创建 Server 代理
        server = MCPServerProxy(
            server_id=server_config.server_id,
            capabilities=capabilities,
            transport=server_config.transport,
            process=process if server_config.transport == "stdio" else None,
        )
        
        self.servers[server_config.server_id] = server
        
        # 启动健康检查
        self.health_checks[server_config.server_id] = asyncio.create_task(
            self._health_check_loop(server_config.server_id)
        )
        
        return server
    
    async def _health_check_loop(self, server_id: str):
        """周期性健康检查"""
        while True:
            await asyncio.sleep(30)
            
            server = self.servers.get(server_id)
            if not server:
                break
            
            try:
                await server.ping()
                server.healthy = True
            except Exception:
                server.healthy = False
                logger.warning(f"MCP Server {server_id} health check failed")
                
                # 尝试重启
                if server.auto_restart:
                    await self.restart_server(server_id)
    
    async def restart_server(self, server_id: str):
        """重启 Server"""
        await self.stop_server(server_id)
        config = self.get_server_config(server_id)
        await self.start_server(config)
    
    async def stop_server(self, server_id: str):
        """停止 Server"""
        # 取消健康检查
        if server_id in self.health_checks:
            self.health_checks[server_id].cancel()
        
        # 终止进程
        if server_id in self.processes:
            process = self.processes[server_id]
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        
        # 清理
        self.servers.pop(server_id, None)
        self.processes.pop(server_id, None)
```

---

## 3. 工具注册与发现

### 3.1 工具注册中心

```python
# udify/tools/registry.py

class ToolRegistry:
    """全局工具注册中心"""
    
    def __init__(self):
        self.tools: Dict[str, RegisteredTool] = {}
        self.categories: Dict[str, List[str]] = {}  # category -> tool_ids
        self.tags_index: Dict[str, List[str]] = {}  # tag -> tool_ids
    
    def register(self, tool: RegisteredTool):
        """注册工具"""
        self.tools[tool.tool_id] = tool
        
        # 索引分类
        for category in tool.categories:
            self.categories.setdefault(category, []).append(tool.tool_id)
        
        # 索引标签
        for tag in tool.tags:
            self.tags_index.setdefault(tag, []).append(tool.tool_id)
        
        logger.info(f"Tool registered: {tool.tool_id} v{tool.version}")
    
    def discover(
        self,
        query: Optional[str] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        engine_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> List[RegisteredTool]:
        """发现工具"""
        candidates = set(self.tools.keys())
        
        if categories:
            category_matches = set()
            for cat in categories:
                category_matches.update(self.categories.get(cat, []))
            candidates &= category_matches
        
        if tags:
            tag_matches = set()
            for tag in tags:
                tag_matches.update(self.tags_index.get(tag, []))
            candidates &= tag_matches
        
        if engine_type:
            candidates = {
                t for t in candidates
                if engine_type in self.tools[t].compatible_engines
            }
        
        if media_type:
            candidates = {
                t for t in candidates
                if media_type in self.tools[t].compatible_media
            }
        
        results = [self.tools[t] for t in candidates]
        
        # 如果有查询词，按语义相似度排序
        if query:
            results = self._rank_by_relevance(results, query)
        
        return results
    
    def _rank_by_relevance(self, tools: List[RegisteredTool], query: str) -> List[RegisteredTool]:
        """按查询词相关性排序"""
        query_embedding = self.embed(query)
        
        scored = []
        for tool in tools:
            # 组合文本用于相似度计算
            tool_text = f"{tool.name} {tool.description} {' '.join(tool.tags)}"
            tool_embedding = self.embed(tool_text)
            
            similarity = cosine_similarity(query_embedding, tool_embedding)
            
            # 考虑声誉权重
            reputation_weight = min(tool.usage_count / 1000, 1.0)
            
            final_score = similarity * 0.7 + reputation_weight * 0.3
            scored.append((tool, final_score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in scored]
```

### 3.2 注册表示例

```yaml
# 内置工具注册表示例

tools:
  - tool_id: "unity.extract_assets"
    name: "Unity Asset Extractor"
    description: "Extract textures, models, audio, and scripts from Unity game files"
    version: "2.1.0"
    server_id: "udify-perception-unity"
    categories: ["perception", "extraction"]
    tags: ["unity", "assets", "textures", "models", "audio"]
    compatible_engines: ["unity"]
    compatible_media: ["game"]
    parameters:
      - name: "game_path"
        type: "string"
        description: "Path to the Unity game directory"
        required: true
      - name: "asset_types"
        type: "array"
        description: "Types of assets to extract"
        required: false
        default: ["texture", "model", "audio", "script"]
        enum: [["texture"], ["model"], ["audio"], ["script"], ["texture", "model", "audio", "script"]]
    returns:
      type: "object"
      properties:
        extracted_assets: { type: "array", items: { type: "object" } }
        total_size_bytes: { type: "number" }
    dangerous: false
    estimated_cost_usd: 0.01
    average_latency_ms: 5000
    usage_count: 15420
    rating: 4.7
  
  - tool_id: "unreal.modify_blueprint"
    name: "Unreal Blueprint Modifier"
    description: "Modify Unreal Engine Blueprint assets programmatically"
    version: "1.5.0"
    server_id: "udify-execution-unreal"
    categories: ["execution", "modification"]
    tags: ["unreal", "blueprint", "visual-scripting"]
    compatible_engines: ["unreal"]
    compatible_media: ["game"]
    parameters:
      - name: "blueprint_path"
        type: "string"
        required: true
      - name: "modifications"
        type: "array"
        required: true
    returns:
      type: "object"
      properties:
        success: { type: "boolean" }
        modified_nodes: { type: "number" }
    dangerous: true  # 修改脚本需要确认
    estimated_cost_usd: 0.05
    average_latency_ms: 10000
    usage_count: 3200
    rating: 4.2
  
  - tool_id: "general.apply_patch"
    name: "CDL Patch Applier"
    description: "Apply a CDL Patch to a ContentGraph"
    version: "3.0.0"
    server_id: "udify-core-patcher"
    categories: ["core", "transformation"]
    tags: ["cdl", "patch", "apply", "transform"]
    compatible_engines: ["*"]  # 通用
    compatible_media: ["game", "music", "video", "novel"]
    parameters:
      - name: "cdl_document"
        type: "object"
        required: true
      - name: "patch"
        type: "object"
        required: true
      - name: "validate_only"
        type: "boolean"
        required: false
        default: false
    returns:
      type: "object"
      properties:
        success: { type: "boolean" }
        modified_cdl: { type: "object" }
        validation_errors: { type: "array" }
    dangerous: false
    estimated_cost_usd: 0.001
    average_latency_ms: 500
    usage_count: 89200
    rating: 4.9
```

---

## 4. 工具执行隔离

### 4.1 执行沙箱

```python
# udify/tools/execution/sandbox.py

class ToolSandbox:
    """工具执行沙箱"""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self.runtime = config.runtime  # "gvisor" | "firecracker" | "docker"
    
    async def execute(
        self,
        tool: RegisteredTool,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> MCPToolResult:
        """在沙箱中执行工具"""
        
        # 1. 准备输入
        input_dir = await self._prepare_input(tool, parameters, context)
        
        # 2. 启动沙箱
        container = await self._spawn_container(
            image=tool.sandbox_image,
            command=tool.execution_command,
            env={
                "UDIFY_PROJECT_ID": context.project_id,
                "UDIFY_USER_ID": context.user_id,
                "UDIFY_INPUT_DIR": "/input",
                "UDIFY_OUTPUT_DIR": "/output",
            },
            mounts=[
                Mount(source=input_dir, target="/input", read_only=True),
                Mount(source=self._create_output_dir(), target="/output", read_only=False),
            ],
            resources=ResourceLimits(
                cpu_cores=tool.max_cpu_cores or 2,
                memory_mb=tool.max_memory_mb or 2048,
                disk_mb=tool.max_disk_mb or 5120,
                network=tool.requires_network or False,
                timeout_seconds=tool.timeout_seconds or 300,
            ),
        )
        
        try:
            # 3. 监控执行
            result = await self._monitor_execution(container)
            
            # 4. 收集输出
            output = await self._collect_output(container)
            
            return MCPToolResult(
                success=result.exit_code == 0,
                data=output.data,
                logs=output.logs,
                artifacts=output.artifacts,
            )
            
        except TimeoutError:
            return MCPToolResult(
                success=False,
                error=f"Tool execution timed out after {tool.timeout_seconds}s"
            )
        finally:
            # 5. 清理
            await container.destroy()
            await self._cleanup_input(input_dir)
    
    async def _monitor_execution(self, container: Container) -> ExecutionResult:
        """监控容器执行"""
        
        start_time = time.time()
        
        while True:
            # 检查是否超时
            elapsed = time.time() - start_time
            if elapsed > container.resource_limits.timeout_seconds:
                await container.kill()
                raise TimeoutError()
            
            # 检查资源使用
            stats = await container.stats()
            
            if stats.memory_usage_mb > container.resource_limits.memory_mb * 0.95:
                logger.warning(f"Container approaching memory limit: {stats.memory_usage_mb}MB")
            
            if stats.memory_usage_mb > container.resource_limits.memory_mb:
                await container.kill()
                return ExecutionResult(exit_code=-1, error="Out of memory")
            
            # 检查是否完成
            status = await container.status()
            if status.state in ["exited", "dead"]:
                return ExecutionResult(exit_code=status.exit_code)
            
            await asyncio.sleep(0.5)
```

### 4.2 网络隔离策略

```yaml
# 工具网络隔离配置

tool_network_policies:
  # 完全隔离（默认）
  isolated:
    allow_egress: false
    allow_ingress: false
    dns: false
    
  # 受限网络（只访问 Udify 内部服务）
  restricted:
    allow_egress:
      - "10.0.0.0/8"      # 内部网络
      - "169.254.0.0/16"  # 链接本地（元数据服务）
    allow_ingress: false
    dns:
      - "internal.udify.dev"
    
  # 外部网络（需要明确白名单）
  external:
    allow_egress:
      - "api.openai.com:443"
      - "api.anthropic.com:443"
      - "huggingface.co:443"
    allow_ingress: false
    dns: true
    
  # 开放（极少使用，需审批）
  open:
    allow_egress: true
    allow_ingress: false
    dns: true
    requires_approval: true
```

---

## 5. 工具版本管理

### 5.1 版本策略

```python
class ToolVersionManager:
    """工具版本管理器"""
    
    def __init__(self):
        self.versions: Dict[str, List[ToolVersion]] = {}  # tool_id -> versions
    
    def register_version(self, tool_version: ToolVersion):
        """注册新版本"""
        tool_id = tool_version.tool_id
        
        if tool_id not in self.versions:
            self.versions[tool_id] = []
        
        # 语义版本排序
        self.versions[tool_id].append(tool_version)
        self.versions[tool_id].sort(key=lambda v: semver.parse(v.version), reverse=True)
    
    def resolve_version(
        self,
        tool_id: str,
        version_constraint: str = "latest"
    ) -> ToolVersion:
        """
        解析版本约束
        
        支持：
        - "latest" → 最新稳定版
        - "latest-beta" → 最新版（含 beta）
        - "1.x" → 1 系列最新
        - "1.2.3" → 精确版本
        - ">=1.2.0" → 语义范围
        """
        versions = self.versions.get(tool_id, [])
        
        if not versions:
            raise ToolNotFoundError(tool_id)
        
        if version_constraint == "latest":
            # 返回最新稳定版
            stable = [v for v in versions if not v.prerelease]
            return stable[0] if stable else versions[0]
        
        if version_constraint == "latest-beta":
            return versions[0]
        
        # 语义版本匹配
        matching = [v for v in versions if semver.match(v.version, version_constraint)]
        if not matching:
            raise VersionNotFoundError(tool_id, version_constraint)
        
        return matching[0]
    
    def deprecate_version(self, tool_id: str, version: str, reason: str):
        """弃用版本"""
        for v in self.versions.get(tool_id, []):
            if v.version == version:
                v.deprecated = True
                v.deprecation_reason = reason
                v.deprecation_date = datetime.utcnow()
                break
    
    def get_compatibility_matrix(self, tool_id: str) -> CompatibilityMatrix:
        """获取版本兼容性矩阵"""
        versions = self.versions.get(tool_id, [])
        
        matrix = {}
        for v in versions:
            matrix[v.version] = {
                "breaking_changes": v.breaking_changes,
                "migration_guide": v.migration_guide,
                "compatible_with": v.compatible_udify_versions,
            }
        
        return matrix
```

### 5.2 版本迁移

```yaml
# 工具版本迁移示例

tool: "unity.extract_assets"
versions:
  - version: "3.0.0"
    status: "current"
    breaking_changes:
      - "output format changed from flat to hierarchical"
      - "parameter 'asset_types' renamed to 'types'"
    migration:
      automatic: true
      script: |
        # 自动迁移脚本
        if 'asset_types' in old_params:
            new_params['types'] = old_params.pop('asset_types')
    
  - version: "2.5.0"
    status: "deprecated"
    deprecation_date: "2026-03-01"
    sunset_date: "2026-09-01"  # 届时停止服务
    replacement: "3.0.0"
```

---

## 6. 内置工具集

### 6.1 按领域分类

```
内置工具集（Built-in Tools）
    │
    ├──→ 感知层工具 (Perception Tools)
    │       ├──→ unity.detect_engine —— Unity 引擎检测
    │       ├──→ unity.extract_assets —— Unity 资源提取
    │       ├──→ unreal.extract_assets —— Unreal 资源提取
    │       ├──→ godot.extract_resources —— Godot 资源提取
    │       ├──→ generic.parse_archive —— 通用压缩包解析
    │       ├──→ generic.detect_file_type —— 文件类型魔数检测
    │       └──→ generic.hash_file —— 文件哈希计算
    │
    ├──→ 解析层工具 (Parsing Tools)
    │       ├──→ unity.parse_monobehaviour —— 解析 MonoBehaviour
    │       ├──→ unity.parse_shader —— 解析 ShaderLab
    │       ├──→ unreal.parse_blueprint —— 解析 Blueprint JSON
    │       ├──→ generic.parse_yaml —— YAML 解析
    │       ├──→ generic.parse_json —— JSON 解析
    │       ├──→ generic.parse_xml —— XML 解析
    │       └──→ generic.parse_binary —— 二进制结构解析
    │
    ├──→ 生成层工具 (Generation Tools)
    │       ├──→ image.generate_texture —— AI 纹理生成（SDXL）
    │       ├──→ image.upscale —— 图像超分辨率
    │       ├──→ audio.generate_sfx —— 音效生成
    │       ├──→ text.generate_dialogue —— 对话生成
    │       ├──→ code.modify_script —— 脚本修改
    │       └──→ mesh.generate_lowpoly —— 低模生成
    │
    ├──→ 执行层工具 (Execution Tools)
    │       ├──→ cdl.apply_patch —— 应用 CDL Patch
    │       ├──→ cdl.validate_patch —— 验证 Patch
    │       ├───> cdl.merge_patches —— 合并多个 Patch
    │       ├──→ file.copy —— 文件复制
    │       ├──→ file.move —— 文件移动
    │       ├──→ file.delete —— 文件删除
    │       ├──→ archive.create —— 创建压缩包
    │       └──→ archive.extract —— 解压
    │
    ├──→ 评估层工具 (Evaluation Tools)
    │       ├──→ game.test_launch —— 游戏启动测试
    │       ├──→ game.capture_screenshot —— 截图对比
    │       ├──→ perf.profile_loading —— 加载性能分析
    │       ├──→ perf.measure_fps —— FPS 测量
    │       └──→ security.scan_malware —— 恶意软件扫描
    │
    └──→ 通用工具 (Utility Tools)
            ├──→ math.calculate —— 数学计算
            ├──→ string.transform —— 字符串变换
            ├──→ json.transform —— JSON 变换
            ├──→ diff.compare_text —— 文本 diff
            ├──→ diff.compare_binary —— 二进制 diff
            └──→ git.clone —— Git 仓库克隆
```

### 6.2 工具实现示例

```python
# udify/tools/servers/perception_unity.py

from udify.tools.mcp.server import UdifyMCPServer, MCPToolDefinition, MCPToolParameter
from udify.core.perception.unity import UnityEngineDetector, UnityResourceExtractor

class UnityPerceptionServer(UdifyMCPServer):
    """Unity 感知 MCP Server"""
    
    def __init__(self):
        super().__init__(server_id="udify-perception-unity", version="2.1.0")
        self.detector = UnityEngineDetector()
        self.extractor = UnityResourceExtractor()
    
    def _register_capabilities(self):
        # 注册工具 1: 引擎检测
        self.register_tool(
            MCPToolDefinition(
                name="detect_engine",
                description="Detect if a game uses Unity engine and identify version",
                parameters=[
                    MCPToolParameter(
                        name="game_path",
                        type="string",
                        description="Path to game executable or directory",
                        required=True,
                    ),
                ],
                returns={"type": "object", "properties": {
                    "is_unity": {"type": "boolean"},
                    "version": {"type": "string"},
                    "scripting_backend": {"type": "string"},
                    "il2cpp": {"type": "boolean"},
                }},
            ),
            self._handle_detect_engine,
        )
        
        # 注册工具 2: 资源提取
        self.register_tool(
            MCPToolDefinition(
                name="extract_assets",
                description="Extract assets from Unity game files",
                parameters=[
                    MCPToolParameter(
                        name="game_path",
                        type="string",
                        description="Path to Unity game data",
                        required=True,
                    ),
                    MCPToolParameter(
                        name="asset_types",
                        type="array",
                        description="Types of assets to extract",
                        required=False,
                        default=["texture", "model", "audio", "script"],
                    ),
                    MCPToolParameter(
                        name="output_dir",
                        type="string",
                        description="Directory to save extracted assets",
                        required=True,
                    ),
                ],
                returns={"type": "object", "properties": {
                    "extracted_count": {"type": "number"},
                    "assets": {"type": "array"},
                    "total_size_bytes": {"type": "number"},
                }},
            ),
            self._handle_extract_assets,
        )
        
        # 注册资源
        self.resources = {
            "unity://engine-docs": MCPResourceDefinition(
                uri="unity://engine-docs",
                name="Unity Engine Documentation",
                mimeType="text/markdown",
                description="Reference documentation for Unity file formats",
            ),
        }
    
    async def _handle_detect_engine(self, params: dict, context) -> dict:
        """处理引擎检测请求"""
        game_path = params["game_path"]
        
        result = await self.detector.detect(game_path)
        
        return {
            "is_unity": result.is_unity,
            "version": result.version,
            "scripting_backend": result.scripting_backend,
            "il2cpp": result.il2cpp,
        }
    
    async def _handle_extract_assets(self, params: dict, context) -> dict:
        """处理资源提取请求"""
        game_path = params["game_path"]
        asset_types = params.get("asset_types", ["texture", "model", "audio", "script"])
        output_dir = params["output_dir"]
        
        extracted = await self.extractor.extract(
            game_path=game_path,
            asset_types=asset_types,
            output_dir=output_dir,
            progress_callback=lambda p: logger.info(f"Extraction progress: {p}%"),
        )
        
        return {
            "extracted_count": len(extracted.assets),
            "assets": [
                {"path": a.path, "type": a.type, "size": a.size}
                for a in extracted.assets
            ],
            "total_size_bytes": extracted.total_size,
        }
```

---

## 7. 第三方工具市场

### 7.1 市场架构

```
Udify Tool Marketplace
    │
    ├──→ 发布流程
    │       ├──→ 开发者提交工具包（Server 代码 + 元数据 + 测试）
    │       ├──→ 自动安全扫描（SBOM + 漏洞检测）
    │       ├──→ 社区评审（可选，高声誉用户）
    │       ├──→ 官方审核（ dangerous 工具）
    │       ├──→ 测试环境验证
    │       └──→ 发布到市场
    │
    ├──→ 发现机制
    │       ├──→ 分类浏览（引擎/媒介/功能）
    │       ├──→ 搜索（语义 + 关键词）
    │       ├──→ Trending（周/月下载量）
    │       ├──→ 编辑推荐
    │       └──→ 用户推荐（"用过这个的人还用了..."）
    │
    ├──→ 交易模式
    │       ├──→ 免费（MIT/Apache/CC0）
    │       ├──→ 一次性购买
    │       ├──→ 订阅制（持续更新）
    │       ├──→ 打赏/捐赠
    │       └──→ 企业授权
    │
    └──→ 信任体系
            ├──→ 数字签名验证
            ├──→ 声誉评分
            ├──→ 下载量/使用量
            ├──→ 用户评价
            └──→ 安全审计徽章
```

### 7.2 工具包格式

```yaml
# udify-tool-package.yml

tool_package:
  manifest_version: "1.0"
  
  # 元数据
  metadata:
    name: "Advanced Texture Upscaler"
    description: "AI-powered texture upscaling with style preservation"
    version: "1.2.0"
    author: "texture_wizard"
    license: "MIT"
    price: 9.99  # USD，0 表示免费
    
    categories:
      - "generation"
      - "image"
    
    tags:
      - "upscale"
      - "texture"
      - "ai"
      - "stable-diffusion"
    
    compatible_engines:
      - "unity"
      - "unreal"
      - "godot"
    
    screenshots:
      - "screenshots/before.png"
      - "screenshots/after.png"
    
    icon: "icon.png"
  
  # Server 定义
  server:
    entrypoint: "server.py"
    runtime: "python3.12"
    
    dependencies:
      - "torch>=2.0"
      - "pillow>=10.0"
      - "numpy>=1.24"
    
    resources:
      - "models/esrgan.pth"       # 包含的模型文件
      - "configs/default.yaml"
    
    sandbox:
      max_memory_mb: 4096
      max_cpu_cores: 2
      requires_gpu: true
      timeout_seconds: 120
  
  # 测试套件
  tests:
    - name: "upscale_2x"
      input:
        image_path: "tests/fixtures/256x256.png"
        scale: 2
      expected:
        output_size: [512, 512]
        ssim_threshold: 0.95
    
    - name: "upscale_4x"
      input:
        image_path: "tests/fixtures/256x256.png"
        scale: 4
      expected:
        output_size: [1024, 1024]
  
  # 权限声明
  permissions:
    network: false
    filesystem: "read-write-output-only"
    gpu: true
```

---

## 8. LLM 与工具的交互协议

### 8.1 ReAct 模式实现

```python
# udify/planning/react_loop.py

class ReActLoop:
    """
    ReAct (Reasoning + Acting) 循环
    
    LLM 交替进行：
    1. Thought: 思考当前状态和下一步
    2. Action: 选择工具并执行
    3. Observation: 观察工具输出
    """
    
    def __init__(self, llm: LLMClient, tools: List[RegisteredTool]):
        self.llm = llm
        self.tools = tools
        self.tool_registry = {t.tool_id: t for t in tools}
    
    async def run(
        self,
        intent: str,
        context: ExecutionContext,
        max_iterations: int = 20,
    ) -> ReActResult:
        """运行 ReAct 循环"""
        
        # 构建系统提示
        system_prompt = self._build_system_prompt()
        
        # 初始化对话历史
        history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Intent: {intent}"},
        ]
        
        for iteration in range(max_iterations):
            # 1. 获取 LLM 响应
            response = await self.llm.chat(history)
            
            # 2. 解析响应
            parsed = self._parse_response(response)
            
            if parsed.type == "thought":
                # 记录思考过程
                history.append({"role": "assistant", "content": response})
                continue
            
            elif parsed.type == "action":
                # 执行工具
                tool = self.tool_registry.get(parsed.tool_name)
                if not tool:
                    observation = f"Error: Tool '{parsed.tool_name}' not found"
                else:
                    result = await self._execute_tool(tool, parsed.parameters, context)
                    observation = self._format_observation(result)
                
                history.append({"role": "assistant", "content": response})
                history.append({"role": "user", "content": f"Observation: {observation}"})
            
            elif parsed.type == "final_answer":
                # 循环结束
                return ReActResult(
                    success=True,
                    answer=parsed.answer,
                    thought_process=self._extract_thoughts(history),
                    tool_calls=self._extract_tool_calls(history),
                    iterations=iteration + 1,
                )
        
        # 超过最大迭代次数
        return ReActResult(
            success=False,
            error="Max iterations reached",
            thought_process=self._extract_thoughts(history),
        )
    
    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        
        tools_description = "\n".join([
            f"- {t.tool_id}: {t.description}\n"
            f"  Parameters: {json.dumps([p.name for p in t.parameters])}"
            for t in self.tools
        ])
        
        return f"""You are an AI assistant that helps users modify game and media content.

You have access to the following tools:
{tools_description}

When responding, you must use the following format:

Thought: <your reasoning about what to do next>
Action: <tool_name>(<parameter1>=<value1>, <parameter2>=<value2>)
Observation: <result from tool execution>

OR, when you have completed the task:

Thought: <your reasoning>
Final Answer: <your final response>

Rules:
1. Always start with a Thought
2. Only use tools that exist in the list above
3. Wait for the Observation before making your next Thought
4. If a tool fails, try an alternative approach
5. Be concise in your reasoning
"""
    
    def _parse_response(self, response: str) -> ParsedResponse:
        """解析 LLM 响应"""
        
        if "Final Answer:" in response:
            answer = response.split("Final Answer:")[1].strip()
            return ParsedResponse(type="final_answer", answer=answer)
        
        if "Action:" in response:
            action_line = response.split("Action:")[1].strip().split("\n")[0]
            # 解析 "tool_name(param=value, ...)"
            match = re.match(r'(\w+)\((.*)\)', action_line)
            if match:
                tool_name = match.group(1)
                params_str = match.group(2)
                params = {}
                for param in params_str.split(','):
                    k, v = param.strip().split('=')
                    params[k.strip()] = eval(v.strip())  # 简化解析，实际用 ast.literal_eval
                return ParsedResponse(type="action", tool_name=tool_name, parameters=params)
        
        return ParsedResponse(type="thought")
```

### 8.2 Function Calling 模式

```python
# udify/planning/function_calling.py

class FunctionCallingPlanner:
    """
    OpenAI/Anthropic Function Calling 模式
    
    将工具定义为 JSON Schema，LLM 直接输出函数调用
    """
    
    def __init__(self, llm: LLMClient, tools: List[RegisteredTool]):
        self.llm = llm
        self.tools = tools
    
    def to_openai_functions(self) -> List[dict]:
        """转换为 OpenAI function 格式"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.tool_id,
                    "description": t.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            p.name: {
                                "type": p.type,
                                "description": p.description,
                                **({"enum": p.enum} if p.enum else {}),
                            }
                            for p in t.parameters
                        },
                        "required": [p.name for p in t.parameters if p.required],
                    },
                },
            }
            for t in self.tools
        ]
    
    async def plan(self, intent: str, context: ExecutionContext) -> Plan:
        """使用 Function Calling 生成计划"""
        
        messages = [
            {"role": "system", "content": "You are a content transformation planner."},
            {"role": "user", "content": f"Create a plan to: {intent}"},
        ]
        
        plan_steps = []
        
        for _ in range(20):  # 最多 20 步
            response = await self.llm.chat(
                messages,
                tools=self.to_openai_functions(),
                tool_choice="auto",
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                # LLM 选择调用工具
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    plan_steps.append(PlanStep(
                        tool_name=tool_name,
                        parameters=arguments,
                        reasoning=message.content or "",
                    ))
                    
                    # 执行工具获取观察
                    tool = self.tool_registry[tool_name]
                    result = await self._execute_tool(tool, arguments, context)
                    
                    # 添加观察回对话
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result),
                    })
            else:
                # LLM 认为任务完成
                break
        
        return Plan(steps=plan_steps)
```

---

> **"工具是 AI 的肢体。没有工具，LLM 只是空谈；有了 MCP，它变成了万能工匠。Udify 的工具生态不是封闭花园，而是热带雨林——每个开发者都可以播种，每个用户都可以采摘。"**
>
> —— Udify MCP 生态设计原则
