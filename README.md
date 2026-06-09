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
- `migrations/001_init.sql` defines only sources and apply-link job posts.
- Storage initializes the SQLite schema by applying the migration; it does not
  delete an existing database file. Remove `data/employment.sqlite` first when a
  clean rebuild is needed.
- Inthiswork responses are limited to the post id and rendered content needed to extract the `지원하러 가기` link.

Generated SQLite files are ignored by git.
