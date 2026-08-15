import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from backend.auth import hash_password
from backend.database import Base, SessionLocal, engine
from backend.models import Project, Task, User


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "demo@taskflow.io"))
        if user is None:
            user = User(
                email="demo@taskflow.io",
                username="demo",
                display_name="Demo User",
                gender="female",
                provider="local",
                hashed_password=hash_password("demo123"),
            )
            db.add(user)
            db.flush()
            print(f"Created user demo@taskflow.io (id {user.id})")
        else:
            print(f"User demo@taskflow.io already exists (id {user.id})")

        project = db.scalar(select(Project).where(Project.title == "Demo Project"))
        if project is None:
            project = Project(
                title="Demo Project",
                content="Main working project used for the capstone demo.",
                owner_id=user.id,
            )
            db.add(project)
            db.flush()
            print(f"Created project 'Demo Project' (id {project.id})")
        else:
            print(f"Project 'Demo Project' already exists (id {project.id})")

        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)).all())
        if not tasks:
            sample = [
                {
                    "title": "Finish report  it is",
                    "priority": "high",
                    "due_date": "tomorrow",
                    "content": "Compile the final report and share it with the team.",
                },
                {
                    "title": "Capstone Project",
                    "priority": "medium",
                    "due_date": None,
                    "content": "Keep all three assignment sections running on one server.",
                },
                {
                    "title": "Complete",
                    "priority": "low",
                    "due_date": None,
                    "content": "Wrap up pending items and mark them done.",
                },
            ]
            for item in sample:
                db.add(Task(project_id=project.id, **item))
            print(f"Created {len(sample)} sample task(s)")
        else:
            print(f"Project already has {len(tasks)} task(s); nothing to add")

        db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    seed()
