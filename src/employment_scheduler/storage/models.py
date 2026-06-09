from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseStorageResult:
    db_path: Path
    fetched_count: int
    unique_count: int
    inserted_count: int
    updated_count: int
    duplicate_count: int
