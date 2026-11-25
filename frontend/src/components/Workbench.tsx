import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  deriveValueType,
  draftToCreateData,
  draftToUpdateFields,
  validateDraft,
} from "../api/draft";
import { ApiError, api } from "../api/client";
import {
  invalidateProject,
  useGraphState,
  useLayout,
  useProject,
  useSchema,
} from "../api/hooks";
import type {
  Capabilities,
  ChangeSet,
  GraphObject,
  Impacted,
  Kind,
  Warning,
} from "../api/types";
import {
  buildInstanceProjection,
  buildModelProjection,
  objectLabel,
} from "../projections/graph";
import { useUI } from "../store/ui";
import ChangePreview from "./ChangePreview";
import ConnectionPanel from "./ConnectionPanel";
import Explorer from "./Explorer";
import GraphCanvas, { GraphCanvasHandle } from "./GraphCanvas";
import HistoryDrawer from "./HistoryDrawer";
import Inspector from "./Inspector";
import ReadPreview from "./ReadPreview";
import TableView from "./TableView";

interface Props {
  token: string;
  projectId: string;
  capabilities: Capabilities;
  onBack: () => void;
  onDisconnect: () => void;
}

function formatIssues(issues: Warning[]): string {
  return issues
    .slice(0, 4)
    .map((issue) => {
      const location = issue.object_id ? ` [${issue.object_id.slice(0, 8)}]` : "";
      return `${issue.code}${location}: ${issue.message}`;
    })
    .join("\n");
}

function download(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function Workbench({
  token,
  projectId,
  capabilities,
  onBack,
  onDisconnect,
}: Props) {
  const queryClient = useQueryClient();
  const projectQuery = useProject(token, projectId);
  const revision = projectQuery.data?.current_revision;
  const stateQuery = useGraphState(token, projectId, revision);
  const schemaQuery = useSchema(token, projectId, revision);
  const layoutQuery = useLayout(token, projectId);

  const ui = useUI();
  const {
    mode,
    view,
    selectedId,
    selectedClassId,
    drawer,
    draft,
    linkMode,
    linkSource,
    notice,
    setMode,
    setView,
    setDrawer,
    select,
    selectClass,
    startCreate,
    startEdit,
    updateDraft,
    clearDraft,
    setDraftBaseRevision,
    setLinkMode,
    setLinkSource,
    setNotice,
  } = ui;

  const state = stateQuery.data;
  const schema = schemaQuery.data;
  const project = projectQuery.data;
  const objects = state?.objects ?? [];

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preparedWarnings, setPreparedWarnings] = useState<Warning[]>([]);
  const [impact, setImpact] = useState<Impacted | null>(null);
  const [preview, setPreview] = useState<ChangeSet | null>(null);
  const [conflict, setConflict] = useState<{ expected: number; current: number } | null>(
    null,
  );
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [layoutVersion, setLayoutVersion] = useState(0);
  const layoutVersionRef = useRef(0);
  const positionsRef = useRef<Record<string, { x: number; y: number }>>({});
  const viewportRef = useRef<{ zoom: number; pan: { x: number; y: number } } | null>(null);
  const layoutInitialized = useRef(false);
  const saveTimer = useRef<number | null>(null);
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const previousRevision = useRef<number | undefined>(undefined);

  useEffect(() => {
    positionsRef.current = positions;
  }, [positions]);

  useEffect(() => {
    if (!layoutQuery.data || layoutInitialized.current) return;
    layoutInitialized.current = true;
    const data = layoutQuery.data.data;
    setPositions(data.positions ?? {});
    positionsRef.current = data.positions ?? {};
    viewportRef.current = data.viewport ?? null;
    layoutVersionRef.current = layoutQuery.data.version;
    setLayoutVersion(layoutQuery.data.version);
  }, [layoutQuery.data]);

  useEffect(
    () => () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    },
    [],
  );

  const scheduleLayoutSave = useCallback(
    (
      nextPositions: Record<string, { x: number; y: number }>,
      nextViewport?: { zoom: number; pan: { x: number; y: number } } | null,
    ) => {
      positionsRef.current = nextPositions;
      setPositions(nextPositions);
      if (nextViewport) viewportRef.current = nextViewport;
      if (!layoutInitialized.current) return;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(async () => {
        try {
          const response = await api.putLayout(
            token,
            projectId,
            layoutVersionRef.current,
            {
              positions: positionsRef.current,
              viewport: viewportRef.current,
            },
          );
          layoutVersionRef.current = response.version;
          setLayoutVersion(response.version);
        } catch (caught) {
          if (caught instanceof ApiError && caught.code === "layout_conflict") {
            const currentVersion = Number(
              (caught.details as { current_version?: number }).current_version ??
                layoutVersionRef.current,
            );
            layoutVersionRef.current = currentVersion;
            setLayoutVersion(currentVersion);
            setNotice(
              "Layout changed in another session; the version was refreshed but this view was not overwritten. Move a node or run Layout to save this view.",
            );
          }
        }
      }, 650);
    },
    [token, projectId, setNotice],
  );

  useEffect(() => {
    if (revision === undefined) return;
    if (
      previousRevision.current !== undefined &&
      previousRevision.current !== revision &&
      draft?.dirty
    ) {
      setNotice(
        `The graph advanced to revision ${revision}. Your draft is preserved; saving will not silently overwrite the other change.`,
      );
    }
    previousRevision.current = revision;
  }, [revision, draft?.dirty, setNotice]);

  const projection = useMemo(() => {
    if (mode === "model") return buildModelProjection(objects);
    return buildInstanceProjection(objects, selectedClassId);
  }, [objects, mode, selectedClassId]);

  const projectionKey = `${mode}:${selectedClassId ?? "all"}`;
  const selected = objects.find((object) => object.id === selectedId) ?? null;
  const warningTarget = draft?.id ?? selectedId;
  const selectedWarnings =
    schema?.warnings.filter((warning) => warning.object_id === warningTarget) ?? [];

  const revisionAdvanced =
    draft && revision !== undefined && draft.baseRevision !== revision
      ? { expected: draft.baseRevision, current: revision }
      : null;
  const activeConflict = conflict ?? revisionAdvanced;

  function resetMessages() {
    setError(null);
    setConflict(null);
    setPreparedWarnings([]);
  }

  async function saveDraft() {
    if (!draft || revision === undefined) return;
    const valueType =
      draft.kind === "attribute_value"
        ? deriveValueType(draft.values, state?.objects ?? [])
        : "string";
    const validation = validateDraft(draft.kind, draft.values, valueType);
    if (validation) {
      setError(validation);
      return;
    }

    let operations: unknown[];
    if (draft.mode === "create") {
      operations = [
        {
          op: "create",
          ref: `new:${draft.kind}`,
          kind: draft.kind,
          data: draftToCreateData(draft.kind, draft.values, valueType),
        },
      ];
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
      operations = [{ op: "update", id: draft.id, fields }];
    }

    setBusy(true);
    resetMessages();
    try {
      const prepared = await api.prepareChangeSet(token, projectId, {
        base_revision: draft.baseRevision,
        reason: `${draft.mode} ${draft.kind}`,
        operations,
      });
      setPreparedWarnings(prepared.warnings);
      if (prepared.status === "invalid" || prepared.errors.length > 0) {
        setPreview(prepared);
        setError(formatIssues(prepared.errors));
        setDrawer("changes");
        return;
      }
      const result = await api.commitChangeSet(
        token,
        projectId,
        prepared.id,
        prepared.base_revision,
      );
      invalidateProject(queryClient, projectId);
      setImpact(prepared.impacted);
      const createdId =
        draft.mode === "create"
          ? Object.values(prepared.id_map)[0]
          : draft.id;
      clearDraft();
      if (createdId) select(createdId);
      setNotice(
        `Saved to revision ${result.revision}${result.changed ? "" : " (no semantic change)"}.`,
      );
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "revision_conflict") {
        const details = caught.details as {
          expected_revision?: number;
          current_revision?: number;
        };
        setConflict({
          expected: details.expected_revision ?? draft.baseRevision,
          current: details.current_revision ?? revision,
        });
        setNotice("Revision conflict: the draft was preserved and not committed.");
      } else if (caught instanceof ApiError && caught.code === "invalid_change_set") {
        setError(formatIssues((caught.details.errors as Warning[]) ?? []));
      } else if (caught instanceof ApiError) {
        setError(`${caught.code}: ${caught.message}`);
      } else {
        setError(String(caught));
      }
    } finally {
      setBusy(false);
    }
  }

  async function deleteObject(object: GraphObject) {
    if (revision === undefined) return;
    setBusy(true);
    resetMessages();
    try {
      const prepared = await api.prepareChangeSet(token, projectId, {
        base_revision: revision,
        reason: `Delete ${object.kind}`,
        operations: [{ op: "delete", id: object.id }],
      });
      if (prepared.status === "invalid" || prepared.errors.length > 0) {
        setPreview(prepared);
        setError(formatIssues(prepared.errors));
        setDrawer("changes");
        return;
      }
      const result = await api.commitChangeSet(
        token,
        projectId,
        prepared.id,
        prepared.base_revision,
      );
      invalidateProject(queryClient, projectId);
      if (selectedId === object.id) select(null);
      setImpact(prepared.impacted);
      setNotice(`Deleted ${objectLabel(object)} at revision ${result.revision}.`);
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function toggleLifecycle(object: GraphObject) {
    if (revision === undefined) return;
    setBusy(true);
    resetMessages();
    const next = object.lifecycle === "active" ? "deprecated" : "active";
    try {
      const prepared = await api.prepareChangeSet(token, projectId, {
        base_revision: revision,
        reason: `${next === "deprecated" ? "Deprecate" : "Restore"} ${object.kind}`,
        operations: [
          { op: "update", id: object.id, fields: { lifecycle: next } },
        ],
      });
      if (prepared.status === "invalid" || prepared.errors.length > 0) {
        setError(formatIssues(prepared.errors));
        return;
      }
      const result = await api.commitChangeSet(
        token,
        projectId,
        prepared.id,
        prepared.base_revision,
      );
      invalidateProject(queryClient, projectId);
      setNotice(
        `${next === "deprecated" ? "Deprecated" : "Restored"} ${objectLabel(object)} at revision ${result.revision}.`,
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  function beginCreate(kind: Kind) {
    if (revision === undefined) return;
    if (draft?.dirty) {
      setNotice("Save or discard the current draft before creating another object.");
      return;
    }
    resetMessages();
    startCreate(kind, revision);
  }

  function beginEdit(object: GraphObject) {
    if (revision === undefined) return;
    if (draft?.dirty) {
      setNotice("Save or discard the current draft before editing another object.");
      return;
    }
    resetMessages();
    startEdit(object, revision);
  }

  function beginRelation(sourceId?: string) {
    if (revision === undefined) return;
    if (draft?.dirty) {
      setNotice("Save or discard the current draft first.");
      return;
    }
    resetMessages();
    startCreate("relation", revision, {
      source_id: sourceId ?? (selected?.kind === "instance" ? selected.id : ""),
    });
  }

  function beginAttribute(subjectId?: string) {
    if (revision === undefined) return;
    if (draft?.dirty) {
      setNotice("Save or discard the current draft first.");
      return;
    }
    resetMessages();
    startCreate("attribute_value", revision, {
      subject_id: subjectId ?? (selected?.kind === "instance" ? selected.id : ""),
    });
  }

  function handleLinkNode(id: string) {
    if (!revision) return;
    if (!linkSource) {
      setLinkSource(id);
      setNotice("Source instance selected. Now select the target instance.");
      return;
    }
    if (linkSource === id) {
      setLinkSource(null);
      return;
    }
    if (draft?.dirty) {
      setNotice("Save or discard the current draft first.");
      setLinkMode(false);
      return;
    }
    resetMessages();
    startCreate("relation", revision, {
      source_id: linkSource,
      target_id: id,
    });
    setLinkMode(false);
    setLinkSource(null);
  }

  function toggleLinkMode() {
    if (linkMode) {
      setLinkMode(false);
      setNotice(null);
    } else {
      if (draft?.dirty) {
        setNotice("Save or discard the current draft first.");
        return;
      }
      setLinkMode(true);
      setNotice("Select the source instance, then the target instance.");
    }
  }

  async function applyPreview() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.commitChangeSet(
        token,
        projectId,
        preview.id,
        preview.base_revision,
      );
      invalidateProject(queryClient, projectId);
      setImpact(preview.impacted);
      setPreview(null);
      setDrawer(null);
      setNotice(`Applied change set at revision ${result.revision}.`);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(`${caught.code}: ${caught.message}`);
      } else {
        setError(String(caught));
      }
    } finally {
      setBusy(false);
    }
  }

  async function exportNative() {
    try {
      const payload = await api.exportNative(token, projectId, revision, true);
      download(
        `${project?.name ?? "graphloom"}-r${revision ?? 0}.json`,
        JSON.stringify(payload, null, 2),
        "application/json",
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    }
  }

  async function exportTurtle() {
    try {
      const payload = await api.exportTurtle(token, projectId, revision);
      download(
        `${project?.name ?? "graphloom"}-r${revision ?? 0}.ttl`,
        payload,
        "text/turtle",
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    }
  }

  async function importFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const text = await file.text();
      const payload = JSON.parse(text);
      const prepared = await api.importPreview(token, projectId, payload);
      setPreview(prepared);
      setDrawer("changes");
      if (prepared.errors.length) setError(formatIssues(prepared.errors));
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(`${caught.code}: ${caught.message}`);
      } else if (caught instanceof SyntaxError) {
        setError("The selected file is not valid JSON.");
      } else {
        setError(String(caught));
      }
    } finally {
      setBusy(false);
    }
  }

  function reformatNotice() {
    if (!activeConflict) return null;
    return (
      <div className="banner conflict" role="alert">
        <div>
          <strong>Revision conflict.</strong> Draft base is r{activeConflict.expected};
          current graph is r{activeConflict.current}. No automatic rebase is performed.
        </div>
        <div className="banner-actions">
          <button
            className="secondary compact"
            onClick={() => {
              setDraftBaseRevision(activeConflict.current);
              setConflict(null);
              setNotice("Draft rebased onto the current revision. Review the fields before saving.");
            }}
          >
            Rebase draft
          </button>
          <button
            className="ghost compact"
            onClick={() => {
              clearDraft();
              setConflict(null);
              setNotice("Draft discarded.");
            }}
          >
            Discard draft
          </button>
        </div>
      </div>
    );
  }

  if (projectQuery.isLoading || stateQuery.isLoading || schemaQuery.isLoading) {
    return <main className="loading-screen">Loading the saved graph…</main>;
  }
  if (projectQuery.error || stateQuery.error || schemaQuery.error) {
    const caught = projectQuery.error ?? stateQuery.error ?? schemaQuery.error;
    return (
      <main className="loading-screen">
        <h1>Could not open the project</h1>
        <p>{caught instanceof Error ? caught.message : String(caught)}</p>
        <button className="primary" onClick={onBack}>Back to projects</button>
      </main>
    );
  }
  if (!project || !state || !schema) return null;

  const drawerTitle =
    drawer === "history"
      ? "History and snapshots"
      : drawer === "changes"
        ? "Pending change"
        : drawer === "read"
          ? "Read access"
          : "";

  return (
    <div className="workbench">
      <header className="workbench-header">
        <div className="header-left">
          <button className="ghost compact" onClick={onBack}>
            ← Projects
          </button>
          <div>
            <h1>{project.name}</h1>
            {project.description && <p>{project.description}</p>}
          </div>
        </div>
        <div className="header-meta">
          <span className="revision-badge">r{revision}</span>
          <span className="role-badge">{capabilities.role}</span>
          <div className="segmented" role="group" aria-label="Graph mode">
            <button
              className={mode === "model" ? "is-active" : ""}
              onClick={() => setMode("model")}
            >
              Model
            </button>
            <button
              className={mode === "instance" ? "is-active" : ""}
              onClick={() => setMode("instance")}
            >
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
          <button className="ghost compact" onClick={() => setDrawer("history")}>
            History
          </button>
          <button className="ghost compact" onClick={() => setDrawer("changes")}>
            Changes{preview ? ` (${preview.diff.counts.added + preview.diff.counts.removed + preview.diff.counts.changed})` : ""}
          </button>
          <button className="ghost compact" onClick={() => setDrawer("read")}>
            Read access
          </button>
          <button className="ghost compact" onClick={onDisconnect}>
            Disconnect
          </button>
        </div>
      </header>

      {reformatNotice()}
      {notice && (
        <div className="banner info">
          <span>{notice}</span>
          <button className="ghost compact" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {error && (
        <div className="banner error" role="alert">
          <span style={{ whiteSpace: "pre-line" }}>{error}</span>
          <button className="ghost compact" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}
      {impact && (
        <div className="banner impact">
          <span>
            Impact of the last save: {impact.instance_ids.length} instance(s),{" "}
            {impact.assertion_ids.length} assertion(s); warnings {impact.warning_counts.before} →{" "}
            {impact.warning_counts.after}.
          </span>
          <button className="ghost compact" onClick={() => setImpact(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="workbench-body">
        <Explorer
          state={state}
          mode={mode}
          selectedId={selectedId}
          selectedClassId={selectedClassId}
          disabled={Boolean(draft?.dirty)}
          onSelect={select}
          onSelectClass={selectClass}
          onCreate={beginCreate}
        />

        <main className="canvas-column">
          <div className="canvas-toolbar">
            <div className="toolbar-group">
              <button className="secondary compact" onClick={() => canvasRef.current?.fit()}>
                Fit
              </button>
              <button className="secondary compact" onClick={() => canvasRef.current?.runLayout()}>
                Layout
              </button>
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
              <span className="muted">
                {projection.nodeCount} nodes · {projection.edgeCount} edges
              </span>
              <button className="ghost compact" onClick={exportNative}>
                Export JSON
              </button>
              <button className="ghost compact" onClick={exportTurtle}>
                Export Turtle
              </button>
              <label className="button-like compact">
                Import JSON
                <input
                  type="file"
                  accept="application/json,.json"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void importFile(file);
                    event.target.value = "";
                  }}
                />
              </label>
            </div>
          </div>

          {projection.hiddenCount > 0 && (
            <div className="truncation-banner">
              {projection.hiddenCount} object(s) are hidden by the current projection. The
              read API remains available for the full saved state.
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
          preparedWarnings={preparedWarnings}
          busy={busy}
          error={error}
          onEdit={() => {
            if (selected) beginEdit(selected);
          }}
          onUpdateDraft={updateDraft}
          onSave={saveDraft}
          onCancel={clearDraft}
          onDelete={deleteObject}
          onLifecycle={toggleLifecycle}
          onAddRelation={beginRelation}
          onAddAttribute={beginAttribute}
          onSelect={select}
        />
      </div>

      {drawer && (
        <section className="drawer" aria-label={drawerTitle}>
          <header className="drawer-header">
            <h2>{drawerTitle}</h2>
            <button className="ghost compact" onClick={() => setDrawer(null)}>
              Close
            </button>
          </header>
          <div className="drawer-body">
            {drawer === "history" && (
              <HistoryDrawer
                token={token}
                projectId={projectId}
                currentRevision={revision ?? 0}
                onApplied={() => {
                  invalidateProject(queryClient, projectId);
                  setDrawer(null);
                  setNotice("Restored state as a new revision.");
                }}
              />
            )}
            {drawer === "changes" && (
              <>
                {preview ? (
                  <ChangePreview
                    changeSet={preview}
                    busy={busy}
                    error={error}
                    onApply={applyPreview}
                    onDiscard={() => {
                      setPreview(null);
                      setError(null);
                      setDrawer(null);
                    }}
                  />
                ) : (
                  <div className="empty-drawer">
                    <p>
                      No pending preview. Importing native JSON or restoring a snapshot
                      prepares a replacement change set here before anything is committed.
                    </p>
                    <p className="muted">
                      Ordinary form saves prepare and commit in one step; destructive bulk
                      replacements are previewed first.
                    </p>
                  </div>
                )}
              </>
            )}
            {drawer === "read" && (
              <div className="read-drawer">
                <ConnectionPanel token={token} projectId={projectId} />
                <ReadPreview
                  token={token}
                  projectId={projectId}
                  revision={revision ?? 0}
                  selectedId={selectedId}
                />
              </div>
            )}
          </div>
        </section>
      )}

      <footer className="workbench-footer">
        <span>
          Graphloom stores the canonical graph in SQLite. Canvas positions are saved
          separately and never advance the semantic revision.
        </span>
        <span>layout v{layoutVersion}</span>
      </footer>
    </div>
  );
}
