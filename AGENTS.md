# Graphloom — Agent Constraints

Product boundary lives in `docs/design.md`; usage lives in `README.md`. This file constrains how agents may change the code.

## Invariants

- Single local user on loopback. Do not add authentication, tokens, accounts, or a public deployment.
- No agent write interface, no built-in modeling assistant or AI features, no MCP server.
- The only semantic write path is `POST /api/v1/projects/{id}/batch`. Saves are atomic: an invalid batch changes nothing.
- Each project is one JSON file under `GRAPPHLOOM_DATA_DIR`, written atomically with a `<id>.bak` of the previous state. Do not reintroduce SQLite, an ORM, or migrations. `DataStore` must not create directories on import — only on first write.
- Data isolation: automated tests use pytest's `tmp_path`; development fixtures and `examples/seed.py` write to `.local/dev` (`GRAPPHLOOM_PROFILE=dev`). Never write test or development data into `.local/projects`.
- Reads are side-effect free and never advance the project version.
- Layout (node positions, viewport) is not semantic. Keep it out of the graph state.
- Ontology definitions and instance assertions stay distinct. Object lifecycle is `status: active | deprecated`; do not add unrequested fields such as `review_status`, `origin`, or actor attribution.
- Do not add these without explicit instruction: RDF/Turtle export, native import, revision history, snapshots, branching, PDF/OCR, embeddings/GraphRAG, multi-user, OWL/SPARQL reasoning, Neo4j/PostgreSQL/Redis/Celery/Docker.

## Environment

- Backend: `uv` with Python 3.13 and a project-local `.venv` under `backend/`. Never use Apple or Homebrew Python.
- Frontend: npm with the committed `package-lock.json`.
- Relative `GRAPPHLOOM_DATA_DIR` / `GRAPPHLOOM_FRONTEND_DIST` resolve against `graphloom/`, not the process CWD.
- Never commit `.local/`, `.env`, `frontend/dist/`, `*.bak`, or caches. Do not copy or modify research materials as part of application work.

## Code conventions

- Backend: FastAPI + Pydantic v2 with plain Python domain services; validate and query on an in-memory graph state.
- Frontend: React + TypeScript + Vite; keep Cytoscape.js behind the `GraphCanvas` adapter; avoid adding a state-management library.
- Errors use `{"error": {"code", "message", "details"}, "request_id"}`.
- Fixtures must be synthetic and must not be presented as research findings; do not prepopulate disciplinary categories.

## Before finishing

Run these and leave them green:

```bash
cd graphloom/backend && uv run python -m pytest -q
cd graphloom/frontend && npm test
cd graphloom/frontend && npm run build
```
