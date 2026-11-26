# Graphloom 图思

A local, single-user workbench for building and inspecting a visual-rhetoric ontology and its knowledge graph. The saved graph is exposed read-only to a consuming agent.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- A browser

## Install

```bash
cd graphloom/backend && uv sync --locked
cd graphloom/frontend && npm ci
```

## Run

Development (two terminals):

```bash
# backend
cd graphloom/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend
cd graphloom/frontend
npm run dev
```

Open <http://127.0.0.1:5173>. The frontend proxies `/api` to the backend.

Single-process run: build the frontend, then start only the backend and open <http://127.0.0.1:8000>.

```bash
cd graphloom/frontend && npm run build
cd graphloom/backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Use the workbench

- Create or open a project; each project holds one ontology and graph.
- **Model** mode edits classes, relation types, and attribute types, with derived hierarchy/domain/range edges.
- **Instances** mode edits instances, relation assertions, and literal assertions; selecting a class filters its instances.
- Switch between **Graph** and **Table** views; create from the explorer, inspect and edit on the right.
- **Deprecate** keeps an object and its references; deleting a referenced object is rejected with its dependency list.
- Node positions are saved separately and never change the graph version.

## Read access for a consuming agent

The **Read access** panel shows the API base and the saved JSON file path. Read endpoints:

- `GET /api/v1/projects/{id}/state`
- `GET /api/v1/projects/{id}/schema`
- `GET /api/v1/projects/{id}/objects` (and `/objects/{object_id}`)
- `GET /api/v1/projects/{id}/neighborhood?id=…`
- `GET /api/v1/projects/{id}/instances?class_id=…`
- `GET /api/v1/projects/{id}/references?id=…`

All return the project `version` and `saved_at`. No token is needed: the service binds to `127.0.0.1`. The reader-only OpenAPI document is at <http://127.0.0.1:8000/api/v1/openapi.reader.json>.

Consumer example:

```bash
python3 examples/reader_client.py \
  --base-url http://127.0.0.1:8000/api/v1 \
  --project-id <project-id>
```

## Data and environments

- Everyday use writes to `.local/projects/`; each project is one JSON file and the previous save is kept as `<project-id>.bak`.
- Development uses a separate store: set `GRAPPHLOOM_PROFILE=dev` (the backend then uses `.local/dev/`), or point `GRAPPHLOOM_DATA_DIR` at any directory. An explicit `GRAPPHLOOM_DATA_DIR` always wins.
- Automated tests use pytest's temporary directories and never touch `.local/projects/`.
- Seed synthetic development data into `.local/dev/` (refuses `.local/projects/` unless `--force`):

  ```bash
  cd graphloom/backend && uv run python ../examples/seed.py
  ```

- Run the backend against development data by prefixing the command with `GRAPPHLOOM_PROFILE=dev`.

- To back up or move a project, copy its file and its `.bak`.
