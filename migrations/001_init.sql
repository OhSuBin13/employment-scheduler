CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  api_type TEXT NOT NULL,
  config_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL,
  mode TEXT NOT NULL,
  target_date TEXT NOT NULL,
  status TEXT NOT NULL,
  request_params_json TEXT NOT NULL,
  raw_dir TEXT,
  fetched_count INTEGER NOT NULL DEFAULT 0,
  inserted_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS job_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  normalized_url_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  excerpt_text TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  latest_source_id INTEGER NOT NULL,
  latest_source_published_at TEXT,
  latest_source_modified_at TEXT,
  FOREIGN KEY (latest_source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS source_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL,
  job_post_id INTEGER NOT NULL,
  collection_run_id INTEGER NOT NULL,
  external_id TEXT NOT NULL,
  original_url TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  title_raw TEXT NOT NULL,
  source_published_at TEXT,
  source_modified_at TEXT,
  categories_json TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  raw_json_path TEXT,
  raw_json TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES sources(id),
  FOREIGN KEY (job_post_id) REFERENCES job_posts(id),
  FOREIGN KEY (collection_run_id) REFERENCES collection_runs(id),
  UNIQUE (source_id, external_id)
);
