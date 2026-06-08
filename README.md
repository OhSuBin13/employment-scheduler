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

The current implementation collects Inthiswork IT posts and stores normalized records in SQLite:

- `data/employment.sqlite` is the default local database path.
- `migrations/001_init.sql` defines sources, collection runs, normalized job posts, and source records.
- Raw source payloads are stored in `source_records.raw_json` for traceability.

Generated SQLite files are ignored by git.
