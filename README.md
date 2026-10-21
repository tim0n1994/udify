<div align="center">

# Udify

### Mod any game by describing what you want.

**Intent-driven game modding — plain language in, a verified, reversible, evidence-backed patch out.**

[![CI](https://github.com/tim0n1994/udify/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/tim0n1994/udify/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-396%20passing-brightgreen.svg)](tests/)
[![UdifyBench](https://img.shields.io/badge/UdifyBench-10%20golden%20cases-8A2BE2.svg)](benchmarks/miu2d/)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#roadmap)

**English** · [简体中文](README.zh-CN.md) · [Website](https://udify.games) · [Docs](docs/TECHNICAL-DOCUMENTATION-INDEX.md) · [Contact](mailto:hi@udify.games)

</div>

---

```bash
udify --game-root ./my-game mod "Make the boss harder, but keep the map reachable"
```

Udify reads the game, finds the boss, plans the edit, shows you **every changed line and why**, waits for your approval, validates the result, and hands you a mod package you can roll back at any time. The original files are never touched until you say yes.

## Why Udify?

Hundreds of millions of players mod games. Very few of them can program. LLMs can now write code, but letting a model blindly rewrite game files is how saves get corrupted and scripts get backdoored.

Udify treats AI modding as a **compiler problem, not a chat problem**:

| Typical "ask an LLM to edit files" | Udify |
|---|---|
| Rewrites whole files | Emits a structured **CDL Patch**: atomic, typed operations |
| "Trust me" | Every operation cites its **evidence**: source span, provenance, confidence |
| Changes land immediately | Preview in a **virtual file system**, then a **human approval gate** |
| Hope it runs | **Static validation** + **headless runtime probe** before packaging |
| No undo | Every patch is **reversible**, with checksum-verified rollback |
| Agent can run anything | All tools go through a **Secure Tool Gateway**: R0–R4 risk tiers, path allowlist, hash-chained audit log |

## How it works

```mermaid
flowchart TD
    A["Intent<br/>make the boss harder"] --> B["Perceive<br/>parse configs and scripts<br/>into a content graph"]
    B --> C["Ground and Plan<br/>resolve references<br/>MCTS search"]
    C --> D["CDL Patch<br/>typed ops + evidence"]
    D --> E["Preview<br/>VFS diff"]
    E --> F{"Human<br/>approval"}
    F -->|approve| G["Validate<br/>static + runtime probe"]
    F -->|reject| C
    G --> H["ModPackage<br/>reversible"]
```

1. **Perceive.** Engine adapters parse INI, object, NPC, and Lua files (Tree-sitter) into a `ContentGraph`. Every node keeps its `SourceSpan` and provenance.
2. **Lift.** A semantic lifter tags nodes ("boss", "shop item", "drop table") with evidence and confidence.
3. **Plan.** Intents are classified, grounded against the graph, checked for conflicts, and searched with **MCTS** under a cost budget. LLMs plug in as the value function; a heuristic is the default, so it runs offline.
4. **Patch.** The planner synthesizes a `CDLPatch`: INI, Lua, and DSL edits with a reverse operation for each.
5. **Verify.** Schema, reference, numeric-range, syntax, and dangerous-API checks, then a headless runtime probe.
6. **Ship.** Export a `ModPackage` with manifest, audit trail, and one-command rollback.

## Quick start

> Requires Python 3.12+. The current end-to-end loop supports **miu2d**-engine games; more engines are on the [roadmap](#roadmap).

```bash
git clone https://github.com/tim0n1994/udify.git
cd udify
pip install -e ".[dev]"

# Run the test suite (396 tests, ~2s)
python3 -m pytest tests/ -q
```

**Option A — CLI.** Previews in a virtual file system and never touches the originals:

```bash
udify --game-root /path/to/miu2d-game mod "Double the boss's HP"   # prints a session ID
udify --game-root /path/to/miu2d-game preview                # inspect the diff
udify --game-root /path/to/miu2d-game apply <session_id>     # write it
udify --game-root /path/to/miu2d-game rollback <session_id>  # undo it
```

**Option B — Review workbench.** Local API plus a Next.js UI:

```bash
udify serve                               # API → http://127.0.0.1:8765/api/docs
cd web && pnpm install && pnpm dev        # UI  → http://localhost:3000
```

Pick a game directory, type an intent, review the file diff, per-operation evidence, and risk tier, approve, watch validation run, then download the package.

## UdifyBench

A golden-case benchmark for **agentic content modification**: does the agent make the right change, *and* refuse the wrong one?

| # | Case | What it checks |
|---|---|---|
| 01 | `hp-modify` | Simple numeric edit lands on the right entity |
| 02 | `boss-difficulty-capped` | Fuzzy intent ("harder") respects sane caps |
| 03 | `npc-skill-reward` | Adds a skill reward to an NPC dialogue |
| 04 | `drop-rate-up` | Probability edits stay in valid range |
| 05 | `potion-nerf` | Targeted nerf, no collateral changes |
| 06 | `add-shop-item` | Adding content, not just editing it |
| 07 | `map-reachability` | Edits don't make maps unreachable |
| 08 | `no-dangerous-lua` | Rejects patches that introduce unsafe Lua APIs |
| 09 | `no-conflicting-edits` | Detects conflicting operations |
| 10 | `rollback-checksum` | Rollback restores byte-identical files |

Cases live in [`benchmarks/miu2d/`](benchmarks/miu2d/). We plan to grow this into a public benchmark across engines.

## Project layout

```
udify/
├── models/          ContentGraph, CDLPatch, evidence primitives (SourceSpan, Provenance…)
├── core/
│   ├── adapters/        Engine adapters (EngineAdapter protocol; miu2d implemented)
│   ├── perception/      Parsers (INI/OBJ/NPC/Lua via Tree-sitter), semantic lifter
│   ├── planning/        Intent state, action schemas, MCTS planner, patch synthesizer
│   ├── validation/      Static validator, headless runtime probe
│   ├── execution/       VFS, sandbox, patch executor, scheduler, MCP server
│   ├── tool_gateway/    Policy, risk tiers, lockfile pins, hash-chained audit
│   └── orchestration/   ModJob state machine + durable SQLite store
├── api/             FastAPI service (`udify serve`)
└── cli.py           `udify` command
web/                 Next.js 15 review workbench
benchmarks/          UdifyBench golden cases
docs/                30+ architecture and research documents
```

## Roadmap

- [x] Content graph with evidence chain (source spans, provenance, confidence)
- [x] MCTS planner + reversible CDL Patch synthesis
- [x] Secure Tool Gateway (risk tiers, allowlist, audit chain)
- [x] Static validation + headless runtime probe
- [x] miu2d end-to-end loop: CLI, API, review workbench
- [x] UdifyBench v0 (10 golden cases)
- [ ] RPG Maker MV/MZ adapter
- [ ] Godot adapter
- [ ] Unity adapter
- [ ] LLM value function vs. heuristic MCTS: public evaluation
- [ ] UdifyBench v1 (50+ cases, cross-engine)
- [ ] Mod sharing and distribution

Longer term, Udify generalizes to any content you can parse into a graph: music, video, interactive fiction. See [VISION.md](docs/VISION.md) and [PLAN.md](docs/PLAN.md).

## Documentation

| Start here | |
|---|---|
| [Technical documentation index](docs/TECHNICAL-DOCUMENTATION-INDEX.md) | Reading order for all docs |
| [Vision](docs/VISION.md) | Why Udify exists |
| [Architecture v3 (OSS-optimized)](docs/ARCHITECTURE-OSS-OPTIMIZED-v3.md) | Current architecture |
| [Security architecture](docs/ARCHITECTURE-SECURITY.md) | Threat model, sandboxing, gateway |
| [Module attack map](docs/MODULE-ATTACK-MAP-v3.md) | Task-level implementation map |

Most design documents are written in Chinese.

## Contributing

Contributions are welcome, especially:

- **Engine adapters**: RPG Maker, Godot, Unity, or the engine you love
- **Benchmark cases**: tricky intents and "should refuse" cases for UdifyBench
- **Parsers and validators**: new file formats, new safety checks
- **Docs and translations**

Open an [issue](https://github.com/tim0n1994/udify/issues) to discuss before larger changes. Before submitting a PR:

```bash
ruff check udify/ tests/ && ruff format --check udify/ tests/
python3 -m pytest tests/ -q
```

## Security

Udify runs tools against files on your machine, so we take this seriously. Please report vulnerabilities privately to **hi@udify.games**, not as a public issue.

## Contact

- Email: **[hi@udify.games](mailto:hi@udify.games)**
- Website: [udify.games](https://udify.games)
- Issues: [GitHub Issues](https://github.com/tim0n1994/udify/issues)

## License

[MIT](LICENSE) © 2026 Udify Contributors

<div align="center">
<sub>We're not here to replace creators. We're here to make everyone one.</sub>
</div>
