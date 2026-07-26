<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify DevOps & CI/CD 架构

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: GitOps 工作流、多环境管理、CI/CD 流水线、IaC、部署策略、秘密管理、镜像策略

---

## 目录

1. [DevOps 架构总览](#1-devops-架构总览)
2. [GitOps 工作流](#2-gitops-工作流)
3. [多环境管理](#3-多环境管理)
4. [CI 流水线设计](#4-ci-流水线设计)
5. [CD 流水线设计](#5-cd-流水线设计)
6. [基础设施即代码（IaC）](#6-基础设施即代码iac)
7. [容器镜像策略](#7-容器镜像策略)
8. [部署策略矩阵](#8-部署策略矩阵)
9. [秘密与配置管理](#9-秘密与配置管理)
10. [数据库迁移流水线](#10-数据库迁移流水线)

---

## 1. DevOps 架构总览

### 1.1 核心原则

```yaml
devops_principles:
  1_infrastructure_as_code:
    description: "所有基础设施通过代码定义，版本控制，可审计"
    tools: ["Terraform", "Pulumi", "Crossplane"]
  
  2_gitops:
    description: "Git 作为唯一事实来源，所有变更通过 PR"
    tools: ["ArgoCD", "Flux"]
  
  3_continuous_integration:
    description: "每次提交自动构建、测试、扫描"
    tools: ["GitHub Actions", "BuildKit", "Trivy"]
  
  4_continuous_delivery:
    description: "自动部署到 staging，一键部署到 production"
    tools: ["ArgoCD", "Helm", "Flagger"]
  
  5_observability_driven:
    description: "部署由指标驱动，自动回滚不健康变更"
    tools: ["Prometheus", "Grafana", "Flagger"]
  
  6_security_by_design:
    description: "安全扫描在流水线早期，拒绝漏洞进入生产"
    tools: ["Trivy", "Snyk", "Sigstore"]
```

### 1.2 架构图

```
Developer Workflow
    │
    ├──→ Local Dev (Docker Compose)
    │       ├──→ git commit
    │       └──→ pre-commit hooks (lint, format, secret-scan)
    │
    ├──→ PR Opened
    │       ├──→ GitHub Actions: CI Pipeline
    │       │       ├──→ Lint & Format Check
    │       │       ├──→ Unit Tests
    │       │       ├──→ Integration Tests
    │       │       ├──→ Security Scan (SAST/DAST/SCA)
    │       │       ├──→ Build Container Images
    │       │       └──→ Push to Dev Registry
    │       └──→ Required Reviews + Auto-merge (if green)
    │
    ├──→ Merge to Main
    │       ├──→ GitHub Actions: Full CI + Image Build
    │       ├──→ Push to Staging Registry
    │       └──→ ArgoCD: Auto-sync to Staging
    │
    ├──→ Release Tagged (vX.Y.Z)
    │       ├──→ GitHub Actions: Production Build
    │       ├──→ Sign Images (Sigstore/cosign)
    │       ├──→ SBOM Generation
    │       ├──→ Push to Production Registry
    │       └──→ ArgoCD: Manual Sync to Production
    │
    └──→ Production Deployment
            ├──→ ArgoCD: Progressive Delivery
            ├──→ Flagger: Canary Analysis
            ├──→ Prometheus: Automated Rollback (if SLO violated)
            └──→ Post-deploy Verification
```

---

## 2. GitOps 工作流

### 2.1 仓库结构（GitOps 模式）

```
udify/                          # 应用源码仓库
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI 流水线
│       ├── cd-staging.yml      # Staging 部署
│       └── cd-production.yml   # Production 部署
├── src/
├── tests/
├── Dockerfile
├── docker-compose.yml
└── helm/
    └── udify-core/             # Helm Chart（与代码同仓）

udify-gitops/                   # GitOps 配置仓库（独立）
├── environments/
│   ├── dev/                    # 开发环境配置
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   └── secrets/            # 加密秘密（SOPS）
│   ├── staging/                # 预发布环境
│   │   ├── kustomization.yaml
│   │   ├── patches/
│   │   │   ├── replicas.yaml
│   │   │   ├── resources.yaml
│   │   │   └── ingress.yaml
│   │   └── secrets/
│   └── production/             # 生产环境
│       ├── kustomization.yaml
│       ├── patches/
│       │   ├── replicas.yaml
│       │   ├── resources.yaml
│       │   ├── hpa.yaml
│       │   ├── pdb.yaml        # Pod Disruption Budget
│       │   └── ingress.yaml
│       └── secrets/
├── infrastructure/
│   ├── terraform/              # 基础设施定义
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── modules/
│   └── crossplane/             # Kubernetes 基础设施
├── policies/
│   ├── kyverno/                # 安全策略
│   └── opa/                    # 准入控制策略
└── apps/
    ├── udify-core.yaml         # ArgoCD Application
    ├── udify-platform.yaml
    └── udify-monitoring.yaml
```

### 2.2 ArgoCD 配置

```yaml
# udify-gitops/apps/udify-core.yaml

apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: udify-core
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  project: udify
  source:
    repoURL: https://github.com/udify/udify-gitops.git
    targetRevision: HEAD
    path: environments/production
    kustomize:
      images:
        - name: udify-api
          newTag: "{{ .Values.image.tag }}"  # 由 CI 自动更新
  destination:
    server: https://kubernetes.default.svc
    namespace: udify-production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas  # HPA 管理副本数，ArgoCD 不覆盖
```

### 2.3 自动镜像更新

```yaml
# udify-gitops/apps/image-updater.yaml

apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: udify-image-updater
  namespace: argocd
spec:
  source:
    helm:
      values: |
        config:
          applications:
            - name: udify-core
              updateStrategy: semver
              allowTags:
                - pattern: '^v\\d+\\.\\d+\\.\\d+$'
                  order: semver
              ignoreTags:
                - pattern: '*-alpha.*'
                - pattern: '*-beta.*'
            - name: udify-core-staging
              updateStrategy: latest
              allowTags:
                - pattern: '*'
```

---

## 3. 多环境管理

### 3.1 环境矩阵

| 维度 | Local | Dev | Staging | Production |
|------|-------|-----|---------|------------|
| **用途** | 开发调试 | 功能验证 | 集成测试/演示 | 用户服务 |
| **数据** | 合成数据 | 合成数据 | 脱敏生产数据 | 真实生产数据 |
| **规模** | 单容器 | 最小 K8s | 50% Production | 100% |
| **更新频率** | 实时 | 每次 PR | 每次 merge | 手动发布 |
| **SLA** | 无 | 无 | 99% | 99.9% |
| **成本/月** | $0 | $200 | $2,000 | $20,000+ |
| **访问控制** | 开发者 | 团队成员 | 团队+QA | 受限 |
| **备份** | 无 | 无 | 每日 | 连续 |

### 3.2 Kustomize 环境差异化

```yaml
# udify-gitops/environments/base/kustomization.yaml

apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: udify

resources:
  - namespace.yaml
  - deployment.yaml
  - service.yaml
  - ingress.yaml
  - configmap.yaml
  - serviceaccount.yaml

commonLabels:
  app.kubernetes.io/part-of: udify
  app.kubernetes.io/managed-by: argocd

images:
  - name: udify-api
    newName: ghcr.io/udify/api
  - name: udify-worker
    newName: ghcr.io/udify/worker
  - name: udify-frontend
    newName: ghcr.io/udify/frontend
```

```yaml
# udify-gitops/environments/staging/kustomization.yaml

apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: udify-staging

resources:
  - ../base

namePrefix: staging-

patchesStrategicMerge:
  - patches/replicas.yaml
  - patches/resources.yaml
  - patches/ingress.yaml

configMapGenerator:
  - name: udify-config
    behavior: merge
    literals:
      - ENVIRONMENT=staging
      - LOG_LEVEL=debug
      - LLM_PROVIDER=openai
      - ENABLE_DEBUG_ENDPOINTS=true

secretGenerator:
  - name: udify-secrets
    behavior: merge
    envs:
      - secrets/staging.env
```

```yaml
# udify-gitops/environments/staging/patches/replicas.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: udify-api
spec:
  replicas: 2
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: udify-worker
spec:
  replicas: 3
```

```yaml
# udify-gitops/environments/production/patches/replicas.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: udify-api
spec:
  replicas: 6
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: udify-worker
spec:
  replicas: 10
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: udify-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: udify-api
  minReplicas: 6
  maxReplicas: 100
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
```

---

## 4. CI 流水线设计

### 4.1 GitHub Actions 主流水线

```yaml
# .github/workflows/ci.yml

name: CI

on:
  push:
    branches: [main, 'release/*']
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ${{ github.repository }}

jobs:
  # ===== Stage 1: 代码质量 =====
  lint-and-format:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Python Lint (Ruff)
        run: |
          pip install ruff
          ruff check .
          ruff format --check .
      
      - name: Python Type Check (mypy)
        run: |
          pip install mypy
          mypy src/ --strict
      
      - name: Frontend Lint (ESLint)
        run: |
          cd frontend
          npm ci
          npm run lint
          npm run type-check
      
      - name: Shell Check
        run: |
          sudo apt-get install shellcheck
          find scripts/ -name "*.sh" -exec shellcheck {} +

  # ===== Stage 2: 安全扫描 =====
  security-scan:
    runs-on: ubuntu-latest
    needs: lint-and-format
    steps:
      - uses: actions/checkout@v4
      
      # SAST (静态应用安全测试)
      - name: Run Bandit (Python SAST)
        run: |
          pip install bandit
          bandit -r src/ -f json -o bandit-report.json || true
      
      # 秘密扫描
      - name: Secret Detection (TruffleHog)
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD
          extra_args: --debug --only-verified
      
      # 依赖漏洞扫描
      - name: SCA (Trivy)
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      # 基础设施扫描
      - name: Terraform Scan (Checkov)
        uses: bridgecrewio/checkov-action@master
        with:
          directory: infrastructure/
          framework: terraform

  # ===== Stage 3: 测试 =====
  test-backend:
    runs-on: ubuntu-latest
    needs: lint-and-format
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      redis:
        image: redis:7
        ports:
          - 6379:6379
      neo4j:
        image: neo4j:5
        env:
          NEO4J_AUTH: neo4j/password
        ports:
          - 7687:7687
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install Dependencies
        run: |
          pip install uv
          uv pip install -e ".[dev]"
      
      - name: Run Unit Tests
        run: pytest tests/unit/ -v --cov=src --cov-report=xml
      
      - name: Run Integration Tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
          REDIS_URL: redis://localhost:6379/0
          NEO4J_URI: bolt://localhost:7687
        run: pytest tests/integration/ -v
      
      - name: Upload Coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: false

  test-frontend:
    runs-on: ubuntu-latest
    needs: lint-and-format
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Install Dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run Unit Tests
        run: |
          cd frontend
          npm run test:unit -- --coverage
      
      - name: Run Component Tests (Storybook Test Runner)
        run: |
          cd frontend
          npm run test:storybook

  test-e2e:
    runs-on: ubuntu-latest
    needs: [test-backend, test-frontend]
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Environment
        run: docker compose -f docker-compose.test.yml up -d
      
      - name: Run E2E Tests (Playwright)
        run: |
          cd e2e
          npm ci
          npx playwright test
      
      - name: Upload Test Results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: e2e/playwright-report/

  # ===== Stage 4: 构建与推送 =====
  build-and-push:
    runs-on: ubuntu-latest
    needs: [security-scan, test-backend, test-frontend]
    if: github.event_name == 'push'
    strategy:
      matrix:
        component: [api, worker, frontend, sandbox-executor]
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract Metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_PREFIX }}/${{ matrix.component }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=sha,prefix=,suffix=,format=short
      
      - name: Build and Push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./docker/${{ matrix.component }}.Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64
```

---

## 5. CD 流水线设计

### 5.1 Staging 自动部署

```yaml
# .github/workflows/cd-staging.yml

name: CD - Staging

on:
  push:
    branches: [main]

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
        with:
          repository: udify/udify-gitops
          token: ${{ secrets.GITOPS_TOKEN }}
      
      - name: Update Image Tags
        run: |
          cd environments/staging
          kustomize edit set image \
            udify-api=ghcr.io/udify/udify/api:sha-${GITHUB_SHA::7} \
            udify-worker=ghcr.io/udify/udify/worker:sha-${GITHUB_SHA::7} \
            udify-frontend=ghcr.io/udify/udify/frontend:sha-${GITHUB_SHA::7}
      
      - name: Commit and Push
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add .
          git commit -m "Update staging images to sha-${GITHUB_SHA::7}"
          git push
      
      - name: Wait for ArgoCD Sync
        run: |
          argocd app wait udify-core-staging \
            --health \
            --timeout 600
      
      - name: Run Smoke Tests
        run: |
          curl -f https://staging-api.udify.dev/health
          curl -f https://staging.udify.dev/
```

### 5.2 Production 发布流程

```yaml
# .github/workflows/cd-production.yml

name: CD - Production

on:
  release:
    types: [published]

jobs:
  # ===== 发布前验证 =====
  pre-deploy-checks:
    runs-on: ubuntu-latest
    steps:
      - name: Verify Release Notes
        run: |
          if [ -z "${{ github.event.release.body }}" ]; then
            echo "Release notes are required!"
            exit 1
          fi
      
      - name: Verify Staging Health
        run: |
          curl -f https://staging-api.udify.dev/health
          curl -f https://staging-api.udify.dev/metrics/slo
      
      - name: Verify Images Signed
        run: |
          cosign verify \
            --key https://udify.dev/cosign.pub \
            ghcr.io/udify/udify/api:${{ github.event.release.tag_name }}

  # ===== 数据库迁移（预部署） =====
  database-migration:
    runs-on: ubuntu-latest
    needs: pre-deploy-checks
    environment: production-db
    steps:
      - uses: actions/checkout@v4
      
      - name: Run Migrations (Dry Run)
        run: |
          alembic upgrade --sql head > migration.sql
          echo "=== Migration Preview ==="
          cat migration.sql
      
      - name: Apply Migrations
        env:
          DATABASE_URL: ${{ secrets.PROD_DATABASE_URL }}
        run: |
          alembic upgrade head
      
      - name: Verify Schema
        run: |
          python scripts/verify_schema.py

  # ===== 渐进式部署 =====
  progressive-deployment:
    runs-on: ubuntu-latest
    needs: database-migration
    environment: production
    steps:
      - uses: actions/checkout@v4
        with:
          repository: udify/udify-gitops
          token: ${{ secrets.GITOPS_TOKEN }}
      
      - name: Update Production Tags
        run: |
          cd environments/production
          kustomize edit set image \
            udify-api=ghcr.io/udify/udify/api:${{ github.event.release.tag_name }} \
            udify-worker=ghcr.io/udify/udify/worker:${{ github.event.release.tag_name }} \
            udify-frontend=ghcr.io/udify/udify/frontend:${{ github.event.release.tag_name }}
          
          git add .
          git commit -m "Release ${{ github.event.release.tag_name }}"
          git push
      
      - name: Trigger Canary Deployment
        run: |
          kubectl apply -f canary/canary-analysis.yaml
      
      - name: Wait for Canary Analysis
        run: |
          kubectl wait --for=condition=Succeeded \
            canary/udify-api-${{ github.event.release.tag_name }} \
            --timeout=30m
      
      - name: Promote or Rollback
        run: |
          if [ "$(kubectl get canary udify-api -o jsonpath='{.status.phase}')" == "Succeeded" ]; then
            echo "Canary succeeded, promoting to full traffic"
            kubectl apply -f canary/promote.yaml
          else
            echo "Canary failed, rolling back"
            kubectl apply -f canary/rollback.yaml
            exit 1
          fi
```

---

## 6. 基础设施即代码（IaC）

### 6.1 Terraform 基础设施定义

```hcl
# infrastructure/terraform/main.tf

terraform {
  required_version = ">= 1.7"
  
  backend "s3" {
    bucket         = "udify-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "udify-terraform-locks"
  }
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "udify"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# EKS 集群
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"
  
  cluster_name    = "udify-${var.environment}"
  cluster_version = "1.29"
  
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  
  eks_managed_node_groups = {
    general = {
      desired_size = var.node_desired_size
      min_size     = var.node_min_size
      max_size     = var.node_max_size
      
      instance_types = ["m6i.2xlarge"]
      capacity_type  = var.environment == "production" ? "ON_DEMAND" : "SPOT"
      
      labels = {
        workload = "general"
      }
    }
    
    sandbox = {
      desired_size = 5
      min_size     = 3
      max_size     = 100
      
      instance_types = ["m6i.4xlarge"]
      capacity_type  = "SPOT"
      
      labels = {
        workload = "sandbox"
      }
      
      taints = [{
        key    = "dedicated"
        value  = "sandbox"
        effect = "NO_SCHEDULE"
      }]
    }
  }
  
  # 集群_addons
  cluster_addons = {
    coredns = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni = { most_recent = true }
    aws-ebs-csi-driver = { most_recent = true }
  }
}

# 数据库
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"
  
  identifier = "udify-postgres-${var.environment}"
  
  engine               = "postgres"
  engine_version       = "16"
  family               = "postgres16"
  major_engine_version = "16"
  instance_class       = var.environment == "production" ? "db.r6g.2xlarge" : "db.t4g.medium"
  
  allocated_storage     = 100
  max_allocated_storage = 1000
  
  db_name  = "udify"
  username = "udify_admin"
  port     = 5432
  
  multi_az               = var.environment == "production"
  db_subnet_group_name   = module.vpc.database_subnet_group
  vpc_security_group_ids = [module.security_groups.rds_sg_id]
  
  backup_retention_period = var.environment == "production" ? 30 : 7
  deletion_protection     = var.environment == "production"
  
  performance_insights_enabled = var.environment == "production"
  
  # 加密
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn
}

# S3 存储桶
module "s3" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "~> 4.0"
  
  for_each = toset(["assets", "patches", "snapshots", "logs"])
  
  bucket = "udify-${each.value}-${var.environment}-${random_id.bucket_suffix.hex}"
  
  versioning = {
    enabled = each.value == "patches"
  }
  
  lifecycle_rule = each.value == "snapshots" ? [{
    id      = "expire-old-snapshots"
    enabled = true
    expiration = {
      days = 7
    }
  }] : []
  
  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm     = "aws:kms"
        kms_master_key_id = aws_kms_key.s3.arn
      }
    }
  }
}
```

### 6.2 基础设施策略验证（OPA）

```rego
# policies/opa/infrastructure.rego

package udify.terraform

import future.keywords.if
import future.keywords.in

# 禁止公开 S3 存储桶
deny[msg] if {
    resource := input.resource_changes[_]
    resource.type == "aws_s3_bucket_public_access_block"
    not resource.change.after.block_public_acls
    msg := sprintf("S3 bucket %s must block public ACLs", [resource.address])
}

# 强制加密 RDS
deny[msg] if {
    resource := input.resource_changes[_]
    resource.type == "aws_db_instance"
    not resource.change.after.storage_encrypted
    msg := sprintf("RDS instance %s must have encryption enabled", [resource.address])
}

# 生产环境必须 Multi-AZ
deny[msg] if {
    resource := input.resource_changes[_]
    resource.type == "aws_db_instance"
    input.variables.environment.value == "production"
    not resource.change.after.multi_az
    msg := sprintf("Production RDS %s must be Multi-AZ", [resource.address])
}

# 强制标签
deny[msg] if {
    resource := input.resource_changes[_]
    required_tags := {"Project", "Environment", "ManagedBy"}
    missing := required_tags - {key | resource.change.after.tags[key]}
    count(missing) > 0
    msg := sprintf("Resource %s missing required tags: %v", [resource.address, missing])
}
```

---

## 7. 容器镜像策略

### 7.1 多阶段 Dockerfile

```dockerfile
# docker/api.Dockerfile

# ===== Stage 1: Builder =====
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY pyproject.toml uv.lock ./
RUN pip install uv && \
    uv pip install --system --no-cache -e ".[prod]"

# ===== Stage 2: Development =====
FROM python:3.12-slim-bookworm AS development

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

CMD ["uvicorn", "udify.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ===== Stage 3: Production =====
FROM python:3.12-slim-bookworm AS production

# 安全：创建非 root 用户
RUN groupadd -r udify && useradd -r -g udify udify

WORKDIR /app

# 只安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已编译的依赖
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY --chown=udify:udify src/ ./src/
COPY --chown=udify:udify pyproject.toml ./

# 安全：移除写入权限
RUN chmod -R 555 /app

USER udify

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "udify.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 7.2 镜像安全扫描与签名

```yaml
# .github/workflows/image-security.yml

name: Image Security

on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  scan-and-sign:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build Image
        run: docker build -t udify-api:scan -f docker/api.Dockerfile .
      
      # 漏洞扫描
      - name: Scan with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: 'udify-api:scan'
          format: 'sarif'
          output: 'trivy-image-results.sarif'
      
      # 如果发布标签，签名镜像
      - name: Sign Image with Cosign
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          cosign sign --yes \
            --key env://COSIGN_PRIVATE_KEY \
            ghcr.io/udify/udify/api:${{ github.ref_name }}
        env:
          COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
          COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
      
      # 生成 SBOM
      - name: Generate SBOM
        if: startsWith(github.ref, 'refs/tags/v')
        uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/udify/udify/api:${{ github.ref_name }}
          format: spdx-json
          output-file: sbom.spdx.json
      
      # 附加 SBOM 到镜像
      - name: Attach SBOM
        if: startsWith(github.ref, 'refs/tags/v')
        run: |
          cosign attach sbom --sbom sbom.spdx.json \
            ghcr.io/udify/udify/api:${{ github.ref_name }}
```

---

## 8. 部署策略矩阵

### 8.1 策略对比

| 策略 | 适用场景 | 风险 | 恢复时间 | 资源成本 |
|------|---------|------|---------|---------|
| **滚动更新** | 无状态服务、向后兼容 | 中 | 慢（需重新部署） | 低 |
| **蓝绿部署** | 数据库变更、关键服务 | 低 | 快（切换流量） | 高（2x 资源） |
| **金丝雀** | 大多数生产部署 | 低 | 中（自动回滚） | 中 |
| **A/B 测试** | 功能验证、业务指标 | 中 | 快 | 中 |
| **影子流量** | 性能对比、风险验证 | 无 | N/A | 高 |

### 8.2 Flagger 金丝雀配置

```yaml
# canary/canary-analysis.yaml

apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: udify-api
  namespace: udify-production
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: udify-api
  service:
    port: 80
    targetPort: 8000
    gateways:
      - udify-api-gateway
    hosts:
      - api.udify.dev
  analysis:
    interval: 30s
    threshold: 5          # 最多 5 次失败
    maxWeight: 50         # 最大 50% 流量
    stepWeight: 10        # 每次增加 10%
    
    # 关键指标监控
    metrics:
      - name: request-success-rate
        interval: 1m
        thresholdRange:
          min: 99
        
      - name: request-duration
        interval: 1m
        thresholdRange:
          max: 500
        
      - name: custom-error-rate
        templateRef:
          name: udify-error-rate
          namespace: istio-system
        thresholdRange:
          max: 1
    
    # Webhook 验证
    webhooks:
      - name: load-test
        type: pre-rollout
        url: http://flagger-loadtester.istio-system/
        timeout: 30s
        metadata:
          cmd: "hey -z 1m -q 10 -c 2 http://udify-api-canary.udify-production/"
      
      - name: conformance-test
        type: pre-rollout
        url: http://flagger-loadtester.istio-system/
        timeout: 3m
        metadata:
          type: bash
          cmd: "curl -sf http://udify-api-canary.udify-production/health"
      
      - name: notify-slack
        type: post-rollout
        url: http://flagger-loadtester.istio-system/
        metadata:
          type: slack
          channel: deployments
          username: flagger
      
      - name: rollback-notification
        type: rollback
        url: http://flagger-loadtester.istio-system/
        metadata:
          type: slack
          channel: alerts
          username: flagger
```

### 8.3 自动回滚策略

```python
# udify/ops/auto_rollback.py

class AutoRollbackController:
    """基于 SLO 的自动回滚控制器"""
    
    def __init__(self):
        self.prometheus = PrometheusClient()
        self.k8s = KubernetesClient()
        self.slack = SlackNotifier()
    
    async def evaluate_and_rollback(self, deployment: str, namespace: str):
        """评估部署健康度，必要时回滚"""
        
        # 1. 收集指标（部署后 5 分钟窗口）
        metrics = await self.prometheus.query_range(
            queries={
                "error_rate": f'sum(rate(http_requests_total{{deployment="{deployment}",status=~"5.."}}[5m]))',
                "latency_p99": f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{deployment="{deployment}"}}[5m])) by (le))',
                "cpu_usage": f'rate(container_cpu_usage_seconds_total{{pod=~"{deployment}-.*"}}[5m])',
            },
            duration="5m",
        )
        
        # 2. 评估 SLO
        violations = []
        
        if metrics["error_rate"] > 0.01:  # > 1% 错误率
            violations.append(f"Error rate {metrics['error_rate']:.2%} exceeds 1%")
        
        if metrics["latency_p99"] > 1.0:  # P99 > 1s
            violations.append(f"P99 latency {metrics['latency_p99']:.0f}ms exceeds 1s")
        
        if metrics["cpu_usage"] > 0.95:  # CPU > 95%
            violations.append(f"CPU usage {metrics['cpu_usage']:.0%} exceeds 95%")
        
        # 3. 决策
        if len(violations) >= 2:
            logger.critical(f"Auto-rollback triggered for {deployment}: {violations}")
            
            # 执行回滚
            await self.k8s.rollback_deployment(deployment, namespace)
            
            # 通知
            await self.slack.send_alert(
                channel="#alerts",
                text=f"🚨 Auto-rollback executed for `{deployment}`\nReasons: {', '.join(violations)}",
            )
            
            return RollbackDecision(
                executed=True,
                reasons=violations,
                timestamp=datetime.utcnow(),
            )
        
        return RollbackDecision(executed=False)
```

---

## 9. 秘密与配置管理

### 9.1 SOPS + Age 加密

```yaml
# .sops.yaml

creation_rules:
  # 开发环境密钥
  - path_regex: environments/dev/secrets/.*\.yaml$
    age: age1devkey...
  
  # 预发布环境密钥
  - path_regex: environments/staging/secrets/.*\.yaml$
    age: age1stagingkey...
  
  # 生产环境密钥（需要多人审批）
  - path_regex: environments/production/secrets/.*\.yaml$
    age: age1prodkey1,age1prodkey2,age1prodkey3
    shamir_threshold: 2  # 需要 2/3 个密钥持有者
```

```bash
# 加密秘密文件
sops --encrypt --in-place environments/production/secrets/database.env

# 在 CI/CD 中解密
sops --decrypt environments/production/secrets/database.env > /tmp/database.env
source /tmp/database.env
rm /tmp/database.env
```

### 9.2 External Secrets Operator

```yaml
# external-secrets/database.yaml

apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: database-credentials
  namespace: udify-production
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-secrets-manager
  target:
    name: database-credentials
    creationPolicy: Owner
    template:
      type: Opaque
      data:
        DATABASE_URL: "postgresql://{{ .username }}:{{ .password }}@{{ .host }}:5432/udify"
  data:
    - secretKey: username
      remoteRef:
        key: udify/production/database
        property: username
    - secretKey: password
      remoteRef:
        key: udify/production/database
        property: password
    - secretKey: host
      remoteRef:
        key: udify/production/database
        property: host
```

### 9.3 配置管理（ConfigMap + Feature Flags）

```yaml
# config/configmap.yaml

apiVersion: v1
kind: ConfigMap
metadata:
  name: udify-config
  namespace: udify-production
data:
  # 应用配置
  ENVIRONMENT: "production"
  LOG_LEVEL: "info"
  LOG_FORMAT: "json"
  
  # 功能开关
  FEATURE_ADVANCED_PLANNING: "true"
  FEATURE_REALTIME_COLLAB: "true"
  FEATURE_MARKETPLACE: "true"
  FEATURE_BETA_TOOLS: "false"
  
  # LLM 配置
  LLM_DEFAULT_PROVIDER: "openai"
  LLM_FALLBACK_PROVIDER: "anthropic"
  LLM_MAX_CONCURRENT: "50"
  LLM_REQUEST_TIMEOUT: "30"
  
  # 速率限制
  RATE_LIMIT_DEFAULT: "100"
  RATE_LIMIT_PRO: "1000"
  RATE_LIMIT_TEAM: "10000"
  
  # 沙箱配置
  SANDBOX_MAX_CONCURRENT: "100"
  SANDBOX_TIMEOUT_SECONDS: "300"
  SANDBOX_MEMORY_LIMIT_MB: "4096"
```

---

## 10. 数据库迁移流水线

### 10.1 Alembic 迁移策略

```python
# alembic/env.py

from alembic import context
from sqlalchemy import engine_from_config, pool
from logging.config import fileConfig

# 导入模型元数据
from udify.models.base import Base

target_metadata = Base.metadata

def run_migrations_offline():
    """离线迁移（生成 SQL）"""
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """在线迁移"""
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # 事务性 DDL
            transactional_ddl=True,
            # 每次迁移在一个事务中
            transaction_per_migration=True,
        )
        
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### 10.2 迁移规范

```yaml
# 数据库迁移规范

migration_rules:
  # 1. 向后兼容性
  backward_compatibility:
    required: true
    description: "所有迁移必须向后兼容，支持零停机部署"
    
    allowed_operations:
      - "ADD COLUMN (nullable or with default)"
      - "CREATE TABLE"
      - "CREATE INDEX (CONCURRENTLY)"
      - "ADD FOREIGN KEY (NOT VALID, then VALIDATE)"
    
    forbidden_operations:
      - "DROP COLUMN"
      - "RENAME COLUMN"
      - "ALTER COLUMN TYPE"
      - "DROP TABLE"
      - "ADD COLUMN NOT NULL without default"
  
  # 2. 分阶段迁移
  multi_stage:
    stage_1_deploy:
      - "Add new column (nullable)"
      - "Create new table"
      - "Add new index"
    
    stage_2_backfill:
      - "Run data migration script"
      - "Backfill new column"
    
    stage_3_validate:
      - "Add NOT NULL constraint (if needed)"
      - "Remove old column (after verification)"
  
  # 3. 性能要求
  performance:
    max_lock_duration: "5s"
    index_creation: "CONCURRENTLY only"
    batch_size: "1000 rows per batch for backfill"
    
  # 4. 回滚策略
  rollback:
    required: true
    description: "每个迁移必须有对应的回滚脚本"
    test_in_staging: true
```

### 10.3 CI 中的迁移验证

```yaml
# .github/workflows/db-migration-check.yml

name: Database Migration Check

on:
  pull_request:
    paths:
      - 'alembic/versions/**'

jobs:
  validate-migration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install Dependencies
        run: pip install alembic psycopg2-binary sqlalchemy
      
      - name: Test Migration (Upgrade)
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
        run: |
          alembic upgrade head
      
      - name: Test Migration (Downgrade)
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
        run: |
          alembic downgrade base
      
      - name: Check Backward Compatibility
        run: |
          python scripts/check_migration_compat.py
      
      - name: Check Migration Duration
        run: |
          python scripts/estimate_migration_time.py
```

---

> **"DevOps 不是工具链，而是文化。GitOps 让每一次部署都可审计、可回滚；金丝雀让每一次发布都安全渐进；IaC 让基础设施像代码一样被评审和测试。Udify 的 DevOps 架构不是成本中心，而是产品交付的加速器。"**
>
> —— Udify DevOps 原则
