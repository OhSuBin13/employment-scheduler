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

CREATE TABLE IF NOT EXISTS job_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL,
  external_id TEXT NOT NULL,
  apply_url TEXT NOT NULL,
  apply_url_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES sources(id),
  UNIQUE (source_id, external_id)
);

CREATE TABLE IF NOT EXISTS notion_publish_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_post_id INTEGER NOT NULL UNIQUE,
  notion_page_id TEXT NOT NULL,
  notion_url TEXT,
  analysis_path TEXT NOT NULL,
  analysis_hash TEXT NOT NULL,
  published_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (job_post_id) REFERENCES job_posts(id)
);
