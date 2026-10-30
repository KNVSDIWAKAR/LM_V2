# Mortgage Agentic Workbench — Loss Mitigation

A **React (JavaScript)** client and a **FastAPI + PostgreSQL** backend.

```
Loss_Mitigation/
├── backend/
│   ├── .env                 DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD / DB_SSLMODE (not committed; see .env.example)
│   ├── app/
│   │   ├── main.py          app, CORS, routers; creates missing tables on start (never inserts data)
│   │   ├── core/            config (.env) · database (engine, session)
│   │   ├── models/          msp · extracted_data · lm_stages · runs
│   │   ├── schemas/         Pydantic: validate imports, shape responses
│   │   └── routes/          msp · extracted_data · lm_stages · runs
│   ├── scripts/import_data.py   loads msp.json / lm_status.json / extracted_data.json
│   └── tests/               pytest (SQLite, inline fixtures)
└── frontend/                React 18 · Vite · Tailwind v4 · TanStack Query · wouter
```

## Database

Nine tables. The loan tables use `loan_id` as their primary key.

| Table | Primary key | Columns |
|---|---|---|
| `msp` | loan_id | Borrower identity as columns. `bankruptcy`, `foreclosure`, `hoa` and one JSONB column per MSP screen: `ana1`, `dlq1` (incl. `payment_history`), `haz1`, `lmt1`, `lmt3` (incl. closing-code dates), `nots`, `usr2`, `task1`, `mes1`, `lsmr` |
| `extracted_data` | loan_id → msp | `extraction_status`, `extracted_at`, `flags`, and one JSONB column per document: `application_form`, `paystubs`, `bank_statement`, `credit_report`, `letter_of_explanation`, `neighbourhood_document` |
| `trial_plans` / `trial_installments` | id | Trial UW proposals (payment, terms, calculation, reason codes, status proposed → approved / not_selected / declined / superseded) and each installment's due date, grace end and matched payment |
| `closing_qc` | loan_id → msp | MOD QC flags, Underwriting sign-off time (starts the 14-day SLA), county recording date |
| `lm_stages` | loan_id → msp | `{stage}_status` and `{stage}_remark` for `intake`, `retention_eligibility`, `trial_uw`, `trial_monitoring`, `closing`. A CHECK constraint allows only that stage's statuses (defined in `app/models/lm_stages.py`) |
| `workflow_runs` | id | One end-to-end run; `loan_id` → msp when it covers one loan |
| `agent_runs` | id | One agent on one stage (`stage_no` 1–5); `workflow_run_id` → workflow_runs, `loan_id` → msp |

## Run it

**Backend** (Python 3.10+):

```bash
cd backend
py -3.10 -m venv .venv                       # macOS/Linux: python3 -m venv .venv
.venv\Scriptsctivate                       # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                       # then fill in the database details
python -m scripts.import_data --msp msp.json --lm-status lm_status.json --extracted extracted_data.json
uvicorn app.main:app --reload --port 8000
```

To wipe the database and rebuild it from the files in one step, put `msp.json`, `lm_status.json` and `extracted_data.json` in `backend/data/` (git-ignored) and run `python -m scripts.reset_db`. It lists the tables, asks you to type `yes`, drops every table (runs included), recreates the five tables and loads the files. Add `--yes` to skip the prompt, or `--data-dir <folder>` to read the files from somewhere else.

The import validates every record against the schemas (unknown fields stop it) and upserts by key, so it is safe to re-run. Nothing is seeded automatically.

Open **http://localhost:8000** — the backend serves the UI on the same port. On startup it runs `npm run build` if anything in `frontend/` changed since the last build (installing `node_modules` first if missing), and while it runs it rebuilds after frontend edits; refresh the browser to see them. Without Node on the machine it serves the existing `frontend/dist`. Switch this off with `FRONTEND_AUTO_BUILD=false` / `FRONTEND_WATCH=false`.

**Deploying the backend alone:** build the UI as part of the build step (`cd frontend && npm ci && npm run build`), then start `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (no `--reload`) with `FRONTEND_AUTO_BUILD=false`. `frontend/dist` is git-ignored, so it has to be built on the server or in CI.

API docs: http://localhost:8000/docs

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev                                   # http://localhost:5173 (proxies /api → :8000)
```

**Single-origin production build:** run `npm run build` in `frontend/`, then start the backend; it serves `frontend/dist` at http://localhost:8000.

## Orchestration (Kairos)

| Layer | Where |
|---|---|
| 1 · Operations — the steps | `backend/harness/<process>/playbook.yaml` — nodes, and which outcome leads to which node |
| 2 · Domain harness — the rules | `backend/harness/<process>/rules.yaml` — versioned; every agent run records the version it used |
| 3 · Context — the memory | the graph state (`CaseState` in `app/engine/playbook.py`): case data, MSP response, findings |
| 4 · Sensors | `app/engine/sensors.py` — Prevent (BK can never reach handoff), Detect (mismatches, intake SLA) |
| 5 · Systems of record | `msp`, `extracted_data` |

`app/engine/playbook.py` compiles each playbook into a LangGraph. Node functions (`app/engine/nodes/<process>.py`, registered with `@node("intake.load_case")`) return an `outcome`; the YAML `routes` decide the next node, so the graph has a single generic router instead of hand-written conditional edges. A `gate` node pauses the case and opens a **Decision Inbox** item; approving resumes the graph at `on_approve`, rejecting at `on_reject`. `app/engine/runner.py` writes every result to `agent_runs`, `lm_stages`, `decisions` and `workflow_runs`; `app/engine/scheduler.py` (auto-flow) starts new cases every `AUTO_FLOW_INTERVAL_SECONDS` (default 30) and continues blocked ones when new documents arrive or the next stage gets a playbook.

**Add a process:** create `harness/<process>/playbook.yaml` + `rules.yaml` with its `stage_no`, write its node functions in `app/engine/nodes/<process>.py`, restart. The playbook is validated on startup (unknown nodes, unregistered functions, statuses the stage doesn't allow). Cases blocked at that stage continue on the next auto-flow tick.

## API

| Endpoint | |
|---|---|
| `GET /api/loans`, `GET /api/loans/{loan_id}` | MSP loans; the detail groups fields by screen |
| `GET /api/documents`, `/api/documents/{loan_id}`, `/api/documents/{loan_id}/{document_type}` | Knowledge Base |
| `GET /api/lm/stages`, `GET /api/lm/status[/{loan_id}]`, `PUT /api/lm/status/{loan_id}/{stage_no}` | Stage tracking |
| `GET /api/processes`, `GET /api/processes/{stage_no}`, `GET …/playbook`, `POST …/run` | The five processes: status board, cases, playbook, run one stage |
| `POST /api/workflow/run`, `GET/PUT /api/workflow/auto` | Run end to end now; auto-flow on/off |
| `GET /api/decisions`, `POST /api/decisions/{id}/decide` | Decision Inbox; deciding resumes the paused case (`selected_plan_id` at Trial UW, `qc` at MOD QC) |
| `GET /api/cases/{3,4,5}/{loan_id}`, `PUT /api/cases/5/{loan_id}/closing-record` | Case drawers for Trial UW / Monitoring / Closing; record QC flags and recording date |
| `GET /api/workflow-runs[/{id}]`, `GET /api/agent-runs[/{id}]` | Run history (written by the engine only) |

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
```

Runs on a throwaway SQLite database with small inline fixtures. Covers per-screen MSP storage, one-column-per-document storage, strict import validation and idempotency, allowed stage statuses, and the workflow/agent run lifecycle.
