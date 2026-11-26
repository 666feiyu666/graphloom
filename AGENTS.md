# Graphloom — Working Instructions

Local, single-user ontology and knowledge-graph workbench. The specification is `docs/design.md`; it owns the product boundary. The saved graph is exposed read-only to a consuming agent over loopback. There is no credential system, no agent write interface, no built-in modeling assistant, and no MCP server.

## Environment

- Backend: `uv` with Python 3.13 and a project-local `.venv` under `backend/`. Do not use Apple or Homebrew Python as the project environment.
- Frontend: npm with the committed `package-lock.json`.
- Runtime data lives in `.local/projects/` (one JSON file per project) and is ignored. Never commit `frontend/dist/`, `.env`, `*.bak`, or caches.
- Relative `GRAPPHLOOM_DATA_DIR` / `GRAPPHLOOM_FRONTEND_DIST` values resolve against the `graphloom/` directory, not the process CWD.

## Setup

```bash
cd graphloom/backend && uv sync --locked
cd graphloom/frontend && npm ci
```

## Run

```bash
# Terminal 1
cd graphloom/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2
cd graphloom/frontend
npm run dev
```

Open `http://127.0.0.1:5173`. For a packaged local run, `npm run build` in `frontend/`; FastAPI serves `frontend/dist` at the same origin.

## Access model

The service binds to `127.0.0.1` and assumes a single local user. There are no tokens or accounts: the workbench writes through `POST /api/v1/projects/{id}/batch`, and the consuming agent receives only the read endpoints (published as `/api/v1/openapi.reader.json`). This is a convention on a trusted loopback, not a security boundary.

Reader example (no credential needed):

```bash
cd graphloom
python3 examples/reader_client.py \
  --base-url http://127.0.0.1:8000/api/v1 \
  --project-id "$GRAPPHLOOM_PROJECT_ID"
```

It performs no writes and needs no OpenAI key. It lists read endpoints, reads schema and paginated objects, and inspects a bounded neighborhood.

## Verification

```bash
cd graphloom/backend && uv run python -m pytest
cd graphloom/frontend && npm test
cd graphloom/frontend && npm run build
```

## Data rules

- Each project is one validated JSON file (`GRAPPHLOOM_DATA_DIR/<project-id>.json`). Saves are atomic (temp file + rename) and keep the previous state as `<project-id>.bak`.
- The JSON file is the authoritative interchange and portability format; copy the file (and `.bak`) to back up or move a project.
- RDF/Turtle export and native import are deferred; do not add them without a concrete need.
- Runtime fixtures must be synthetic and must not be presented as research findings. Do not prepopulate disciplinary categories or copy research materials into application storage.
