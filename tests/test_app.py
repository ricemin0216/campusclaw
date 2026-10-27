import io
import sqlite3
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db
from tests.conftest import login


def class_id(app, code: str) -> int:
    with app.app_context():
        return get_db().execute("SELECT id FROM classes WHERE code = ?", (code,)).fetchone()["id"]


def add_teacher_to_class_b(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users(username, display_name, role, password_hash) VALUES (?, ?, ?, ?)",
            ("teacher_b", "B班教师", "teacher", generate_password_hash("test-seed-password")),
        )
        db.execute(
            """INSERT INTO class_memberships(user_id, class_id)
               SELECT users.id, classes.id FROM users, classes
               WHERE users.username = ? AND classes.code = ?""",
            ("teacher_b", "class-b"),
        )
        db.commit()


def test_health_is_public_and_database_ready(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "healthy"}


def test_seeded_accounts_only_store_hashes(app):
    with app.app_context():
        users = get_db().execute("SELECT username, password_hash FROM users ORDER BY username").fetchall()
    assert [user["username"] for user in users] == ["student_a", "student_b", "teacher_a"]
    assert all(user["password_hash"] != "test-seed-password" for user in users)
    assert all("password" not in user.keys() for user in users)


def test_missing_auth_secret_fails_fast(tmp_path):
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        create_app({"SEED_PASSWORD": "only-a-test-password", "DATABASE_PATH": str(tmp_path / "db.sqlite")})


def test_login_and_unauthenticated_protection(client):
    assert client.get("/materials").status_code == 302
    assert client.get("/api/classes/1/materials").status_code == 401
    token_response = client.post("/api/auth/login", json={"username": "teacher_a", "password": "test-seed-password"})
    assert token_response.status_code == 200
    client.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {token_response.json['access_token']}"
    assert client.get("/materials").status_code == 302
    assert client.get("/api/me").status_code == 200


def test_token_logout_allows_another_user_login(client):
    login(client, "teacher_a")
    assert client.get("/api/me").json["display_name"] == "A班教师"

    logout_response = client.post("/api/auth/logout")
    assert logout_response.json == {"status": "logged_out"}
    assert client.get("/api/me").status_code == 401

    login(client, "student_a")
    assert client.get("/api/me").json["display_name"] == "A班学生"


def test_student_upload_is_forbidden_and_creates_nothing(app, client):
    login(client, "student_a")
    response = client.post(
        f"/api/classes/{class_id(app, 'class-a')}/materials",
        data={"file": (io.BytesIO(b"notes"), "notes.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0


def test_class_isolation_upload_listing_and_download(app, client):
    class_a = class_id(app, "class-a")
    class_b = class_id(app, "class-b")
    login(client, "teacher_a")
    assert client.post(
        f"/api/classes/{class_b}/materials",
        data={"file": (io.BytesIO(b"secret"), "b.txt")},
        content_type="multipart/form-data",
    ).status_code == 403

    uploaded = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO(b"lesson"), "lesson.txt")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    material_id = uploaded.json["material"]["id"]
    assert client.get(f"/api/classes/{class_b}/materials").status_code == 403

    client.post("/logout")
    login(client, "student_a")
    listed = client.get(f"/api/classes/{class_a}/materials")
    assert listed.status_code == 200
    assert [record["filename"] for record in listed.json["materials"]] == ["lesson.txt"]

    assert client.get("/materials").status_code == 302
    downloaded = client.get(f"/api/materials/{material_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.data == b"lesson"
    assert downloaded.headers["Content-Disposition"] == 'attachment; filename=lesson.txt'

    client.post("/logout")
    login(client, "student_b")
    denied_list = client.get(f"/api/classes/{class_a}/materials")
    denied_download = client.get(f"/api/materials/{material_id}/download")
    assert denied_list.status_code == 403
    assert denied_list.json == {"error": "forbidden"}
    assert denied_download.status_code == 403


def test_text_and_markdown_uploads_persist_original_file_and_escaped_body(app, client):
    class_a = class_id(app, "class-a")
    content = b"# Lesson\n<script>alert('xss')</script>"
    login(client, "teacher_a")
    uploaded = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO(content), "lesson.MD")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    material_id = uploaded.json["material"]["id"]
    with app.app_context():
        material = get_db().execute("SELECT filename, content_text FROM materials WHERE id = ?", (material_id,)).fetchone()
    assert dict(material) == {"filename": "lesson.MD", "content_text": content.decode("utf-8")}

    client.post("/logout")
    login(client, "student_a")
    opened = client.get(f"/api/materials/{material_id}")
    assert opened.status_code == 200
    assert opened.json["content_text"] == content.decode("utf-8")
    assert opened.json["download_url"] == f"/api/materials/{material_id}/download"
    assert client.get(f"/api/materials/{material_id}/download").data == content


def test_chinese_filename_is_preserved_while_storage_name_is_safe(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    uploaded = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO("校园规则".encode("utf-8")), "中小学生行为守则.txt")},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    material_id = uploaded.json["material"]["id"]
    with app.app_context():
        material = get_db().execute("SELECT filename, storage_name FROM materials WHERE id = ?", (material_id,)).fetchone()
    assert material["filename"] == "中小学生行为守则.txt"
    assert material["storage_name"].endswith("_material.txt")
    assert client.get(f"/api/materials/{material_id}/download").data == "校园规则".encode("utf-8")


def test_upload_rejects_disallowed_formats_and_files_larger_than_ten_megabytes(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    invalid_format = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO(b"pdf"), "lesson.pdf")},
        content_type="multipart/form-data",
    )
    at_limit = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO(b"x" * (10 * 1024 * 1024)), "at-limit.txt")},
        content_type="multipart/form-data",
    )
    too_large = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)), "large.txt")},
        content_type="multipart/form-data",
    )
    assert invalid_format.status_code == 400
    assert at_limit.status_code == 201
    assert too_large.status_code == 413
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 1
        assert get_db().execute("SELECT COUNT(*) FROM knowledge_base_records").fetchone()[0] == 1
    assert len(list(Path(app.config["UPLOAD_DIR"]).iterdir())) == 1


def test_only_a_teacher_in_the_material_class_can_delete_material(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    uploaded = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO(b"delete me"), "delete.txt")},
        content_type="multipart/form-data",
    )
    material_id = uploaded.json["material"]["id"]

    client.post("/logout")
    login(client, "student_a")
    assert client.post(f"/api/materials/{material_id}/delete").status_code == 403
    assert client.get(f"/api/materials/{material_id}").status_code == 200

    client.post("/logout")
    add_teacher_to_class_b(app)
    login(client, "teacher_b")
    assert client.post(f"/api/materials/{material_id}/delete").status_code == 403
    assert client.get(f"/api/materials/{material_id}").status_code == 403

    client.post("/logout")
    login(client, "teacher_a")
    deleted = client.post(f"/api/materials/{material_id}/delete")
    assert deleted.json == {"status": "deleted"}
    assert client.get(f"/api/materials/{material_id}").status_code == 404
    assert client.get(f"/api/materials/{material_id}/download").status_code == 404
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM knowledge_base_records").fetchone()[0] == 0
    assert list(Path(app.config["UPLOAD_DIR"]).iterdir()) == []


def test_failed_material_persistence_leaves_no_record_or_file(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    with app.app_context():
        get_db().execute(
            """CREATE TRIGGER reject_test_material BEFORE INSERT ON materials
               BEGIN SELECT RAISE(ABORT, 'forced test failure'); END;"""
        )
        get_db().commit()

    with pytest.raises(sqlite3.IntegrityError, match="forced test failure"):
        client.post(
            f"/api/classes/{class_a}/materials",
            data={"file": (io.BytesIO(b"lesson"), "will-not-persist.txt")},
            content_type="multipart/form-data",
        )

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0
    assert list(Path(app.config["UPLOAD_DIR"]).iterdir()) == []


def test_foreign_keys_are_enforced(app):
    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError):
            get_db().execute(
                "INSERT INTO class_memberships(user_id, class_id) VALUES (?, ?)", (999, 999)
            )
