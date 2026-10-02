"""Persistence for the learning workspace. This module only owns learn_* tables."""
import sqlite3
from contextlib import contextmanager

from app.db import connect

SCHEMA = """
CREATE TABLE IF NOT EXISTS learn_users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('teacher','student','tutor','parent')),
 is_admin INTEGER NOT NULL DEFAULT 0, password_hash TEXT NOT NULL,
 learning_preference TEXT NOT NULL DEFAULT 'balanced', created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE TABLE IF NOT EXISTS learn_sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 csrf_hash TEXT NOT NULL, csrf_token TEXT NOT NULL DEFAULT '', expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE INDEX IF NOT EXISTS learn_sessions_expiry ON learn_sessions(expires_at);
CREATE TABLE IF NOT EXISTS learn_parent_links (
 parent_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 student_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 PRIMARY KEY(parent_id,student_id)
);
CREATE TABLE IF NOT EXISTS learn_courses (
 id INTEGER PRIMARY KEY, teacher_id INTEGER NOT NULL REFERENCES learn_users(id),
 title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE TABLE IF NOT EXISTS learn_enrollments (
 course_id INTEGER NOT NULL REFERENCES learn_courses(id) ON DELETE CASCADE,
 student_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 PRIMARY KEY(course_id,student_id)
);
CREATE TABLE IF NOT EXISTS learn_tutor_assignments (
 course_id INTEGER NOT NULL REFERENCES learn_courses(id) ON DELETE CASCADE,
 student_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 tutor_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 PRIMARY KEY(course_id,student_id,tutor_id)
);
CREATE TABLE IF NOT EXISTS learn_lessons (
 id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES learn_courses(id) ON DELETE CASCADE,
 author_id INTEGER NOT NULL REFERENCES learn_users(id), title TEXT NOT NULL, content TEXT NOT NULL,
 learning_objectives TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL DEFAULT '', target_student_id INTEGER REFERENCES learn_users(id),
 created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE TABLE IF NOT EXISTS learn_assignments (
 id INTEGER PRIMARY KEY, course_id INTEGER NOT NULL REFERENCES learn_courses(id) ON DELETE CASCADE,
 author_id INTEGER NOT NULL REFERENCES learn_users(id), title TEXT NOT NULL, instructions TEXT NOT NULL,
 lesson_id INTEGER REFERENCES learn_lessons(id), topic TEXT NOT NULL DEFAULT '', max_points REAL NOT NULL,
 due_date TEXT, target_student_id INTEGER REFERENCES learn_users(id), kind TEXT NOT NULL CHECK(kind IN ('official','practice')),
 created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE TABLE IF NOT EXISTS learn_submissions (
 id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL REFERENCES learn_assignments(id) ON DELETE CASCADE,
 student_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE, content TEXT NOT NULL,
 submitted_at TEXT NOT NULL DEFAULT(datetime('now')), UNIQUE(assignment_id,student_id)
);
CREATE TABLE IF NOT EXISTS learn_grades (
 id INTEGER PRIMARY KEY, submission_id INTEGER NOT NULL UNIQUE REFERENCES learn_submissions(id) ON DELETE CASCADE,
 grader_id INTEGER NOT NULL REFERENCES learn_users(id), points REAL NOT NULL, feedback TEXT NOT NULL DEFAULT '',
 published INTEGER NOT NULL DEFAULT 0, graded_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE TABLE IF NOT EXISTS learn_chats (
 id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES learn_users(id) ON DELETE CASCADE,
 course_id INTEGER NOT NULL REFERENCES learn_courses(id) ON DELETE CASCADE,
 lesson_id INTEGER REFERENCES learn_lessons(id), assignment_id INTEGER REFERENCES learn_assignments(id),
 created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE TABLE IF NOT EXISTS learn_chat_messages (
 id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL REFERENCES learn_chats(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT(datetime('now'))
);
CREATE INDEX IF NOT EXISTS learn_chat_messages_chat ON learn_chat_messages(chat_id,id);
"""


@contextmanager
def db():
    """Open the configured Notebook SQLite file without initializing personal tables."""
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(learn_sessions)")}
        if "csrf_token" not in cols:
            conn.execute("ALTER TABLE learn_sessions ADD COLUMN csrf_token TEXT NOT NULL DEFAULT ''")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rowdict(row):
    return dict(row) if row is not None else None


def user_public(row):
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"],
            "role": row["role"], "is_admin": bool(row["is_admin"]),
            "learning_preference": row["learning_preference"]}
