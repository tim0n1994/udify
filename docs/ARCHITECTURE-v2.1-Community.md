<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 架构补充文档：社区、生态与商业层

> **版本**: v2.1 | **日期**: 2026-04-27 | **状态**: 基于 COMMUNITY_RESEARCH.md 的架构细化
>
> **评审依据**: 社区调研发现 | **范围**: 社区层、生态层、商业层、伦理治理层

---

## 目录

1. [架构总览更新](#1-架构总览更新)
2. [社区层（Community Layer）](#2-社区层community-layer)
3. [创作者经济系统（Creator Economy）](#3-创作者经济系统creator-economy)
4. [伦理与治理架构（Ethics & Governance）](#4-伦理与治理架构ethics--governance)
5. [跨媒介扩展架构](#5-跨媒介扩展架构)
6. [开放平台与第三方生态](#6-开放平台与第三方生态)
7. [产品定位修正与功能优先级](#7-产品定位修正与功能优先级)
8. [社区敏感度响应矩阵](#8-社区敏感度响应矩阵)

---

## 1. 架构总览更新

### 1.1 v2.1 架构分层（增加社区/生态层）

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              用户界面层 (Presentation Layer)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Web App    │  │  CLI Tool    │  │   API/SDK    │  │  Browser Ext │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
└─────────┼─────────────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                         Udiface 平台层 (Platform Layer)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   内容管理    │  │   用户系统    │  │   发现机制    │  │   运行环境    │             │
│  │ • Project CRUD│  │ • Auth       │  │ • Search     │  │ • Web Player │             │
│  │ • Versioning  │  │ • Profile    │  │ • Recommend  │  │ • Cloud Play │             │
│  │ • CDN Dist    │  │ • Following  │  │ • Curated    │  │ • Download   │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
└─────────┼─────────────────┼─────────────────┼─────────────────┼───────────────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                      社区层 (Community Layer) ←── 新增                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   声誉系统    │  │   治理系统    │  │   协作工具    │  │   反馈回路    │             │
│  │ • Reputation │  │ • Rules      │  │ • Fork/Merge │  │ • Rating     │             │
│  │ • Badges     │  │ • Moderation │  │ • Co-edit    │  │ • Comment    │             │
│  │ • Leaderboard│  │ • Dispute    │  │ • Review     │  │ • Report     │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
└─────────┼─────────────────┼─────────────────┼─────────────────┼───────────────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                     商业层 (Economy Layer) ←── 新增                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   支付系统    │  │   收益分配    │  │   订阅系统    │  │   市场系统    │             │
│  │ • Stripe     │  │ • Revenue    │  │ • Creator    │  │ • Asset      │             │
│  │   Connect    │  │   Share      │  │   Sub        │  │   Store      │             │
│  │ • Crypto     │  │ • Tips       │  │ • Premium    │  │ • Template   │             │
│  │   (Future)   │  │ • Bounties   │  │   User       │  │   Market     │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
└─────────┼─────────────────┼─────────────────┼─────────────────┼───────────────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                     Udify Core 引擎层 (Core Engine)                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   感知层      │  │   认知层      │  │   规划层      │  │   执行层      │             │
│  │  Perception  │  │  Cognition   │  │  Planning    │  │  Execution   │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                 │                     │
│         └─────────────────┴─────────────────┴─────────────────┘                     │
│                                     │                                                 │
│                          ┌──────────┴──────────┐                                    │
│                          │     评估层           │                                    │
│                          │   Evaluation       │                                    │
│                          └──────────┬──────────┘                                    │
│                                     │                                                 │
│  ┌──────────────────────────────────┼──────────────────────────────────────────┐    │
│  │                        记忆系统 (Memory System)                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ User Pref   │  │ Content KG  │  │ Template Lib│  │ Execution   │         │    │
│  │  │ (Vectors)   │  │ (Neo4j)     │  │ (Versioned) │  │ History     │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  └──────────────────────────────────┴──────────────────────────────────────────┘    │
└────────────────────────────────────┼─────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                        工具层 (Tool Layer - MCP Protocol)                            │
└────────────────────────────────────┼─────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                     基础设施层 (Infrastructure Layer)                                │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 新增模块职责

| 新增模块 | 职责 | 输入 | 输出 |
|---------|------|------|------|
| **社区层** | 管理用户声誉、社区规则、协作工具、反馈回路 | 用户行为、内容互动、治理决策 | 声誉分数、治理状态、协作产物 |
| **商业层** | 处理支付、收益分配、订阅、市场交易 | 交易请求、收益事件、订阅状态 | 交易记录、分成结算、订阅权益 |
| **伦理治理层** | 内容审核、版权检测、AI 标注、合规检查 | 内容提交、举报、版权声明 | 审核结果、合规报告、标注状态 |

---

## 2. 社区层（Community Layer）

### 2.1 声誉系统（Reputation System）

**设计目标**：
- 激励高质量创作和协作
- 识别和奖励社区贡献者
- 为新用户提供信任信号

**声誉维度**：

```yaml
reputation_profile:
  user_id: "uuid"
  
  # 创作声誉（Creator Reputation）
  creator_score:
    value: 850  # 0-1000
    breakdown:
      content_quality: 300    # 基于用户评分和评估层分数
      content_volume: 150     # 发布数量（有上限，防刷）
      innovation: 200         # 原创内容 vs 复制
      community_impact: 200   # 被 fork、引用、协作的次数
    
  # 策展声誉（Curator Reputation）
  curator_score:
    value: 420
    breakdown:
      collection_quality: 150  # 创建的精选集质量
      discovery_accuracy: 120  # 推荐/标签的准确度
      review_helpfulness: 150  # 评论/评测被点赞数
  
  # 技术声誉（Technical Reputation）
  technical_score:
    value: 680
    breakdown:
      bug_reports: 200         # 有效 bug 报告
      contributions: 300       # 代码/工具贡献
      mentorship: 180          # 帮助新手解答
  
  # 治理声誉（Governance Reputation）
  governance_score:
    value: 300
    breakdown:
      vote_participation: 100  # 参与社区投票
      dispute_resolution: 120  # 参与争议调解
      rule_proposals: 80       # 提出被采纳的规则
  
  # 徽章系统（Badges）
  badges:
    - id: "first_mod"
      name: "初出茅庐"
      description: "发布第一个 Mod"
      earned_at: "2026-01-15T10:00:00Z"
    
    - id: "trending_creator"
      name: " trending 之星"
      description: "连续 7 天进入 trending 榜"
      earned_at: "2026-03-20T10:00:00Z"
    
    - id: "compatibility_master"
      name: "兼容性大师"
      description: "创建的 Mod 被 100+ 用户同时使用无冲突"
      earned_at: "2026-04-01T10:00:00Z"
    
    - id: "open_source_hero"
      name: "开源英雄"
      description: "发布 10+ 个开源模板供社区使用"
      earned_at: "2026-04-10T10:00:00Z"
  
  # 声誉历史（用于防刷和审计）
  history:
    - timestamp: "2026-04-27T10:00:00Z"
      event: "mod_endorsed"
      mod_id: "uuid"
      delta: +5
      reason: "User endorsed your mod 'Dark Souls Difficulty Pack'"
```

**声誉计算算法**：

```python
class ReputationEngine:
    """声誉计算引擎"""
    
    def calculate_creator_score(self, user_id: str) -> float:
        """计算创作者声誉"""
        # 获取用户的所有项目
        projects = self.get_user_projects(user_id)
        
        # 内容质量分（基于评估层分数和用户评分）
        quality_score = sum(
            p.evaluation_score * 0.6 + p.user_rating * 0.4
            for p in projects
        ) / max(len(projects), 1) * 300
        
        # 内容量分（对数衰减，防止刷量）
        volume_score = math.log(len(projects) + 1) * 50
        volume_score = min(volume_score, 150)  # 上限
        
        # 创新分（检查内容相似性）
        innovation_score = self._calculate_innovation(projects) * 200
        
        # 社区影响分
        impact_score = sum(
            p.fork_count * 2 + p.collaborator_count * 5
            for p in projects
        )
        impact_score = min(impact_score, 200)
        
        return quality_score + volume_score + innovation_score + impact_score
    
    def _calculate_innovation(self, projects: List[Project]) -> float:
        """计算创新度（与现有内容的差异性）"""
        if len(projects) < 2:
            return 1.0
        
        # 计算项目之间的平均相似度
        similarities = []
        for i, p1 in enumerate(projects):
            for p2 in projects[i+1:]:
                sim = self._content_similarity(p1, p2)
                similarities.append(sim)
        
        avg_similarity = sum(similarities) / len(similarities)
        
        # 与社区平均的相似度
        community_sim = self._community_similarity(projects)
        
        # 创新度 = 1 - 平均相似度（越高越创新）
        innovation = 1.0 - (avg_similarity * 0.5 + community_sim * 0.5)
        return max(0, innovation)
```

### 2.2 协作工具（Collaboration Tools）

**设计目标**：让 Mod 创作从"单人劳动"变成"协作创作"。

**核心功能**：

1. **Fork / Branch**
   ```
   原始 Mod: "Enhanced Combat v1.0" (by Alice)
       │
       ├──→ Fork: "Enhanced Combat - Hardcore Edition" (by Bob)
       │       └──→ 修改: 伤害 x2, 死亡掉落全部
       │
       ├──→ Fork: "Enhanced Combat - RPG Elements" (by Carol)
       │       └──→ 修改: 添加技能树, 经验值系统
       │
       └──→ Merge Request: "Balanced Combat Patch"
               └──→ 合并 Bob 和 Carol 的部分改动
   ```

2. **Co-editing（协同编辑）**
   - 类似 Google Docs 的实时协同
   - 但用于改造计划 DAG 的编辑
   - 支持"建议模式"（类似 GitHub Suggested Changes）

3. **Review System（代码审查式评审）**
   ```yaml
   review:
     review_id: "uuid"
     target_project: "uuid"
     reviewer_id: "uuid"
     status: "approved"  # pending, approved, changes_requested, dismissed
     
     comments:
       - line_reference: "operation_3"
         type: "suggestion"
         content: "建议将敌人 HP 增加从 200% 改为 150%，否则前期太难"
         severity: "minor"
       
       - line_reference: "operation_7"
         type: "issue"
         content: "这个操作会删除原版的关键任务触发器，导致主线卡死"
         severity: "blocking"
     
     overall_assessment:
       quality: 4  # 1-5
       innovation: 5
       compatibility: 2  # 低分因为会导致主线卡死
       recommendation: "changes_requested"
   ```

4. **Bounty System（悬赏系统）**
   - 用户可以发布"我想要某个 Mod"的悬赏
   - 创作者接单完成，获得悬赏金额
   - 类似于 Fiverr，但专注于 Mod 创作

### 2.3 反馈回路（Feedback Loop）

**设计目标**：建立从用户反馈到系统改进的闭环。

```
用户下载/体验 Mod
    │
    ├──→ 显式反馈
    │       ├──→ 评分（1-5 星）
    │       ├──→ 文字评论
    │       ├──→ 标签（"太难""有 bug""画面好"）
    │       └──→ 截图/视频反馈
    │
    ├──→ 隐式反馈
    │       ├──→ 游玩时长
    │       ├──→ 是否完成安装
    │       ├──→ 是否卸载
    │       ├──→ 是否分享
    │       └──→ 是否 fork
    │
    └──→ 行为数据
            ├──→ 下载来源（搜索/推荐/直接链接）
            ├──→ 设备信息
            └──→ 地域/语言

              │
              ▼
        ┌─────────────┐
        │ 反馈聚合器   │
        │ (Feedback   │
        │  Aggregator) │
        └──────┬──────┘
               │
      ┌────────┼────────┐
      │        │        │
      ▼        ▼        ▼
 ┌────────┐┌────────┐┌────────┐
 │创作者  ││系统    ││社区    │
 │通知    ││学习    ││趋势    │
 │(实时)  ││(批量)  ││(实时)  │
 └────────┘└────────┘└────────┘
      │        │        │
      ▼        ▼        ▼
 创作者改进  记忆系统   Trending
  下一版本   更新      榜单更新
```

---

## 3. 创作者经济系统（Creator Economy）

### 3.1 核心原则

基于社区调研，确立以下商业原则：

1. **工具/服务收费，内容免费**: 用户为使用 Udify 的服务付费，生成的 Mod 免费分享
2. **创作者优先**: 平台抽成低于行业标准（15% vs 行业 30%）
3. **透明**: 所有收益计算公开可审计
4. **即时**: 收益实时结算，不是月结

### 3.2 收入流设计

```
Udify 收入模型
    │
    ├──→ B2C: 用户付费
    │       ├──→ Free Tier
    │       │       • 每月 3 次简单改造
    │       │       • 社区模板使用
    │       │       • 基础分辨率资源
    │       │
    │       ├──→ Pro Tier ($9.99/月)
    │       │       • 无限次改造
    │       │       • 高级模板
    │       │       • 4K 资源生成
    │       │       • 优先队列
    │       │       • 高级分析
    │       │
    │       ├──→ Team Tier ($29.99/月)
    │       │       • 多人协作
    │       │       • 共享工作区
    │       │       • API 访问
    │       │       • 定制模型
    │       │
    │       └──→ Pay-as-you-go
    │               • 复杂改造按计算资源计费
    │               • 适合低频用户
    │
    ├──→ B2B: 企业/开发者付费
    │       ├──→ Studio License
    │       │       • 游戏工作室集成 Udify
    │       │       • 官方 Mod 工具
    │       │
    │       └──→ White-label
    │               • 为其他平台提供底层能力
    │
    └──→ Marketplace: 交易佣金
            ├──→ Asset Store (10% 佣金)
            │       • 高级纹理包
            │       • 音效库
            │       • 3D 模型
            │
            ├──→ Template Market (5% 佣金)
            │       • 改造模板
            │       • 预设配置
            │
            └──→ Service Market (15% 佣金)
                    • 定制改造服务
                    • 技术咨询
```

### 3.3 创作者收益分配

```yaml
# 收益分配示例
sale:
  transaction_id: "uuid"
  type: "mod_endorsement"  # 或 "asset_purchase", "template_purchase"
  amount_usd: 10.00
  
  distribution:
    creator:
      user_id: "creator_uuid"
      amount: 7.50    # 75%
      reason: "Creator share"
    
    original_author:
      user_id: "original_game_author_uuid"
      amount: 1.00    # 10%
      reason: "Original IP revenue share (optional, configurable by game)"
    
    platform:
      entity: "Udify"
      amount: 1.00    # 10%
      reason: "Platform fee"
    
    community_pool:
      entity: "Community Fund"
      amount: 0.50    # 5%
      reason: "Community development fund"

  # 如果使用了社区模板/资源，额外分配
  attribution:
    - user_id: "template_creator_uuid"
      amount: 0.50
      reason: "Based on template 'Dark Souls Difficulty Framework'"
    
    - user_id: "asset_creator_uuid"
      amount: 0.30
      reason: "Used asset pack 'Medieval Weapons HD'"
```

**关键设计**：
- **Attribution Chain（归属链）**: 任何使用了他人模板/资源的作品，自动分配收益给上游创作者
- **Original IP Share（原作 IP 分成）**: 游戏厂商可以选择参与收益分成（可选，激励厂商支持 Mod 生态）
- **Community Fund（社区基金）**: 5% 收益进入社区基金，用于举办比赛、资助开源工具、奖励贡献者

### 3.4 Donation / Tipping 系统

```
用户欣赏某个 Mod
    │
    ├──→ One-time Tip（一次性打赏）
    │       • 预设金额: $1, $5, $10, $50
    │       • 自定义金额
    │       • 可选留言
    │
    ├──→ Recurring Support（周期性支持）
    │       • 类似 Patreon 的月订阅
    │       • 支持者获得:
    │           - 提前访问新 Mod
    │           - 支持者专属 Discord 频道
    │           - 投票决定下一个 Mod 方向
    │
    └──→ Bounty（悬赏）
            • 用户发布"我想要这个 Mod"
            • 设置悬赏金额
            • 创作者接单完成
            • 完成后悬赏自动发放
```

---

## 4. 伦理与治理架构（Ethics & Governance）

### 4.1 AI 内容标注系统

基于社区调研，透明度是**最关键**的伦理要求。

```yaml
ai_disclosure:
  # 每个项目必须声明 AI 使用程度
  project_id: "uuid"
  
  ai_usage:
    # 自动化程度
    automation_level: "assisted"  # none, assisted, hybrid, fully_automated
    
    # AI 参与的环节
    ai_involvement:
      - stage: "planning"
        tool: "Udify Planner v2.1"
        description: "AI generated the transformation plan"
        human_reviewed: true
      
      - stage: "texture_generation"
        tool: "Stable Diffusion XL"
        description: "AI generated 3 textures based on prompt"
        human_reviewed: true
        human_modified: true  # 人类是否修改过
      
      - stage: "script_modification"
        tool: "Udify Code Assistant"
        description: "AI suggested code changes, human approved"
        human_reviewed: true
      
      - stage: "testing"
        tool: "Udify Evaluator"
        description: "AI ran automated tests"
        human_reviewed: false
    
    # 人类贡献度
    human_contribution_percentage: 65  # 估算
    
    # 训练数据声明
    training_data:
      - source: "Community Mod Database"
        license: "CC-BY-SA"
      - source: "Original Game Assets"
        note: "Used for reference only, not included in output"
  
  # 可见性
  public_disclosure: true  # 是否公开显示 AI 使用信息
  disclosure_badge: "AI-Assisted"  # 显示在项目页面的徽章
```

**徽章系统**：

| 徽章 | 含义 | 条件 |
|------|------|------|
| **🧑‍🎨 Handmade** | 纯手工 | 无 AI 参与 |
| **🤝 AI-Assisted** | AI 辅助 | AI 参与 < 50%，人类审核所有 AI 输出 |
| **⚙️ AI-Hybrid** | AI 混合 | AI 参与 50-90%，人类参与关键决策 |
| **🤖 AI-Generated** | AI 生成 | AI 参与 > 90%，人类主要提供意图 |

### 4.2 内容审核管道

```
用户提交 Mod
    │
    ▼
┌────────────────────────┐  Layer 1: 自动化预审
│ Automated Pre-screening │  • 病毒扫描
│                        │  • 版权指纹匹配
│                        │  • 毒性内容检测
│                        │  • 格式验证
└──────────┬─────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌────────┐   ┌────────┐
│通过    │   │可疑    │
└───┬────┘   └───┬────┘
    │            │
    ▼            ▼
┌────────────────────────┐  Layer 2: 社区复审
│ Community Review       │  • 高声誉用户随机抽样评审
│ (for suspicious/new)   │  • 3-5 人投票决定
│                        │  • 争议升级至 Layer 3
└──────────┬─────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌────────┐   ┌────────┐
│通过    │   │争议    │
└───┬────┘   └───┬────┘
    │            │
    ▼            ▼
┌────────────────────────┐  Layer 3: 专家/官方仲裁
│ Expert Arbitration     │  • 官方审核团队
│ (for disputes)         │  • 特邀领域专家
│                        │  • 最终裁决
└──────────┬─────────────┘
           │
           ▼
    ┌────────┬────────┐
    │        │        │
    ▼        ▼        ▼
┌──────┐┌──────┐┌──────┐
│发布  ││修改  ││拒绝  │
└──────┘└──────┘└──────┘
```

**社区复审激励**：
- 参与复审获得声誉点
- 评审质量高（与其他评审一致）获得额外奖励
- 评审质量低（经常与其他人冲突）降低评审权重

### 4.3 版权与合规系统

```python
class CopyrightSystem:
    """版权检测与管理系统"""
    
    def __init__(self):
        self.fingerprint_db = FingerprintDatabase()
        self.whitelist = WhitelistManager()  # 允许 Mod 的游戏列表
        self.blocklist = BlocklistManager()  # 明确禁止 Mod 的游戏列表
    
    async def check(self, project: Project) -> ComplianceReport:
        """检查项目合规性"""
        issues = []
        
        # 1. 检查游戏是否允许 Mod
        game = project.target_game
        if game in self.blocklist:
            issues.append(ComplianceIssue(
                severity="blocking",
                type="mod_not_allowed",
                message=f"Game '{game}' explicitly prohibits modding",
            ))
        
        # 2. 检查资源版权
        for asset in project.assets:
            match = await self.fingerprint_db.search(asset)
            if match.confidence > 0.95:
                issues.append(ComplianceIssue(
                    severity="blocking",
                    type="copyright_infringement",
                    message=f"Asset '{asset.path}' matches copyrighted content",
                    evidence=match,
                ))
        
        # 3. 检查 EULA 合规
        eula_issues = self._check_eula_compliance(project)
        issues.extend(eula_issues)
        
        # 4. 检查 AI 训练数据合规
        if project.ai_usage:
            for data_source in project.ai_usage.training_data:
                if not self._is_license_compatible(data_source.license, project.license):
                    issues.append(ComplianceIssue(
                        severity="warning",
                        type="license_incompatibility",
                        message=f"Training data license '{data_source.license}' may not be compatible",
                    ))
        
        return ComplianceReport(
            passed=len([i for i in issues if i.severity == "blocking"]) == 0,
            issues=issues,
        )
    
    def _check_eula_compliance(self, project: Project) -> List[ComplianceIssue]:
        """检查是否符合游戏 EULA"""
        issues = []
        game = project.target_game
        eula = self._get_eula(game)
        
        # 检查是否涉及反编译
        if project.has_decompiled_content and not eula.allows_decompilation:
            issues.append(ComplianceIssue(
                severity="warning",
                type="eula_decompilation",
                message="Project contains decompiled content, which may violate EULA",
            ))
        
        # 检查是否涉及在线功能修改
        if project.modifies_online_features and not eula.allows_online_mods:
            issues.append(ComplianceIssue(
                severity="blocking",
                type="eula_online",
                message="Modifying online features is prohibited by EULA",
            ))
        
        return issues
```

### 4.4 治理 DAO（未来方向）

**长期愿景**：Udify 社区逐步过渡到去中心化治理。

```
Phase 1 (现在-2年): 官方治理
    • Udify 团队制定规则
    • 社区反馈驱动规则调整
    
Phase 2 (2-4年): 混合治理
    • 核心规则由官方制定
    • 具体社区规则由选举的社区委员会制定
    • 重大决策通过社区投票
    
Phase 3 (4-6年): 去中心化治理 (DAO)
    • 声誉代币化（非金融代币，不可交易）
    • 高声誉用户获得治理权
    • 智能合约执行规则
    • 争议由去中心化仲裁解决
```

---

## 5. 跨媒介扩展架构

### 5.1 媒介适配器架构

```
原始内容
    │
    ├──→ [游戏适配器] ──→ CDL (GameGraph)
    │       ├──→ Unity Parser
    │       ├──→ Unreal Parser
    │       ├──→ Godot Parser
    │       └──→ RPG Maker Parser
    │
    ├──→ [音乐适配器] ──→ CDL (MusicGraph)
    │       ├──→ MIDI Parser
    │       ├──→ Audio File Parser
    │       └──→ DAW Project Parser
    │
    ├──→ [视频适配器] ──→ CDL (VideoGraph)
    │       ├──→ Video File Parser
    │       ├──→ Project File Parser
    │       └──── Subtitle Parser
    │
    └──→ [小说适配器] ──→ CDL (NarrativeGraph)
            ├──→ Text Parser
            ├──→ EPUB Parser
            └──→ Script Parser

              │
              ▼
        统一 CDL 格式
              │
              ├──→ [跨媒介转换器]
              │       ├──→ 游戏 → 小说 (提取叙事)
              │       ├──→ 小说 → 游戏 (生成设计文档)
              │       ├──→ 音乐 → 视频 (生成配乐)
              │       └──→ 视频 → 音乐 (提取节奏)
              │
              └──→ [媒介生成器]
                      ├──→ Game Generator
                      ├──→ Music Generator
                      ├──→ Video Generator
                      └──→ Novel Generator
```

### 5.2 跨媒介转换示例：小说 → 游戏

```yaml
# 输入: 小说 CDL
source:
  media_type: novel
  title: "The Witch's Journey"
  chapters:
    - id: ch1
      title: "The Beginning"
      scenes:
        - id: sc1
          setting: "Dark Forest"
          characters: ["Elara", "Mysterious Stranger"]
          events: ["Elara discovers magic crystal"]

# 转换指令
transformation:
  target_media: game
  intent: "Convert this novel into a 2D action RPG"
  constraints:
    - "Keep the dark fantasy atmosphere"
    - "Elara is the playable character"
    - "Magic crystal is the core mechanic"

# 输出: 游戏设计 CDL
target:
  media_type: game
  game_genre: action_rpg
  
  mechanics:
    - id: magic_crystal
      name: "Crystal Magic System"
      type: resource_mechanic
      properties:
        resource_name: "Crystal Energy"
        max_capacity: 100
        regeneration_rate: 5
        abilities:
          - name: "Crystal Blast"
            cost: 20
            damage: 50
          - name: "Crystal Shield"
            cost: 30
            defense: 40
  
  levels:
    - id: dark_forest
      name: "Dark Forest"
      theme: "dark_fantasy"
      size: "medium"
      enemies: ["forest_spirit", "shadow_wolf"]
      boss: "mysterious_stranger_boss"
  
  characters:
    - id: elara_player
      name: "Elara"
      type: player_character
      stats:
        health: 100
        magic: 100
        speed: medium
      starting_abilities: ["crystal_blast"]
```

---

## 6. 开放平台与第三方生态

### 6.1 API 策略

```yaml
# Udify API 分层策略

api_tiers:
  # 公开 API（免费，限流）
  public:
    rate_limit: "100 requests/day"
    endpoints:
      - "GET /v1/projects/{id}"  # 获取公开项目信息
      - "GET /v1/search"         # 搜索公开项目
      - "GET /v1/trending"       # 获取 trending
      - "GET /v1/users/{id}/public"  # 获取用户公开资料
    
  # 开发者 API（需要 API Key，按量计费）
  developer:
    rate_limit: "10,000 requests/day"
    pricing: "$0.01 per request"
    endpoints:
      - "POST /v1/projects"      # 创建项目
      - "GET /v1/projects/{id}/plan"  # 获取改造计划
      - "POST /v1/projects/{id}/execute"  # 执行改造
      - "GET /v1/projects/{id}/status"    # 查询状态
      - "POST /v1/intent/recognize"       # 意图识别
      - "POST /v1/content/parse"          # 内容解析
    
  # 合作伙伴 API（定制化，企业合同）
  partner:
    rate_limit: "Custom"
    pricing: "Custom"
    features:
      - "White-label access"
      - "Custom model training"
      - "Dedicated infrastructure"
      - "SLA guarantees"
    
    # 典型合作伙伴
    partners:
      - type: "game_studio"
        example: "Studio X integrates Udify as official modding tool"
      - type: "platform_integrator"
        example: "Nexus Mods uses Udify for automated compatibility checking"
      - type: "hardware_vendor"
        example: "Gaming laptop pre-installs Udify CLI"
```

### 6.2 插件生态

```python
# Udify 插件接口

class UdifyPlugin(ABC):
    """Udify 插件基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        pass
    
    @property
    @abstractmethod
    def hooks(self) -> List[Hook]:
        """声明插件要挂载的钩子点"""
        pass
    
    @abstractmethod
    def on_content_parsed(self, graph: ContentGraph) -> ContentGraph:
        """内容解析后的钩子"""
        pass
    
    @abstractmethod
    def on_plan_generated(self, plan: TransformationPlan) -> TransformationPlan:
        """计划生成后的钩子"""
        pass
    
    @abstractmethod
    def on_execution_complete(self, result: ExecutionResult) -> ExecutionResult:
        """执行完成后的钩子"""
        pass

# 示例插件：自动翻译插件
class AutoTranslatePlugin(UdifyPlugin):
    """自动将 Mod 内容翻译为多语言"""
    
    def on_content_parsed(self, graph: ContentGraph) -> ContentGraph:
        # 提取所有文本节点
        text_nodes = graph.get_nodes_by_type(NodeType.DIALOGUE)
        
        # 自动翻译
        for node in text_nodes:
            original_text = node.properties.get("text", "")
            translations = self.translate(original_text, target_languages=["zh", "ja", "es"])
            node.properties["translations"] = translations
        
        return graph
    
    def translate(self, text: str, target_languages: List[str]) -> Dict[str, str]:
        # 调用翻译 API
        pass

# 示例插件：性能分析插件
class PerformanceAnalyzerPlugin(UdifyPlugin):
    """分析 Mod 对游戏性能的影响"""
    
    def on_plan_generated(self, plan: TransformationPlan) -> TransformationPlan:
        # 分析每个操作对性能的预估影响
        for op in plan.operations:
            if op.type == "add_asset":
                asset_size = op.parameters.get("size", 0)
                if asset_size > 100 * 1024 * 1024:  # > 100MB
                    op.warnings.append("Large asset may impact loading time")
        
        return plan
```

### 6.3 模板市场

```
模板市场 (Template Marketplace)
    │
    ├──→ 官方模板
    │       ├──→ "Dark Souls Difficulty Framework"
    │       ├──→ "Visual Novel Engine"
    │       ├──→ "Roguelike Item Generator"
    │       └──→ "Retro Pixel Art Style Pack"
    │
    ├──→ 社区模板
    │       ├──→ 免费模板（CC0 / CC-BY）
    │       └──→ 付费模板（创作者定价）
    │
    └──→ 企业模板
            ├──→ 游戏厂商官方授权模板
            └──→ 第三方工具集成模板

模板结构：
template:
  id: "uuid"
  name: "Dark Souls Difficulty Framework"
  author: "community_user_123"
  license: "CC-BY-SA"
  price: 0  # 免费，或 > 0 表示付费
  
  description: "A reusable framework for adding Dark Souls-style difficulty to any RPG"
  
  compatibility:
    engines: [unity, unreal, godot]
    genres: [rpg, action_rpg]
  
  contents:
    - type: "operation_set"
      name: "Core Difficulty Mechanics"
      operations: [...]  # 预定义的操作序列
    
    - type: "config_preset"
      name: "Balanced Difficulty"
      parameters:
        enemy_damage_multiplier: 1.5
        player_health_regen: 0
        death_penalty: "lose_currency"
    
    - type: "documentation"
      name: "Usage Guide"
      content: "..."
  
  usage_stats:
    downloads: 15000
    active_projects: 3200
    average_rating: 4.7
```

---

## 7. 产品定位修正与功能优先级

### 7.1 产品定位声明（基于社区调研更新）

**原版**: "Udify 是一个通用的内容编译器，自动化的魔改一切"

**修正版**: 
> **"Udify 是创意意图的执行平台。它消除技术门槛，让每个人都能将想法转化为可玩、可体验、可分享的内容改造。AI 是伙伴，不是替代；自动化是手段，不是目的；社区是生态，不是用户群。"**

### 7.2 核心价值主张

| 受众 | 痛点 | Udify 价值 |
|------|------|-----------|
| **游戏玩家** | "我想让游戏更适合我，但不会做 Mod" | 用自然语言描述愿望，系统自动实现 |
| **Mod 创作者** | "90% 时间在折腾工具，10% 在创作" | 自动化技术执行，让你专注创意 |
| **独立开发者** | "想支持 Mod 但没有资源做工具" | 集成 Udify SDK，一键支持社区创作 |
| **内容消费者** | "找不到好的 Mod，安装太麻烦" | AI 推荐 + 一键安装 + 自动兼容 |
| **跨媒介创作者** | "想把小说改成游戏，但不懂编程" | 跨媒介自动转换 |

### 7.3 功能优先级矩阵（RICE 评分）

| 功能 | Reach (覆盖) | Impact (影响) | Confidence (信心) | Effort (成本) | RICE 分数 | 优先级 |
|------|-------------|--------------|------------------|--------------|----------|--------|
| 自动化资源提取+打包 | 10 | 9 | 90% | 5 | 162 | **P0** |
| 兼容性自动检测 | 10 | 10 | 80% | 6 | 133 | **P0** |
| 自然语言意图识别 | 9 | 9 | 70% | 7 | 81 | **P1** |
| 数值平衡调整 | 8 | 8 | 85% | 4 | 136 | **P1** |
| AI 推荐/发现 | 9 | 8 | 75% | 5 | 108 | **P1** |
| 纹理/材质生成 | 7 | 7 | 80% | 6 | 65 | **P2** |
| 脚本逻辑修改 | 6 | 9 | 50% | 8 | 34 | **P2** |
| 跨媒介转换 | 5 | 10 | 40% | 10 | 20 | **P3** |
| 协同编辑 | 4 | 7 | 70% | 7 | 28 | **P3** |
| 创作者经济系统 | 6 | 8 | 60% | 8 | 36 | **P3** |

### 7.4 发布策略（渐进式）

```
Alpha (M1-M3): 内部测试
    • 核心功能: 感知引擎 + 简单数值调整
    • 用户: 团队成员 + 5 位信任测试者
    • 目标: 验证技术可行性

Closed Beta (M4-M6): 邀请制
    • 核心功能: + 意图识别 + 计划生成 + 评估层
    • 用户: 100 位社区 KOL（Reddit/Discord 上的活跃 Mod 作者）
    • 目标: 收集反馈，改进 UX
    • 激励: 免费 Pro 账号 + 早期支持者徽章

Open Beta (M7-M9): 公开注册
    • 核心功能: + Udiface MVP + 社区功能
    • 用户: 10,000 注册用户
    • 目标: 验证 PMF（Product-Market Fit）
    • 限制: 免费 tier + 排队系统

v1.0 Launch (M10-M12): 正式发布
    • 核心功能: 完整 Phase 1 功能 + 创作者经济
    • 用户: 100,000 注册用户
    • 目标: 商业化启动
    • 营销: 游戏媒体合作 + KOL 推广 + 社区活动
```

---

## 8. 社区敏感度响应矩阵

基于社区调研，建立以下响应机制：

### 8.1 功能发布的风险评估

| 功能 | 社区敏感度 | 发布策略 | 回滚计划 |
|------|-----------|---------|---------|
| **AI 辅助数值调整** | 🟢 低 | 直接发布 | 无需 |
| **自动化兼容性检测** | 🟢 低 | 直接发布 | 无需 |
| **AI 生成纹理** | 🟡 中 | 标注 AI 生成 + 人类审核 | 关闭该功能 |
| **AI 修改游戏脚本** | 🟠 高 | A/B 测试 + 仅 Pro 用户 | 回退到手动模式 |
| **AI 生成完整 Mod** | 🔴 极高 | 严格限制 + 强制标注 | 完全关闭 |
| **小说同人 AI 改编** | 🔴 极高 | **暂缓发布** | N/A |

### 8.2 危机响应预案

**场景 1: 社区大规模反对 AI 功能**
- **触发**: Reddit/Twitter 出现负面 viral 内容， sentiment < 30%
- **响应**: 
  1. 24 小时内发布透明声明
  2. 强调"人类在环"和"透明度"
  3. 邀请社区代表参与产品决策
  4. 暂停争议功能，直到达成共识

**场景 2: 版权诉讼**
- **触发**: 收到游戏厂商的 DMCA 通知
- **响应**:
  1. 立即下架相关内容
  2. 法律团队介入
  3. 与厂商协商合作（官方 Mod 工具）
  4. 加强版权检测系统

**场景 3: AI 生成低质量内容泛滥**
- **触发**: 平台上 AI 生成内容 > 50%，平均评分下降
- **响应**:
  1. 提高评估层阈值
  2. 引入社区审核
  3. 调整推荐算法，降低 AI 生成内容的权重
  4. 推出"手工创作"筛选器

---

> **"技术决定能做什么，社区决定应该做什么。Udify 的架构不仅要强大，还要 wise。"**
>
> —— Udify 社区优先架构原则
