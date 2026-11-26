#!/usr/bin/env python3
"""Ask an OpenAI model to answer questions from a saved knowledge graph.

This proves a consuming agent can read the graph; it does not judge the quality
of the ontology. The API key is read from OPENAI_API_KEY or graphloom/.env and
is never printed. The questions are case-specific: edit QUESTION/CHECKS for a
new case.

The graph is serialized as a label-based summary (labels alongside ids, per the
reader contract) so the model can follow edges faithfully instead of guessing
from raw UUID JSON.

    cd graphloom/knowledge
    python3 agent_read_test.py --case banksy
    python3 agent_read_test.py --case banksy --project-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GRAPHLOOM_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = GRAPHLOOM_DIR / "knowledge"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_MODEL = "gpt-4o-mini"

QUESTION = (
    "Knowledge graph:\n"
    "{graph}\n\n"
    "Answer only from the graph above. Name the graph labels.\n"
    "1. Which artwork is sited at Frogmore Street, Bristol?\n"
    "2. Following the 'deploys' relation, which rhetorical trope does 'Well Hung Lover' deploy?\n"
    "3. Which installation is at Bristol Museum and Art Gallery?\n"
    "4. Which work is a mural by Tetoux appropriating Girl with Balloon?"
)
CHECKS = {
    "well_hung_lover": "Well Hung Lover",
    "irony": "Irony",
    "paint_pot_angel": "Paint Pot Angel",
    "tetoux": "Tetoux",
}


def summarize(objects: list[dict]) -> str:
    index = {obj["id"]: obj for obj in objects}

    def label(object_id: str) -> str:
        obj = index.get(object_id)
        if obj is None:
            return object_id[:8]
        return obj.get("label") or f"{obj['kind']} {object_id[:8]}"

    lines: list[str] = []
    classes = [obj["label"] for obj in objects if obj["kind"] == "class"]
    lines.append("Classes: " + "; ".join(classes))

    relation_types = [obj["label"] for obj in objects if obj["kind"] == "relation_type"]
    lines.append("Relation types: " + "; ".join(relation_types))

    attribute_types = [obj["label"] for obj in objects if obj["kind"] == "attribute_type"]
    lines.append("Attribute types: " + "; ".join(attribute_types))

    lines.append("Instances:")
    for obj in objects:
        if obj["kind"] != "instance":
            continue
        definition = obj.get("definition") or ""
        lines.append(f"- {obj['label']} ({obj['kind']})" + (f": {definition}" if definition else ""))

    lines.append("Relations:")
    for obj in objects:
        if obj["kind"] != "relation":
            continue
        relation_type = label(obj["relation_type_id"])
        lines.append(f"- {label(obj['source_id'])} --{relation_type}--> {label(obj['target_id'])}")

    lines.append("Attribute values:")
    for obj in objects:
        if obj["kind"] != "attribute_value":
            continue
        attribute = label(obj["attribute_type_id"])
        lines.append(f"- {label(obj['subject_id'])} .{attribute} = {obj['value']}")

    return "\n".join(lines)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {body[:400]}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach {url}: {exc.reason}") from exc


def post_json(url: str, payload: dict, api_key: str) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"OpenAI HTTP {exc.code}: {body[:600]}") from exc
    except URLError as exc:
        raise SystemExit(f"OpenAI unreachable: {exc.reason}") from exc


def pick_project(base_url: str, case: str, project_id: str | None) -> str:
    if project_id:
        return project_id
    ontology_path = KNOWLEDGE_DIR / case / "ontology.json"
    name = json.loads(ontology_path.read_text(encoding="utf-8"))["project"]["name"]
    projects = get_json(f"{base_url}/projects").get("projects", [])
    for project in projects:
        if project["name"] == name:
            return project["id"]
    raise SystemExit(f"No project named '{name}' found; pass --project-id.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="banksy")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    env = load_env(GRAPHLOOM_DIR / ".env")
    api_key = os.environ.get("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set (environment or graphloom/.env).")

    base_url = args.base_url.rstrip("/")
    project_id = pick_project(base_url, args.case, args.project_id)
    state = get_json(f"{base_url}/projects/{project_id}/state")
    objects = state["objects"]

    question = QUESTION.format(graph=summarize(objects))
    payload = {
        "model": args.model,
        "temperature": 0,
        "max_tokens": 600,
        "messages": [
            {
                "role": "system",
                "content": "You answer only from the provided knowledge graph. If something is absent, say 'not in graph'.",
            },
            {"role": "user", "content": question},
        ],
    }
    response = post_json("https://api.openai.com/v1/chat/completions", payload, api_key)
    answer = response["choices"][0]["message"]["content"]
    answer_lower = answer.lower()
    checks = {key: expected.lower() in answer_lower for key, expected in CHECKS.items()}
    result = {
        "model": args.model,
        "project_id": project_id,
        "object_count": len(objects),
        "answer": answer,
        "checks": checks,
        "passed": all(checks.values()),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
