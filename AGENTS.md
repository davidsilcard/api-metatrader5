# Repository Guidelines

## Project Structure & Module Organization
This repository is currently minimal, so contributors should follow a consistent Python API layout as files are added:
- `src/` for application code (for example, `src/api_metatrader5/`).
- `tests/` for automated tests mirroring `src/` modules.
- `scripts/` for local utilities (setup, data migration, diagnostics).
- `docs/` for design notes and operational runbooks.
- `.env.example` for documented environment variables (never commit real secrets).

Example module path: `src/api_metatrader5/trading/orders.py` with tests in `tests/trading/test_orders.py`.

## Build, Test, and Development Commands
Use a virtual environment and standard Python tooling:
- `python -m venv .venv` creates the local environment.
- `.\.venv\Scripts\Activate.ps1` activates it on Windows PowerShell.
- `pip install -r requirements.txt` installs runtime dependencies.
- `pip install -r requirements-dev.txt` installs lint/test tooling.
- `pytest -q` runs the test suite.
- `python -m src.api_metatrader5` runs the app entry point (adjust when entry module changes).

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation.
- Use `snake_case` for functions/modules, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- Prefer type hints for public functions and service boundaries.
- Keep modules focused; avoid files that mix API, business logic, and infrastructure concerns.
- If formatting/linting is configured, run it before PRs (typically `ruff check .` and `ruff format .`).

## Testing Guidelines
- Use `pytest` with test files named `test_*.py`.
- Mirror package structure under `tests/` for discoverability.
- Add unit tests for new logic and regression tests for bug fixes.
- Aim for meaningful coverage on core trading and integration paths; avoid untested critical logic.

## Commit & Pull Request Guidelines
Git history is not available in this environment, so use Conventional Commits going forward:
- `feat: add order validation for market buy`
- `fix: handle MT5 reconnect on timeout`

For each PR:
- Describe what changed and why.
- Link related issues/tasks.
- Include test evidence (command + result summary).
- Note configuration or migration impacts.

## Security & Configuration Tips
- Store broker/API credentials only in local `.env` files.
- Keep `.env` in `.gitignore` and update `.env.example` when variables change.
- Do not log secrets, tokens, or account identifiers.

