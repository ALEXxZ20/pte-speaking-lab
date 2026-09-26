import base64

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.main import create_app


def test_lan_requires_password_and_protects_api_and_frontend(tmp_path):
    settings = Settings(_env_file=None, pte_data_dir=tmp_path, pte_lan_mode=True,
                        pte_lan_bind_ip="192.168.5.14", pte_lan_password=SecretStr("test-password-123456"))
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 401
        assert client.get("/api/v1/health").status_code == 401
        bad = base64.b64encode(b"pte:wrong").decode()
        assert client.get("/api/v1/health", headers={"Authorization": f"Basic {bad}"}).status_code == 401
        good = base64.b64encode(b"pte:test-password-123456").decode()
        headers = {"Authorization": f"Basic {good}"}
        assert client.get("/", headers=headers).status_code == 200
        assert client.get("/api/v1/health", headers=headers).status_code == 200
        assert client.get("/comparisons/example", headers=headers).status_code == 200
        assert client.get("/api/v1/missing", headers=headers).status_code == 404


def test_lan_rejects_weak_password_and_public_bind_ip(tmp_path):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, pte_lan_bind_ip="0.0.0.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, pte_lan_bind_ip="8.8.8.8")
    with pytest.raises(RuntimeError, match="password"):
        create_app(Settings(_env_file=None, pte_data_dir=tmp_path, pte_lan_mode=True,
                            pte_lan_password=SecretStr("short")))
