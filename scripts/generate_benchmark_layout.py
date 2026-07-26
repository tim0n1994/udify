"""从 miu2d_cases.py 生成 benchmarks/miu2d/<case>/ 目录布局（BENCH-01）。

对应 ITERATION-PLAN-2026-07.md §8:286：
    benchmarks/miu2d/<case>/{input_game, intent.md, expected_patterns.yaml,
                            forbidden_patterns.yaml, probes.yaml, scoring.yaml}

运行：``python3 scripts/generate_benchmark_layout.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让脚本能 import udify 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # type: ignore[import-not-found]  # 可选依赖，运行时检查

from udify.core.evaluation.miu2d_cases import get_miu2d_golden_cases


def write_case(
    base: Path,
    case_id: str,
    intent: str,
    game_fixture: dict,
    expected,
    forbidden,
    constraints,
    probes,
) -> None:
    case_dir = base / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    # input_game/
    game_dir = case_dir / "input_game"
    game_dir.mkdir(exist_ok=True)
    for fname, content in game_fixture.items():
        (game_dir / fname).write_text(content)
    # intent.md
    (case_dir / "intent.md").write_text(f"# {case_id}\n\n{intent}\n")
    # expected_patterns.yaml
    (case_dir / "expected_patterns.yaml").write_text(
        yaml.safe_dump(list(expected), allow_unicode=True)
    )
    # forbidden_patterns.yaml
    (case_dir / "forbidden_patterns.yaml").write_text(
        yaml.safe_dump(list(forbidden), allow_unicode=True)
    )
    # scoring.yaml
    scoring = {
        "hard_constraints": list(constraints),
        "weights": {"goal": 0.45, "constraint": 0.30, "scope": 0.25},
    }
    (case_dir / "scoring.yaml").write_text(yaml.safe_dump(scoring, allow_unicode=True))
    # probes.yaml
    (case_dir / "probes.yaml").write_text(yaml.safe_dump(list(probes), allow_unicode=True))


def main() -> None:
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("PyYAML required: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    base = Path(__file__).resolve().parent.parent / "benchmarks" / "miu2d"
    base.mkdir(parents=True, exist_ok=True)
    cases = get_miu2d_golden_cases()
    for c in cases:
        gc = c.case
        write_case(
            base,
            gc.case_id,
            gc.intent,
            c.game_fixture,
            gc.expected_patterns,
            gc.forbidden_patterns,
            gc.hard_constraints,
            gc.probes,
        )
    print(f"Generated {len(cases)} cases under {base}")


if __name__ == "__main__":
    main()
