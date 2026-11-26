import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  defaultValues,
  deriveValueType,
  draftToCreateData,
  draftToUpdateFields,
  validateDraft,
  valuesFromObject,
} from "../api/draft";
import { ApiError, api } from "../api/client";
import type {
  GraphObject,
  GraphState,
  Kind,
  Operation,
  ProjectSummary,
  SchemaResponse,
  Warning,
} from "../api/types";
import {
  buildInstanceProjection,
  buildModelProjection,
  objectLabel,
} from "../projections/graph";
import type { Draft, Mode, View } from "../ui";
import ConnectionPanel from "./ConnectionPanel";
import Explorer from "./Explorer";
import GraphCanvas, { GraphCanvasHandle } from "./GraphCanvas";
import Inspector from "./Inspector";
import ReadPreview from "./ReadPreview";
import TableView from "./TableView";

interface Props {
  projectId: string;
  onBack: () => void;
}

function formatError(caught: unknown): string {
  if (caught instanceof ApiError) {
    const errors = (caught.details as { errors?: Warning[] }).errors;
    if (errors && errors.length) {
      return errors
        .slice(0, 5)
        .map((issue) => `${issue.code}: ${issue.message}`)
        .join("\n");
    }
    return `${caught.code}: ${caught.message}`;
  }
  return String(caught);
}

export default function Workbench({ projectId, onBack }: Props) {
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [state, setState] = useState<GraphState | null>(null);
  const [schema, setSchema] = useState<SchemaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [fatal, setFatal] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>("model");
  const [view, setView] = useState<View>("graph");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [linkMode, setLinkMode] = useState(false);
  const [linkSource, setLinkSource] = useState<string | null>(null);
  const [showRead, setShowRead] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const positionsRef = useRef<Record<string, { x: number; y: number }>>({});
  const viewportRef = useRef<{ zoom: number; pan: { x: number; y: number } } | null>(null);
  const saveTimer = useRef<number | null>(null);
  const layoutReady = useRef(false);
  const canvasRef = useRef<GraphCanvasHandle>(null);

  const refresh = useCallback(async () => {
    const [nextProject, nextState, nextSchema] = await Promise.all([
      api.getProject(projectId),
      api.getState(projectId),
      api.getSchema(projectId),
    ]);
    setProject(nextProject);
    setState(nextState);
    setSchema(nextSchema);
  }, [projectId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [nextProject, nextState, nextSchema, layout] = await Promise.all([
          api.getProject(projectId),
          api.getState(projectId),
          api.getSchema(projectId),
          api.getLayout(projectId),
        ]);
        if (cancelled) return;
        setProject(nextProject);
        setState(nextState);
        setSchema(nextSchema);
        setPositions(layout.data.positions ?? {});
        positionsRef.current = layout.data.positions ?? {};
        viewportRef.current = layout.data.viewport ?? null;
        layoutReady.current = true;
      } catch (caught) {
        if (!cancelled) setFatal(formatError(caught));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [projectId]);

  // Poll the project version while the tab is visible. A new version reloads
  // the graph unless an unsaved draft is open.
  const currentVersion = project?.version;
  const hasDraft = draft !== null;
  useEffect(() => {
    if (currentVersion === undefined) return;
    const timer = window.setInterval(async () => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;
      try {
        const latest = await api.getProject(projectId);
        if (latest.version === currentVersion) return;
        if (hasDraft) {
          setNotice(
            `The graph advanced to v${latest.version} elsewhere. Your draft is preserved; save or discard it first.`,
          );
          return;
        }
        const [nextState, nextSchema] = await Promise.all([
          api.getState(projectId),
          api.getSchema(projectId),
        ]);
        setProject(latest);
        setState(nextState);
        setSchema(nextSchema);
      } catch {
        // transient polling errors are ignored; the next tick retries
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [projectId, currentVersion, hasDraft]);

  const scheduleLayoutSave = useCallback(
    (
      nextPositions: Record<string, { x: number; y: number }>,
      nextViewport?: { zoom: number; pan: { x: number; y: number } } | null,
    ) => {
      positionsRef.current = nextPositions;
      setPositions(nextPositions);
      if (nextViewport) viewportRef.current = nextViewport;
      if (!layoutReady.current) return;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => {
        void api
          .putLayout(projectId, {
            positions: positionsRef.current,
            viewport: viewportRef.current ?? undefined,
          })
          .catch(() => undefined);
      }, 650);
    },
    [projectId],
  );

  const objects = state?.objects ?? [];
  const projection = useMemo(() => {
    if (mode === "model") return buildModelProjection(objects);
    return buildInstanceProjection(objects, selectedClassId);
  }, [objects, mode, selectedClassId]);

  const projectionKey = `${mode}:${selectedClassId ?? "all"}`;
  const selected = objects.find((object) => object.id === selectedId) ?? null;
  const warningTarget = draft?.id ?? selectedId;
  const selectedWarnings =
    schema?.warnings.filter((warning) => warning.object_id === warningTarget) ?? [];

  function resetMessages() {
    setError(null);
    setNotice(null);
  }

  function select(id: string | null) {
    if (draft) {
      setNotice("Save or discard the current draft before selecting another object.");
      return;
    }
    setSelectedId(id);
    resetMessages();
  }

  function selectClass(id: string | null) {
    setSelectedClassId(id);
    setSelectedId(null);
    setDraft(null);
  }

  function beginCreate(kind: Kind, initial: Record<string, unknown> = {}) {
    if (draft) {
      setNotice("Save or discard the current draft before creating another object.");
      return;
    }
    resetMessages();
    setDraft({
      mode: "create",
      kind,
      values: { ...defaultValues(kind), ...initial },
      original: null,
    });
    setSelectedId(null);
  }

  function beginEdit(object: GraphObject) {
    if (draft) {
      setNotice("Save or discard the current draft before editing another object.");
      return;
    }
    resetMessages();
    setDraft({
      mode: "edit",
      kind: object.kind,
      id: object.id,
      values: valuesFromObject(object),
      original: valuesFromObject(object),
    });
    setSelectedId(object.id);
  }

  function updateDraft(field: string, value: unknown) {
    setDraft((current) =>
      current ? { ...current, values: { ...current.values, [field]: value } } : current,
    );
  }

  async function saveDraft() {
    if (!draft) return;
    const valueType =
      draft.kind === "attribute_value"
        ? deriveValueType(draft.values, objects)
        : "string";
    const validation = validateDraft(draft.kind, draft.values, valueType);
    if (validation) {
      setError(validation);
      return;
    }

    let operation: Operation;
    if (draft.mode === "create") {
      operation = {
        op: "create",
        ref: `new:${draft.kind}`,
        kind: draft.kind,
        data: draftToCreateData(draft.kind, draft.values, valueType),
      };
    } else {
      const fields = draftToUpdateFields(
        draft.kind,
        draft.values,
        draft.original ?? {},
        valueType,
      );
      if (Object.keys(fields).length === 0) {
        setNotice("No changes to save.");
        return;
      }
      operation = { op: "update", id: draft.id as string, fields };
    }

    setBusy(true);
    setError(null);
    try {
      const result = await api.applyBatch(projectId, [operation]);
      await refresh();
      const createdId =
        draft.mode === "create" ? Object.values(result.id_map)[0] : draft.id;
      setDraft(null);
      if (createdId) setSelectedId(createdId);
      setNotice(`Saved at version ${result.version}.`);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function deleteObject(object: GraphObject) {
    setBusy(true);
    resetMessages();
    try {
      const result = await api.applyBatch(projectId, [{ op: "delete", id: object.id }]);
      await refresh();
      if (selectedId === object.id) setSelectedId(null);
      setNotice(`Deleted ${objectLabel(object)} at version ${result.version}.`);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus(object: GraphObject) {
    setBusy(true);
    resetMessages();
    const next = object.status === "active" ? "deprecated" : "active";
    try {
      const result = await api.applyBatch(projectId, [
        { op: "update", id: object.id, fields: { status: next } },
      ]);
      await refresh();
      setNotice(
        `${next === "deprecated" ? "Deprecated" : "Restored"} ${objectLabel(object)} at version ${result.version}.`,
      );
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  function beginRelation(sourceId?: string) {
    startCreate("relation", {
      source_id: sourceId ?? (selected?.kind === "instance" ? selected.id : ""),
    });
  }

  function beginAttribute(subjectId?: string) {
    startCreate("attribute_value", {
      subject_id: subjectId ?? (selected?.kind === "instance" ? selected.id : ""),
    });
  }

  function startCreate(kind: Kind, initial: Record<string, unknown>) {
    if (draft) {
      setNotice("Save or discard the current draft first.");
      return;
    }
    resetMessages();
    setDraft({ mode: "create", kind, values: { ...defaultValues(kind), ...initial }, original: null });
    setSelectedId(null);
  }

  function toggleLinkMode() {
    if (linkMode) {
      setLinkMode(false);
      setLinkSource(null);
      setNotice(null);
      return;
    }
    if (draft) {
      setNotice("Save or discard the current draft first.");
      return;
    }
    setLinkMode(true);
    setLinkSource(null);
    setNotice("Select the source instance, then the target instance.");
  }

  function handleLinkNode(id: string) {
    if (!linkSource) {
      setLinkSource(id);
      setNotice("Source instance selected. Now select the target instance.");
      return;
    }
    if (linkSource === id) {
      setLinkSource(null);
      return;
    }
    const source = linkSource;
    setLinkMode(false);
    setLinkSource(null);
    startCreate("relation", { source_id: source, target_id: id });
  }

  if (loading) {
    return <main className="loading-screen">Loading the saved graph…</main>;
  }
  if (fatal || !project || !state || !schema) {
    return (
      <main className="loading-screen">
        <h1>Could not open the project</h1>
        <p>{fatal ?? "The project could not be loaded."}</p>
        <button className="primary" onClick={onBack}>Back to projects</button>
      </main>
    );
  }

  return (
    <div className="workbench">
      <header className="workbench-header">
        <div className="header-left">
          <button className="ghost compact" onClick={onBack}>← Projects</button>
          <div>
            <h1>{project.name}</h1>
            {project.description && <p>{project.description}</p>}
          </div>
        </div>
        <div className="header-meta">
          <span className="revision-badge">v{project.version}</span>
          <div className="segmented" role="group" aria-label="Graph mode">
            <button className={mode === "model" ? "is-active" : ""} onClick={() => setMode("model")}>
              Model
            </button>
            <button className={mode === "instance" ? "is-active" : ""} onClick={() => setMode("instance")}>
              Instances
            </button>
          </div>
          <div className="segmented" role="group" aria-label="View">
            <button className={view === "graph" ? "is-active" : ""} onClick={() => setView("graph")}>
              Graph
            </button>
            <button className={view === "table" ? "is-active" : ""} onClick={() => setView("table")}>
              Table
            </button>
          </div>
          <button className="ghost compact" onClick={() => setShowRead((value) => !value)}>
            {showRead ? "Hide read access" : "Read access"}
          </button>
        </div>
      </header>

      {notice && (
        <div className="banner info">
          <span>{notice}</span>
          <button className="ghost compact" onClick={() => setNotice(null)}>Dismiss</button>
        </div>
      )}
      {error && (
        <div className="banner error" role="alert">
          <span style={{ whiteSpace: "pre-line" }}>{error}</span>
          <button className="ghost compact" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="workbench-body">
        <Explorer
          state={state}
          mode={mode}
          selectedId={selectedId}
          selectedClassId={selectedClassId}
          disabled={Boolean(draft)}
          onSelect={select}
          onSelectClass={selectClass}
          onCreate={(kind) => beginCreate(kind)}
        />

        <main className="canvas-column">
          <div className="canvas-toolbar">
            <div className="toolbar-group">
              <button className="secondary compact" onClick={() => canvasRef.current?.fit()}>Fit</button>
              <button className="secondary compact" onClick={() => canvasRef.current?.runLayout()}>Layout</button>
              {mode === "instance" && (
                <button
                  className={`secondary compact ${linkMode ? "is-active" : ""}`}
                  onClick={toggleLinkMode}
                >
                  {linkMode ? "Cancel connect" : "Connect instances"}
                </button>
              )}
            </div>
            <div className="toolbar-group">
              <span className="muted">{projection.nodeCount} nodes · {projection.edgeCount} edges</span>
            </div>
          </div>

          {projection.hiddenCount > 0 && (
            <div className="truncation-banner">
              {projection.hiddenCount} object(s) are hidden by the current projection. The read API
              still exposes the full saved state.
            </div>
          )}

          {view === "graph" ? (
            <GraphCanvas
              ref={canvasRef}
              elements={projection.elements}
              positions={positions}
              selectedId={selectedId}
              linkMode={linkMode}
              linkSource={linkSource}
              autoLayout={Object.keys(positions).length === 0}
              projectionKey={projectionKey}
              onSelect={select}
              onEdit={(id) => {
                const object = objects.find((item) => item.id === id);
                if (object) beginEdit(object);
              }}
              onPositions={(next) => scheduleLayoutSave(next)}
              onViewport={(next) => scheduleLayoutSave(positionsRef.current, next)}
              onLinkNode={handleLinkNode}
            />
          ) : (
            <TableView
              objects={objects}
              selectedId={selectedId}
              warnings={schema.warnings}
              onSelect={select}
              onEdit={beginEdit}
            />
          )}
        </main>

        <Inspector
          state={state}
          schema={schema}
          selected={selected}
          draft={draft}
          warnings={selectedWarnings}
          busy={busy}
          error={error}
          onEdit={() => {
            if (selected) beginEdit(selected);
          }}
          onUpdateDraft={updateDraft}
          onSave={saveDraft}
          onCancel={() => {
            setDraft(null);
            setError(null);
          }}
          onDelete={deleteObject}
          onToggleStatus={toggleStatus}
          onAddRelation={beginRelation}
          onAddAttribute={beginAttribute}
          onSelect={(id) => select(id)}
        />
      </div>

      {showRead && (
        <section className="drawer" aria-label="Read access">
          <header className="drawer-header">
            <h2>Read access</h2>
            <button className="ghost compact" onClick={() => setShowRead(false)}>Close</button>
          </header>
          <div className="drawer-body read-drawer">
            <ConnectionPanel projectId={projectId} version={project.version} />
            <ReadPreview projectId={projectId} selectedId={selectedId} />
          </div>
        </section>
      )}

      <footer className="workbench-footer">
        <span>
          The graph is saved as one JSON file per project. Canvas positions are saved separately and
          never change the graph an agent reads.
        </span>
        <span>v{project.version}</span>
      </footer>
    </div>
  );
}
