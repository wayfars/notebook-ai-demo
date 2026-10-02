"""Role-scoped JSON API for courses and learning records."""
import math
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from . import auth, store

router = APIRouter(prefix="/learn/api", tags=["learning"])
MAX_BODY = 100_000
PREFERENCES = {"balanced", "step_by_step", "worked_examples", "visual", "practice"}


def _body(request: Request, data: dict):
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_BODY: raise HTTPException(413, "request body too large")
        except ValueError: raise HTTPException(400, "invalid content length")
    if not isinstance(data, dict):
        raise HTTPException(422, "expected a JSON object")


def _only(data, allowed):
    if set(data) - set(allowed): raise HTTPException(422, "unexpected field")


def _check_origin(request):
    origin=request.headers.get("origin")
    if origin and origin.rstrip("/") != f"{request.url.scheme}://{request.url.netloc}".rstrip("/"):
        raise HTTPException(403,"cross-origin login denied")


async def _user(request: Request):
    return auth.current_user(request)


def _mut(request, user):
    auth.require_csrf(request, user)


def _need(user, roles=None, admin=False):
    if admin and not user["is_admin"]:
        raise HTTPException(403, "teacher administrator access required")
    if roles and user["role"] not in roles:
        raise HTTPException(403, "role not permitted")


def _text(data, key, limit=20_000, required=True):
    value = data.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise HTTPException(422, f"invalid {key}")
    return value.strip()


def _id(value, key):
    if isinstance(value, bool):
        raise HTTPException(422, f"invalid {key}")
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        raise HTTPException(422, f"invalid {key}")
    try:
        v = int(value)
        if v <= 0 or v > 2**63 - 1: raise ValueError()
        return v
    except (ValueError, TypeError):
        raise HTTPException(422, f"invalid {key}")


def _course(conn, course_id):
    row = conn.execute("SELECT * FROM learn_courses WHERE id=?", (course_id,)).fetchone()
    if not row: raise HTTPException(404, "course not found")
    return row


def _is_tutor(conn, course_id, student_id, tutor_id):
    return conn.execute("SELECT 1 FROM learn_tutor_assignments WHERE course_id=? AND student_id=? AND tutor_id=?",
                        (course_id, student_id, tutor_id)).fetchone() is not None


def _can_course(conn, user, course_id, student_id=None):
    c = _course(conn, course_id)
    if user["role"] == "teacher" and c["teacher_id"] == user["id"]: return c
    if user["role"] == "student" and user["id"] == student_id and conn.execute(
        "SELECT 1 FROM learn_enrollments WHERE course_id=? AND student_id=?", (course_id, user["id"])).fetchone(): return c
    if user["role"] == "tutor" and student_id and _is_tutor(conn, course_id, student_id, user["id"]): return c
    if user["role"] == "parent" and student_id and conn.execute("""SELECT 1 FROM learn_parent_links p JOIN learn_enrollments e
        ON e.student_id=p.student_id WHERE p.parent_id=? AND p.student_id=? AND e.course_id=?""",
        (user["id"], student_id, course_id)).fetchone(): return c
    raise HTTPException(403, "course access denied")


def _owns_or_tutor(conn, user, course_id, target_student_id=None):
    c = _course(conn, course_id)
    if user["role"] == "teacher" and c["teacher_id"] == user["id"]: return c
    if user["role"] == "tutor" and target_student_id and _is_tutor(conn, course_id, target_student_id, user["id"]): return c
    raise HTTPException(403, "course authoring access denied")


def _progress(student, records):
    from app.learning.progress import summarize
    return summarize(student, records)


def _records(conn, student_id, course_id=None):
    sql = """SELECT a.course_id,c.title course_title,a.id assignment_id,a.title,a.topic,a.kind,a.max_points,a.due_date,
      s.id submission_id, (s.id IS NOT NULL) submitted,g.points,g.published,g.feedback
      FROM learn_assignments a JOIN learn_courses c ON c.id=a.course_id JOIN learn_enrollments e ON e.course_id=a.course_id AND e.student_id=?
      LEFT JOIN learn_submissions s ON s.assignment_id=a.id AND s.student_id=?
      LEFT JOIN learn_grades g ON g.submission_id=s.id WHERE (a.target_student_id IS NULL OR a.target_student_id=?)"""
    params = [student_id, student_id, student_id]
    if course_id is not None: sql += " AND a.course_id=?"; params.append(course_id)
    return [dict(r) for r in conn.execute(sql, params)]


def _redact_parent_practice_feedback(records):
    """Parents retain aggregate practice progress, but not practice feedback."""
    for record in records:
        if record.get("kind") == "practice":
            record["feedback"] = ""
    return records


@router.post("/auth/login")
def login(request: Request, response: Response, data: dict):
    _body(request, data); _only(data,{"username","password"}); _check_origin(request)
    username = _text(data, "username", 128)
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 1024: raise HTTPException(422, "invalid credentials")
    with store.db() as conn:
        row = conn.execute("SELECT * FROM learn_users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    if not row or not auth.verify_password(password, row["password_hash"]):
        raise HTTPException(401, "invalid username or password")
    token, csrf, expires = auth.create_session(row["id"])
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="lax", secure=request.url.scheme=="https",
                        max_age=auth.SESSION_HOURS * 3600, path="/learn")
    return {"user": store.user_public(row), "csrf_token": csrf}


@router.post("/auth/logout")
def logout(request: Request, response: Response, user=Depends(_user)):
    _mut(request, user); auth.clear_session(request)
    response.delete_cookie(auth.SESSION_COOKIE, path="/learn")
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(_user)):
    return {"user": store.user_public(user), "csrf_token": user["csrf_token"]}


@router.get("/users")
def users(user=Depends(_user)):
    _need(user, {"teacher"}, admin=True)
    with store.db() as conn:
        return [store.user_public(r) for r in conn.execute("SELECT * FROM learn_users ORDER BY display_name,id")]


@router.get("/directory")
def directory(user=Depends(_user)):
    _need(user,{"teacher"})
    with store.db() as conn:
        return [dict(r) for r in conn.execute("SELECT id,username,display_name,role FROM learn_users WHERE role IN ('student','tutor') ORDER BY role,display_name,id")]


@router.post("/users")
def create_user(request: Request, data: dict, user=Depends(_user)):
    _mut(request, user); _need(user, {"teacher"}, admin=True); _body(request, data); _only(data,{"username","display_name","role","password"})
    username = _text(data, "username", 64)
    if not re.fullmatch(r"[A-Za-z0-9_.@+-]+", username): raise HTTPException(422, "invalid username")
    display = _text(data, "display_name", 120)
    role = data.get("role")
    if not isinstance(role, str) or role not in {"teacher", "student", "tutor", "parent"}: raise HTTPException(422, "invalid role")
    try: pw = auth.hash_password(data.get("password"))
    except ValueError as e: raise HTTPException(422, str(e))
    with store.db() as conn:
        try:
            cur = conn.execute("INSERT INTO learn_users(username,display_name,role,password_hash) VALUES(?,?,?,?)", (username,display,role,pw))
        except Exception as e:
            if "UNIQUE" in str(e): raise HTTPException(409, "username already exists")
            raise
        return store.user_public(conn.execute("SELECT * FROM learn_users WHERE id=?", (cur.lastrowid,)).fetchone())


@router.post("/parent-links")
def parent_link(request: Request, data: dict, user=Depends(_user)):
    _mut(request, user); _need(user, {"teacher"}, admin=True); _body(request,data)
    parent_id, student_id = _id(data.get("parent_id"),"parent_id"), _id(data.get("student_id"),"student_id")
    with store.db() as conn:
        p=conn.execute("SELECT role FROM learn_users WHERE id=?",(parent_id,)).fetchone(); s=conn.execute("SELECT role FROM learn_users WHERE id=?",(student_id,)).fetchone()
        if not p or p["role"]!="parent" or not s or s["role"]!="student": raise HTTPException(422,"parent_id and student_id must identify a parent and student")
        conn.execute("INSERT OR IGNORE INTO learn_parent_links VALUES(?,?)",(parent_id,student_id))
    return {"parent_id":parent_id,"student_id":student_id}


@router.get("/courses")
def courses(user=Depends(_user)):
    with store.db() as conn:
        if user["role"]=="teacher": rows=conn.execute("SELECT * FROM learn_courses WHERE teacher_id=?",(user["id"],))
        elif user["role"]=="student": rows=conn.execute("SELECT c.* FROM learn_courses c JOIN learn_enrollments e ON e.course_id=c.id WHERE e.student_id=?",(user["id"],))
        elif user["role"]=="tutor": rows=conn.execute("SELECT DISTINCT c.* FROM learn_courses c JOIN learn_tutor_assignments t ON t.course_id=c.id WHERE t.tutor_id=?",(user["id"],))
        else: rows=conn.execute("SELECT DISTINCT c.* FROM learn_courses c JOIN learn_enrollments e ON e.course_id=c.id JOIN learn_parent_links p ON p.student_id=e.student_id WHERE p.parent_id=?",(user["id"],))
        return [dict(r) for r in rows]


@router.post("/courses")
def create_course(request: Request, data: dict, user=Depends(_user)):
    _mut(request,user); _need(user,{"teacher"}); _body(request,data)
    title=_text(data,"title",200); description=_text(data,"description",5000,False)
    with store.db() as conn:
        cur=conn.execute("INSERT INTO learn_courses(teacher_id,title,description) VALUES(?,?,?)",(user["id"],title,description))
        return dict(conn.execute("SELECT * FROM learn_courses WHERE id=?",(cur.lastrowid,)).fetchone())


@router.get("/courses/{course_id}")
def course_detail(course_id: int, user=Depends(_user)):
    with store.db() as conn:
        c=_course(conn,course_id)
        owner=user["role"]=="teacher" and c["teacher_id"]==user["id"]
        if owner:
            student_ids=[r[0] for r in conn.execute("SELECT student_id FROM learn_enrollments WHERE course_id=?",(course_id,))]
        elif user["role"]=="student":
            _can_course(conn,user,course_id,user["id"]); student_ids=[user["id"]]
        elif user["role"]=="parent":
            student_ids=[r[0] for r in conn.execute("SELECT p.student_id FROM learn_parent_links p JOIN learn_enrollments e ON e.student_id=p.student_id WHERE p.parent_id=? AND e.course_id=?",(user["id"],course_id))]
            if not student_ids: raise HTTPException(403,"course access denied")
        elif user["role"]=="tutor":
            student_ids=[r[0] for r in conn.execute("SELECT student_id FROM learn_tutor_assignments WHERE tutor_id=? AND course_id=?",(user["id"],course_id))]
            if not student_ids: raise HTTPException(403,"course access denied")
        else: raise HTTPException(403,"course access denied")
        if owner:
            students=[dict(r) for r in conn.execute("SELECT u.id,u.username,u.display_name,u.learning_preference FROM learn_users u JOIN learn_enrollments e ON e.student_id=u.id WHERE e.course_id=?",(course_id,))]
            tutors=[dict(r) for r in conn.execute("SELECT DISTINCT u.id,u.username,u.display_name FROM learn_users u JOIN learn_tutor_assignments t ON t.tutor_id=u.id WHERE t.course_id=?",(course_id,))]
        else:
            marks=','.join('?' for _ in student_ids)
            students=[dict(r) for r in conn.execute(f"SELECT id,username,display_name,learning_preference FROM learn_users WHERE id IN ({marks}) ORDER BY display_name,id",student_ids)] if user["role"] in {"parent","tutor"} else []
            tutors=[dict(r) for r in conn.execute(f"SELECT DISTINCT u.id,u.username,u.display_name FROM learn_users u JOIN learn_tutor_assignments t ON t.tutor_id=u.id WHERE t.course_id=? AND t.student_id IN ({marks})",[course_id,*student_ids])]
        marks=','.join('?' for _ in student_ids)
        lesson_rows=conn.execute(f"SELECT * FROM learn_lessons WHERE course_id=? AND (target_student_id IS NULL OR target_student_id IN ({marks}))",[course_id,*student_ids])
        lessons=[dict(r) for r in lesson_rows]
        assignments=[]
        for row in conn.execute(f"SELECT * FROM learn_assignments WHERE course_id=? AND (target_student_id IS NULL OR target_student_id IN ({marks}))",[course_id,*student_ids]):
            a=dict(row)
            if user["role"]=="parent" and a["kind"]!="official": continue
            if user["role"]=="tutor" and a["kind"]=="official":
                visible=conn.execute(f"SELECT 1 FROM learn_submissions s JOIN learn_grades g ON g.submission_id=s.id WHERE s.assignment_id=? AND s.student_id IN ({marks}) AND g.published=1 LIMIT 1",[a["id"],*student_ids]).fetchone()
                if not visible: continue
            if not owner: a.pop("author_id",None)
            assignments.append(a)
        return {"course":dict(c),"lessons":lessons,"assignments":assignments,"students":students,"tutors":tutors}


@router.post("/courses/{course_id}/enrollments")
def enroll(course_id:int,request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _body(request,data); student=_id(data.get("student_id"),"student_id")
    with store.db() as conn:
        c=_course(conn,course_id)
        if user["role"]!="teacher" or c["teacher_id"]!=user["id"]: raise HTTPException(403,"course owner required")
        row=conn.execute("SELECT role FROM learn_users WHERE id=?",(student,)).fetchone()
        if not row or row["role"]!="student": raise HTTPException(422,"student_id must identify a student")
        conn.execute("INSERT OR IGNORE INTO learn_enrollments VALUES(?,?)",(course_id,student))
    return {"course_id":course_id,"student_id":student}


@router.post("/courses/{course_id}/tutors")
def assign_tutor(course_id:int,request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _body(request,data); student=_id(data.get("student_id"),"student_id"); tutor=_id(data.get("tutor_id"),"tutor_id")
    with store.db() as conn:
        c=_course(conn,course_id)
        if user["role"]!="teacher" or c["teacher_id"]!=user["id"]: raise HTTPException(403,"course owner required")
        if not conn.execute("SELECT 1 FROM learn_enrollments WHERE course_id=? AND student_id=?",(course_id,student)).fetchone(): raise HTTPException(422,"student is not enrolled")
        tr=conn.execute("SELECT role FROM learn_users WHERE id=?",(tutor,)).fetchone()
        if not tr or tr["role"]!="tutor": raise HTTPException(422,"tutor_id must identify a tutor")
        conn.execute("INSERT OR IGNORE INTO learn_tutor_assignments VALUES(?,?,?)",(course_id,student,tutor))
    return {"course_id":course_id,"student_id":student,"tutor_id":tutor}


@router.post("/courses/{course_id}/lessons")
def create_lesson(course_id:int,request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _body(request,data); target=data.get("target_student_id"); target=_id(target,"target_student_id") if target is not None else None
    with store.db() as conn:
        _owns_or_tutor(conn,user,course_id,target)
        if target and not conn.execute("SELECT 1 FROM learn_enrollments WHERE course_id=? AND student_id=?",(course_id,target)).fetchone(): raise HTTPException(422,"target student is not enrolled")
        content=_text(data,"content",30000); title=_text(data,"title",200); objectives=_text(data,"learning_objectives",5000,False); topic=_text(data,"topic",200,False)
        cur=conn.execute("INSERT INTO learn_lessons(course_id,author_id,title,content,learning_objectives,topic,target_student_id) VALUES(?,?,?,?,?,?,?)",(course_id,user["id"],title,content,objectives,topic,target))
        return dict(conn.execute("SELECT * FROM learn_lessons WHERE id=?",(cur.lastrowid,)).fetchone())


@router.post("/courses/{course_id}/assignments")
def create_assignment(course_id:int,request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _body(request,data); target=data.get("target_student_id"); target=_id(target,"target_student_id") if target is not None else None
    kind=data.get("kind","official"); points=data.get("max_points")
    if not isinstance(kind,str) or kind not in {"official","practice"}: raise HTTPException(422,"invalid kind")
    if isinstance(points,bool) or not isinstance(points,(float,int)) or not math.isfinite(points) or points<=0 or points>1_000_000: raise HTTPException(422,"max_points must be finite and positive")
    if user["role"]=="tutor" and (kind!="practice" or target is None): raise HTTPException(403,"tutors may create only targeted practice")
    with store.db() as conn:
        _owns_or_tutor(conn,user,course_id,target)
        if target and not conn.execute("SELECT 1 FROM learn_enrollments WHERE course_id=? AND student_id=?",(course_id,target)).fetchone(): raise HTTPException(422,"target student is not enrolled")
        lesson=data.get("lesson_id"); lesson=_id(lesson,"lesson_id") if lesson is not None else None
        if lesson and not conn.execute("SELECT 1 FROM learn_lessons WHERE id=? AND course_id=? AND (target_student_id IS NULL OR target_student_id=?)",(lesson,course_id,target)).fetchone(): raise HTTPException(422,"lesson must belong to course and target")
        due=data.get("due_date")
        if due is not None:
            try:
                if not isinstance(due,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",due): raise ValueError()
                date.fromisoformat(due)
            except (ValueError,TypeError): raise HTTPException(422,"due_date must be YYYY-MM-DD")
        title=_text(data,"title",200); instructions=_text(data,"instructions",20000); topic=_text(data,"topic",200,False)
        cur=conn.execute("INSERT INTO learn_assignments(course_id,author_id,title,instructions,lesson_id,topic,max_points,due_date,target_student_id,kind) VALUES(?,?,?,?,?,?,?,?,?,?)",(course_id,user["id"],title,instructions,lesson,topic,float(points),due,target,kind))
        return dict(conn.execute("SELECT * FROM learn_assignments WHERE id=?",(cur.lastrowid,)).fetchone())


@router.get("/assignments/{assignment_id}")
def assignment_detail(assignment_id:int,user=Depends(_user)):
    with store.db() as conn:
        a=conn.execute("SELECT a.*,c.title course_title FROM learn_assignments a JOIN learn_courses c ON c.id=a.course_id WHERE a.id=?",(assignment_id,)).fetchone()
        if not a: raise HTTPException(404,"assignment not found")
        if user["role"]=="parent" and a["kind"]!="official": raise HTTPException(404,"assignment not found")
        if user["role"]=="teacher":
            if a["author_id"]!=user["id"] and _course(conn,a["course_id"])["teacher_id"]!=user["id"]: raise HTTPException(403,"assignment access denied")
            sids=[r[0] for r in conn.execute("SELECT student_id FROM learn_enrollments WHERE course_id=?",(a["course_id"],))]
        elif user["role"]=="student":
            _can_course(conn,user,a["course_id"],user["id"]); sids=[user["id"]]
        elif user["role"]=="tutor":
            sids=[r[0] for r in conn.execute("SELECT student_id FROM learn_tutor_assignments WHERE course_id=? AND tutor_id=?",(a["course_id"],user["id"]))]
            if not sids: raise HTTPException(403,"assignment access denied")
            if a["kind"]=="official":
                if a["target_student_id"] is not None:
                    relevant_sids=[sid for sid in sids if sid==a["target_student_id"]]
                else:
                    relevant_sids=sids
                if not relevant_sids:
                    raise HTTPException(404,"assignment not found")
                relevant_clause=','.join('?' for _ in relevant_sids)
                visible=conn.execute(f"SELECT 1 FROM learn_submissions s JOIN learn_grades g ON g.submission_id=s.id WHERE s.assignment_id=? AND s.student_id IN ({relevant_clause}) AND g.published=1 LIMIT 1",[assignment_id,*relevant_sids]).fetchone()
                if not visible:
                    raise HTTPException(404,"assignment not found")
                # Official submission timestamps are hidden until that learner's grade is published.
                sids=relevant_sids
        else:
            sids=[r[0] for r in conn.execute("SELECT p.student_id FROM learn_parent_links p JOIN learn_enrollments e ON e.student_id=p.student_id WHERE p.parent_id=? AND e.course_id=?",(user["id"],a["course_id"]))]
            if not sids: raise HTTPException(403,"assignment access denied")
        if a["target_student_id"] and a["target_student_id"] not in sids: raise HTTPException(403,"assignment access denied")
        sid_clause=','.join('?' for _ in sids) or 'NULL'
        subs=[]
        for s in conn.execute(f"SELECT s.*,u.display_name,u.username,g.points,g.feedback,g.published FROM learn_submissions s JOIN learn_users u ON u.id=s.student_id LEFT JOIN learn_grades g ON g.submission_id=s.id WHERE s.assignment_id=? AND s.student_id IN ({sid_clause})",[assignment_id,*sids]):
            if user["role"]=="tutor" and a["kind"]=="official" and not s["published"]:
                continue
            d=dict(s); visible=user["role"]=="teacher" or bool(d["published"]) or (user["role"]=="tutor" and a["kind"]=="practice")
            if not visible: d["points"]=None; d["feedback"]=""; d["published"]=False
            tutor_targeted_practice=(user["role"]=="tutor" and a["kind"]=="practice" and a["target_student_id"]==d["student_id"])
            if user["role"] in {"student","parent","tutor"} and not (user["role"]=="student" and d["student_id"]==user["id"]) and not tutor_targeted_practice: d.pop("content",None)
            subs.append(d)
        lesson=conn.execute("SELECT * FROM learn_lessons WHERE id=?",(a["lesson_id"],)).fetchone() if a["lesson_id"] else None
        return {"assignment":dict(a),"lesson":dict(lesson) if lesson else None,"submissions":subs}


@router.post("/assignments/{assignment_id}/submissions")
def submit(assignment_id:int,request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _need(user,{"student"}); _body(request,data); content=_text(data,"content",30000)
    with store.db() as conn:
        a=conn.execute("SELECT * FROM learn_assignments WHERE id=?",(assignment_id,)).fetchone()
        if not a: raise HTTPException(404,"assignment not found")
        _can_course(conn,user,a["course_id"],user["id"])
        if a["target_student_id"] not in (None,user["id"]): raise HTTPException(403,"assignment is targeted to another student")
        exists=conn.execute("SELECT id FROM learn_submissions WHERE assignment_id=? AND student_id=?",(assignment_id,user["id"])).fetchone()
        if exists:
            if conn.execute("SELECT 1 FROM learn_grades WHERE submission_id=?",(exists[0],)).fetchone(): raise HTTPException(409,"graded work cannot be changed")
            conn.execute("UPDATE learn_submissions SET content=?,submitted_at=datetime('now') WHERE id=?",(content,exists[0])); sid=exists[0]
        else:
            sid=conn.execute("INSERT INTO learn_submissions(assignment_id,student_id,content) VALUES(?,?,?)",(assignment_id,user["id"],content)).lastrowid
        return dict(conn.execute("SELECT * FROM learn_submissions WHERE id=?",(sid,)).fetchone())


@router.post("/submissions/{submission_id}/grade")
def grade(submission_id:int,request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _need(user,{"teacher","tutor"}); _body(request,data)
    points=data.get("points"); feedback=_text(data,"feedback",5000,False); published=data.get("published",False)
    if not isinstance(published,bool): raise HTTPException(422,"published must be boolean")
    if isinstance(points,bool) or not isinstance(points,(int,float)) or not math.isfinite(points): raise HTTPException(422,"points must be finite")
    with store.db() as conn:
        row=conn.execute("SELECT s.*,a.course_id,a.kind,a.max_points,a.target_student_id,c.teacher_id FROM learn_submissions s JOIN learn_assignments a ON a.id=s.assignment_id JOIN learn_courses c ON c.id=a.course_id WHERE s.id=?",(submission_id,)).fetchone()
        if not row: raise HTTPException(404,"submission not found")
        if points<0 or points>row["max_points"]: raise HTTPException(422,"points outside assignment range")
        if user["role"]=="teacher":
            if row["teacher_id"]!=user["id"]: raise HTTPException(403,"course owner required")
        elif row["kind"]!="practice" or row["target_student_id"]!=row["student_id"] or not _is_tutor(conn,row["course_id"],row["student_id"],user["id"]): raise HTTPException(403,"assigned tutor may grade only targeted practice")
        if user["role"]=="tutor":
            existing=conn.execute("SELECT grader_id FROM learn_grades WHERE submission_id=?",(submission_id,)).fetchone()
            if existing and existing["grader_id"]==row["teacher_id"]:
                raise HTTPException(409,"course teacher grade cannot be overwritten by a tutor")
        conn.execute("INSERT INTO learn_grades(submission_id,grader_id,points,feedback,published) VALUES(?,?,?,?,?) ON CONFLICT(submission_id) DO UPDATE SET grader_id=excluded.grader_id,points=excluded.points,feedback=excluded.feedback,published=excluded.published,graded_at=datetime('now')",(submission_id,user["id"],float(points),feedback,int(published)))
        return dict(conn.execute("SELECT * FROM learn_grades WHERE submission_id=?",(submission_id,)).fetchone())


@router.get("/students/{student_id}/progress")
def student_progress(student_id:int,user=Depends(_user)):
    with store.db() as conn:
        student=conn.execute("SELECT id,username,display_name,learning_preference,role FROM learn_users WHERE id=?",(student_id,)).fetchone()
        if not student or student["role"]!="student": raise HTTPException(404,"student not found")
        courses=[r[0] for r in conn.execute("SELECT course_id FROM learn_enrollments WHERE student_id=?",(student_id,))]
        if user["id"]!=student_id:
            if user["role"]=="parent": allowed=conn.execute("SELECT 1 FROM learn_parent_links WHERE parent_id=? AND student_id=?",(user["id"],student_id)).fetchone()
            elif user["role"]=="tutor": allowed=conn.execute("SELECT 1 FROM learn_tutor_assignments WHERE tutor_id=? AND student_id=?",(user["id"],student_id)).fetchone()
            elif user["role"]=="teacher": allowed=conn.execute("SELECT 1 FROM learn_courses c JOIN learn_enrollments e ON e.course_id=c.id WHERE c.teacher_id=? AND e.student_id=? LIMIT 1",(user["id"],student_id)).fetchone()
            else: allowed=None
            if not allowed: raise HTTPException(403,"student progress access denied")
        records=_records(conn,student_id)
        if user["role"]=="teacher":
            visible={r[0] for r in conn.execute("SELECT id FROM learn_courses WHERE teacher_id=?",(user["id"],))}
            records=[r for r in records if r["course_id"] in visible]
        elif user["role"]=="tutor":
            visible={r[0] for r in conn.execute("SELECT course_id FROM learn_tutor_assignments WHERE tutor_id=? AND student_id=?",(user["id"],student_id))}
            records=[r for r in records if r["course_id"] in visible]
        elif user["role"]=="parent":
            _redact_parent_practice_feedback(records)
        return _progress(dict(student),records)


@router.post("/profile")
def profile(request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _need(user,{"student"}); _body(request,data)
    pref=data.get("learning_preference")
    if not isinstance(pref,str) or pref not in PREFERENCES: raise HTTPException(422,"invalid learning_preference")
    with store.db() as conn: conn.execute("UPDATE learn_users SET learning_preference=? WHERE id=?",(pref,user["id"]))
    user["learning_preference"]=pref
    return store.user_public(user)


@router.post("/tutor-chat")
def tutor_chat(request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _need(user,{"student"}); _body(request,data)
    course_id=_id(data.get("course_id"),"course_id"); lesson_id=data.get("lesson_id"); assignment_id=data.get("assignment_id")
    lesson_id=_id(lesson_id,"lesson_id") if lesson_id is not None else None; assignment_id=_id(assignment_id,"assignment_id") if assignment_id is not None else None
    if not lesson_id and not assignment_id: raise HTTPException(422,"lesson_id or assignment_id is required")
    question=_text(data,"question",8000)
    with store.db() as conn:
        c=_can_course(conn,user,course_id,user["id"])
        lesson=conn.execute("SELECT * FROM learn_lessons WHERE id=? AND course_id=? AND (target_student_id IS NULL OR target_student_id=?)",(lesson_id,course_id,user["id"])).fetchone() if lesson_id else None
        a=conn.execute("SELECT * FROM learn_assignments WHERE id=? AND course_id=? AND (target_student_id IS NULL OR target_student_id=?)",(assignment_id,course_id,user["id"])).fetchone() if assignment_id else None
        if lesson_id and not lesson: raise HTTPException(404,"lesson not found")
        if assignment_id and not a: raise HTTPException(404,"assignment not found")
        ctx={"course":dict(c),"lessons":[dict(lesson)] if lesson else [],"assignment":dict(a) if a else None,
             "student":{"id":user["id"],"learning_preference":user["learning_preference"]}}
        chat=conn.execute("SELECT id FROM learn_chats WHERE student_id=? AND course_id=? AND lesson_id IS ? AND assignment_id IS ? ORDER BY id DESC LIMIT 1",(user["id"],course_id,lesson_id,assignment_id)).fetchone()
        chat_id=chat[0] if chat else conn.execute("INSERT INTO learn_chats(student_id,course_id,lesson_id,assignment_id) VALUES(?,?,?,?)",(user["id"],course_id,lesson_id,assignment_id)).lastrowid
        hist=[dict(r) for r in conn.execute("SELECT role,content FROM learn_chat_messages WHERE chat_id=? ORDER BY id DESC LIMIT 12",(chat_id,))][::-1]
        conn.execute("INSERT INTO learn_chat_messages(chat_id,role,content) VALUES(?,?,?)",(chat_id,"user",question))
    try:
        from app.learning.ai import answer_question
        result=answer_question(ctx,question,hist)
    except HTTPException: raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(503,"tutoring is temporarily unavailable") from e
    answer=result.get("answer","") if isinstance(result,dict) else str(result)
    if len(answer)>12000: answer=answer[:12000]
    with store.db() as conn: conn.execute("INSERT INTO learn_chat_messages(chat_id,role,content) VALUES(?,?,?)",(chat_id,"assistant",answer))
    return {"answer":answer,"citations":result.get("citations",[]) if isinstance(result,dict) else [], **({"warning":result["warning"]} if isinstance(result,dict) and result.get("warning") else {})}


@router.post("/practice-drafts")
def practice_draft(request:Request,data:dict,user=Depends(_user)):
    _mut(request,user); _need(user,{"teacher","tutor"}); _body(request,data)
    cid=_id(data.get("course_id"),"course_id"); sid=_id(data.get("student_id"),"student_id"); topic=_text(data,"topic",200); request_text=_text(data,"request",4000,False)
    with store.db() as conn:
        _owns_or_tutor(conn,user,cid,sid)
        if not conn.execute("SELECT 1 FROM learn_enrollments WHERE course_id=? AND student_id=?",(cid,sid)).fetchone(): raise HTTPException(422,"student is not enrolled")
        st=conn.execute("SELECT id,learning_preference FROM learn_users WHERE id=? AND role='student'",(sid,)).fetchone()
        c=_course(conn,cid)
        lessons=[dict(r) for r in conn.execute("SELECT id,title,content,learning_objectives,topic FROM learn_lessons WHERE course_id=? AND (target_student_id IS NULL OR target_student_id=?)",(cid,sid))]
        records=_records(conn,sid,cid)
        ctx={"course":dict(c),"lessons":lessons,"assignment":None,"student":dict(st),"progress":_progress(dict(st),records),"topic":topic}
    try:
        from app.learning.ai import draft_practice
        return draft_practice(ctx,request_text)
    except HTTPException: raise
    except ValueError as e: raise HTTPException(400,str(e)) from e
    except Exception as e: raise HTTPException(503,"practice drafting is temporarily unavailable") from e


@router.get("/dashboard")
def dashboard(user=Depends(_user)):
    with store.db() as conn:
        if user["role"]=="teacher":
            crs=[dict(r) for r in conn.execute("SELECT id,title,description,teacher_id FROM learn_courses WHERE teacher_id=?",(user["id"],))]
            students=[dict(r) for r in conn.execute("SELECT DISTINCT u.id,u.username,u.display_name,u.learning_preference FROM learn_users u JOIN learn_enrollments e ON e.student_id=u.id JOIN learn_courses c ON c.id=e.course_id WHERE c.teacher_id=?",(user["id"],))]
            assignrows=conn.execute("SELECT a.*,c.title course_title FROM learn_assignments a JOIN learn_courses c ON c.id=a.course_id WHERE c.teacher_id=?",(user["id"],))
        elif user["role"]=="student":
            crs=[dict(r) for r in conn.execute("SELECT c.id,c.title,c.description,c.teacher_id FROM learn_courses c JOIN learn_enrollments e ON e.course_id=c.id WHERE e.student_id=?",(user["id"],))]; students=[]
            assignrows=conn.execute("SELECT a.*,c.title course_title FROM learn_assignments a JOIN learn_courses c ON c.id=a.course_id JOIN learn_enrollments e ON e.course_id=c.id WHERE e.student_id=? AND (a.target_student_id IS NULL OR a.target_student_id=?)",(user["id"],user["id"]))
        elif user["role"]=="tutor":
            students=[dict(r) for r in conn.execute("SELECT DISTINCT u.id,u.username,u.display_name,u.learning_preference FROM learn_users u JOIN learn_tutor_assignments t ON t.student_id=u.id WHERE t.tutor_id=?",(user["id"],))]
            crs=[dict(r) for r in conn.execute("SELECT DISTINCT c.id,c.title,c.description,c.teacher_id FROM learn_courses c JOIN learn_tutor_assignments t ON t.course_id=c.id WHERE t.tutor_id=?",(user["id"],))]
            assignrows=conn.execute("SELECT DISTINCT a.*,c.title course_title FROM learn_assignments a JOIN learn_courses c ON c.id=a.course_id JOIN learn_tutor_assignments t ON t.course_id=a.course_id AND (a.target_student_id=t.student_id OR a.target_student_id IS NULL) WHERE t.tutor_id=? AND (a.kind='practice' OR EXISTS(SELECT 1 FROM learn_submissions s JOIN learn_grades g ON g.submission_id=s.id WHERE s.assignment_id=a.id AND s.student_id=t.student_id AND g.published=1))",(user["id"],))
        else:
            students=[dict(r) for r in conn.execute("SELECT u.id,u.username,u.display_name,u.learning_preference FROM learn_users u JOIN learn_parent_links p ON p.student_id=u.id WHERE p.parent_id=?",(user["id"],))]
            crs=[dict(r) for r in conn.execute("SELECT DISTINCT c.id,c.title,c.description,c.teacher_id FROM learn_courses c JOIN learn_enrollments e ON e.course_id=c.id JOIN learn_parent_links p ON p.student_id=e.student_id WHERE p.parent_id=?",(user["id"],))]
            assignrows=conn.execute("SELECT DISTINCT a.*,c.title course_title FROM learn_assignments a JOIN learn_courses c ON c.id=a.course_id JOIN learn_enrollments e ON e.course_id=c.id JOIN learn_parent_links p ON p.student_id=e.student_id WHERE p.parent_id=? AND (a.target_student_id IS NULL OR a.target_student_id=e.student_id) AND (a.kind='official' AND EXISTS(SELECT 1 FROM learn_submissions s JOIN learn_grades g ON g.submission_id=s.id WHERE s.assignment_id=a.id AND s.student_id=e.student_id AND g.published=1))",(user["id"],))
        assignments=[]
        for row in assignrows:
            a=dict(row)
            if user["role"]=="student":
                sub=conn.execute("SELECT s.id,g.points,g.published,g.feedback FROM learn_submissions s LEFT JOIN learn_grades g ON g.submission_id=s.id WHERE s.assignment_id=? AND s.student_id=?",(a["id"],user["id"])).fetchone()
                a["submitted"]=bool(sub); a["points"]=sub["points"] if sub and sub["published"] else None
                if sub and sub["published"]: a["feedback"]=sub["feedback"]
            elif user["role"] in {"parent","tutor"}:
                a["points"]=None
            assignments.append(a)
        progress=[]
        for st in students:
            rec=_records(conn,st["id"])
            if user["role"]=="teacher":
                visible={r[0] for r in conn.execute("SELECT id FROM learn_courses WHERE teacher_id=?",(user["id"],))}
                rec=[r for r in rec if r["course_id"] in visible]
            elif user["role"]=="tutor":
                visible={r[0] for r in conn.execute("SELECT course_id FROM learn_tutor_assignments WHERE tutor_id=? AND student_id=?",(user["id"],st["id"]))}
                rec=[r for r in rec if r["course_id"] in visible]
            elif user["role"]=="parent":
                _redact_parent_practice_feedback(rec)
            progress.append(_progress(st,rec))
        return {"user":store.user_public(user),"courses":crs,"students":students,"assignments":assignments,"progress":progress}
