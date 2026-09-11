#!/usr/bin/env bash
# File list must stay identical to .github/workflows/ci.yml ("Mypy on new v3 modules").
# --follow-imports=silent skips legacy transitive imports; full-package mypy stays non-blocking.
set -euo pipefail
cd "$(dirname "$0")/.."

MYPY=(mypy)
if [[ -x .venv/bin/mypy ]]; then
  MYPY=(.venv/bin/mypy)
fi

exec "${MYPY[@]}" --follow-imports=silent \
  udify/models/source.py \
  udify/core/text_normalize.py \
  udify/core/tool_gateway/sandbox.py \
  udify/core/tool_gateway/policy.py \
  udify/core/tool_gateway/lockfile.py \
  udify/core/tool_gateway/audit.py \
  udify/core/validation/static_validator.py \
  udify/core/validation/runtime_probe.py \
  udify/core/evaluation/eval_v3.py \
  udify/core/planning/action_schemas.py \
  udify/core/orchestration/mod_job.py \
  udify/core/orchestration/job_store.py \
  udify/core/orchestration/job_runner.py \
  udify/api/app.py \
  udify/api/schemas.py
