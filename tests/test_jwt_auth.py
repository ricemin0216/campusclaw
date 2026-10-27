import time

import jwt
import pytest

from app import create_app
from app.auth import JwtService, TokenValidationError
from app.db import get_db, revoke_token
from tests.conftest import login


def test_jwt_service_requires_hs256_claims_and_expiration():
    service = JwtService("test-secret")
    token = service.issue(12)
    claims = service.decode(token.value)
    assert claims["sub"] == "12"
    assert {"iat", "exp", "jti"} <= claims.keys()

    expired = jwt.encode({"sub": "12", "iat": 1, "exp": 2, "jti": "expired"}, "test-secret", algorithm="HS256")
    wrong_algorithm = jwt.encode({"sub": "12", "iat": 1, "exp": int(time.time()) + 60, "jti": "wrong"}, "test-secret", algorithm="HS512")
    for invalid in (expired, wrong_algorithm, jwt.encode({"sub": "12"}, "test-secret", algorithm="HS256")):
        with pytest.raises(TokenValidationError):
            service.decode(invalid)


@pytest.mark.parametrize("username", ["teacher_a", "student_a"])
def test_token_login_does_not_create_cookie_and_rejects_invalid_credentials(client, username):
    invalid = client.post("/api/auth/login", json={"username": "teacher_a", "password": "wrong"})
    assert invalid.status_code == 401
    assert invalid.json == {"error": "authentication_failed"}

    response = client.post("/api/auth/login", json={"username": username, "password": "test-seed-password"})
    assert response.status_code == 200
    assert response.json["token_type"] == "Bearer"
    assert response.json["expires_in"] == 3600
    assert isinstance(response.json["access_token"], str)
    assert "Set-Cookie" not in response.headers


def test_browser_shell_keeps_token_in_memory_and_uses_bearer_apis(client):
    page = client.get("/login").get_data(as_text=True)
    assert "workspace-shell" in page
    assert "主要功能" in page
    assert "skill-picker" in page
    assert "选好智能体和技能后直接提问" in page
    assert "ensureConversationForSelection" in page
    assert "使用所选技能新建会话" not in page
    assert "checkbox.type = 'checkbox'" in page
    assert "let accessToken = null" in page
    assert "Authorization', 'Bearer ' + accessToken" in page
    assert "/api/classes/" in page
    assert "/questions" in page
    assert "askQuestion" in page
    assert "/ai-questions" in page
    assert "/api/materials/" in page
    assert "CHAT_MODEL" not in page
    assert "EMBEDDING_API_KEY" not in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page
    assert client.get("/materials").status_code == 302
    assert client.get("/search").status_code == 302


def test_bearer_authentication_rejects_old_cookie_and_revokes_logout(app, client):
    client.set_cookie("session", "legacy-cookie")
    assert client.get("/api/classes/1/materials").status_code == 401
    login(client, "teacher_a")
    assert client.get("/api/classes/1/materials").status_code == 200

    first_logout = client.post("/api/auth/logout")
    second_logout = client.post("/api/auth/logout")
    assert first_logout.json == {"status": "logged_out"}
    assert second_logout.json == {"status": "logged_out"}
    assert client.get("/api/classes/1/materials").status_code == 401
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM revoked_tokens").fetchone()[0] == 1


def test_revocation_cleanup_keeps_unexpired_unique_token(app):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO revoked_tokens(jti, expires_at) VALUES (?, ?)", ("expired", 1))
        db.commit()
        revoke_token("still-valid", int(time.time()) + 3600)
        revoke_token("still-valid", int(time.time()) + 3600)
        rows = db.execute("SELECT jti FROM revoked_tokens ORDER BY jti").fetchall()
    assert [row["jti"] for row in rows] == ["still-valid"]


def test_missing_token_secret_fails_without_echoing_other_secrets(tmp_path):
    with pytest.raises(RuntimeError) as error:
        create_app({"AUTH_SECRET": "server-secret", "SEED_PASSWORD": "seed-password", "DATABASE_PATH": str(tmp_path / "db")})
    assert "AUTH_TOKEN_SECRET" in str(error.value)
    assert "server-secret" not in str(error.value)
    assert "seed-password" not in str(error.value)


def test_empty_chat_model_fails_without_echoing_other_secrets(tmp_path):
    with pytest.raises(RuntimeError) as error:
        create_app({
            "TESTING": True,
            "AUTH_SECRET": "server-secret",
            "AUTH_TOKEN_SECRET": "token-secret",
            "SEED_PASSWORD": "seed-password",
            "CHAT_MODEL": "",
            "DATABASE_PATH": str(tmp_path / "db"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
        })
    assert "CHAT_MODEL" in str(error.value)
    assert "server-secret" not in str(error.value)
    assert "seed-password" not in str(error.value)
