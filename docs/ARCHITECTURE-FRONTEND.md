<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 前端架构设计

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: ReactFlow DAG 编辑器、状态管理、WebSocket 实时协作、组件设计系统、性能优化

---

## 1. 前端架构总览

### 技术栈

| 层级 | 技术 | 理由 |
|------|------|------|
| **框架** | Next.js 15 (App Router) | SSR/SSG、Edge Runtime、API Routes |
| **语言** | TypeScript 5.5 (strict) | 类型安全、IDE 支持 |
| **样式** | Tailwind CSS + shadcn/ui | Utility-first、Radix 无障碍基础 |
| **状态** | Zustand + TanStack Query | 轻量客户端状态 + 服务端状态同步 |
| **DAG 编辑器** | ReactFlow 11 | 行业标准、高度可定制、性能优秀 |
| **可视化** | D3.js + Recharts | 数据图表、评估结果展示 |
| **3D 预览** | React Three Fiber | 游戏资源实时预览 |
| **协作** | Yjs + WebSocket | CRDT、实时协同编辑 |
| **构建** | Next.js ( Turbopack ) | 快速 HMR、优化打包 |
| **测试** | Vitest + Playwright + Storybook | 单元 + E2E + 组件文档 |

### 应用目录结构

```
app/
  (marketing)/          # 营销页面组
    page.tsx            # 首页
    about/
    pricing/
    blog/
  (platform)/           # 平台功能（需登录）
    layout.tsx          # 平台 Shell（侧边栏 + 头部）
    dashboard/page.tsx
    discover/page.tsx
    project/[id]/
      page.tsx          # 项目详情
      edit/page.tsx     # DAG 编辑器
      play/page.tsx     # Web Player 预览
    profile/[user]/page.tsx
    settings/page.tsx
  api/                  # API Routes（BFF 层）

components/
  ui/                   # shadcn/ui 基础组件
  dag/                  # DAG 编辑器组件
  perception/           # 感知层可视化
  evaluation/           # 评估结果展示
  collaboration/        # 协作组件（光标、头像）
  preview/              # 资源预览（3D/纹理/音频）

hooks/
  useDagStore.ts
  useProject.ts
  useCollaboration.ts
  useRealtime.ts

stores/
  dagStore.ts           # Zustand: DAG 状态
  projectStore.ts       # Zustand: 项目元数据
  uiStore.ts            # Zustand: UI 状态（主题、面板）
  userStore.ts          # Zustand: 用户状态

lib/
  api.ts                # 自动生成的 Typed API Client (openapi-typescript)
  websocket.ts          # WebSocket 连接管理
  crdt.ts               # Yjs 封装
  wasm.ts               # WASM 模块加载器
```

---

## 2. ReactFlow DAG 编辑器

### 2.1 节点类型 Schema

```typescript
// types/dag.ts

export type UDifyNodeType =
  | 'source'        // 源内容（CDL 根）
  | 'intent'        // 用户意图
  | 'perception'    // 感知引擎输出
  | 'planning'      // 规划器输出
  | 'operation'     // 原子操作
  | 'evaluation'    // 评估结果
  | 'execution'     // 执行结果
  | 'asset'         // 资源文件
  | 'decision'      // 人工决策点
  | 'template';     // 模板引用

export interface UDifyNodeData {
  label: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'paused' | 'waiting_for_approval';
  progress?: number;
  
  // 类型特定数据
  operation?: {
    op_type: string;
    target_id: string;
    property_changes?: Record<string, { old: any; new: any }>;
    risk_level: 'low' | 'medium' | 'high' | 'critical';
    requires_approval: boolean;
  };
  
  evaluation?: {
    quality: number;
    innovation: number;
    compatibility: number;
    safety: number;
    performance: number;
    overall: number;
  };
  
  asset?: {
    asset_type: 'texture' | 'model' | 'audio' | 'script';
    preview_url?: string;
    file_size: number;
  };
  
  logs?: string[];
  errors?: string[];
}

export type UDifyEdgeType = 'data-flow' | 'dependency' | 'approval' | 'fallback' | 'feedback';

export interface UDifyEdgeData {
  edge_type: UDifyEdgeType;
  condition?: string;
  weight?: number;
}
```

### 2.2 核心编辑器组件

```tsx
// components/dag/TransformationEditor.tsx

'use client';

import { useCallback, useState } from 'react';
import ReactFlow, {
  Background, Controls, MiniMap, useNodesState, useEdgesState,
  addEdge, Connection, Panel, useReactFlow,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { OperationNode } from './nodes/OperationNode';
import { IntentNode } from './nodes/IntentNode';
import { EvaluationNode } from './nodes/EvaluationNode';
import { useCollaboration } from '@/hooks/useCollaboration';
import { useDagStore } from '@/stores/dagStore';

const nodeTypes = { operation: OperationNode, intent: IntentNode, evaluation: EvaluationNode };

export function TransformationEditor({ projectId }: { projectId: string }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const { fitView } = useReactFlow();
  const store = useDagStore();
  const collab = useCollaboration(projectId);

  // 连接节点
  const onConnect = useCallback((conn: Connection) => {
    const edge = { ...conn, id: `e-${conn.source}-${conn.target}`,
      type: 'smoothstep', animated: true, data: { edge_type: 'data-flow' } };
    setEdges((eds) => addEdge(edge, eds));
    collab.broadcastEdgeAdd(edge);
  }, [setEdges, collab]);

  // 执行 DAG
  const onRun = useCallback(async () => {
    const order = topologicalSort(nodes, edges);
    store.setExecutionState('running');
    
    for (const nodeId of order) {
      setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, status: 'running' } } : n));
      try {
        const result = await api.executeNode(projectId, nodeId);
        setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, status: 'success', ...result } } : n));
      } catch (err) {
        setNodes(nds => nds.map(n => n.id === nodeId ? { ...n, data: { ...n.data, status: 'failed', errors: [err.message] } } : n));
        break;
      }
    }
    store.setExecutionState('completed');
  }, [nodes, edges, projectId, setNodes, store]);

  return (
    <div className="flex h-full">
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes} edges={edges}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_evt, node) => setSelectedNode(node.id)}
          nodeTypes={nodeTypes} fitView
        >
          <Background gap={12} size={1} />
          <Controls />
          <MiniMap nodeStrokeWidth={3} zoomable pannable />
          
          <Panel position="top-left">
            <Toolbar onRun={onRun} status={store.executionState} />
          </Panel>
          
          <Panel position="bottom-right">
            <CollaborationIndicator users={collab.activeUsers} />
          </Panel>
        </ReactFlow>
      </div>
      
      <PropertyPanel
        node={nodes.find(n => n.id === selectedNode)}
        onUpdate={(updates) => setNodes(nds => nds.map(n => n.id === selectedNode ? { ...n, data: { ...n.data, ...updates } } : n))}
      />
    </div>
  );
}

// 拓扑排序用于 DAG 执行
function topologicalSort(nodes: Node[], edges: Edge[]): string[] {
  const adj = new Map<string, string[]>();
  const inDegree = new Map<string, number>();
  nodes.forEach(n => { adj.set(n.id, []); inDegree.set(n.id, 0); });
  edges.forEach(e => { adj.get(e.source)!.push(e.target); inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1); });
  const queue = Array.from(inDegree.entries()).filter(([, d]) => d === 0).map(([id]) => id);
  const result: string[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    result.push(id);
    adj.get(id)!.forEach(next => { const d = inDegree.get(next)! - 1; inDegree.set(next, d); if (d === 0) queue.push(next); });
  }
  return result;
}
```

### 2.3 自定义节点示例

```tsx
// components/dag/nodes/OperationNode.tsx

import { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Loader2, CheckCircle2, XCircle, Shield } from 'lucide-react';

const statusConfig = {
  pending:    { icon: Loader2, color: 'text-gray-400', bg: 'bg-gray-50', border: 'border-gray-200' },
  running:    { icon: Loader2, color: 'text-blue-500', bg: 'bg-blue-50', border: 'border-blue-300' },
  success:    { icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50', border: 'border-green-300' },
  failed:     { icon: XCircle, color: 'text-red-500', bg: 'bg-red-50', border: 'border-red-300' },
  paused:     { icon: Shield, color: 'text-amber-500', bg: 'bg-amber-50', border: 'border-amber-300' },
  waiting_for_approval: { icon: Shield, color: 'text-purple-500', bg: 'bg-purple-50', border: 'border-purple-300' },
};

const riskBorder = { low: 'border-l-green-400', medium: 'border-l-yellow-400', high: 'border-l-orange-500', critical: 'border-l-red-500' };

export const OperationNode = memo(({ data, selected }: NodeProps) => {
  const cfg = statusConfig[data.status];
  const Icon = cfg.icon;
  
  return (
    <div className={`min-w-[220px] rounded-lg shadow-sm border border-l-4 ${cfg.bg} ${cfg.border} ${riskBorder[data.operation?.risk_level || 'low']} ${selected ? 'ring-2 ring-blue-500' : ''}`}>
      <Handle type="target" position={Position.Top} className="!w-2.5 !h-2.5 !bg-blue-500" />
      
      <div className="px-3 py-2 flex items-center gap-2 border-b border-gray-200/50">
        <Icon className={`w-4 h-4 ${data.status === 'running' ? 'animate-spin' : ''} ${cfg.color}`} />
        <span className="text-sm font-medium truncate">{data.label}</span>
        {data.operation?.requires_approval && (
          <span className="ml-auto text-[9px] font-bold bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">APPROVAL</span>
        )}
      </div>
      
      {data.status === 'running' && data.progress !== undefined && (
        <div className="px-3 py-1.5">
          <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 transition-all" style={{ width: `${data.progress}%` }} />
          </div>
          <span className="text-[10px] text-gray-500">{data.progress}%</span>
        </div>
      )}
      
      {data.operation?.property_changes && (
        <div className="px-3 py-2 space-y-1">
          {Object.entries(data.operation.property_changes).slice(0, 3).map(([key, ch]) => (
            <div key={key} className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="text-gray-500">{key}:</span>
              <span className="text-red-500 line-through">{JSON.stringify(ch.old).slice(0, 15)}</span>
              <span className="text-gray-300">→</span>
              <span className="text-green-600">{JSON.stringify(ch.new).slice(0, 15)}</span>
            </div>
          ))}
        </div>
      )}
      
      {data.errors && data.errors.length > 0 && (
        <div className="px-3 py-1.5 bg-red-100 border-t border-red-200">
          <p className="text-[10px] text-red-700 font-mono line-clamp-2">{data.errors[0]}</p>
        </div>
      )}
      
      <Handle type="source" position={Position.Bottom} className="!w-2.5 !h-2.5 !bg-blue-500" />
    </div>
  );
});
OperationNode.displayName = 'OperationNode';
```

---

## 3. 状态管理架构

### 3.1 Zustand DAG Store

```typescript
// stores/dagStore.ts

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import { Node, Edge } from 'reactflow';

interface DagStore {
  nodes: Node[];
  edges: Edge[];
  selectedNodeIds: string[];
  executionState: 'idle' | 'running' | 'paused' | 'completed' | 'failed';
  history: { nodes: Node[]; edges: Edge[]; timestamp: number }[];
  historyIndex: number;
  canUndo: boolean;
  canRedo: boolean;

  setNodes: (updater: Node[] | ((prev: Node[]) => Node[])) => void;
  setEdges: (updater: Edge[] | ((prev: Edge[]) => Edge[])) => void;
  addNode: (node: Node) => void;
  updateNodeData: (id: string, data: Partial<Node['data']>) => void;
  removeNode: (id: string) => void;
  selectNode: (id: string | null) => void;
  
  setExecutionState: (s: DagStore['executionState']) => void;
  
  undo: () => void;
  redo: () => void;
  saveSnapshot: () => void;
}

export const useDagStore = create<DagStore>()(
  devtools(
    immer((set, get) => ({
      nodes: [], edges: [], selectedNodeIds: [],
      executionState: 'idle', history: [], historyIndex: -1, canUndo: false, canRedo: false,

      setNodes: (updater) => { set(s => { s.nodes = typeof updater === 'function' ? updater(s.nodes) : updater; }); get().saveSnapshot(); },
      setEdges: (updater) => { set(s => { s.edges = typeof updater === 'function' ? updater(s.edges) : updater; }); get().saveSnapshot(); },
      
      addNode: (node) => { set(s => { s.nodes.push(node); }); get().saveSnapshot(); },
      
      updateNodeData: (id, data) => set(s => {
        const n = s.nodes.find(x => x.id === id);
        if (n) n.data = { ...n.data, ...data };
      }),
      
      removeNode: (id) => set(s => {
        s.nodes = s.nodes.filter(n => n.id !== id);
        s.edges = s.edges.filter(e => e.source !== id && e.target !== id);
        get().saveSnapshot();
      }),
      
      selectNode: (id) => set(s => { s.selectedNodeIds = id ? [id] : []; }),
      setExecutionState: (state) => set({ executionState: state }),
      
      saveSnapshot: () => set(s => {
        const snap = { nodes: JSON.parse(JSON.stringify(s.nodes)), edges: JSON.parse(JSON.stringify(s.edges)), timestamp: Date.now() };
        s.history = s.history.slice(0, s.historyIndex + 1);
        s.history.push(snap);
        if (s.history.length > 100) { s.history.shift(); }
        s.historyIndex = s.history.length - 1;
        s.canUndo = s.historyIndex > 0;
        s.canRedo = false;
      }),
      
      undo: () => set(s => {
        if (s.historyIndex <= 0) return;
        s.historyIndex--;
        const snap = s.history[s.historyIndex];
        s.nodes = JSON.parse(JSON.stringify(snap.nodes));
        s.edges = JSON.parse(JSON.stringify(snap.edges));
        s.canUndo = s.historyIndex > 0;
        s.canRedo = true;
      }),
      
      redo: () => set(s => {
        if (s.historyIndex >= s.history.length - 1) return;
        s.historyIndex++;
        const snap = s.history[s.historyIndex];
        s.nodes = JSON.parse(JSON.stringify(snap.nodes));
        s.edges = JSON.parse(JSON.stringify(snap.edges));
        s.canUndo = true;
        s.canRedo = s.historyIndex < s.history.length - 1;
      }),
    })),
    { name: 'DagStore' }
  )
);
```

### 3.2 服务端状态同步（TanStack Query）

```typescript
// hooks/useProject.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.projects.get(projectId),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePatchExecution(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patchId: string) => api.patches.execute(projectId, patchId),
    onMutate: async (patchId) => {
      await qc.cancelQueries({ queryKey: ['patch', patchId] });
      const prev = qc.getQueryData(['patch', patchId]);
      qc.setQueryData(['patch', patchId], (old: any) => ({ ...old, status: 'running' }));
      return { prev };
    },
    onError: (_err, patchId, ctx) => { qc.setQueryData(['patch', patchId], ctx?.prev); },
    onSettled: (_data, _err, patchId) => {
      qc.invalidateQueries({ queryKey: ['patch', patchId] });
    },
  });
}
```

---

## 4. 实时协作系统

### 4.1 Yjs + WebSocket 封装

```typescript
// lib/collaboration.ts

import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';

export class CollaborationManager {
  private doc: Y.Doc;
  private provider: WebsocketProvider;
  private awareness: any;
  private yNodes: Y.Array<Y.Map<any>>;
  private yEdges: Y.Array<Y.Map<any>>;

  constructor(projectId: string, user: { id: string; name: string }) {
    this.doc = new Y.Doc();
    this.provider = new WebsocketProvider('wss://collab.udify.dev', projectId, this.doc);
    this.awareness = this.provider.awareness;
    this.yNodes = this.doc.getArray('nodes');
    this.yEdges = this.doc.getArray('edges');
    
    this.awareness.setLocalStateField('user', {
      id: user.id, name: user.name,
      color: this.genColor(user.id),
    });
  }

  syncNodes(localNodes: Node[], onChange: (nodes: Node[]) => void) {
    // Yjs -> 本地
    this.yNodes.observe(() => {
      onChange(this.yNodes.toArray().map(yn => ({
        id: yn.get('id'), type: yn.get('type'), position: yn.get('position'), data: yn.get('data'),
      })));
    });
  }

  updateCursor(pos: { x: number; y: number }) {
    this.awareness.setLocalStateField('cursor', pos);
  }

  getRemoteCursors() {
    return Array.from(this.awareness.getStates().values())
      .filter((s: any) => s.cursor && s.user)
      .map((s: any) => ({ userId: s.user.id, username: s.user.name, color: s.user.color, x: s.cursor.x, y: s.cursor.y }));
  }

  private genColor(id: string): string {
    const colors = ['#EF4444','#F97316','#F59E0B','#84CC16','#10B981','#06B6D4','#3B82F6','#6366F1','#8B5CF6','#EC4899'];
    let h = 0; for (const c of id) h = c.charCodeAt(0) + ((h << 5) - h);
    return colors[Math.abs(h) % colors.length];
  }

  destroy() { this.provider.destroy(); this.doc.destroy(); }
}
```

### 4.2 协作光标组件

```tsx
// components/collaboration/CursorOverlay.tsx

'use client';

import { useEffect, useState } from 'react';

export function CursorOverlay({ cursors }: { cursors: Array<{ userId: string; username: string; color: string; x: number; y: number }> }) {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {cursors.map(c => <Cursor key={c.userId} {...c} />)}
    </div>
  );
}

function Cursor({ username, color, x, y }: { username: string; color: string; x: number; y: number }) {
  const [pos, setPos] = useState({ x, y });
  
  useEffect(() => {
    let raf: number;
    const animate = () => {
      setPos(p => ({ x: p.x + (x - p.x) * 0.3, y: p.y + (y - p.y) * 0.3 }));
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, [x, y]);

  return (
    <div className="absolute" style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M5.65 12.37L0.5 16.88V1.19L11.78 12.37H5.65Z" fill={color} stroke="white" strokeWidth="1.5"/>
      </svg>
      <span className="absolute left-3 top-3 text-[10px] text-white px-1 rounded" style={{ backgroundColor: color }}>{username}</span>
    </div>
  );
}
```

---

## 5. 组件设计系统

### 5.1 设计 Token

```typescript
// design-system/tokens.ts

export const tokens = {
  colors: {
    brand: { 50: '#f0f9ff', 100: '#e0f2fe', 200: '#bae6fd', 300: '#7dd3fc', 400: '#38bdf8', 500: '#0ea5e9', 600: '#0284c7', 700: '#0369a1', 800: '#075985', 900: '#0c4a6e' },
    success: { light: '#dcfce7', DEFAULT: '#22c55e', dark: '#15803d' },
    warning: { light: '#fef9c3', DEFAULT: '#eab308', dark: '#a16207' },
    danger:  { light: '#fee2e2', DEFAULT: '#ef4444', dark: '#b91c1c' },
    node: {
      pending: { bg: '#f9fafb', border: '#e5e7eb' },
      running: { bg: '#eff6ff', border: '#3b82f6' },
      success: { bg: '#f0fdf4', border: '#22c55e' },
      failed:  { bg: '#fef2f2', border: '#ef4444' },
      paused:  { bg: '#fffbeb', border: '#f59e0b' },
    },
    risk: { low: '#22c55e', medium: '#eab308', high: '#f97316', critical: '#ef4444' },
  },
  shadows: {
    node: '0 2px 4px rgb(0 0 0 / 0.1), 0 0 0 1px rgb(0 0 0 / 0.05)',
    'node-selected': '0 0 0 2px #3b82f6, 0 4px 12px rgb(59 130 246 / 0.2)',
  },
  fontFamily: { sans: 'Inter, system-ui, sans-serif', mono: 'JetBrains Mono, Fira Code, monospace' },
} as const;
```

---

## 6. 性能优化策略

| 策略 | 实现 | 效果 |
|------|------|------|
| **虚拟列表** | `@tanstack/react-virtual` | 1000+ 项目流畅滚动 |
| **React.memo** | 所有自定义节点包裹 memo | 减少重渲染 80%+ |
| **Viewport Culling** | ReactFlow 内置 | 只渲染可视节点 |
| **代码分割** | `dynamic()` 按需加载编辑器 | 首屏 < 200KB |
| **图片懒加载** | `loading="lazy"` + blurhash 占位 | 感知加载速度提升 |
| **请求去重** | TanStack Query `staleTime` | 减少重复 API 调用 |
| **乐观更新** | Mutation `onMutate` | UI 响应 < 16ms |
| **WASM 解析** | Rust/WASM 游戏文件头检测 | 解析速度提升 10x |
| **WebGPU 预览** | 3D 模型实时渲染 | 60fps 预览 |

---

> **"前端是用户与意图之间的唯一界面。ReactFlow 让复杂的改造计划变得可触摸、可理解、可协作。每一个像素都应该服务于同一个目标：让用户专注于创意，而非技术。"**
>
> —— Udify 前端架构原则
