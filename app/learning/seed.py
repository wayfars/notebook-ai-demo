"""Explicit CLI for provisioning a teacher administrator or fictional demo."""
import argparse
import getpass
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

from . import auth, store


def _with_db(path):
    from app import db as app_db
    previous = app_db.DB_PATH
    app_db.DB_PATH = Path(path).expanduser().resolve()
    return app_db, previous


def bootstrap(path, username, display_name):
    password = getpass.getpass("Teacher administrator password (12+ characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise ValueError("passwords did not match")
    encoded = auth.hash_password(password)
    with store.db() as conn:
        if conn.execute("SELECT 1 FROM learn_users WHERE is_admin=1 LIMIT 1").fetchone():
            raise ValueError("a teacher administrator already exists")
        conn.execute("INSERT INTO learn_users(username,display_name,role,is_admin,password_hash) VALUES(?,?, 'teacher',1,?)",
                     (username, display_name, encoded))
    return f"Created teacher administrator {username!r} in {path}"


def demo(path):
    path = Path(path).expanduser().resolve()
    if path.exists() and path.stat().st_size:
        # Refuse any nonempty SQLite database, even one without learning tables.
        try:
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            c.close()
        except sqlite3.Error as e:
            raise ValueError("demo database must be an empty SQLite file") from e
        if tables:
            raise ValueError("demo mode requires an empty throwaway database")
    path.parent.mkdir(parents=True, exist_ok=True)
    password = "Fictional-Demo-2026!"
    users = {}
    with store.db() as conn:
        for username, display, role in [
            ("demo-teacher", "Demo Teacher", "teacher"), ("demo-student", "Demo Student", "student"),
            ("demo-tutor", "Demo Tutor", "tutor"), ("demo-parent", "Demo Parent", "parent")]:
            cur = conn.execute("INSERT INTO learn_users(username,display_name,role,is_admin,password_hash) VALUES(?,?,?,?,?)",
                               (username, display, role, int(role == "teacher"), auth.hash_password(password)))
            users[role] = cur.lastrowid
        course = conn.execute("INSERT INTO learn_courses(teacher_id,title,description) VALUES(?,?,?)",
                              (users["teacher"], "Fictional Algebra", "A sample course with invented learning records.")).lastrowid
        conn.execute("INSERT INTO learn_enrollments VALUES(?,?)", (course, users["student"]))
        conn.execute("INSERT INTO learn_parent_links VALUES(?,?)", (users["parent"], users["student"]))
        conn.execute("INSERT INTO learn_tutor_assignments VALUES(?,?,?)", (course, users["student"], users["tutor"]))
        lesson = conn.execute("INSERT INTO learn_lessons(course_id,author_id,title,content,learning_objectives,topic) VALUES(?,?,?,?,?,?)",
                              (course, users["teacher"], "Linear equations", "An equation stays balanced when the same operation is applied to each side.", "Solve one-step equations", "equations")).lastrowid
        assignment = conn.execute("INSERT INTO learn_assignments(course_id,author_id,title,instructions,lesson_id,topic,max_points,kind) VALUES(?,?,?,?,?,?,?,?)",
                                  (course, users["teacher"], "Practice: isolate x", "Solve 2x + 4 = 12 and explain each step.", lesson, "equations", 10, "official")).lastrowid
        sub = conn.execute("INSERT INTO learn_submissions(assignment_id,student_id,content) VALUES(?,?,?)",
                           (assignment, users["student"], "2x + 4 = 12; subtract 4, then divide by 2. x = 4.")).lastrowid
        conn.execute("INSERT INTO learn_grades(submission_id,grader_id,points,feedback,published) VALUES(?,?,?,?,1)",
                     (sub, users["teacher"], 9, "Clear explanation; check notation.",))
        needs_work = conn.execute("INSERT INTO learn_assignments(course_id,author_id,title,instructions,lesson_id,topic,max_points,kind) VALUES(?,?,?,?,?,?,?,?)",
                                  (course, users["teacher"], "Fraction models", "Represent three quarters in two ways.", lesson, "fractions", 10, "official")).lastrowid
        needs_sub = conn.execute("INSERT INTO learn_submissions(assignment_id,student_id,content) VALUES(?,?,?)",
                                 (needs_work, users["student"], "Three of four parts.")).lastrowid
        conn.execute("INSERT INTO learn_grades(submission_id,grader_id,points,feedback,published) VALUES(?,?,?,?,1)",
                     (needs_sub, users["teacher"], 5, "Show the whole divided into equal parts."))
        conn.execute("INSERT INTO learn_assignments(course_id,author_id,title,instructions,lesson_id,topic,max_points,due_date,kind) VALUES(?,?,?,?,?,?,?,?,?)",
                     (course, users["teacher"], "Review equations", "Complete the two review problems.", lesson, "equations", 5,
                      (date.today()-timedelta(days=1)).isoformat(), "official"))
    return f"Seeded fictional learning demo in {path}. All demo passwords: {password}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bootstrap", help="create the first teacher administrator")
    p.add_argument("--db-path", help="SQLite path (defaults to NOTEBOOK_LEARNING_DB_PATH)")
    p.add_argument("--username", required=True)
    p.add_argument("--display-name", required=True)
    d = sub.add_parser("demo", help="seed fictional data into an empty throwaway database")
    d.add_argument("--db-path", required=True, help="explicit empty throwaway SQLite path")
    args = parser.parse_args(argv)
    from app import db as app_db
    configured_path = Path(app_db.DB_PATH).expanduser().resolve()
    if args.command == "demo":
        path = Path(args.db_path).expanduser().resolve()
        if path == configured_path:
            parser.error("demo path must be separate from NOTEBOOK_LEARNING_DB_PATH")
    else:
        path = Path(args.db_path).expanduser().resolve() if args.db_path else configured_path
    app_db, previous = _with_db(path)
    try:
        message = demo(path) if args.command == "demo" else bootstrap(path, args.username, args.display_name)
        print(message)
    except (ValueError, sqlite3.IntegrityError) as e:
        parser.error(str(e))
    finally:
        app_db.DB_PATH = previous


if __name__ == "__main__":
    main()
