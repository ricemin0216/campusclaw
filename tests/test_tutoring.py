import io
import json

import pytest

from app.db import get_db, initialize_database
from app.tutoring import SkillValidationError, build_system_message, parse_skill_source, route_skill
from tests.conftest import login


class StreamingChat:
    def __init__(self, chunks=None):
        self.chunks = chunks or ["先检查去括号时", "是否乘到了每一项。[1]"]
        self.calls = []

    def stream_messages(self, messages):
        self.calls.append(messages)
        yield from self.chunks


def class_id(app, code):
    with app.app_context():
        return get_db().execute("SELECT id FROM classes WHERE code = ?", (code,)).fetchone()["id"]


def skill_source(name="方程解题引导", enabled="是"):
    return (
        f"名称：{name}\n"
        "适用条件：方程,去括号,未知数\n"
        "资料：数学\n"
        "工具：knowledge_search\n"
        f"启用：{enabled}\n\n"
        "先判断学生已有步骤是否正确，只提示下一步，不给最终得数。"
    )


def test_primary_school_seed_skills_are_repeatable_and_bound_to_default_agents(app):
    expected = {
        "古诗词讲解与推荐",
        "英语词义例句与搭配",
        "汉字词语学习",
        "生活科学探究",
    }
    with app.app_context():
        db = get_db()
        count_before = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
        for class_code, agent_seed_key in (
            ("class-a", "seed-agent-class-a"),
            ("class-b", "seed-agent-class-b"),
        ):
            class_row = db.execute("SELECT id FROM classes WHERE code = ?", (class_code,)).fetchone()
            rows = db.execute(
                "SELECT * FROM skills WHERE class_id = ? AND seed_key IS NOT NULL",
                (class_row["id"],),
            ).fetchall()
            assert expected.issubset({row["name"] for row in rows})
            for row in rows:
                assert parse_skill_source(row["source_text"])["name"] == row["name"]
            assert route_skill("这首古诗的诗意是什么？请推荐相似诗词", [dict(row) for row in rows])["name"] == "古诗词讲解与推荐"
            poetry = route_skill("请讲讲《静夜思》", [dict(row) for row in rows])
            assert poetry["name"] == "古诗词讲解与推荐"
            assert "拓展阅读" in poetry["description"]
            poetry_prompt = build_system_message("学习助手", poetry, False)
            for section in ("作品信息", "诗意讲解", "画面与情感", "拓展阅读"):
                assert section in poetry_prompt
            assert route_skill("apple 这个英语单词是什么意思？请给例句和词组搭配", [dict(row) for row in rows])["name"] == "英语词义例句与搭配"
            agent = db.execute(
                "SELECT id FROM tutor_agents WHERE seed_key = ?", (agent_seed_key,)
            ).fetchone()
            bound = {
                row["skill_id"]
                for row in db.execute(
                    "SELECT skill_id FROM tutor_agent_skills WHERE agent_id = ?", (agent["id"],)
                ).fetchall()
            }
            assert {row["id"] for row in rows}.issubset(bound)
        db.execute(
            "UPDATE skills SET trigger_text = '旧触发', description = '旧说明' WHERE seed_key = 'seed-class-a-poetry-guide'"
        )
        db.commit()
        initialize_database()
        assert db.execute("SELECT COUNT(*) FROM skills").fetchone()[0] == count_before
        refreshed = db.execute(
            "SELECT trigger_text, description FROM skills WHERE seed_key = 'seed-class-a-poetry-guide'"
        ).fetchone()
        assert "静夜思" in refreshed["trigger_text"]
        assert "拓展阅读" in refreshed["description"]


def test_skill_parser_and_router_are_deterministic():
    parsed = parse_skill_source(skill_source())
    assert parsed["name"] == "方程解题引导"
    assert json.loads(parsed["tools_json"]) == ["knowledge_search"]
    winner = route_skill(
        "这道方程应该怎样去括号？",
        [
            {"id": 9, "enabled": 1, "name": "只命中一个", "trigger_text": "方程"},
            {"id": 3, "enabled": 1, "name": "命中两个", "trigger_text": "方程,去括号"},
        ],
    )
    assert winner["id"] == 3
    assert route_skill("无关问题", [{"id": 1, "enabled": 1, "trigger_text": "方程"}]) is None

    for invalid in (
        "名称：缺说明\n适用条件：方程\n启用：是",
        "名称：非法工具\n适用条件：方程\n工具：shell\n启用：是\n\n说明",
        "名称：重复\n名称：重复2\n适用条件：方程\n启用：是\n\n说明",
    ):
        with pytest.raises(SkillValidationError):
            parse_skill_source(invalid)


def test_teacher_manages_agents_skills_and_student_is_read_only(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    created_skill = client.post(
        f"/api/classes/{class_a}/skills", json={"source_text": skill_source("自建解题引导")}
    )
    assert created_skill.status_code == 201
    skill_id = created_skill.json["skill"]["id"]

    material = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO("数学方程去括号时要乘到每一项。".encode()), "数学自学笔记.md")},
        content_type="multipart/form-data",
    ).json["material"]
    agent = client.post(
        f"/api/classes/{class_a}/agents",
        json={
            "name": "方程辅导员",
            "prompt": "你是启发式数学老师。",
            "enabled": True,
            "skill_ids": [skill_id],
            "material_ids": [material["id"]],
        },
    )
    assert agent.status_code == 201
    assert agent.json["agent"]["skill_ids"] == [skill_id]
    assert agent.json["agent"]["material_ids"] == [material["id"]]

    client.post("/api/auth/logout")
    login(client, "student_a")
    assert client.post(f"/api/classes/{class_a}/skills", json={"source_text": skill_source("学生技能")}).status_code == 403
    assert client.post(f"/api/classes/{class_a}/agents", json={"name": "学生智能体"}).status_code == 403
    assert any(item["name"] == "方程辅导员" for item in client.get(f"/api/classes/{class_a}/agents").json["agents"])


def test_conversation_locks_agent_streams_sse_and_hides_other_users(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    skill = client.post(
        f"/api/classes/{class_a}/skills", json={"source_text": skill_source("流式解题引导")}
    ).json["skill"]
    bound = client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO("数学方程去括号时要乘到每一项。".encode()), "数学资料.md")},
        content_type="multipart/form-data",
    ).json["material"]
    client.post(
        f"/api/classes/{class_a}/materials",
        data={"file": (io.BytesIO("未绑定秘密材料。".encode()), "未绑定资料.md")},
        content_type="multipart/form-data",
    )
    agent = client.post(
        f"/api/classes/{class_a}/agents",
        json={"name": "流式辅导员", "prompt": "你是启发式老师。", "skill_ids": [skill["id"]], "material_ids": [bound["id"]]},
    ).json["agent"]

    client.post("/api/auth/logout")
    login(client, "student_a")
    conversation = client.post(
        f"/api/classes/{class_a}/conversations", json={"agent_id": agent["id"]}
    ).json["conversation"]
    chat = StreamingChat()
    app.extensions["chat_client"] = chat
    response = client.post(
        f"/api/conversations/{conversation['id']}/messages",
        json={"question": "这道方程怎么去括号？", "agent_id": 999999},
    )
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert body.index("event: meta") < body.index("event: delta") < body.index("event: done")
    assert '"name":"流式解题引导"' in body
    assert body.count("event: delta") == 2
    assert "未绑定秘密材料" not in json.dumps(chat.calls, ensure_ascii=False)
    assert "数学方程去括号" in json.dumps(chat.calls, ensure_ascii=False)

    replay = client.get(f"/api/conversations/{conversation['id']}").json["conversation"]
    assert replay["title"] == "这道方程怎么去括号？"
    assert [message["role"] for message in replay["messages"]] == ["user", "assistant"]
    assert replay["messages"][1]["skill_name"] == "流式解题引导"
    assert replay["messages"][1]["citations"][0]["title"] == "数学资料.md"

    client.post("/api/auth/logout")
    login(client, "student_b")
    forbidden = client.get(f"/api/conversations/{conversation['id']}")
    missing = client.get("/api/conversations/999999")
    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.json == missing.json == {"error": "not_found"}


def test_user_selects_and_updates_skills_loaded_by_conversation(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    math_skill = client.post(
        f"/api/classes/{class_a}/skills", json={"source_text": skill_source("用户数学技能")}
    ).json["skill"]
    chinese_skill = client.post(
        f"/api/classes/{class_a}/skills",
        json={
            "source_text": (
                "名称：用户语文技能\n适用条件：作文,开头\n资料：语文\n"
                "工具：knowledge_search\n启用：是\n\n先提示作文结构。"
            )
        },
    ).json["skill"]
    unbound_skill = client.post(
        f"/api/classes/{class_a}/skills", json={"source_text": skill_source("未开放技能")}
    ).json["skill"]
    agent = client.post(
        f"/api/classes/{class_a}/agents",
        json={
            "name": "用户选技能助手",
            "skill_ids": [math_skill["id"], chinese_skill["id"]],
            "material_ids": [],
        },
    ).json["agent"]

    client.post("/api/auth/logout")
    login(client, "student_a")
    invalid = client.post(
        f"/api/classes/{class_a}/conversations",
        json={"agent_id": agent["id"], "skill_ids": [unbound_skill["id"]]},
    )
    assert invalid.status_code == 400
    assert invalid.json["error"] == "invalid_skill_selection"

    conversation = client.post(
        f"/api/classes/{class_a}/conversations",
        json={"agent_id": agent["id"], "skill_ids": [math_skill["id"]]},
    ).json["conversation"]
    assert conversation["skill_ids"] == [math_skill["id"]]

    app.extensions["chat_client"] = StreamingChat(["先看题目要求。"])
    first = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"question": "作文开头怎么写？"}
    ).get_data(as_text=True)
    assert '"skill":null' in first

    updated = client.patch(
        f"/api/conversations/{conversation['id']}/skills",
        json={"skill_ids": [chinese_skill["id"]]},
    )
    assert updated.status_code == 200
    assert updated.json["conversation"]["skill_ids"] == [chinese_skill["id"]]
    second = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"question": "作文开头怎么写？"}
    ).get_data(as_text=True)
    assert '"name":"用户语文技能"' in second

    cleared = client.patch(
        f"/api/conversations/{conversation['id']}/skills", json={"skill_ids": []}
    )
    assert cleared.status_code == 200
    assert cleared.json["conversation"]["skill_ids"] == []

    client.post("/api/auth/logout")
    login(client, "student_b")
    assert client.patch(
        f"/api/conversations/{conversation['id']}/skills", json={"skill_ids": []}
    ).status_code == 404


def test_existing_conversation_survives_agent_disable_and_empty_evidence_still_answers(app, client):
    class_a = class_id(app, "class-a")
    login(client, "teacher_a")
    created = client.post(
        f"/api/classes/{class_a}/agents",
        json={"name": "无资料助手", "prompt": "直接给出简短提示。", "enabled": True},
    ).json["agent"]
    client.post("/api/auth/logout")
    login(client, "student_a")
    conversation = client.post(
        f"/api/classes/{class_a}/conversations", json={"agent_id": created["id"]}
    ).json["conversation"]

    client.post("/api/auth/logout")
    login(client, "teacher_a")
    disabled = client.patch(
        f"/api/classes/{class_a}/agents/{created['id']}", json={"enabled": False}
    )
    assert disabled.status_code == 200

    client.post("/api/auth/logout")
    login(client, "student_a")
    assert client.post(f"/api/classes/{class_a}/conversations", json={"agent_id": created["id"]}).status_code == 404
    app.extensions["chat_client"] = StreamingChat(["可以先整理已知条件 [", "1]，", "再尝试列式。"])
    streamed = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"question": "我应该从哪里开始？"}
    ).get_data(as_text=True)
    assert '"citations":[]' in streamed
    assert "资料中未找到相关内容" not in streamed
    assert "[1]" not in streamed
    assert "可以先整理已知条件" in streamed


def test_openapi_and_swagger_are_public(client):
    document = client.get("/api/openapi.json")
    assert document.status_code == 200
    assert document.json["openapi"] == "3.0.3"
    assert "/api/conversations/{conversation_id}/messages" in document.json["paths"]
    assert client.get("/swagger").status_code == 200
