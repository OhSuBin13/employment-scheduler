# employment-scheduler

Local CLI pipeline for collecting employment posts.

## Structure

```text
employment-scheduler/
  scripts/
    collect_today.py
  src/
    employment_scheduler/
      cli.py
      models.py
      normalization.py
      collection/
      sources/
      storage/
  migrations/
    001_init.sql
  data/
    raw/
      inthiswork/
  tests/
```

## Usage

```bash
python scripts/collect_today.py --source inthiswork --date 2026-06-04
python scripts/collect_today.py --source inthiswork --dry-run
```

The current files define the project skeleton only. Collection, storage, and normalization modules are separated so the implementation can be filled in incrementally.
