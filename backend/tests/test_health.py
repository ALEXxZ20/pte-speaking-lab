import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.persistence.database import MIGRATIONS, connect, migrate


def test_health_masks_secret_and_reports_missing_tools(tmp_path):
    settings = Settings(
        _env_file=None, pte_data_dir=tmp_path, ffmpeg_bin="/missing/ffmpeg",
        ffprobe_bin="/missing/ffprobe", openai_api_key=SecretStr("private-test-secret"),
        openai_analysis_model="configured-model",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        result = response.json()
        assert result["database"]["status"] == "ok"
        assert result["ffmpeg"]["status"] == "missing"
        assert result["status"] == "degraded"
        assert result["providers"]["llm"]["configured"] is True
        assert result["providers"]["llm"]["status"] == "configured"
        assert "private-test-secret" not in response.text


def test_migration_is_repeatable_and_connections_enforce_foreign_keys(tmp_path):
    path = tmp_path / "db.sqlite3"
    migrate(path)
    migrate(path)
    with connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(list(MIGRATIONS.glob("*.sql")))
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO child VALUES (123)")
