from pathlib import Path

import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path: Path):
    return create_app(
        {
            "TESTING": True,
            "AUTH_SECRET": "test-auth-secret-not-for-production",
            "AUTH_TOKEN_SECRET": "test-token-secret-not-for-production",
            "SEED_PASSWORD": "test-seed-password",
            "DATABASE_PATH": str(tmp_path / "campusclaw.db"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username: str):
    response = client.post("/api/auth/login", json={"username": username, "password": "test-seed-password"})
    if response.status_code == 200:
        client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {response.json['access_token']}"
    return response
