# TaskFlow — Full-Stack Task Management Platform

TaskFlow is a single working full-stack application for a capstone assignment,
covering three graded sections that operate on the same three tables
(`users`, `projects`, `tasks`) and the same running server:

- **Section 1 — Core App:** FastAPI + SQLAlchemy backend and an HTML/CSS/JS dashboard.
- **Section 2 — Algorithms Engine:** hand-rolled Insertion Sort, Binary Search and
  Linear Search powering the `/tasks` sort and `/tasks/search` endpoints.
- **Section 3 — AI Quick-Add:** a deterministic, keyless mock parser behind
  `POST /tasks/quick-add` (with an optional, off-by-default real-LLM path).

```
taskflow/
├── backend/
│   ├── database.py        # SQLite engine, session, declarative Base
│   ├── models.py          # User -> Project -> Task ORM models
│   ├── schemas.py         # Pydantic models, Field constraints + validators
│   ├── algorithms.py      # Section 2: insertion/binary/linear search + counters
│   ├── parser.py          # Section 3: mock quick-add parser + prompt builder
│   └── main.py            # FastAPI app: CRUD, stats, sort/search, quick-add
├── frontend/
│   ├── index.html         # Dashboard (sidebar, task form, task list)
│   └── styles.css         # Box-model layout, sticky sidebar, 2 breakpoints
├── check_algorithms.py    # Section 2 PASS/FAIL checks
├── benchmark.py           # Section 2 comparison-count benchmarks
├── results/
│   └── benchmarks.txt     # Raw benchmark counts
└── README.md
```

## Environment setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# or: source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

`requirements.txt` pins `fastapi`, `pydantic`, `sqlalchemy`, `uvicorn`, and `httpx2`.

## How to run the whole app (single process)

The backend also serves the frontend, so one command starts everything. From the
repository root:

```bash
.\.venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000
```

Then open:

- Frontend dashboard: http://127.0.0.1:8000/
- Interactive API docs: http://127.0.0.1:8000/docs

Because the frontend is served from the same origin, its Fetch calls use relative
paths (e.g. `/projects/1/tasks`). CORS is configured to also allow the
two-process setup (`http://127.0.0.1:5500`, `http://localhost:5500`).

Run the checks and benchmarks:

```bash
python check_algorithms.py   # Section 2 PASS/FAIL checks
python benchmark.py          # Section 2 comparison-count benchmarks
```

### Seed demo data

Creates `demo@taskflow.io` (password `demo123`), the project `Demo Project`,
and a sample task. Safe to run repeatedly — it never duplicates:

```bash
python seed.py
```

### Auto-start the server (permanent fix)

The server normally runs only while the terminal is open. To make it start
automatically every time you log in (no console window, no manual command):

```powershell
# 1. Double-click start_server.vbs (or run it once):
wscript start_server.vbs

# 2. Register it for auto-start at login (already done on the author's machine):
#    a shortcut named "TaskFlow Server" is placed in the Startup folder
#    pointing to start_server.vbs. It launches .venv\Scripts\pythonw.exe
#    with run_server.py, which writes logs to server.log.
```

After a reboot (or after the shortcut runs), open http://127.0.0.1:8000 —
no manual command needed. `run_server.py` logs to `server.log` in the repo
root so errors are still visible.

To stop the background server: `Get-Process pythonw | Stop-Process` (closes
all hidden `pythonw` instances).

> To let *other devices* on your network reach the app, change `host` to
> `0.0.0.0` in `run_server.py` (and allow port 8000 in Windows Firewall).
> This is already the default in this repo.

### Public access for anyone (internet)

A Cloudflare tunnel exposes the app to the whole internet with a public
`https://` URL — no router setup, no account needed.

```powershell
# start_tunnel.vbs launches cloudflared hidden and appends to tunnel.log
wscript start_tunnel.vbs
```

A startup shortcut named "TaskFlow Tunnel" auto-starts it at login (already
installed on the author's machine). The public URL is printed in
`tunnel.log`:

```powershell
Select-String -Path tunnel.log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com"
```

Example: `https://something-words.trycloudflare.com`. Anyone with that link
can open the app from any device/browser.

> **Note:** the free quick-tunnel URL **changes every time** the tunnel
> restarts (reboot). If you need one permanent URL, deploy the app to a
> free cloud host (e.g. Render) or use a Cloudflare named tunnel with a
> domain. The local URL `http://127.0.0.1:8000` always works on the PC.

## Endpoint list

### Create — users
`POST /users`
```json
// Request
{"email": "a@b.com", "password": "secret"}
```
```json
// Response 201
{"email": "a@b.com", "id": 1}
```

### Create — projects
`POST /projects?owner_id=1`
```json
// Request
{"title": "Dark Store A"}
```
```json
// Response 201
{"title": "Dark Store A", "id": 1, "owner_id": 1}
```

### Create — task
`POST /projects/1/tasks`
```json
// Request
{"title": "Restock shelves", "priority": "high", "due_date": "tomorrow"}
```
```json
// Response 201
{"title": "Restock shelves", "priority": "high", "due_date": "tomorrow", "id": 1, "project_id": 1}
```
422 is returned for a blank title or a priority outside `low|medium|high`.

### List
- `GET /users` → `[{"email": "a@b.com", "id": 1}]`
- `GET /projects` → `[{"title": "Dark Store A", "id": 1, "owner_id": 1}]`
- `GET /projects/1/tasks` → `[{...task...}]`
- `GET /tasks` → all tasks

### Get by id
`GET /tasks/1`
```json
// Response 200
{"title": "Restock shelves", "priority": "high", "due_date": "tomorrow", "id": 1, "project_id": 1}
```
404 if the id does not exist.

### Update
`PUT /tasks/1`
```json
// Request
{"title": "Restock shelves tonight", "priority": "low", "due_date": null}
```
```json
// Response 200
{"title": "Restock shelves tonight", "priority": "low", "due_date": null, "id": 1, "project_id": 1}
```

### Delete
`DELETE /tasks/1` → `204 No Content` (404 if the id does not exist).

### Statistics (SQL aggregate across a join)
`GET /projects/stats`
```json
// Response 200
[
  {
    "project_id": 1,
    "project_title": "Dark Store A",
    "task_count": 3,
    "counts_by_priority": {"low": 1, "medium": 1, "high": 1}
  }
]
```
Computed with `COUNT` + `GROUP BY` over a `projects ⟕ tasks` join in SQL, never in Python.

### Sorted list
`GET /tasks?sort=priority` (also accepts `sort=due_date`)

Tasks are fetched into dicts, priority is mapped to its weight
(low=1, medium=2, high=3), sorted with the custom `insertion_sort`, then the
weight is mapped back to the label before returning:
```json
// Response 200
[
  {"title": "Sweep floor", "priority": "low", "due_date": null, "id": 2, "project_id": 1},
  {"title": "Restock shelves", "priority": "high", "due_date": "tomorrow", "id": 1, "project_id": 1}
]
```

### Search
`GET /tasks/search?title=Restock%20shelves&algo=binary` (`algo` defaults to `binary`)

Builds an in-memory index of `{"id", "title"}` pairs, sorts it with
`insertion_sort` for binary search, and searches with `binary_search`
(or `linear_search` over the unsorted index when `algo=linear`):
```json
// Response 200
{"title": "Restock shelves", "priority": "high", "due_date": "tomorrow", "id": 1, "project_id": 1}
```
404 when no task matches the exact title.

### Quick-add (Section 3)
`POST /tasks/quick-add`
```json
// Request
{"description": "Finish the report next Friday, it's urgent", "project_id": 1}
```
```json
// Response 201
{"title": "Finish the report , it's", "priority": "high", "due_date": "next friday", "id": 4, "project_id": 1}
```

## Section 2 — Algorithms: complexity & benchmark evidence

### Time complexities

| Algorithm | Best case | Worst case | Average case | Space |
| --- | --- | --- | --- | --- |
| `insertion_sort` | O(n) | O(n²) | O(n²) | O(1) |
| `binary_search` | O(1) | O(log n) | O(log n) | O(1) |
| `linear_search` | O(1) | O(n) | O(n) | O(1) |

### Benchmark results (comparison counts on real task rows)

| Size | insertion(priority) | insertion(title) | binary found (idx,count) | binary missing | linear found | linear missing |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | 24 | 9 | 5, 3 | 4 | 6 | 10 |
| 500 | 42,082 | 31,259 | 169, 9 | 9 | 251 | 500 |
| 3000 | 1,501,499 | 1,820,009 | 559, 11 | 12 | 1,501 | 3,000 |

Raw numbers are saved in `results/benchmarks.txt`.

### Is sorting first worth it?

The counted numbers show clearly that yes, it is. Searching 3,000 tasks linearly
needs up to 3,000 comparisons when the title is missing, and about 1,500 on
average when it is present; binary search finds the same title in at most 11
comparisons. The one-time cost to make that possible is sorting: insertion sort
needs 1.82 million comparisons to order 3,000 titles — expensive, but it happens
once. After that, every search drops from roughly O(n) (1,500–3,000 comparisons)
to O(log n) (≤12 comparisons), a ~150–250× reduction per lookup. As the task
list grows, that trade-off gets strictly better: the sort grows quadratically
but stays a one-off, while each search stays logarithmic instead of growing
linearly with the dataset. When lookups outnumber sorts, sorting first is clearly
the right call; for a single one-off lookup on a small list, a plain linear scan
is simpler and cheaper.

## Section 3 — AI Quick-Add

### Prompting technique

TaskFlow's quick-add feature uses a **role-based prompt structure**: a `system`
instruction that fixes the output contract, followed by a `user` message
containing the free-text description. The system instruction tells the model it
is a quick-add assistant, names the exact JSON fields it must return (`title`,
`priority`, `due_date_hint`), enumerates the allowed priority values
(`low`/`medium`/`high`), and specifies the `"Untitled task"` fallback so every
response is well-typed. Keeping all of that in the system message — separate from
the user's description — means the model treats the rules as instructions rather
than as part of the data, which is the standard role-based technique for
extracting structured data from unstructured input. The user message stays a raw
description, so nothing the user types can override the schema rules.

Because the default grading path must work with **zero API keys and zero network
calls**, the endpoint runs a **deterministic mock parser** instead of an LLM.
The mock follows the same contract: it checks priority keywords in priority order
(`urgent`/`asap` → high beats `whenever`/`low priority` → low, else medium),
matches due-date phrases in a fixed order, and strips keywords and the matched
date phrase from the original-cased title. A real LLM call is supported behind
the `USE_REAL_LLM` flag (default off); when enabled it builds the role-based
prompt above and only then calls an LLM if an API key is available, otherwise it
falls back to the mock parser. This keeps the feature free, deterministic, and
fully testable while still demonstrating the prompt design.

### Worked examples (mock output — exactly what the API produces)

**Example 1**
```json
// POST /tasks/quick-add
{"description": "This is urgent, mark it ASAP please", "project_id": 1}
{"title": "This is , mark it  please", "priority": "high", "due_date_hint": null}
```

**Example 2**
```json
{"description": "   ", "project_id": 1}
{"title": "Untitled task", "priority": "medium", "due_date_hint": null}
```

**Example 3**
```json
{"description": "Finish the report next Friday, it's urgent", "project_id": 1}
{"title": "Finish the report , it's", "priority": "high", "due_date_hint": "next friday"}
```

**Example 4**
```json
{"description": "tomorrow review tomorrow", "project_id": 1}
{"title": "review", "priority": "medium", "due_date_hint": "tomorrow"}
```

**Example 5**
```json
{"description": "whenever, send the invoice next monday", "project_id": 1}
{"title": ", send the invoice", "priority": "low", "due_date_hint": "next monday"}
```

## Notes

- Every request is logged to the console by a middleware as
  `METHOD path - X.XX ms`.
- The dashboard renders user input with `textContent` and builds DOM nodes with
  `document.createElement` (no `innerHTML`), caches the task list in
  `localStorage` (rendered instantly on reload, then refreshed from the API),
  and validates the task form client-side before submitting.
- The required repository should be a single public GitHub repo with a feature
  branch that was committed to at least twice and merged back into `main`.
