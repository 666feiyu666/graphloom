# Graphloom — Working Instructions

Local ontology and knowledge-graph workbench. The specification is `docs/design.md`; it owns the product boundary. Owner editing and the reader-facing graph contract are separate: there is no agent write interface, no built-in modeling assistant, and no MCP server in this MVP.

## Environment

- Backend: `uv` with Python 3.13 and a project-local `.venv` under `backend/`. Do not use Apple or Homebrew Python as the project environment.
- Frontend: npm with the committed `package-lock.json`.
- Runtime data lives in `.local/` and is ignored. Never commit databases, tokens, `frontend/dist/`, `.e2e/`, Playwright output, or caches.
- Relative `GRAPPHLOOM_DB_PATH` / `GRAPPHLOOM_FRONTEND_DIST` values resolve against the `graphloom/` directory, not the process CWD.

## Setup

```bash
cd graphloom/backend && uv sync --locked
cd graphloom/frontend && npm ci
```

## Owner and reader credentials

```bash
cd graphloom/backend
uv run python -m app.cli init-owner              # print the owner token once
uv run python -m app.cli init-owner --rotate     # replace an existing owner token
uv run python -m app.cli create-reader --label agent --project-id <project-uuid>
uv run python -m app.cli list-credentials
uv run python -m app.cli revoke --credential-id <credential-uuid>
```

The browser keeps the owner token in memory only. Reader credentials are project-scoped and can be created or revoked from **Read access** in the workbench.

## Run

```bash
# Terminal 1
cd graphloom/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2
cd graphloom/frontend
npm run dev
```

Open `http://127.0.0.1:5173`. For a packaged local run, `npm run build` in `frontend/`; FastAPI serves `frontend/dist` at the same origin. Startup runs Alembic migrations.

## Verification

```bash
cd graphloom/backend && uv run python -m pytest
cd graphloom/frontend && npm test
cd graphloom/frontend && npm run build
cd graphloom/frontend && npm run e2e
```

`npm run e2e` uses the installed Google Chrome (`channel: "chrome"`) and starts temporary backend/frontend servers with a throwaway `frontend/.e2e/graphloom.db`. It deletes that database at startup. Do not point E2E at the research runtime database.

## Reader example

```bash
cd graphloom
python3 examples/reader_client.py \
  --base-url http://127.0.0.1:8000/api/v1 \
  --token "$GRAPPHLOOM_READER_TOKEN" \
  --project-id "$GRAPPHLOOM_PROJECT_ID"
```

The example performs no writes and needs no OpenAI key. It pins a revision, reads schema and paginated objects, and inspects a bounded neighborhood.

## Data and export rules

- Native JSON is the authoritative interchange format. Import replaces the selected project's graph through a previewed change set; it does not merge.
- Turtle is a bounded projection. Advisory domain/range lists are exported as Graphloom metadata, not OWL/RDFS restrictions; assertion identity is preserved with reified records.
- Runtime fixtures must be synthetic and must not be presented as research findings. Do not prepopulate disciplinary categories or copy research materials into application storage.
