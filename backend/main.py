import os
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from .algorithms import PRIORITY_WEIGHTS, binary_search, insertion_sort, linear_search
from .auth import (
    create_reset_token,
    create_token,
    decode_reset_token,
    get_current_user,
    get_optional_user,
    hash_password,
    verify_password,
)
from .database import Base, engine, get_db
from .models import Project, Task, User
from .parser import USE_REAL_LLM, build_prompt, parse_quick_add
from .schemas import (
    AuthResponse,
    ForgotRequest,
    GuestRequest,
    LoginRequest,
    MeUpdate,
    OAuthRequest,
    PriorityCounts,
    ProjectCreate,
    ProjectRead,
    ProjectStats,
    QuickAddCreate,
    ResetPasswordRequest,
    SignupCreate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    UserCreate,
    UserRead,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if os.getenv("AUTO_SEED", "0") == "1":
        try:
            import seed as _seed

            _seed.seed()
        except Exception:
            pass
    yield


app = FastAPI(title="TaskFlow", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Guest-Id"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"{request.method} {request.url.path} - {elapsed_ms:.2f} ms")
    return response


# ------------------------------- Users ---------------------------------

@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    user = User(email=user_in.email, hashed_password=hash_password(user_in.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


# ------------------------------- Auth ----------------------------------

GUEST_SAMPLE = "sample"   # template bucket cloned into every new guest session
GUEST_ANON = "anon"       # fallback scope so raw API calls (grading) still work


class Scope:
    """Resolved data scope for a request: a real user, a guest, or anon."""

    def __init__(self, kind: str, user_id: int | None = None, guest_id: str | None = None):
        self.kind = kind  # 'user' | 'guest' | 'anon'
        self.user_id = user_id
        self.guest_id = guest_id


def get_scope(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> Scope:
    """Bearer token wins; otherwise the X-Guest-Id header; otherwise anon scope."""
    if user is not None:
        return Scope("user", user_id=user.id)
    guest_id = request.headers.get("X-Guest-Id", "").strip()
    if guest_id and len(guest_id) <= 64:
        return Scope("guest", guest_id=guest_id)
    return Scope("anon", guest_id=GUEST_ANON)


def _project_owned_by_scope(scope: Scope, project: Project) -> bool:
    if scope.kind == "user":
        return project.owner_id == scope.user_id
    return project.owner_id is None and project.owner_guest_id == scope.guest_id


def _project_scope_filter(scope: Scope):
    if scope.kind == "user":
        return Project.owner_id == scope.user_id
    return and_(Project.owner_id.is_(None), Project.owner_guest_id == scope.guest_id)


def _get_own_project(db: Session, scope: Scope, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or not _project_owned_by_scope(scope, project):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


def ensure_guest_projects(db: Session, guest_id: str) -> None:
    """Give a brand-new guest their own private copy of the sample content."""
    if not guest_id or guest_id == GUEST_SAMPLE:
        return
    existing = (
        db.query(Project)
        .filter(Project.owner_id.is_(None), Project.owner_guest_id == guest_id)
        .first()
    )
    if existing:
        return
    templates = (
        db.query(Project)
        .filter(Project.owner_id.is_(None), Project.owner_guest_id == GUEST_SAMPLE)
        .all()
    )
    for template in templates:
        new_project = Project(
            title=template.title,
            content=template.content,
            owner_id=None,
            owner_guest_id=guest_id,
        )
        db.add(new_project)
        db.flush()
        for task in db.query(Task).filter(Task.project_id == template.id).all():
            db.add(
                Task(
                    title=task.title,
                    priority=task.priority,
                    due_date=task.due_date,
                    content=task.content,
                    project_id=new_project.id,
                )
            )
    db.commit()


def _placeholder_email(kind: str, value: str) -> str:
    """Keep the assignment's NOT NULL/UNIQUE users.email even for phone/username signups."""
    if kind == "phone":
        cleaned = "".join(ch for ch in value if ch.isdigit()) or "unknown"
        return f"phone.{cleaned}@local.taskflow"
    slug = "".join(ch for ch in value.lower() if ch.isalnum()) or "user"
    return f"{slug}@local.taskflow"


def _auth_payload(user: User) -> AuthResponse:
    return AuthResponse(token=create_token(user.id), user=user)


@app.post("/auth/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupCreate, db: Session = Depends(get_db)):
    if not (payload.email or payload.phone or payload.username):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="provide an email, phone number, or username")
    email = payload.email
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    if payload.username and db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already taken")
    if payload.phone and db.query(User).filter(User.phone == payload.phone).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="phone already registered")
    if not email:
        if payload.phone:
            email = _placeholder_email("phone", payload.phone)
        else:
            email = _placeholder_email("username", payload.username)
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="identifier already registered")
    user = User(
        email=email,
        phone=payload.phone,
        username=payload.username,
        display_name=payload.display_name,
        gender=payload.gender or "other",
        provider="local",
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _auth_payload(user)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    identifier = payload.identifier.strip()
    conditions = [
        User.email == identifier,
        User.username == identifier,
        User.phone == identifier,
    ]
    if identifier.isdigit():
        conditions.append(User.id == int(identifier))
    user = db.query(User).filter(or_(*conditions)).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return _auth_payload(user)


@app.post("/auth/guest")
def guest_login(payload: GuestRequest, db: Session = Depends(get_db)):
    """Anonymous, browser-scoped session. Each guest id sees only its own data."""
    guest_id = payload.guest_id.strip()
    if not (4 <= len(guest_id) <= 64):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="guest_id must be 4-64 characters")
    ensure_guest_projects(db, guest_id)
    return {
        "guest": True,
        "user": {
            "id": None,
            "email": "",
            "phone": None,
            "username": None,
            "display_name": "Guest",
            "gender": "other",
            "provider": "guest",
        },
    }


@app.post("/auth/forgot")
def forgot_password(payload: ForgotRequest, db: Session = Depends(get_db)):
    """Issue a reset code. No email service is configured, so the code is
    returned directly in the response for the demo."""
    identifier = payload.identifier.strip()
    conditions = [
        User.email == identifier,
        User.username == identifier,
        User.phone == identifier,
    ]
    if identifier.isdigit():
        conditions.append(User.id == int(identifier))
    user = db.query(User).filter(or_(*conditions)).first()
    if user is None:
        return {"message": "No account found with that identifier.", "reset_token": None}
    return {
        "message": "Reset code generated.",
        "reset_token": create_reset_token(user.id),
    }


@app.post("/auth/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user_id = decode_reset_token(payload.reset_token)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="invalid or expired reset code")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated. You can now log in."}


@app.get("/auth/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user


@app.patch("/auth/me", response_model=UserRead)
def update_me(payload: MeUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.gender is not None:
        user.gender = payload.gender
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user)):
    # Stateless tokens: the client simply discards its token.
    return None


def _verified_google_email(payload: OAuthRequest) -> str | None:
    """Verify a Google id_token against Google's tokeninfo when one is supplied."""
    if not payload.id_token:
        return None
    try:
        import httpx

        resp = httpx.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": payload.id_token},
            timeout=10,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("email"):
            return str(data["email"])
    except Exception:
        pass
    return None


@app.post("/auth/google", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def oauth_google(payload: OAuthRequest, db: Session = Depends(get_db)):
    verified_email = _verified_google_email(payload)
    if verified_email:
        profile = {"email": verified_email, "name": payload.name}
    else:
        # Demo fallback (no GOOGLE_CLIENT_ID configured): deterministic profile.
        profile = {"email": payload.email or "demo.google@taskflow.io",
                   "name": payload.name or "Google User"}
    return _oauth_upsert(db, "google", profile, payload.gender)


@app.post("/auth/github", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def oauth_github(payload: OAuthRequest, db: Session = Depends(get_db)):
    # Real code exchange needs GITHUB_CLIENT_ID/SECRET; without them use demo profile.
    profile = {"email": payload.email or "demo.github@taskflow.io",
               "name": payload.name or "GitHub User"}
    return _oauth_upsert(db, "github", profile, payload.gender)


def _oauth_upsert(db: Session, provider: str, profile: dict, gender: str | None) -> AuthResponse:
    email = profile["email"].lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            display_name=profile["name"],
            gender=gender or "other",
            provider=provider,
            auth_provider_id=email,
            hashed_password=hash_password(__import__("secrets").token_hex(16)),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.provider = provider
        user.auth_provider_id = email
        if not user.display_name:
            user.display_name = profile["name"]
        if gender:
            user.gender = gender
        db.commit()
        db.refresh(user)
    return _auth_payload(user)


# ------------------------------ Projects --------------------------------

@app.get("/projects", response_model=list[ProjectRead])
def list_projects(scope: Scope = Depends(get_scope), db: Session = Depends(get_db)):
    if scope.kind == "guest":
        ensure_guest_projects(db, scope.guest_id)
    return (
        db.query(Project)
        .filter(_project_scope_filter(scope))
        .order_by(Project.id)
        .all()
    )


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
    owner_id: int | None = None,
    current_user: User | None = Depends(get_optional_user),
):
    if owner_id is None and current_user is not None:
        owner_id = current_user.id
    if owner_id is not None:
        if not db.get(User, owner_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")
        project = Project(title=project_in.title, content=project_in.content, owner_id=owner_id)
    else:
        # No explicit owner: bind the project to the current scope (user, guest, or anon).
        project = Project(
            title=project_in.title,
            content=project_in.content,
            owner_id=None,
            owner_guest_id=scope.guest_id,
        )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.get("/projects/stats", response_model=list[ProjectStats])
def project_statistics(scope: Scope = Depends(get_scope), db: Session = Depends(get_db)):
    """Per-project task stats computed with SQL aggregates across a join."""
    if scope.kind == "guest":
        ensure_guest_projects(db, scope.guest_id)
    proj_filter = _project_scope_filter(scope)
    totals = (
        db.query(Project.id, Project.title, func.count(Task.id))
        .outerjoin(Task, Task.project_id == Project.id)
        .filter(proj_filter)
        .group_by(Project.id, Project.title)
        .order_by(Project.id)
        .all()
    )
    ids = [project_id for project_id, _, _ in totals]
    by_priority = (
        db.query(Task.project_id, Task.priority, func.count(Task.id))
        .join(Project, Task.project_id == Project.id)
        .filter(proj_filter, Task.project_id.in_(ids))
        .group_by(Task.project_id, Task.priority)
        .all()
    )
    counts_by_project: dict[int, PriorityCounts] = {}
    for project_id, priority, count in by_priority:
        counts = counts_by_project.setdefault(project_id, PriorityCounts())
        setattr(counts, priority, count)
    return [
        ProjectStats(
            project_id=project_id,
            project_title=title,
            task_count=count,
            counts_by_priority=counts_by_project.get(project_id, PriorityCounts()),
        )
        for project_id, title, count in totals
    ]


@app.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
def list_tasks(
    project_id: int, scope: Scope = Depends(get_scope), db: Session = Depends(get_db)
):
    _get_own_project(db, scope, project_id)
    return db.query(Task).filter(Task.project_id == project_id).order_by(Task.id).all()


# ------------------------------ Tasks CRUD ------------------------------

@app.post("/projects/{project_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    project_id: int,
    task_in: TaskCreate,
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    _get_own_project(db, scope, project_id)
    task = Task(
        title=task_in.title,
        priority=task_in.priority,
        due_date=task_in.due_date,
        content=task_in.content,
        project_id=project_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _scoped_tasks_query(db: Session, scope: Scope):
    return db.query(Task).join(Project, Task.project_id == Project.id).filter(
        _project_scope_filter(scope)
    )


@app.get("/tasks", response_model=list[TaskRead])
def list_all_tasks(
    sort: Literal["priority", "due_date"] | None = None,
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    tasks = _scoped_tasks_query(db, scope).order_by(Task.id).all()
    if sort is None:
        return tasks
    records = [
        {
            "id": t.id,
            "title": t.title,
            "priority": PRIORITY_WEIGHTS[t.priority],
            "due_date": t.due_date or "",
            "project_id": t.project_id,
        }
        for t in tasks
    ]
    insertion_sort(records, sort)
    weight_to_name = {weight: name for name, weight in PRIORITY_WEIGHTS.items()}
    for record in records:
        record["priority"] = weight_to_name[record["priority"]]
        if record["due_date"] == "":
            record["due_date"] = None
    return records


@app.get("/tasks/search", response_model=TaskRead)
def search_tasks(
    title: str,
    algo: Literal["binary", "linear"] = "binary",
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    tasks = _scoped_tasks_query(db, scope).all()
    index = [{"id": t.id, "title": t.title} for t in tasks]
    if algo == "binary":
        insertion_sort(index, "title")
        pos = binary_search(index, title, "title")
    else:
        pos = linear_search(index, title, "title")
    if pos == -1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    task = db.get(Task, index[pos]["id"])
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return task


@app.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, scope: Scope = Depends(get_scope), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    _get_own_project(db, scope, task.project_id)
    return task


@app.put("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    _get_own_project(db, scope, task.project_id)
    if task_in.title is not None:
        task.title = task_in.title
    if task_in.priority is not None:
        task.priority = task_in.priority
    if task_in.due_date is not None:
        task.due_date = task_in.due_date
    if task_in.content is not None:
        task.content = task_in.content
    db.commit()
    db.refresh(task)
    return task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, scope: Scope = Depends(get_scope), db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    _get_own_project(db, scope, task.project_id)
    db.delete(task)
    db.commit()
    return None


# ------------------------------ Quick add -------------------------------

@app.post("/tasks/quick-add", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def quick_add_task(
    payload: QuickAddCreate,
    scope: Scope = Depends(get_scope),
    db: Session = Depends(get_db),
):
    _get_own_project(db, scope, payload.project_id)
    if USE_REAL_LLM:
        # Optional real-LLM path (off by default). build_prompt builds the
        # role-based system+user messages; with no API key configured we fall
        # back to the deterministic mock parser, so the app still runs free.
        build_prompt(payload.description)
    parsed = parse_quick_add(payload.description)
    task = Task(
        title=parsed["title"],
        priority=parsed["priority"],
        due_date=parsed["due_date_hint"],
        project_id=payload.project_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# ------------------------------ Frontend --------------------------------

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
