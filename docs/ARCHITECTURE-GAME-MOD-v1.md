# Udify 游戏魔改架构设计 v1.0

> **目标**: 基于 Udify 意图驱动架构 + miu2d 深度分析，制定可落地的游戏魔改系统架构
> **范围**: 聚焦于游戏 Mod 自动化，暂不考虑跨媒介扩展
> **参考项目**: [miu2d](https://github.com/luckyyyyy/miu2d) — 2D ARPG 引擎（176k 行，TS+Rust+React）
> **日期**: 2026-04-27

---

## 目录

1. [战略定位](#1-战略定位)
2. [miu2d 深度分析](#2-miu2d-深度分析)
3. [核心架构](#3-核心架构)
4. [感知层：游戏资产解析](#4-感知层游戏资产解析)
5. [认知层：游戏语义理解](#5-认知层游戏语义理解)
6. [规划层：意图到修改计划](#6-规划层意图到修改计划)
7. [执行层：Patch 到文件变更](#7-执行层patch-到文件变更)
8. [验证层：修改效果确认](#8-验证层修改效果确认)
9. [编辑器集成层](#9-编辑器集成层)
10. [技术栈与依赖](#10-技术栈与依赖)
11. [实施路线图](#11-实施路线图)
12. [风险与缓解](#12-风险与缓解)

---

## 1. 战略定位

### 1.1 为什么选择 miu2d 作为首攻目标

| 维度 | miu2d 的优势 |
|------|-------------|
| **数据透明** | 8 种二进制格式全部逆向工程完成，有详细文档（`docs/binary-formats.md` 等） |
| **编辑能力** | 内置 Dashboard 编辑器（13 个模块），验证了数据可被结构化编辑 |
| **运行时可控** | 基于 Web 技术，可直接在浏览器中运行和测试修改 |
| **脚本杠杆** | 双脚本系统（218 DSL 命令 + Lua 5.4），脚本是高 ROI 的魔改入口 |
| **社区验证** | 已成功复刻 3 款完整游戏，证明引擎成熟度 |
| **AI 友好** | TypeScript + Rust，类型系统完整，Zod Schema 共享前后端 |

### 1.2 与通用架构的关系

本架构是 Udify 通用架构在游戏领域的**特化实现**：

```
Udify 通用架构                    游戏魔改特化架构
─────────────────────────────────────────────────────────
ContentGraph                →   GameWorldGraph（游戏世界图谱）
CDLPatch                    →   GameModPatch（游戏 Mod 补丁）
PerceptionEngine            →   AssetDecoder + WorldBuilder
PlanningEngine (MCTS)       →   ModPlanner（Mod 规划器）
ExecutionEngine             →   FilePatcher + ScriptInjector
ValidationEngine            →   RuntimeValidator（运行时验证）
```

**原则**: 先垂直做深（游戏），再横向扩展（音乐/视频/小说）。

---

## 2. miu2d 深度分析

### 2.1 引擎架构总览

```
miu2d (176k 行，11 个包)
├── @miu2d/engine          # 纯 TS 游戏引擎（215 文件，19 模块）
│   ├── renderer/          # 原始 WebGL 渲染（SpriteBatcher, RectBatcher）
│   ├── character/         # 8 级继承链（Sprite → Player/NPC）
│   ├── combat/            # 伤害计算、击退、死亡重生
│   ├── magic/             # 22 MoveKind × 10 SpecialKind
│   ├── npc/               # 行为状态机（idle/patrol/chase/flee/dead）
│   ├── map/               # 多层瓦片、障碍网格、陷阱区域
│   ├── script/            # DSL VM（parser + executor）+ Lua 5.4（wasmoon）
│   ├── player/            # 控制器、背包、装备、技能槽
│   ├── obj/               # 可交互场景对象（宝箱、门、障碍）
│   ├── weather/           # 雨、雪、屏幕水滴
│   ├── audio/             # Web Audio API（BGM + 位置音效）
│   ├── resource/          # 8 种二进制格式解码器
│   ├── storage/           # IndexedDB + 云端存档
│   └── wasm/              # Rust WASM（A* 寻路、SpatialHash、zstd）
├── @miu2d/dashboard       # VS Code 风格编辑器（13 个编辑模块）
├── @miu2d/game            # 游戏运行时（3 套 UI 主题）
├── @miu2d/server          # Hono + tRPC + Prisma + PostgreSQL
├── @miu2d/types           # Zod Schema 共享（18 个领域模块）
└── @miu2d/converter       # Rust CLI：格式批量转换
```

### 2.2 数据资产分析

#### 2.2.1 二进制格式（8 种）

| 格式 | 内容 | 可编辑性 | 魔改价值 |
|------|------|---------|---------|
| **ASF** | 精灵动画帧（RLE 压缩、调色板索引 RGBA） | 中（需专用工具） | 高（角色外观、技能特效） |
| **MPC** | 资源包容器（精灵图集） | 中 | 高（批量替换贴图） |
| **MAP** | 地图数据（多层瓦片、障碍、陷阱） | 高 | 高（关卡设计） |
| **SHD** | 阴影/高度图 | 中 | 中（光影氛围） |
| **XNB** | XNA 二进制（音频资产） | 低 | 低 |
| **MSF** | Miu 精灵格式 v2（索引调色板 + zstd） | 高 | 高（精灵替换） |
| **MMF** | Miu 地图格式（zstd 压缩二进制） | 高 | 高（地图编辑） |
| **INI/OBJ** | 配置文件（GBK/UTF-8） | **极高** | **极高（数值、脚本引用）** |

#### 2.2.2 配置数据（INI/OBJ）— 魔改主战场

INI/OBJ 文件是**文本配置**，包含游戏的核心参数：

```ini
; 示例：角色属性配置
[Main]
Name=南宫飞云
Level=1
MaxLife=100
MaxMana=50
Strength=10
Dexterity=8
Constitution=12
Intelligence=6

[Magic]
Magic1=fireball.ini
Magic2=heal.ini

[Script]
OnTalk=talk/npc_001.txt
OnDeath=script/death_001.txt
```

**魔改价值排序**:
1. **数值平衡**（HP/MP/攻击力/经验值/掉落率）— 零门槛，高 impact
2. **脚本逻辑**（对话分支、任务触发、事件链）— 中门槛，极高 impact
3. **技能配置**（MoveKind + SpecialKind 组合）— 中门槛，高 impact
4. **地图数据**（MAP/MMF）— 高门槛，高 impact
5. **美术资源**（ASF/MSF/MPC）— 高门槛，中 impact

#### 2.2.3 脚本系统 — 魔改的核心杠杆

**DSL 脚本（.txt / .npc）**:
- 218 个命令，分 9 大类
- 关键命令示例:
  - `Say`, `Talk`, `Choose` — 对话系统
  - `AddLife`, `AddMana`, `SetPlayerPos` — 玩家属性
  - `AddNpc`, `DelNpc`, `SetNpcRelation` — NPC 管理
  - `LoadMap`, `Assign`, `If/Goto` — 流程控制
  - `AddGoods`, `DelGoods`, `ClearGoods` — 物品管理
  - `PlayMusic`, `PlaySound` — 音频
  - `FadeIn`, `FadeOut`, `BeginRain` — 视觉效果

**Lua 脚本（.lua）**:
- 完整 Lua 5.4 运行时（wasmoon WASM）
- 170 个 GameAPI 函数暴露为 PascalCase 全局变量
- wasmoon 自动桥接 JS async 到 Lua coroutine

```lua
-- 示例 Lua 游戏脚本
FadeOut()
LoadMap("map/town.map")
SetPlayerPos(10, 15)
FadeIn()
Talk(0, "Welcome to the village.")
local choice = Choose("Join the quest?", "Yes", "No")
if choice == 1 then
  AddMagic("magic/fireball.ini")
  AddExp(500)
end
```

**关键洞察**: 脚本系统已经是一个**声明式 DSL**，非常适合 AI 生成和修改。

### 2.3 Dashboard 编辑器分析

miu2d 的 Dashboard 有 13 个编辑模块，这直接映射了游戏的可编辑维度：

| 模块 | 编辑内容 | 对应魔改场景 |
|------|---------|------------|
| Magic Editor | 技能配置 + ASF 精灵预览 | "增加新技能"、"修改技能伤害" |
| NPC Editor | 属性、脚本、AI 行为、精灵 | "让某个 NPC 变强"、"修改对话" |
| Scene Editor | 地图、出生点、陷阱、触发器 | "新增一个场景"、"修改关卡布局" |
| Item Editor | 武器、护甲、消耗品、掉落表 | "新增传说武器"、"调整掉落率" |
| Shop Editor | 商店库存和价格 | "让商店卖更好的东西" |
| Dialog Editor | 分支对话树 + 头像分配 | "改写剧情对话" |
| Player Editor | 初始属性、装备、技能槽 | "让主角一开始就很强" |
| Level Editor | 经验曲线和属性成长 | "加快升级速度" |
| Game Config | 全局设置（掉落、玩家默认） | "全局难度调整" |
| File Manager | 文件树 + 拖拽上传 | 资产替换 |
| Resources | 资源浏览器 | 资源管理 |
| Statistics | 数据概览 | 平衡性分析 |

**关键洞察**: Dashboard 的每个编辑模块都对应一种**数据 Schema**。这些 Schema 可以被 AI 直接理解和生成。

---

## 3. 核心架构

### 3.1 系统总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           用户层 (User Layer)                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ 自然语言输入  │  │ 编辑器 GUI   │  │ 预设模板     │  │ 社区 Mod 市场│   │
│  │ "让游戏更难" │  │ (ReactFlow)  │  │ "武侠变仙侠" │  │ 下载/分享    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
└─────────┼─────────────────┼─────────────────┼─────────────────┼───────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         意图层 (Intent Layer)                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ Intent Parser                                                       │   │
│  │  • 自然语言 → 结构化意图 (目标子系统 + 修改类型 + 约束条件)           │   │
│  │  • 示例: "让第一个 BOSS 的血量翻倍"                                   │   │
│  │    → {target: "npc/boss_001.ini", property: "MaxLife", factor: 2.0}  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        感知层 (Perception Layer)                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ Asset Decoder   │  │ World Builder   │  │ Schema Extractor│             │
│  │ (8 种格式解析)   │  │ (构建游戏世界图谱)│  │ (提取类型Schema)│             │
│  │                 │  │                 │  │                 │             │
│  │ • ASF/MSF 精灵  │  │ • 角色关系网     │  │ • NPC Schema    │             │
│  │ • MAP/MMF 地图  │  │ • 地图连接图     │  │ • Item Schema   │             │
│  │ • INI/OBJ 配置  │  │ • 任务依赖链     │  │ • Magic Schema  │             │
│  │ • Lua/DSL 脚本  │  │ • 物品经济系统   │  │ • Map Schema    │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           └─────────────────────┴────────┬───────────┘                      │
│                                          ▼                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ GameWorldGraph (游戏世界图谱)                                         │  │
│  │  • 节点: Character, Item, Magic, Map, Scene, Quest, Dialog          │  │
│  │  • 边:  contains, depends_on, triggers, requires, references        │  │
│  │  • 属性: 数值参数、脚本引用、资源路径、状态标记                       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        规划层 (Planning Layer)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ModPlanner (MCTS + LLM)                                             │   │
│  │                                                                     │   │
│  │  ActionSpace: 针对游戏特化的动作生成                                  │   │
│  │    • NUMERIC_SCALE: 数值缩放 (HP×2, 掉落率+50%)                     │   │
│  │    • SCRIPT_INSERT: 脚本插入 (新增事件、修改对话分支)                 │   │
│  │    • ASSET_REPLACE: 资源替换 (精灵图、音频)                          │   │
│  │    • MAP_EDIT: 地图编辑 (障碍、出生点、触发区)                       │   │
│  │    • MAGIC_COMPOSE: 技能组合 (MoveKind + SpecialKind)               │   │
│  │                                                                     │   │
│  │  ValueFunction: 游戏特化评估                                         │   │
│  │    • 平衡性: 修改后数值是否在合理范围                                 │   │
│  │    • 一致性: 引用是否仍然有效 (NPC 引用的脚本是否存在)                 │   │
│  │    • 可玩性: 难度曲线是否平滑                                         │   │
│  │    • 保守性: 修改范围是否受控                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        补丁层 (Patch Layer)                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ GameModPatch (CDLPatch 特化)                                        │   │
│  │                                                                     │   │
│  │  操作类型:                                                          │   │
│  │    • MODIFY_INI: 修改 INI/OBJ 配置文件中的键值                       │   │
│  │    • INSERT_SCRIPT: 在 Lua/DSL 脚本中插入/替换代码块                 │   │
│  │    • REPLACE_ASSET: 替换二进制资源文件                               │   │
│  │    • EDIT_MAP: 修改 MAP/MMF 中的瓦片/障碍/触发器数据                 │   │
│  │    • ADD_RECORD: 在列表型配置中新增记录 (如新增物品、技能)            │   │
│  │                                                                     │   │
│  │  验证: PatchValidator (引用完整性 + 数值范围 + 格式合法性)            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       执行层 (Execution Layer)                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ FilePatcher     │  │ ScriptInjector  │  │ AssetBundler    │             │
│  │ (文件级修改)     │  │ (脚本级注入)     │  │ (资源打包)       │             │
│  │                 │  │                 │  │                 │             │
│  │ • INI 键值修改  │  │ • Lua 代码插入  │  │ • MSF 重新编码  │             │
│  │ • 文本替换      │  │ • DSL 命令替换  │  │ • MPC 重新打包  │             │
│  │ • 文件备份      │  │ • 语法校验      │  │ • 增量更新包    │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           └─────────────────────┴────────┬───────────┘                      │
│                                          ▼                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ ModPackage (Mod 包)                                                 │  │
│  │  • 修改后的文件集合                                                  │  │
│  │  • 增量补丁 (二进制 diff)                                            │  │
│  │  • 元数据 (作者、版本、依赖、兼容性)                                  │  │
│  │  • 回滚脚本                                                          │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       验证层 (Validation Layer)                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │ Static Validator│  │ Runtime Validator│  │ Playtest Agent  │             │
│  │ (静态检查)       │  │ (运行时检查)     │  │ (自动化试玩)     │             │
│  │                 │  │                 │  │                 │             │
│  │ • 引用完整性    │  │ • 游戏能否启动  │  │ • 能否通关      │             │
│  │ • 数值范围      │  │ • 脚本是否报错  │  │ • 战斗是否平衡  │             │
│  │ • 格式合法性    │  │ • 资源能否加载  │  │ • 任务是否完成  │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 与 miu2d 的集成点

```
Udify 游戏魔改系统              miu2d 引擎/编辑器
─────────────────────────────────────────────────
AssetDecoder (ASF/MSF)    →   @miu2d/engine/resource/
AssetDecoder (MAP/MMF)    →   @miu2d/engine/map/
AssetDecoder (INI/OBJ)    →   @miu2d/types/ (Zod Schema)
AssetDecoder (Lua/DSL)    →   @miu2d/engine/script/
WorldBuilder              →   @miu2d/dashboard/ (编辑器数据模型)
ModPlanner                →   @miu2d/dashboard/modules/ (编辑操作)
FilePatcher               →   @miu2d/converter/ (格式转换)
RuntimeValidator          →   @miu2d/engine/runtime/ + @miu2d/game/
```

---

## 4. 感知层：游戏资产解析

### 4.1 资产解析器设计

```python
class GameAssetDecoder:
    """游戏资产解码器 — 将二进制/文本资产解析为结构化数据"""

    decoders: Dict[str, AssetDecoder] = {
        # 文本配置（最高优先级 — 魔改主战场）
        ".ini": IniDecoder(),
        ".obj": ObjDecoder(),
        ".txt": DslScriptDecoder(),   # DSL 脚本
        ".npc": DslScriptDecoder(),
        ".lua": LuaScriptDecoder(),   # Lua 脚本

        # 二进制格式（需要专用解码器）
        ".asf": AsfDecoder(),         # 精灵动画
        ".msf": MsfDecoder(),         # Miu 精灵格式 v2
        ".mpc": MpcDecoder(),         # 资源包
        ".map": MapDecoder(),         # 地图数据
        ".mmf": MmfDecoder(),         # Miu 地图格式
        ".shd": ShdDecoder(),         # 阴影/高度图
        ".xnb": XnbDecoder(),         # XNA 音频
    }
```

### 4.2 INI/OBJ 解析器（最高优先级）

INI/OBJ 是**文本格式**，解析简单，但语义丰富。需要领域特定的 Schema：

```python
@dataclass
class NpcConfig:
    """NPC 配置 Schema（基于 miu2d 的 NPC Editor 数据模型）"""
    id: str
    name: str
    level: int
    max_life: int
    max_mana: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    magic_slots: List[str]       # 技能引用列表
    script_talk: str             # 对话脚本路径
    script_death: str            # 死亡脚本路径
    sprite_path: str             # 精灵资源路径
    ai_behavior: str             # AI 行为类型
    faction: str                 # 阵营

@dataclass
class ItemConfig:
    """物品配置 Schema"""
    id: str
    name: str
    category: str                # weapon / armor / drug / event
    level_requirement: int
    price: int
    effects: List[ItemEffect]    # 使用效果列表
    equip_position: Optional[str] # 装备位置
    sprite_path: str
    description: str

@dataclass
class MagicConfig:
    """技能配置 Schema（基于 Magic Editor）"""
    id: str
    name: str
    move_kind: str               # 22 种之一
    special_kind: str            # 10 种之一
    level_config: List[MagicLevel]  # 每级配置
    damage_formula: str
    mp_cost: int
    cooldown: float
    sprite_path: str
    sound_effect: str
```

### 4.3 脚本解析器

DSL 脚本解析为 AST（抽象语法树），便于插入、删除、修改命令：

```python
@dataclass
class DslCommand:
    name: str                    # "Say", "AddLife", "LoadMap" 等
    args: List[Union[str, int, float]]
    line_number: int

@dataclass
class DslScript:
    commands: List[DslCommand]
    labels: Dict[str, int]       # Goto 标签映射

class DslScriptDecoder:
    def decode(self, content: str) -> DslScript:
        # 分词 → 解析 → AST
        tokens = self._tokenize(content)
        return self._parse(tokens)

    def encode(self, script: DslScript) -> str:
        # AST → 文本（保留原始格式）
        return "\n".join(cmd.to_string() for cmd in script.commands)
```

Lua 脚本解析使用 Tree-sitter Lua grammar：

```python
class LuaScriptDecoder:
    def decode(self, content: str) -> LuaAST:
        # 使用 tree-sitter 解析为 AST
        tree = self.parser.parse(content.encode())
        return LuaAST(tree.root_node)

    def find_function_calls(self, func_name: str) -> List[ASTNode]:
        # 查找所有特定函数调用（如所有 Talk() 调用）
        return self.ast.query(f'(function_call name: (identifier) @name (#eq? @name "{func_name}"))')
```

### 4.4 游戏世界图谱 (GameWorldGraph)

从解析后的资产构建图结构：

```
GameWorldGraph extends ContentGraph
├── characters: List[NpcConfig]        → 节点类型: CHARACTER
├── items: List[ItemConfig]            → 节点类型: ITEM
├── magics: List[MagicConfig]          → 节点类型: MAGIC
├── maps: List[MapConfig]              → 节点类型: LEVEL
├── quests: List[QuestConfig]          → 节点类型: QUEST (从脚本推导)
├── dialogs: List[DialogConfig]        → 节点类型: DIALOGUE (从脚本推导)
└── shops: List[ShopConfig]            → 节点类型: SHOP

边类型:
  • CHARACTER --HAS_MAGIC--> MAGIC       (角色拥有技能)
  • CHARACTER --DROPS--> ITEM            (角色掉落物品)
  • MAP --CONTAINS--> CHARACTER          (地图包含角色)
  • MAP --CONTAINS--> ITEM               (地图包含物品)
  • QUEST --TRIGGERS--> DIALOGUE         (任务触发对话)
  • DIALOGUE --REQUIRES--> QUEST         (对话需要任务前置)
  • ITEM --RECIPE_REQUIRES--> ITEM       (合成配方)
```

### 4.5 与 miu2d Dashboard 的数据对齐

miu2d Dashboard 编辑器已经定义了完整的数据模型（通过 Zod Schema）。Udify 的感知层直接复用这些 Schema：

```typescript
// miu2d/packages/types/src/gameConfig.ts (已有)
export const GameConfigSchema = z.object({
  player: PlayerConfigSchema,
  drops: DropConfigSchema,
  magicExp: MagicExpConfigSchema,
  // ...
});

// Udify Python 侧使用 pydantic 对齐
class GameConfig(BaseModel):
    player: PlayerConfig
    drops: DropConfig
    magic_exp: MagicExpConfig
    # ...
```

---

## 5. 认知层：游戏语义理解

### 5.1 语义标注系统

在 GameWorldGraph 上叠加语义层，帮助 AI 理解"这是什么"、"它做什么"、"改它会有什么影响"。

```python
@dataclass
class GameSemantics:
    """游戏语义标注"""

    # 角色语义
    character_roles: Dict[str, str]   # boss / merchant / quest_giver / companion
    difficulty_tier: int               # 1-10 难度分级
    story_importance: str              # main / side / optional / easter_egg

    # 经济语义
    item_rarity: str                   # common / rare / epic / legendary
    item_power_level: float            # 相对强度 (基于属性计算)
    drop_source: List[str]             # 哪些怪物/宝箱掉落

    # 技能语义
    magic_archetype: str               # damage / heal / buff / debuff / control
    magic_combo_potential: List[str]   # 可与哪些技能组合

    # 地图语义
    map_region: str                    # 森林 / 城镇 / 地下城 / 雪山
    map_level_range: Tuple[int, int]   # 适合等级范围
    map_connections: List[str]         # 相邻地图
```

### 5.2 影响分析器

当用户说"让第一个 BOSS 变强"时，系统需要理解这会影响什么：

```python
class ImpactAnalyzer:
    """影响分析器 — 分析修改的连锁反应"""

    def analyze_npc_stat_change(self, npc_id: str, stat: str, new_value: float) -> ImpactReport:
        impacts = []

        # 1. 直接影响: 该 NPC 的战斗力变化
        old_power = self._calculate_combat_power(npc_id)
        new_power = self._calculate_combat_power(npc_id, {stat: new_value})
        impacts.append(DirectImpact(
            target=npc_id,
            description=f"战斗力从 {old_power:.1f} 变为 {new_power:.1f} ({new_power/old_power:.1f}x)",
            severity="high" if new_power > old_power * 2 else "medium",
        ))

        # 2. 连锁影响: 掉落物品价值变化
        drops = self.graph.get_drops(npc_id)
        for item in drops:
            old_value = item.power_level
            # 如果 BOSS 变强，其掉落的物品应该也更有价值
            impacts.append(ChainImpact(
                target=item.id,
                description=f"掉落物品 {item.name} 可能需要同步增强以匹配 BOSS 难度",
                severity="medium",
            ))

        # 3. 连锁影响: 前置任务难度
        quests = self.graph.get_quests_requiring(npc_id)
        for quest in quests:
            impacts.append(ChainImpact(
                target=quest.id,
                description=f"任务 {quest.name} 的难度可能因 BOSS 增强而不平衡",
                severity="low",
            ))

        return ImpactReport(impacts=impacts)
```

### 5.3 意图到目标映射

```python
class IntentToTargetMapper:
    """意图到目标的语义映射"""

    mappings = {
        # 模式: (关键词正则, 目标提取逻辑)
        (r"第一个?\s*BOSS|第一个?\s*首领", r"变强|加强|增强|更难"): {
            "target_type": "CHARACTER",
            "filter": lambda c: c.character_role == "boss",
            "sort": lambda c: c.first_encounter_map.level,  # 按首次遭遇地图排序
            "action": "NUMERIC_SCALE",
            "properties": ["MaxLife", "Strength", "Dexterity"],
            "factor_range": (1.5, 3.0),
        },
        (r"掉落率|掉率|掉落"): {
            "target_type": "ITEM",
            "filter": None,  # 全局
            "action": "NUMERIC_SCALE",
            "properties": ["drop_probability"],
            "factor_range": (1.2, 5.0),
        },
        (r"经验|升级|EXP"): {
            "target_type": "GAME_CONFIG",
            "action": "NUMERIC_SCALE",
            "properties": ["exp_per_level", "exp_reward_multiplier"],
            "factor_range": (0.5, 3.0),
        },
        (r"对话|剧情|台词"): {
            "target_type": "DIALOGUE",
            "action": "SCRIPT_INSERT",
            "properties": ["dialog_text"],
        },
    }
```

---

## 6. 规划层：意图到修改计划

### 6.1 游戏特化的 ActionSpace

```python
class GameModActionSpace(ActionSpace):
    """游戏 Mod 动作空间 — 基于 miu2d 编辑器操作设计"""

    def generate_actions(self, state: PlanState) -> List[PatchOperation]:
        intent = state.intent
        graph = state.graph

        # 根据意图类型分发到不同的动作生成器
        if self._is_numeric_intent(intent):
            return self._generate_numeric_actions(intent, graph)
        elif self._is_script_intent(intent):
            return self._generate_script_actions(intent, graph)
        elif self._is_asset_intent(intent):
            return self._generate_asset_actions(intent, graph)
        elif self._is_map_intent(intent):
            return self._generate_map_actions(intent, graph)
        else:
            return self._generate_mixed_actions(intent, graph)

    def _generate_numeric_actions(self, intent: Intent, graph: GameWorldGraph) -> List[PatchOperation]:
        """生成数值修改动作"""
        actions = []

        # 1. 识别目标对象
        targets = self._resolve_targets(intent, graph)

        for target in targets:
            # 2. 识别可修改的数值属性
            numeric_props = self._get_numeric_properties(target)

            for prop in numeric_props:
                # 3. 生成修改操作（多种候选值）
                for factor in [1.2, 1.5, 2.0, 3.0]:
                    old_value = target.properties[prop.name]
                    new_value = int(old_value * factor) if prop.is_int else old_value * factor

                    actions.append(create_modify_ini_op(
                        file_path=target.source_path,
                        section=prop.section,
                        key=prop.key,
                        old_value=old_value,
                        new_value=new_value,
                    ))

        return actions

    def _generate_script_actions(self, intent: Intent, graph: GameWorldGraph) -> List[PatchOperation]:
        """生成脚本修改动作"""
        actions = []

        # 示例: "让新手村导师在对话后给玩家一个额外的技能"
        # 1. 找到新手村导师的 NPC 配置
        npc = graph.find_npc(role="tutorial_mentor", map_region="starter_village")

        # 2. 找到其对话脚本
        script_path = npc.script_talk

        # 3. 生成在对话末尾插入技能的候选操作
        actions.append(create_insert_script_op(
            file_path=script_path,
            position="end_of_dialog",  # 在对话末尾
            code="AddMagic(\"magic/fireball.ini\")\n",
        ))

        # 4. 生成另一种候选（在特定分支后插入）
        actions.append(create_insert_script_op(
            file_path=script_path,
            position=ScriptPosition(after_label="choice_yes"),
            code="AddMagic(\"magic/icebolt.ini\")\n",
        ))

        return actions
```

### 6.2 游戏特化的 ValueFunction

```python
class GameBalanceValueFunction(ValueFunction):
    """游戏平衡性价值函数"""

    def evaluate(self, state: PlanState) -> float:
        graph = state.graph
        history = state.action_history

        scores = {
            "balance": self._evaluate_balance(graph, history),
            "consistency": self._evaluate_consistency(graph, history),
            "playability": self._evaluate_playability(graph, history),
            "preservative": self._evaluate_preservative(graph, history),
        }

        weights = {
            "balance": 0.35,
            "consistency": 0.25,
            "playability": 0.25,
            "preservative": 0.15,
        }

        return sum(scores[k] * weights[k] for k in scores)

    def _evaluate_balance(self, graph: GameWorldGraph, history: List[PatchOperation]) -> float:
        """评估数值平衡性"""
        score = 1.0

        # 检查数值跳跃是否过大
        for op in history:
            if op.op_type == OpType.MODIFY_INI:
                old_val = op.payload.get("old_value", 0)
                new_val = op.payload.get("new_value", 0)
                if old_val > 0:
                    ratio = new_val / old_val
                    if ratio > 5.0 or ratio < 0.2:
                        score -= 0.3  # 过大跳跃扣分
                    elif ratio > 3.0 or ratio < 0.33:
                        score -= 0.1

        # 检查难度曲线
        bosses = sorted(graph.get_bosses(), key=lambda b: b.encounter_order)
        powers = [b.combat_power for b in bosses]
        for i in range(1, len(powers)):
            if powers[i] < powers[i-1]:
                score -= 0.2  # 后期 BOSS 比前期弱 — 不合理

        return max(0.0, score)

    def _evaluate_consistency(self, graph: GameWorldGraph, history: List[PatchOperation]) -> float:
        """评估引用一致性"""
        score = 1.0

        # 检查修改后的引用是否仍然有效
        for op in history:
            if "script" in op.payload:
                script_path = op.payload["script"]
                if not graph.has_file(script_path):
                    score -= 0.5  # 引用了不存在的脚本

            if "magic" in op.payload:
                magic_id = op.payload["magic"]
                if not graph.has_magic(magic_id):
                    score -= 0.5

        return max(0.0, score)

    def _evaluate_playability(self, graph: GameWorldGraph, history: List[PatchOperation]) -> float:
        """评估可玩性"""
        score = 0.5  # 基础分

        # 有合理数量的修改加分
        if 1 <= len(history) <= 10:
            score += 0.2
        elif 10 < len(history) <= 20:
            score += 0.1
        elif len(history) > 30:
            score -= 0.2  # 修改太多可能导致不可玩

        # 修改了数值属性加分（玩家可感知）
        numeric_ops = [op for op in history if op.op_type == OpType.MODIFY_INI]
        if len(numeric_ops) > 0:
            score += 0.1

        # 修改了对话/任务加分（内容丰富）
        script_ops = [op for op in history if op.op_type == OpType.INSERT_SCRIPT]
        if len(script_ops) > 0:
            score += 0.2

        return min(1.0, score)
```

### 6.3 规划器使用示例

```python
# 用户意图: "让游戏更难，但增加经验获取"
planner = GameModPlanner()

# 意图会被分解为多个子意图
sub_intents = [
    Intent(description="增加所有 BOSS 的生命值和攻击力", priority="high"),
    Intent(description="增加普通怪物的攻击力", priority="medium"),
    Intent(description="增加经验获取速度", priority="high"),
]

# 对每个子意图分别规划，然后合并
results = []
for sub_intent in sub_intents:
    result = planner.plan(graph, sub_intent)
    results.append(result)

# 合并并检查冲突
merged_patch = PatchMerger.merge([r.to_patch() for r in results])
```

---

## 7. 执行层：Patch 到文件变更

### 7.1 文件级 Patch 执行器

```python
class GameFilePatcher:
    """游戏文件 Patch 执行器"""

    def __init__(self, game_root: Path):
        self.game_root = game_root
        self.backup_manager = BackupManager(game_root)

    def apply(self, patch: GameModPatch) -> ModPackage:
        # 1. 创建备份
        backup_id = self.backup_manager.create_backup()

        # 2. 按文件分组操作
        file_ops = self._group_by_file(patch.operations)

        # 3. 逐个文件应用
        modified_files = []
        for file_path, ops in file_ops.items():
            full_path = self.game_root / file_path
            new_content = self._apply_file_ops(full_path, ops)

            # 写入修改后的内容
            full_path.write_text(new_content, encoding=self._detect_encoding(full_path))
            modified_files.append(file_path)

        # 4. 生成 Mod 包
        return ModPackage(
            files=modified_files,
            patch=patch,
            backup_id=backup_id,
        )

    def _apply_file_ops(self, file_path: Path, ops: List[PatchOperation]) -> str:
        content = file_path.read_text(encoding=self._detect_encoding(file_path))

        for op in ops:
            if op.op_type == OpType.MODIFY_INI:
                content = self._apply_modify_ini(content, op)
            elif op.op_type == OpType.INSERT_SCRIPT:
                content = self._apply_insert_script(content, op)
            elif op.op_type == OpType.ADD_RECORD:
                content = self._apply_add_record(content, op)

        return content

    def _apply_modify_ini(self, content: str, op: PatchOperation) -> str:
        """修改 INI 文件中的键值"""
        section = op.payload["section"]
        key = op.payload["key"]
        new_value = op.payload["new_value"]

        # 使用 configparser 或正则替换
        parser = configparser.ConfigParser()
        parser.read_string(content)
        parser.set(section, key, str(new_value))

        # 写回（保留原始格式尽量）
        output = io.StringIO()
        parser.write(output)
        return output.getvalue()
```

### 7.2 二进制资产 Patch 执行器

对于二进制格式（ASF/MSF/MPC/MAP/MMF），需要调用 miu2d 的 converter：

```python
class BinaryAssetPatcher:
    """二进制资产 Patch 执行器"""

    def __init__(self, converter_path: Path):
        self.converter = Miu2dConverter(converter_path)

    def replace_sprite(self, asset_path: Path, new_image: Path) -> Path:
        """替换精灵资源"""
        # 1. 解码原始 ASF/MSF 为中间格式
        intermediate = self.converter.decode(asset_path)

        # 2. 替换图像数据
        intermediate.replace_frame(0, new_image)

        # 3. 重新编码
        output_path = asset_path.with_suffix(".patched" + asset_path.suffix)
        self.converter.encode(intermediate, output_path)

        return output_path

    def edit_map(self, map_path: Path, edits: List[MapEdit]) -> Path:
        """编辑地图数据"""
        # 1. 解码 MMF/MAP
        map_data = self.converter.decode_map(map_path)

        # 2. 应用编辑
        for edit in edits:
            if edit.type == "ADD_OBSTACLE":
                map_data.obstacles.append(edit.coordinates)
            elif edit.type == "MOVE_SPAWN":
                map_data.spawn_points[edit.spawn_id] = edit.new_position

        # 3. 重新编码
        output_path = map_path.with_suffix(".patched" + map_path.suffix)
        self.converter.encode_map(map_data, output_path)

        return output_path
```

### 7.3 Mod 包格式

```
mod_package/
├── mod.json              # 元数据
│   {
│     "id": "hard_mode_v1",
│     "name": "困难模式",
│     "version": "1.0.0",
│     "author": "Udify AI",
│     "target_game": "sword2",
│     "target_version": "1.0.0",
│     "dependencies": [],
│     "conflicts": [],
│     "description": "所有 BOSS 血量翻倍，经验获取增加 50%"
│   }
├── patches/
│   ├── npc/
│   │   └── boss_001.ini.patch      # 文本 diff 或完整替换
│   ├── script/
│   │   └── tutorial_001.txt.patch
│   └── config/
│       └── game_config.ini.patch
├── assets/
│   └── (可选) 替换的二进制资源
├── rollback/
│   └── backup_manifest.json        # 回滚所需信息
└── checksums.sha256                # 完整性校验
```

---

## 8. 验证层：修改效果确认

### 8.1 静态验证

```python
class GameStaticValidator:
    """游戏静态验证器"""

    def validate(self, patch: GameModPatch, graph: GameWorldGraph) -> ValidationReport:
        errors = []
        warnings = []

        # 1. 引用完整性检查
        for op in patch.operations:
            if op.op_type == OpType.MODIFY_INI:
                file_path = op.payload["file_path"]
                if not (self.game_root / file_path).exists():
                    errors.append(f"目标文件不存在: {file_path}")

            if op.op_type == OpType.INSERT_SCRIPT:
                script_path = op.payload["file_path"]
                if not (self.game_root / script_path).exists():
                    errors.append(f"脚本文件不存在: {script_path}")

        # 2. 数值范围检查
        for op in patch.operations:
            if op.op_type == OpType.MODIFY_INI:
                key = op.payload["key"]
                new_value = op.payload["new_value"]
                if key in ["MaxLife", "MaxMana", "Strength"] and new_value < 0:
                    errors.append(f"属性 {key} 不能为负数: {new_value}")
                if key in ["MaxLife"] and new_value > 999999:
                    warnings.append(f"生命值过高可能影响游戏平衡: {new_value}")

        # 3. 格式合法性检查
        for op in patch.operations:
            if op.op_type == OpType.INSERT_SCRIPT:
                code = op.payload["code"]
                if not self._is_valid_lua_syntax(code):
                    errors.append(f"Lua 语法错误: {code[:50]}...")

        return ValidationReport(errors=errors, warnings=warnings)
```

### 8.2 运行时验证

```python
class GameRuntimeValidator:
    """游戏运行时验证器 — 在浏览器中运行游戏并检查"""

    def __init__(self, game_url: str):
        self.game_url = game_url
        self.browser = HeadlessBrowser()

    def validate_mod(self, mod_package: ModPackage) -> RuntimeReport:
        # 1. 启动游戏（带 Mod）
        self.browser.navigate(f"{self.game_url}?mod={mod_package.id}")

        # 2. 检查游戏能否正常启动
        if not self._wait_for_game_load(timeout=30):
            return RuntimeReport(success=False, error="游戏启动失败")

        # 3. 运行自动化测试脚本
        results = []

        # 3.1 检查数值修改是否生效
        results.append(self._check_npc_stat("boss_001", "MaxLife", expected_factor=2.0))

        # 3.2 检查脚本是否执行正确
        results.append(self._check_script_execution("tutorial_mentor", "对话后是否给予技能"))

        # 3.3 检查游戏能否通关（简化版）
        results.append(self._check_playability(duration_minutes=5))

        return RuntimeReport(success=all(r.success for r in results), details=results)

    def _check_npc_stat(self, npc_id: str, stat: str, expected_factor: float) -> CheckResult:
        """通过浏览器控制台检查 NPC 属性"""
        actual_value = self.browser.execute_script(f"""
            return game.engine.getNpc('{npc_id}').{stat};
        """)
        # 与原始值比较
        return CheckResult(success=actual_value >= original_value * expected_factor * 0.9)
```

### 8.3 Playtest Agent（未来扩展）

```python
class PlaytestAgent:
    """自动化游戏试玩 Agent"""

    def playtest(self, game_url: str, duration: int = 300) -> PlaytestReport:
        """
        在浏览器中自动玩游戏 5 分钟，收集数据：
        - 死亡次数
        - 战斗时长
        - 经验获取速度
        - 任务完成率
        """
        # 使用强化学习或规则策略自动操作游戏
        # 记录关键指标
        pass
```

---

## 9. 编辑器集成层

### 9.1 与 miu2d Dashboard 的集成

Udify 可以直接嵌入 miu2d Dashboard，提供 AI 辅助编辑功能：

```
miu2d Dashboard (React)
├── 现有模块:
│   ├── Magic Editor
│   ├── NPC Editor
│   ├── Scene Editor
│   ├── ... (13 个)
│   └── 🆕 AI Mod Assistant (新增)
│       ├── 自然语言输入框
│       ├── 修改预览 (diff 视图)
│       ├── 影响分析面板
│       ├── 一键应用/回滚
│       └── Mod 历史记录
```

### 9.2 AI Mod Assistant 组件设计

```typescript
// React 组件
interface AIModAssistantProps {
  gameId: string;
  currentFile?: string;      // 当前正在编辑的文件
  onApplyPatch: (patch: GameModPatch) => void;
  onRollback: (patchId: string) => void;
}

function AIModAssistant({ gameId, currentFile, onApplyPatch, onRollback }: AIModAssistantProps) {
  const [input, setInput] = useState("");
  const [plan, setPlan] = useState<ModPlan | null>(null);
  const [isPlanning, setIsPlanning] = useState(false);

  const handleSubmit = async () => {
    setIsPlanning(true);
    const result = await fetch("/api/udify/plan", {
      method: "POST",
      body: JSON.stringify({
        game_id: gameId,
        intent: input,
        context_file: currentFile,
      }),
    }).then(r => r.json());
    setPlan(result);
    setIsPlanning(false);
  };

  return (
    <div className="ai-mod-assistant">
      <textarea
        placeholder="描述你想要的修改，例如: 让第一个 BOSS 血量翻倍"
        value={input}
        onChange={e => setInput(e.target.value)}
      />
      <button onClick={handleSubmit} disabled={isPlanning}>
        {isPlanning ? "思考中..." : "生成修改方案"}
      </button>

      {plan && (
        <div className="plan-preview">
          <ImpactAnalysis impacts={plan.impacts} />
          <FileDiffView changes={plan.changes} />
          <button onClick={() => onApplyPatch(plan.patch)}>应用修改</button>
        </div>
      )}
    </div>
  );
}
```

### 9.3 API 设计

```typescript
// tRPC Router 扩展
const udifyRouter = router({
  // 感知
  analyzeGame: publicProcedure
    .input(z.object({ game_id: z.string() }))
    .output(GameWorldGraphSchema)
    .query(async ({ input }) => {
      return udify.perception.analyze(input.game_id);
    }),

  // 规划
  planMod: publicProcedure
    .input(z.object({
      game_id: z.string(),
      intent: z.string(),
      context: z.object({
        current_file: z.string().optional(),
        selected_npc: z.string().optional(),
      }).optional(),
    }))
    .output(ModPlanSchema)
    .mutation(async ({ input }) => {
      return udify.planning.plan(input.game_id, input.intent, input.context);
    }),

  // 执行
  applyPatch: publicProcedure
    .input(z.object({
      game_id: z.string(),
      patch: GameModPatchSchema,
    }))
    .output(ModPackageSchema)
    .mutation(async ({ input }) => {
      return udify.execution.apply(input.game_id, input.patch);
    }),

  // 验证
  validateMod: publicProcedure
    .input(z.object({
      mod_id: z.string(),
      validation_type: z.enum(["static", "runtime"]),
    }))
    .output(ValidationReportSchema)
    .query(async ({ input }) => {
      return udify.validation.validate(input.mod_id, input.validation_type);
    }),

  // 回滚
  rollbackMod: publicProcedure
    .input(z.object({ mod_id: z.string() }))
    .output(z.boolean())
    .mutation(async ({ input }) => {
      return udify.execution.rollback(input.mod_id);
    }),
});
```

---

## 10. 技术栈与依赖

### 10.1 核心依赖

| 组件 | 技术 | 理由 |
|------|------|------|
| 后端 | Python 3.12+ | 与现有 Udify 代码一致 |
| 游戏解析 | pydantic + configparser | INI/OBJ 解析、类型验证 |
| Lua 解析 | tree-sitter (lua grammar) | AST 级脚本修改 |
| 二进制解码 | 调用 miu2d converter (Rust CLI) | 复用成熟实现 |
| 图数据库 | 内存（Phase 1）→ Neo4j（Phase 2） | 当前规模小，内存足够 |
| LLM 接口 | OpenAI API / 本地 llama.cpp | 意图理解 + 价值评估 |
| 前端 | React 19 + TypeScript | 与 miu2d 一致 |
| API | tRPC 11 | 与 miu2d server 一致 |
| 测试 | pytest + Playwright | 单元测试 + E2E 运行时验证 |

### 10.2 与 miu2d 的代码复用策略

```
复用级别:
├── 直接复用 (零改动)
│   ├── @miu2d/converter (Rust CLI)      → 二进制编解码
│   ├── @miu2d/types (Zod Schema)        → 数据模型参考
│   └── @miu2d/engine-wasm (WASM)        → 运行时组件
│
├── 适配复用 (轻量包装)
│   ├── @miu2d/dashboard 编辑器模块       → AI Mod Assistant 嵌入
│   └── @miu2d/server 路由结构           → API 设计参考
│
└── 参考实现 (学习但自研)
    ├── @miu2d/engine/resource/           → Python 端资产解析器
    └── @miu2d/engine/script/             → DSL/Lua 解析器
```

---

## 11. 实施路线图

### Phase 1A: 文本配置魔改（Week 1-2）

**目标**: 实现 INI/OBJ 配置的 AI 辅助修改

```
Week 1:
├── Day 1-2: 实现 IniDecoder + ObjDecoder
│   └── 输出: 可解析 miu2d 的所有 INI/OBJ 文件
├── Day 3-4: 实现 GameWorldGraph 构建器（文本配置部分）
│   └── 输出: 从配置构建角色/物品/技能/地图节点
├── Day 5: 实现 IntentToTargetMapper（数值类意图）
│   └── 输出: "让 BOSS 变强" → 识别目标 BOSS + 属性

Week 2:
├── Day 1-2: 实现 GameModActionSpace（数值修改动作）
│   └── 输出: 生成候选数值缩放操作
├── Day 3-4: 实现 GameFilePatcher（INI 修改）
│   └── 输出: 应用 Patch 到实际文件
├── Day 5: 端到端测试
│   └── 输入: "让南宫飞云初始 HP 变成 200"
│   └── 输出: player.ini 被修改，数值正确
```

### Phase 1B: 脚本魔改（Week 3-4）

**目标**: 实现 Lua/DSL 脚本的 AI 辅助修改

```
Week 3:
├── Day 1-2: 集成 tree-sitter Lua parser
│   └── 输出: 可解析 miu2d 的所有 Lua 脚本为 AST
├── Day 3-4: 实现 DslScriptDecoder（DSL 脚本解析为 AST）
│   └── 输出: 可解析 218 命令的 DSL 脚本
├── Day 5: 实现 ScriptInjector（脚本插入/修改）
│   └── 输出: 可在指定位置插入/替换代码

Week 4:
├── Day 1-2: 扩展 IntentToTargetMapper（脚本类意图）
│   └── 输出: "让导师给玩家一个技能" → 识别脚本位置
├── Day 3-4: 扩展 ActionSpace（脚本动作）
│   └── 输出: 生成脚本插入候选操作
├── Day 5: 端到端测试
│   └── 输入: "让新手村导师对话后给火球术"
│   └── 输出: talk/tutor_001.txt 被修改，游戏内验证
```

### Phase 1C: 运行时验证（Week 5-6）

**目标**: 实现自动化运行时验证

```
Week 5:
├── Day 1-2: 搭建 Playwright + miu2d 测试环境
│   └── 输出: 可在 headless 浏览器中运行 miu2d
├── Day 3-4: 实现 RuntimeValidator（基础版）
│   └── 输出: 检查游戏启动 + 数值读取
├── Day 5: 实现静态验证（引用完整性 + 数值范围）

Week 6:
├── Day 1-3: 集成到 miu2d Dashboard（AI Mod Assistant）
│   └── 输出: React 组件嵌入 Dashboard
├── Day 4-5: 完整端到端测试
│   └── 场景: 自然语言 → AI 规划 → 文件修改 → 浏览器验证
```

### Phase 2: 二进制资产魔改（Month 2）

**目标**: 实现精灵、地图等二进制资产的 AI 辅助修改

- 集成 miu2d converter（Rust CLI）到 Udify 执行层
- 实现 AssetReplace action（AI 生成/替换精灵图）
- 实现 MapEdit action（AI 辅助地图编辑）
- 与 Stable Diffusion / ComfyUI 集成（AI 生成美术资源）

### Phase 3: 社区与生态（Month 3+）

- Mod 市场（上传、评分、下载）
- Mod 兼容性检查（A Mod 和 B Mod 是否会冲突）
- Mod 组合优化（自动解决多个 Mod 的冲突）
- 支持更多游戏引擎（RPG Maker MV、Unity 等）

---

## 12. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解策略 |
|------|--------|------|---------|
| miu2d 数据格式变更 | 低 | 高 | 与 miu2d 社区保持同步，格式版本化管理 |
| AI 生成无效脚本 | 中 | 高 | 强静态验证 + 运行时沙箱 |
| 数值修改导致游戏崩溃 | 中 | 高 | 数值范围检查 + 自动回滚 + 运行时验证 |
| 修改范围过大不可控 | 中 | 中 | preservative_bias 参数 + 影响分析器 |
| LLM API 成本高 | 高 | 中 | 本地模型 fallback + 缓存 + 分层评估 |
| 二进制格式解析错误 | 中 | 高 | 复用 miu2d converter（经过实战验证） |
| 版权问题（游戏资产） | 低 | 高 | 明确法律边界，只提供工具，不提供资产 |

---

## 附录 A: miu2d 关键文件速查

```
miu2d/
├── docs/
│   ├── binary-formats.md      # 8 种二进制格式详细规范
│   ├── script-commands.md     # 218 个 DSL 命令参考
│   ├── lua-scripting.md       # Lua 5.4 绑定文档
│   ├── magic-types.md         # 22 MoveKind × 10 SpecialKind
│   ├── editor.md              # Dashboard 编辑器架构
│   └── pathfinder.md          # Rust WASM 寻路实现
├── packages/
│   ├── types/src/             # Zod Schema（18 个领域模块）
│   ├── engine/src/resource/   # 8 种格式解码器
│   ├── engine/src/script/     # DSL VM + Lua 运行时
│   ├── dashboard/src/modules/ # 13 个编辑器模块
│   ├── converter/             # Rust CLI 格式转换
│   └── server/src/modules/    # tRPC 路由
```

## 附录 B: 关键洞察总结

1. **INI/OBJ 是魔改主战场**: 文本配置占魔改价值的 70%，应优先实现
2. **脚本是核心杠杆**: 修改 Lua/DSL 比修改二进制资产 ROI 高 10 倍
3. **Dashboard Schema 是宝藏**: miu2d 已经定义了完整的数据模型，直接复用
4. **Converter 是关键依赖**: 二进制魔改必须复用 miu2d converter，不自研解码器
5. **运行时验证是护城河**: 能自动验证修改效果的系统才具备产品化价值

---

> **文档作者**: OpenCode Agent
> **参考项目**: [miu2d](https://github.com/luckyyyyy/miu2d) by luckyyyyy
> **关联文档**: `docs/ARCHITECTURE-v2.md`, `docs/PROGRESS-SESSION-2.md`
