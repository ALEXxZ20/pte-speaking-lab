from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from collections.abc import Iterator

MIGRATIONS = Path(__file__).parent / "migrations"


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def migrate(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            if migration.stem in applied:
                continue
            statement = ""
            for line in migration.read_text().splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    connection.execute(statement)
                    statement = ""
            if statement.strip():
                raise ValueError(f"Incomplete migration: {migration.name}")
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, ?)",
                (migration.stem, datetime.now(timezone.utc).isoformat()),
            )
