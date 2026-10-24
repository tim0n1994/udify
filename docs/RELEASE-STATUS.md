# Udify 0.1.0a1 release status

Release identity:

- Git tag: `v0.1.0-alpha.1`
- Python package: `0.1.0a1`
- Distribution: GitHub Release source archive, sdist, and wheel
- Date: 2026-10-24
- Stage: public technical preview

## Verified before release

- Local Python 3.14 validation: Ruff check, Ruff format check, blocking mypy, 396 tests, 64.05% coverage, and sdist/wheel build.
- GitHub Actions validation: Python 3.12 and 3.13 jobs passed in [CI run 40042818412](https://github.com/tim0n1994/udify/actions/runs/40042818412).
- The release workflow builds the same sdist and wheel shape and runs `twine check` before creating the GitHub Release.
- License file is present and the package metadata declares MIT.
- The README and Chinese entry point describe the same scope and the same release boundary.

## Supported in this preview

- The Python CLI and API path for `miu2d` engine game content.
- Evidence-backed CDL patch generation, preview, validation, approval, apply, packaging, and rollback paths represented by the repository tests.
- Source-level access to the Next.js review workbench under `web/`.

## Explicit boundary

- Other engines are roadmap items.
- The web workbench is not included in the Python wheel; run it from the repository source.
- No PyPI upload is part of this first preview.
- No production hosting, multi-user service, or external LLM provider acceptance is claimed.
- A README command is documentation; the release checks above prove packaging and tests, not every external game or hardware environment.

## Release commands

```bash
python -m pip install udify-0.1.0a1-py3-none-any.whl
udify --game-root ./my-game mod "Make the boss harder, but keep the map reachable"
udify --game-root ./my-game preview
udify --game-root ./my-game apply <session_id>
udify --game-root ./my-game rollback <session_id>
```

For the web workbench:

```bash
cd web
pnpm install
pnpm dev
```
