"""Hermetic checks for learning auth, ownership, and grade visibility."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app import db as app_db
from app.learning import auth, store
from app.learning.api import router


@pytest.fixture
def learn_client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "DB_PATH", tmp_path / "learning.db")
    app = FastAPI()
    app.include_router(router)
    with store.db() as conn:
        for username, role in [("admin", "teacher"), ("teacher2", "teacher"),
                               ("student", "student"), ("tutor", "tutor"), ("parent", "parent")]:
            conn.execute("INSERT INTO learn_users(username,display_name,role,is_admin,password_hash) VALUES(?,?,?,?,?)",
                         (username, username.title(), role, int(username == "admin"), auth.hash_password("correct horse battery staple")))
    with TestClient(app) as client:
        yield client


def login(client, username):
    result = client.post("/learn/api/auth/login", json={"username": username, "password": "correct horse battery staple"})
    assert result.status_code == 200
    return result.json()["csrf_token"]


def post(client, url, csrf, **data):
    return client.post(url, json=data, headers={"X-CSRF-Token": csrf})


def workspace(client):
    csrf = login(client, "admin")
    student = client.get("/learn/api/users").json()
    ids = {u["username"]: u["id"] for u in student}
    course = post(client, "/learn/api/courses", csrf, title="Algebra", description="Linear equations").json()
    course_id = course["id"]
    assert post(client, f"/learn/api/courses/{course_id}/enrollments", csrf, student_id=ids["student"]).status_code == 200
    assert post(client, f"/learn/api/courses/{course_id}/tutors", csrf, student_id=ids["student"], tutor_id=ids["tutor"]).status_code == 200
    lesson = post(client, f"/learn/api/courses/{course_id}/lessons", csrf, title="Balance", content="Keep equations balanced.", learning_objectives="Solve equations", topic="algebra").json()
    assignment = post(client, f"/learn/api/courses/{course_id}/assignments", csrf, title="Solve x", instructions="Solve x + 2 = 5", lesson_id=lesson["id"], topic="algebra", max_points=10, kind="official").json()
    return csrf, ids, course, lesson, assignment


def test_login_csrf_course_submission_and_published_grade(learn_client):
    c = learn_client
    teacher_csrf, ids, course, lesson, assignment = workspace(c)
    # The student can refresh the CSRF token after a page reload.
    stu_csrf = login(c, "student")
    assert c.get("/learn/api/auth/me").json()["csrf_token"] == stu_csrf
    assert c.get(f"/learn/api/courses/{course['id']}").status_code == 200
    assert post(c, f"/learn/api/assignments/{assignment['id']}/submissions", "bad", content="x=3").status_code == 403
    submission = post(c, f"/learn/api/assignments/{assignment['id']}/submissions", stu_csrf, content="x=3").json()
    # Teacher can grade; student cannot see an unpublished official grade.
    teacher_csrf=login(c,"admin")
    assert post(c, f"/learn/api/submissions/{submission['id']}/grade", teacher_csrf, points=8, feedback="Good", published=False).status_code == 200
    login(c,"student")
    detail = c.get(f"/learn/api/assignments/{assignment['id']}").json()
    assert detail["submissions"][0]["points"] is None
    teacher_csrf = login(c, "admin")
    assert post(c, f"/learn/api/submissions/{submission['id']}/grade", teacher_csrf, points=8, feedback="Good", published=True).status_code == 200
    stu_csrf=login(c,"student")
    detail = c.get(f"/learn/api/assignments/{assignment['id']}").json()
    assert detail["submissions"][0]["points"] == 8
    assert post(c, f"/learn/api/assignments/{assignment['id']}/submissions", stu_csrf, content="overwrite").status_code == 409


def test_role_scopes_admin_parent_tutor_and_course_owner(learn_client):
    c=learn_client
    admin_csrf, ids, course, lesson, assignment=workspace(c)
    assert post(c,"/learn/api/users",admin_csrf,username="extra",display_name="Extra",role="student",password="correct horse battery staple").status_code==200
    extra_id=next(u["id"] for u in c.get("/learn/api/users").json() if u["username"]=="extra")
    assert post(c,f"/learn/api/courses/{course['id']}/enrollments",admin_csrf,student_id=extra_id).status_code==200
    assert post(c,f"/learn/api/courses/{course['id']}/tutors",admin_csrf,student_id=extra_id,tutor_id=ids["tutor"]).status_code==200
    assert post(c,"/learn/api/parent-links",admin_csrf,parent_id=ids["parent"],student_id=extra_id).status_code==200
    teacher_csrf=login(c,"teacher2")
    assert c.get("/learn/api/users").status_code==403
    assert post(c,"/learn/api/courses",teacher_csrf,title="Other",description="").status_code==200
    assert c.get(f"/learn/api/courses/{course['id']}").status_code==403
    # Parent needs an explicit admin-created link.
    admin_csrf=login(c,"admin")
    assert post(c,"/learn/api/parent-links",admin_csrf,parent_id=ids["parent"],student_id=ids["student"]).status_code==200
    parent_csrf=login(c,"parent")
    assert c.get(f"/learn/api/courses/{course['id']}").status_code==200
    assert c.get("/learn/api/dashboard").json()["students"][0]["id"]==ids["student"]
    tutor_csrf=login(c,"tutor")
    assert c.get(f"/learn/api/courses/{course['id']}").status_code==200
    tutor_detail=c.get(f"/learn/api/courses/{course['id']}").json()
    assert {s["id"] for s in tutor_detail["students"]}=={ids["student"],extra_id}
    # Tutors can author only assigned student practice, never official grading.
    denied=post(c,f"/learn/api/courses/{course['id']}/assignments",tutor_csrf,title="Exam",instructions="",max_points=10,kind="official",target_student_id=ids["student"])
    assert denied.status_code==403
    practice=post(c,f"/learn/api/courses/{course['id']}/assignments",tutor_csrf,title="Extra practice",instructions="Try it",max_points=5,kind="practice",target_student_id=ids["student"])
    assert practice.status_code==200
    assert c.get("/learn/api/directory").status_code==403
    assert login(c,"teacher2")
    directory=c.get("/learn/api/directory").json()
    assert {u["role"] for u in directory}=={"student","tutor"}
    assert all(set(u)=={"id","username","display_name","role"} for u in directory)

    # Progress may cross linked courses for parents, but a tutor is bounded to
    # the course in which that tutor is assigned.
    admin_csrf=login(c,"admin")
    other_course=post(c,"/learn/api/courses",admin_csrf,title="Other class",description="").json()
    assert post(c,f"/learn/api/courses/{other_course['id']}/enrollments",admin_csrf,student_id=ids["student"]).status_code==200
    created=post(c,f"/learn/api/courses/{other_course['id']}/assignments",admin_csrf,title="Private classwork",instructions="Do not leak",max_points=5,kind="official")
    assert created.status_code==200,created.text
    login(c,"tutor")
    tutor_report=c.get(f"/learn/api/students/{ids['student']}/progress").json()
    assert all(r["course_id"]==course["id"] for r in tutor_report["records"])
    login(c,"parent")
    parent_report=c.get(f"/learn/api/students/{ids['student']}/progress").json()
    assert any(r["course_id"]==other_course["id"] for r in parent_report["records"]), parent_report["records"]
    parent_detail=c.get(f"/learn/api/courses/{course['id']}").json()
    assert {s["id"] for s in parent_detail["students"]}=={ids["student"],extra_id}


def test_login_rejects_origin_mismatch_and_unknown_fields(learn_client):
    c=learn_client
    assert c.post("/learn/api/auth/login",json={"username":"admin","password":"correct horse battery staple","is_admin":True}).status_code==422
    assert c.post("/learn/api/auth/login",json={"username":"admin","password":"correct horse battery staple"},headers={"Origin":"https://evil.example"}).status_code==403


def test_invalid_grade_dates_and_finite_values(learn_client):
    c=learn_client
    csrf, ids, course, lesson, assignment=workspace(c)
    assert post(c,f"/learn/api/courses/{course['id']}/assignments",csrf,title="Bad date",instructions="Try",max_points=5,kind="official",due_date="tomorrow").status_code==422
    response=c.post(f"/learn/api/courses/{course['id']}/assignments",content='{"title":"Bad points","instructions":"Try","max_points":Infinity,"kind":"official"}',headers={"X-CSRF-Token":csrf,"Content-Type":"application/json"})
    assert response.status_code==422
    stu=login(c,"student")
    sub=post(c,f"/learn/api/assignments/{assignment['id']}/submissions",stu,content="x").json()
    csrf=login(c,"admin")
    assert post(c,f"/learn/api/submissions/{sub['id']}/grade",csrf,points=11,feedback="",published=True).status_code==422


def test_api_only_creates_prefixed_tables(learn_client):
    # The isolated learning API does not initialize or inspect personal Notebook tables.
    with store.db() as conn:
        names={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names and all(name.startswith("learn_") or name.startswith("sqlite_") for name in names)


def test_targeted_material_parent_redaction_and_tutor_grade_limits(learn_client):
    c=learn_client
    admin_csrf, ids, course, lesson, assignment=workspace(c)
    login_response=c.post("/learn/api/auth/login",json={"username":"admin","password":"correct horse battery staple"})
    cookie=login_response.headers["set-cookie"].lower()
    admin_csrf=login_response.json()["csrf_token"]
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/learn" in cookie
    # Bootstrap account escalation fields are rejected, not silently accepted.
    spoof=post(c,"/learn/api/users",admin_csrf,username="spoof",display_name="Spoof",role="teacher",password="correct horse battery staple",is_admin=True)
    assert spoof.status_code==422
    second=post(c,"/learn/api/users",admin_csrf,username="second",display_name="Second Learner",role="student",password="correct horse battery staple").json()
    assert post(c,f"/learn/api/courses/{course['id']}/enrollments",admin_csrf,student_id=second["id"]).status_code==200
    targeted=post(c,f"/learn/api/courses/{course['id']}/lessons",admin_csrf,title="Private lesson",content="Only for the first learner.",learning_objectives="A private objective",topic="private",target_student_id=ids["student"]).json()
    targeted_assignment=post(c,f"/learn/api/courses/{course['id']}/assignments",admin_csrf,title="Private exercise",instructions="First learner only",lesson_id=targeted["id"],topic="private",max_points=4,kind="official",target_student_id=ids["student"]).json()
    # A different enrolled learner can enter the course but cannot see targeted rows.
    second_csrf=login(c,"second")
    detail=c.get(f"/learn/api/courses/{course['id']}").json()
    assert targeted["id"] not in {row["id"] for row in detail["lessons"]}
    assert targeted_assignment["id"] not in {row["id"] for row in detail["assignments"]}
    assert c.get(f"/learn/api/assignments/{targeted_assignment['id']}").status_code==403
    # Only the course tutor can see the target learner's work; tutors cannot grade official work.
    student_csrf=login(c,"student")
    submitted=post(c,f"/learn/api/assignments/{targeted_assignment['id']}/submissions",student_csrf,content="Private response").json()
    tutor_csrf=login(c,"tutor")
    assert post(c,f"/learn/api/submissions/{submitted['id']}/grade",tutor_csrf,points=3,feedback="No",published=True).status_code==403
    teacher_csrf=login(c,"admin")
    assert post(c,f"/learn/api/submissions/{submitted['id']}/grade",teacher_csrf,points=3,feedback="Good",published=True).status_code==200
    assert post(c,"/learn/api/parent-links",teacher_csrf,parent_id=ids["parent"],student_id=ids["student"]).status_code==200
    login(c,"parent")
    parent_detail=c.get(f"/learn/api/assignments/{targeted_assignment['id']}").json()
    assert parent_detail["submissions"][0]["points"]==3
    assert "content" not in parent_detail["submissions"][0]


def test_progress_and_assignment_exclude_unenrolled_course(learn_client):
    c=learn_client
    admin_csrf, ids, course, lesson, assignment=workspace(c)
    unrelated=post(c,"/learn/api/courses",admin_csrf,title="Unrelated",description="").json()
    other_assignment=post(c,f"/learn/api/courses/{unrelated['id']}/assignments",admin_csrf,title="Unenrolled work",instructions="No access",max_points=5,kind="official").json()
    student_csrf=login(c,"student")
    assert c.get(f"/learn/api/assignments/{other_assignment['id']}").status_code==403
    report=c.get(f"/learn/api/students/{ids['student']}/progress").json()
    assert all(record["course_id"]!=unrelated["id"] for record in report["records"])
