"""TaskFlow Section 2 benchmark: comparison counts at 10 / 500 / 3000 tasks.

Seeds an in-memory SQLite database with the real Task model, fetches rows into
dicts, and runs the counting wrappers. Prints results and saves the raw counts
to results/benchmarks.txt.

Run from the repository root:

    python benchmark.py
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.algorithms import (
    binary_search_count,
    insertion_sort,
    insertion_sort_count,
    linear_search_count,
)
from backend.database import Base
from backend.models import Task

SIZES = [10, 500, 3000]
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(ROOT, "results", "benchmarks.txt")


def build_tasks(size):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    priorities = ["low", "medium", "high"]
    for i in range(size):
        db.add(Task(
            title=f"Benchmark task {i}",
            priority=priorities[i % 3],
            due_date="tomorrow" if i % 2 else None,
            project_id=1,
        ))
    db.commit()
    tasks = db.query(Task).order_by(Task.id).all()
    db.close()
    engine.dispose()
    return tasks


def run_size(size):
    tasks = build_tasks(size)

    title_index = [{"id": t.id, "title": t.title} for t in tasks]
    target = title_index[size // 2]["title"]
    missing = "zz-no-such-title"

    priority_records = [
        {
            "id": t.id,
            "title": t.title,
            "priority": {"low": 1, "medium": 2, "high": 3}[t.priority],
            "due_date": t.due_date,
            "project_id": t.project_id,
        }
        for t in tasks
    ]
    insertion_priority = insertion_sort_count(priority_records, "priority")

    title_copy = [dict(r) for r in title_index]
    insertion_title = insertion_sort_count(title_copy, "title")

    sorted_titles = [dict(r) for r in title_index]
    insertion_sort(sorted_titles, "title")
    binary_found = binary_search_count(sorted_titles, target, "title")
    binary_missing = binary_search_count(sorted_titles, missing, "title")

    linear_found = linear_search_count(title_index, target, "title")
    linear_missing = linear_search_count(title_index, missing, "title")

    return {
        "size": size,
        "insertion_priority": insertion_priority,
        "insertion_title": insertion_title,
        "binary_found": binary_found,
        "binary_missing": binary_missing,
        "linear_found": linear_found,
        "linear_missing": linear_missing,
    }


def main():
    results = [run_size(size) for size in SIZES]

    lines = ["TaskFlow Section 2 benchmark (comparison counts)"]
    lines.append("dataset_size | insertion_sort(priority) | insertion_sort(title) | "
                 "binary_search(found index,count) | binary_search(missing count) | "
                 "linear_search(found count) | linear_search(missing count)")
    for r in results:
        lines.append(
            f"{r['size']} | {r['insertion_priority']} | {r['insertion_title']} | "
            f"{r['binary_found']['index']},{r['binary_found']['comparison_count']} | "
            f"{r['binary_missing']['comparison_count']} | "
            f"{r['linear_found']['comparison_count']} | "
            f"{r['linear_missing']['comparison_count']}"
        )

    print("\n".join(lines))
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nSaved to {OUT_FILE}")


if __name__ == "__main__":
    main()
