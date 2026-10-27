"""SQLite persistence and repeatable demo data for CampusClaw Freebird."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from flask import current_app, g
from werkzeug.security import generate_password_hash


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS class_memberships (
    user_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, class_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    uploaded_by INTEGER NOT NULL,
    filename TEXT NOT NULL,
    storage_name TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    content_text TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS knowledge_base_records (
    id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL UNIQUE,
    class_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS revoked_tokens_expires_at ON revoked_tokens(expires_at);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    trigger_text TEXT NOT NULL,
    subject_text TEXT NOT NULL DEFAULT '',
    tools_json TEXT NOT NULL DEFAULT '[]',
    description TEXT NOT NULL,
    source_text TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    seed_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (class_id, name),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tutor_agents (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    seed_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (class_id, name),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tutor_agent_skills (
    agent_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    PRIMARY KEY (agent_id, skill_id),
    FOREIGN KEY (agent_id) REFERENCES tutor_agents(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tutor_agent_materials (
    agent_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL,
    PRIMARY KEY (agent_id, material_id),
    FOREIGN KEY (agent_id) REFERENCES tutor_agents(id) ON DELETE CASCADE,
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mcp_servers (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    auth_token_ciphertext TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disconnected' CHECK (status IN ('disconnected', 'connected', 'error')),
    last_error TEXT,
    connected_at TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (class_id, name),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS mcp_tools (
    id INTEGER PRIMARY KEY,
    server_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    input_schema_json TEXT NOT NULL DEFAULT '{}',
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (server_id, name),
    FOREIGN KEY (server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mcp_audit_logs (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    server_id INTEGER,
    tool_ref TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'denied', 'error')),
    user_id INTEGER NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (server_id) REFERENCES mcp_servers(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    agent_id INTEGER NOT NULL,
    skill_selection_initialized INTEGER NOT NULL DEFAULT 1 CHECK (skill_selection_initialized IN (0, 1)),
    title TEXT NOT NULL DEFAULT '新的提问',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (agent_id) REFERENCES tutor_agents(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS conversation_skills (
    conversation_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    PRIMARY KEY (conversation_id, skill_id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    skill_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS conversations_owner_updated ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS conversation_skills_skill_id ON conversation_skills(skill_id);
CREATE INDEX IF NOT EXISTS messages_conversation_id ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS mcp_tools_server_id ON mcp_tools(server_id);
CREATE INDEX IF NOT EXISTS mcp_audit_class_created ON mcp_audit_logs(class_id, created_at DESC, id DESC);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE_PATH"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_: object | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def initialize_database() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    columns = {column["name"] for column in db.execute("PRAGMA table_info(materials)").fetchall()}
    if "content_text" not in columns:
        db.execute("ALTER TABLE materials ADD COLUMN content_text TEXT NOT NULL DEFAULT ''")
    conversation_columns = {
        column["name"] for column in db.execute("PRAGMA table_info(conversations)").fetchall()
    }
    if "skill_selection_initialized" not in conversation_columns:
        db.execute(
            "ALTER TABLE conversations ADD COLUMN skill_selection_initialized INTEGER NOT NULL DEFAULT 0"
        )
    db.execute(
        """INSERT OR IGNORE INTO conversation_skills(conversation_id, skill_id)
           SELECT c.id, binding.skill_id
           FROM conversations c
           JOIN tutor_agent_skills binding ON binding.agent_id = c.agent_id
           WHERE c.skill_selection_initialized = 0"""
    )
    db.execute(
        "UPDATE conversations SET skill_selection_initialized = 1 WHERE skill_selection_initialized = 0"
    )
    db.commit()
    _seed_data(db, current_app.config["SEED_PASSWORD"])


def _seed_data(db: sqlite3.Connection, seed_password: str) -> None:
    """Create deterministic classes and users without storing plaintext passwords."""
    db.execute("INSERT OR IGNORE INTO classes(code, name) VALUES (?, ?)", ("class-a", "A班"))
    db.execute("INSERT OR IGNORE INTO classes(code, name) VALUES (?, ?)", ("class-b", "B班"))

    accounts = (
        ("teacher_a", "A班教师", "teacher", "class-a"),
        ("student_a", "A班学生", "student", "class-a"),
        ("student_b", "B班学生", "student", "class-b"),
    )
    password_hash = generate_password_hash(seed_password)
    for username, display_name, role, class_code in accounts:
        db.execute(
            """
            INSERT OR IGNORE INTO users(username, display_name, role, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (username, display_name, role, password_hash),
        )
        db.execute(
            """
            INSERT OR IGNORE INTO class_memberships(user_id, class_id)
            SELECT users.id, classes.id FROM users, classes
            WHERE users.username = ? AND classes.code = ?
            """,
            (username, class_code),
        )

    class_a = db.execute("SELECT id FROM classes WHERE code = 'class-a'").fetchone()["id"]
    class_b = db.execute("SELECT id FROM classes WHERE code = 'class-b'").fetchone()["id"]
    skill_templates = (
        (
            "math-guide",
            "数学解题引导",
            "方程,去括号,分数,通分,面积,应用题,未知数,行程",
            "数学",
            "学生正在自己做数学作业。先判断已有步骤是否正确，只指出下一步该检查什么，不要算出最终得数。",
        ),
        (
            "chinese-guide",
            "语文解题引导",
            "默写,阅读,中心,作文,开头,段落,词语",
            "语文",
            "学生正在背诵、做阅读或修改作文。先接住学生已写出的内容，再提示应该寻找哪类线索，不直接给出完整答案。",
        ),
        (
            "poetry-guide",
            "古诗词讲解与推荐",
            "古诗,诗词,诗句,诗名,作者,诗人,诗意,翻译,赏析,意境,情感,主题,推荐,相似,类似,拓展,延伸,同类,背诵,静夜思,春晓,登鹳雀楼,望庐山瀑布,悯农,咏鹅,江雪,村居,小池",
            "语文",
            "面向小学生完成古诗词的理解与拓展。回答应清楚展示四部分：①作品名、作者和朝代；②用浅显现代汉语解释关键词与诗句大意；③描述诗中画面、主题和情感；④拓展阅读，推荐二至三首同作者、同主题、同季节或同意象的古诗词，并逐首写明题目、作者、朝代和关联理由。学生只给出一句诗时，先尝试识别作品；无法确定时再请学生补充。除非学生明确只要简短释义，否则必须给出拓展阅读。不要编造原文、作者或出处。",
        ),
        (
            "english-vocabulary-guide",
            "英语词义例句与搭配",
            "英语,英文,单词,词义,什么意思,例句,造句,词组,短语,搭配,近义词,反义词",
            "英语",
            "面向小学生解释英语单词。依次给出常见词性和中文词义、一至两个简短自然的英文例句及中文翻译、二至四个常用词组或搭配；必要时提醒易混淆单词。句子使用小学阶段常见词汇，不堆砌生僻含义；若拼写不明确，先请学生确认单词。",
        ),
        (
            "character-words-guide",
            "汉字词语学习",
            "汉字,拼音,部首,笔画,组词,造句,近义词,反义词,多音字,成语",
            "语文",
            "帮助小学生学习汉字和词语。按问题给出拼音、常用含义、部首或关键笔画、常见组词和一个简短例句；遇到多音字时按不同读音分别举例，并提醒容易写错或混淆的地方。不要一次提供超出学生需要的大量信息。",
        ),
        (
            "daily-science-guide",
            "生活科学探究",
            "科学,为什么,实验,观察,植物,动物,天气,水,空气,光,声音,磁铁",
            "科学",
            "用观察、猜想、验证的顺序解释小学生提出的生活科学问题。先用生活中的例子说明现象，再给出简单原理；可以推荐安全、低风险且有成人陪同的观察活动，但不得建议接触明火、强电、危险化学品或进行可能伤害身体的实验。",
        ),
    )
    legacy_keys = {
        ("class-a", "math-guide"): "seed-math-guide",
        ("class-a", "chinese-guide"): "seed-chinese-guide",
    }
    for class_code, class_id in (("class-a", class_a), ("class-b", class_b)):
        for slug, name, trigger_text, subject_text, description in skill_templates:
            seed_key = legacy_keys.get((class_code, slug), f"seed-{class_code}-{slug}")
            source_text = (
                f"名称：{name}\n适用条件：{trigger_text}\n资料：{subject_text}\n"
                f"工具：knowledge_search\n启用：是\n\n{description}"
            )
            db.execute(
                """INSERT INTO skills(
                       class_id, name, trigger_text, subject_text, tools_json, description, source_text, enabled, seed_key
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(seed_key) DO UPDATE SET
                       name = excluded.name,
                       trigger_text = excluded.trigger_text,
                       subject_text = excluded.subject_text,
                       tools_json = excluded.tools_json,
                       description = excluded.description,
                       source_text = excluded.source_text,
                       updated_at = CURRENT_TIMESTAMP""",
                (class_id, name, trigger_text, subject_text, json.dumps(["knowledge_search"]), description, source_text, seed_key),
            )

    for seed_key, class_id, name in (
        ("seed-agent-class-a", class_a, "A班学习助手"),
        ("seed-agent-class-b", class_b, "B班学习助手"),
    ):
        db.execute(
            """INSERT OR IGNORE INTO tutor_agents(class_id, name, prompt, enabled, seed_key)
               VALUES (?, ?, ?, 1, ?)""",
            (class_id, name, "你是本班耐心、准确的学习助手。回答要适合中小学生理解。", seed_key),
        )
    for agent_seed_key, class_id in (("seed-agent-class-a", class_a), ("seed-agent-class-b", class_b)):
        agent_id = db.execute(
            "SELECT id FROM tutor_agents WHERE seed_key = ?", (agent_seed_key,)
        ).fetchone()["id"]
        db.execute(
            """INSERT OR IGNORE INTO tutor_agent_skills(agent_id, skill_id)
               SELECT ?, id FROM skills WHERE class_id = ? AND seed_key IS NOT NULL""",
            (agent_id, class_id),
        )
    db.commit()


def get_user(user_id: int) -> sqlite3.Row | None:
    return get_db().execute(
        "SELECT id, username, display_name, role FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def get_user_by_username(username: str) -> sqlite3.Row | None:
    return get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def is_member(user_id: int, class_id: int) -> bool:
    return (
        get_db()
        .execute(
            "SELECT 1 FROM class_memberships WHERE user_id = ? AND class_id = ?",
            (user_id, class_id),
        )
        .fetchone()
        is not None
    )


def revoke_token(jti: str, expires_at: int) -> None:
    db = get_db()
    db.execute("DELETE FROM revoked_tokens WHERE expires_at <= strftime('%s', 'now')")
    db.execute("INSERT OR IGNORE INTO revoked_tokens(jti, expires_at) VALUES (?, ?)", (jti, expires_at))
    db.commit()


def is_token_revoked(jti: str) -> bool:
    db = get_db()
    db.execute("DELETE FROM revoked_tokens WHERE expires_at <= strftime('%s', 'now')")
    db.commit()
    return db.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,)).fetchone() is not None
