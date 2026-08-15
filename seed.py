import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select

from backend.database import Base, SessionLocal, engine
from backend.models import Project, Task

SAMPLE_GUEST = "sample"


def seed() -> None:
    """Seed the sample content as a guest template. Every new guest session
    gets its own private copy of this content, so accounts start empty and
    nobody can see anybody else's data."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        project = db.scalar(
            select(Project).where(
                Project.owner_id.is_(None), Project.owner_guest_id == SAMPLE_GUEST
            )
        )
        if project is None:
            project = Project(
                title="Sample Project",
                content="Sample content for exploring TaskFlow. Every guest gets their own private copy.",
                owner_id=None,
                owner_guest_id=SAMPLE_GUEST,
            )
            db.add(project)
            db.flush()
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
            db.commit()
            print(f"Created sample template project + {len(sample)} task(s)")
        else:
            print("Sample template already exists")


if __name__ == "__main__":
    seed()
