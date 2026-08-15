import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models import Project, Task, User


def seed() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "demo@taskflow.io"))
        if user is None:
            user = User(email="demo@taskflow.io", hashed_password="demo123")
            db.add(user)
            db.flush()
            print(f"Created user demo@taskflow.io (id {user.id})")
        else:
            print(f"User demo@taskflow.io already exists (id {user.id})")

        project = db.scalar(select(Project).where(Project.title == "Demo Project"))
        if project is None:
            project = Project(title="Demo Project", owner_id=user.id)
            db.add(project)
            db.flush()
            print(f"Created project 'Demo Project' (id {project.id})")
        else:
            print(f"Project 'Demo Project' already exists (id {project.id})")

        tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)).all())
        if not tasks:
            db.add(
                Task(
                    title="Welcome to TaskFlow",
                    priority="medium",
                    due_date=None,
                    project_id=project.id,
                )
            )
            print("Created sample task 'Welcome to TaskFlow'")
        else:
            print(f"Project already has {len(tasks)} task(s); nothing to add")

        db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    seed()
