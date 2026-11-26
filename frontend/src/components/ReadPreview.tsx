import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";

type ReadView = "object" | "state" | "schema" | "instances";

interface Props {
  projectId: string;
  selectedId: string | null;
}

const VIEWS: { value: ReadView; label: string }[] = [
  { value: "object", label: "Selected object" },
  { value: "state", label: "Full state" },
  { value: "schema", label: "Schema" },
  { value: "instances", label: "Instances page" },
];

export default function ReadPreview({ projectId, selectedId }: Props) {
  const [view, setView] = useState<ReadView>(selectedId ? "object" : "state");
  const [payload, setPayload] = useState<unknown>(null);
  const [endpoint, setEndpoint] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedId && view === "object") return;
    if (!selectedId && view === "object") setView("state");
  }, [selectedId, view]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (view === "object" && !selectedId) {
        setPayload(null);
        setEndpoint("");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        let next: unknown;
        let path: string;
        if (view === "object" && selectedId) {
          path = `/projects/${projectId}/objects/${selectedId}`;
          next = await api.getObject(projectId, selectedId);
        } else if (view === "schema") {
          path = `/projects/${projectId}/schema`;
          next = await api.getSchema(projectId);
        } else if (view === "instances") {
          path = `/projects/${projectId}/objects?kind=instance&limit=100`;
          next = await api.getObjects(projectId, { kind: "instance", limit: 100 });
        } else {
          path = `/projects/${projectId}/state`;
          next = await api.getState(projectId);
        }
        if (!cancelled) {
          setPayload(next);
          setEndpoint(path);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof ApiError
              ? `${caught.code}: ${caught.message}`
              : "Could not read the saved graph.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [projectId, selectedId, view]);

  return (
    <section className="read-preview" aria-label="Read preview">
      <div className="drawer-section-head">
        <h3>Reader view</h3>
      </div>
      <div className="read-tabs">
        {VIEWS.map((item) => (
          <button
            key={item.value}
            className={view === item.value ? "is-active" : ""}
            onClick={() => setView(item.value)}
            disabled={item.value === "object" && !selectedId}
          >
            {item.label}
          </button>
        ))}
      </div>
      <p className="fine-print">
        This preview calls the actual read endpoints, not a separately maintained sample. Unsaved
        forms and layouts are excluded.
      </p>
      {endpoint && <code className="endpoint-line">GET /api/v1{endpoint}</code>}
      {loading && <p className="muted">Reading…</p>}
      {error && <p className="form-error">{error}</p>}
      {payload !== null && <pre className="read-json">{JSON.stringify(payload, null, 2)}</pre>}
    </section>
  );
}
