# Knowledge graphs

Declarative, versionable knowledge graphs that load into the Graphloom workbench. Each case is one directory of three JSON files; a single generic builder turns them into a Graphloom project.

## Layout

```text
knowledge/
  build.py              generic builder
  agent_read_test.py    generic read-back test (OpenAI)
  banksy/
    ontology.json       classes, relation types, attribute types
    sources.json        source references (CC photographs, evidence state)
    data.json           instances, relations, attribute values
```

## Build

```bash
cd graphloom/backend && uv run python ../knowledge/build.py --case banksy
```

- Idempotent by project name; pass `--replace` to rebuild the existing project.
- `--data-dir .local/dev` (or `--profile dev`) builds into the development store instead of `.local/projects`.

## JSON conventions

- Every object has a stable author-facing `id` (a slug). The builder maps slugs to UUIDs, so cross-references stay stable across edits and re-runs.
- `ontology.json` → `classes[].parents` reference class slugs; `relation_types[].domain/range` and `attribute_types[].domain` reference class slugs.
- `sources.json` → each entry is a `source_ref` with `locator` (`url` | `workspace_relative_path` | `zotero_key` | `free_text`), `citation_text`, and `evidence_state`.
- `data.json` → `instances[].classes` reference class slugs; `instances[].sources` reference source slugs; `relations[].source/type/target` and `attribute_values[].subject/attribute` reference slugs.

## Evidence rules

- Do not invent sources or locators. Cite what was actually retrieved, and keep `evidence_state` explicit (`discovered`, `bibliographically_verified`, `abstract_preview_verified`, `full_text_verified`, `secondary_only`, `unverified`).
- Artwork photographs may be CC-licensed while the artworks themselves are not; say which is which.
- Analytical claims (tropes, rhetorical functions) are agent-proposed until the researcher confirms them — mark them in `notes` and in the project description.

## Add a case

1. Create `knowledge/<case>/` with the three JSON files.
2. Run `python ../knowledge/build.py --case <case>`.
3. Add a case `README.md` documenting its sources, evidence state, and open questions.

## Read-back test

With the backend running, an OpenAI model answers questions from the saved graph:

```bash
cd graphloom/knowledge
python3 agent_read_test.py --case banksy --project-id <id>
```

The API key is read from `OPENAI_API_KEY` or `graphloom/.env` and is never printed. The questions are case-specific; edit the `QUESTION` in `agent_read_test.py` for a new case.
