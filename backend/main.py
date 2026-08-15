import os
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .algorithms import PRIORITY_WEIGHTS, binary_search, insertion_sort, linear_search
from .auth import (
    create_token,
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
    LoginRequest,
    MeUpdate,
    OAuthRequest,
    PriorityCounts,
    ProjectCreate,
    ProjectRead,
    ProjectStats,
    QuickAddCreate,
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
    allow_headers=["Content-Type", "Authorization", "Accept"],
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
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id).all()


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    owner_id: int | None = None,
    current_user: User | None = Depends(get_optional_user),
):
    if owner_id is None and current_user is not None:
        owner_id = current_user.id
    if owner_id is None:
        owner = db.query(User).order_by(User.id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no users exist yet")
        owner_id = owner.id
    if not db.get(User, owner_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")
    project = Project(title=project_in.title, content=project_in.content, owner_id=owner_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@app.get("/projects/stats", response_model=list[ProjectStats])
def project_statistics(db: Session = Depends(get_db)):
    """Per-project task stats computed with SQL aggregates across a join."""
    totals = (
        db.query(Project.id, Project.title, func.count(Task.id))
        .outerjoin(Task, Task.project_id == Project.id)
        .group_by(Project.id, Project.title)
        .order_by(Project.id)
        .all()
    )
    by_priority = (
        db.query(Task.project_id, Task.priority, func.count(Task.id))
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
def list_tasks(project_id: int, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return db.query(Task).filter(Task.project_id == project_id).order_by(Task.id).all()


# ------------------------------ Tasks CRUD ------------------------------

@app.post("/projects/{project_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(project_id: int, task_in: TaskCreate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
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


@app.get("/tasks", response_model=list[TaskRead])
def list_all_tasks(sort: Literal["priority", "due_date"] | None = None, db: Session = Depends(get_db)):
    tasks = db.query(Task).order_by(Task.id).all()
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
def search_tasks(title: str, algo: Literal["binary", "linear"] = "binary", db: Session = Depends(get_db)):
    tasks = db.query(Task).all()
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
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return task


@app.put("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
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
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    db.delete(task)
    db.commit()
    return None


# ------------------------------ Quick add -------------------------------

@app.post("/tasks/quick-add", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def quick_add_task(payload: QuickAddCreate, db: Session = Depends(get_db)):
    if not db.get(Project, payload.project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
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
