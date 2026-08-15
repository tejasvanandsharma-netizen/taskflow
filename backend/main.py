import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session

from .algorithms import PRIORITY_WEIGHTS, binary_search, insertion_sort, linear_search
from .database import Base, engine, get_db
from .models import Project, Task, User
from .parser import USE_REAL_LLM, build_prompt, parse_quick_add
from .schemas import (
    PriorityCounts,
    ProjectCreate,
    ProjectRead,
    ProjectStats,
    QuickAddCreate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    UserCreate,
    UserRead,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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
    user = User(email=user_in.email, hashed_password=user_in.password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


# ------------------------------ Projects --------------------------------

@app.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id).all()


@app.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db), owner_id: int | None = None):
    if owner_id is None:
        owner = db.query(User).order_by(User.id).first()
        if not owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no users exist yet")
        owner_id = owner.id
    if not db.get(User, owner_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="owner not found")
    project = Project(title=project_in.title, owner_id=owner_id)
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
