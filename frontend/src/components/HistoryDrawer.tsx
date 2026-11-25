import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { useRevisions, useSnapshots } from "../api/hooks";
import type { ChangeSet, Diff } from "../api/types";
import ChangePreview from "./ChangePreview";

interface Props {
  token: string;
  projectId: string;
  currentRevision: number;
  onApplied: () => void;
}

function timeText(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").replace(/\..*$/, "");
}

export default function HistoryDrawer({
  token,
  projectId,
  currentRevision,
  onApplied,
}: Props) {
  const queryClient = useQueryClient();
  const revisionsQuery = useRevisions(token, projectId, true);
  const snapshotsQuery = useSnapshots(token, projectId, true);
  const [fromRevision, setFromRevision] = useState(Math.max(0, currentRevision - 1));
  const [toRevision, setToRevision] = useState(currentRevision);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [snapshotName, setSnapshotName] = useState("");
  const [preview, setPreview] = useState<ChangeSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const revisions = useMemo(
    () => [...(revisionsQuery.data?.revisions ?? [])].reverse(),
    [revisionsQuery.data],
  );
  const snapshots = snapshotsQuery.data?.snapshots ?? [];

  async function compare() {
    setBusy(true);
    setError(null);
    try {
      const response = await api.getDiff(token, projectId, fromRevision, toRevision);
      setDiff(response.diff as Diff);
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function createSnapshot() {
    if (!snapshotName.trim()) {
      setError("A snapshot name is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createSnapshot(token, projectId, snapshotName.trim(), currentRevision);
      setSnapshotName("");
      await queryClient.invalidateQueries({ queryKey: ["snapshots", projectId] });
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function previewRestore(revision: number, reason: string) {
    setBusy(true);
    setError(null);
    try {
      const prepared = await api.restoreRevisionPreview(token, projectId, revision, reason);
      setPreview(prepared);
      if (prepared.errors.length) {
        setError("The restore candidate has structural errors; it cannot be applied.");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function previewSnapshot(snapshotId: string, name: string) {
    setBusy(true);
    setError(null);
    try {
      const prepared = await api.restorePreview(
        token,
        projectId,
        snapshotId,
        `Restore snapshot '${name}'`,
      );
      setPreview(prepared);
      if (prepared.errors.length) {
        setError("The restore candidate has structural errors; it cannot be applied.");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function applyPreview() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      await api.commitChangeSet(token, projectId, preview.id, preview.base_revision);
      setPreview(null);
      onApplied();
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  if (preview) {
    return (
      <ChangePreview
        changeSet={preview}
        busy={busy}
        error={error}
        onApply={applyPreview}
        onDiscard={() => {
          setPreview(null);
          setError(null);
        }}
      />
    );
  }

  return (
    <div className="history-drawer">
      <section className="history-column">
        <div className="drawer-section-head">
          <h3>Committed revisions</h3>
          <span>{revisions.length}</span>
        </div>
        {currentRevision > 0 && (
          <button
            className="secondary compact"
            onClick={() =>
              previewRestore(
                Math.max(0, currentRevision - 1),
                `Restore revision ${Math.max(0, currentRevision - 1)}`,
              )
            }
            disabled={busy}
          >
            Preview restore of previous revision
          </button>
        )}
        <ul className="revision-list">
          {revisions.map((revision) => (
            <li key={revision.id}>
              <div>
                <strong>r{revision.revision}</strong>
                <span>{revision.actor}</span>
              </div>
              <p>{revision.reason || "No reason recorded."}</p>
              <span className="muted">{timeText(revision.created_at)}</span>
            </li>
          ))}
          {revisions.length === 0 && <li className="muted">No committed revisions yet.</li>}
        </ul>
      </section>

      <section className="history-column">
        <div className="drawer-section-head">
          <h3>Compare revisions</h3>
        </div>
        <div className="compare-controls">
          <label>
            From
            <select
              value={fromRevision}
              onChange={(event) => setFromRevision(Number(event.target.value))}
            >
              {Array.from({ length: currentRevision + 1 }, (_, index) => (
                <option key={index} value={index}>
                  r{index}
                </option>
              ))}
            </select>
          </label>
          <label>
            To
            <select
              value={toRevision}
              onChange={(event) => setToRevision(Number(event.target.value))}
            >
              {Array.from({ length: currentRevision + 1 }, (_, index) => (
                <option key={index} value={index}>
                  r{index}
                </option>
              ))}
            </select>
          </label>
          <button className="secondary compact" onClick={compare} disabled={busy}>
            Compare
          </button>
        </div>
        {diff && (
          <div className="diff-summary">
            <p>
              r{diff.from_revision} → r{diff.to_revision}: {diff.counts.added} added,{" "}
              {diff.counts.removed} removed, {diff.counts.changed} changed.
            </p>
            <ul>
              {diff.added.slice(0, 8).map((entry) => (
                <li key={`a-${entry.id}`}>+ {entry.label}</li>
              ))}
              {diff.removed.slice(0, 8).map((entry) => (
                <li key={`r-${entry.id}`}>− {entry.label}</li>
              ))}
              {diff.changed.slice(0, 8).map((entry) => (
                <li key={`c-${entry.id}`}>
                  ~ {entry.label}: {Object.keys(entry.fields).join(", ")}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="history-column">
        <div className="drawer-section-head">
          <h3>Named snapshots</h3>
          <span>{snapshots.length}</span>
        </div>
        <div className="snapshot-form">
          <input
            value={snapshotName}
            onChange={(event) => setSnapshotName(event.target.value)}
            placeholder={`Name revision ${currentRevision}`}
          />
          <button className="secondary compact" onClick={createSnapshot} disabled={busy}>
            Save snapshot
          </button>
        </div>
        <ul className="snapshot-list">
          {snapshots.map((snapshot) => (
            <li key={snapshot.id}>
              <div>
                <strong>{snapshot.name}</strong>
                <span className="revision-badge">r{snapshot.revision}</span>
              </div>
              <div className="snapshot-actions">
                <button
                  className="mini"
                  onClick={() => previewRestore(snapshot.revision, `Restore snapshot '${snapshot.name}'`)}
                  disabled={busy}
                >
                  Preview restore
                </button>
                <button
                  className="mini"
                  onClick={() => previewSnapshot(snapshot.id, snapshot.name)}
                  disabled={busy}
                >
                  Open snapshot preview
                </button>
              </div>
            </li>
          ))}
          {snapshots.length === 0 && <li className="muted">No snapshots saved.</li>}
        </ul>
      </section>

      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
