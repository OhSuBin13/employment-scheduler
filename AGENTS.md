# Repository Guidelines

## Project Structure & Module Organization

This repository is a small Python package for a local employment-post collection pipeline.

- `src/employment_scheduler/` contains application code.
- `src/employment_scheduler/cli.py` parses command-line options.
- `src/employment_scheduler/collection/` coordinates collection workflow.
- `src/employment_scheduler/sources/` contains source-specific logic, currently `inthiswork.py`.
- `src/employment_scheduler/storage/` contains database/storage code.
- `src/employment_scheduler/models.py` defines shared dataclasses.
- `scripts/collect_today.py` is the executable wrapper that adds `src/` to `sys.path`.
- `migrations/` stores SQL schema changes.
- `data/raw/` is reserved for collected raw source data; keep generated data out of commits unless explicitly needed.
- `tests/` contains pytest tests.

## Build, Test, and Development Commands

Use Python 3.12 or newer.

```bash
python -m pip install -e ".[dev]"
```

Installs the package in editable mode with test dependencies.

```bash
pytest
```

Runs the test suite. `pyproject.toml` configures `pythonpath = ["src"]` and `testpaths = ["tests"]`.

```bash
python scripts/collect_today.py --source inthiswork --date 2026-06-04
python scripts/collect_today.py --source inthiswork --dry-run
```

Runs the collection entrypoint for a date, or validates options without writing data.

## Coding Style & Naming Conventions

Use 4-space indentation, type annotations, and clear module-level docstrings where they add context. Prefer absolute imports from `employment_scheduler`, for example:

```python
from employment_scheduler.models import CollectionOptions
```

Use `snake_case` for modules, functions, variables, and test names. Use dataclasses for shared structured values when they cross module boundaries.

## Testing Guidelines

Tests use `pytest`. Name files `test_*.py` and test functions `test_<behavior>()`. Keep tests focused on observable behavior, such as parsed options, normalized links, source parameters, and storage side effects. Add or update tests when changing CLI parsing, source-specific parameters, URL normalization, migrations, or database behavior.

## Commit & Pull Request Guidelines

Git history currently contains only an initial `first commit`, so there is no established project-specific convention yet. Use concise, imperative commit subjects, for example `Add inthiswork collection runner` or `Fix archive URL normalization`.

Pull requests should include a short summary, the commands run for verification, and any relevant notes about migrations, data files, or CLI behavior changes. Link related issues when available. Screenshots are not required unless a future UI is added.

## Security & Configuration Tips

Do not commit credentials, cookies, API keys, or scraped private data. Keep generated raw collection output under `data/raw/` out of version control unless the file is intentionally used as a small fixture.
