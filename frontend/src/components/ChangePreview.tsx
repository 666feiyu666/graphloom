import type { ChangeSet, Warning } from "../api/types";

interface Props {
  changeSet: ChangeSet;
  busy: boolean;
  error: string | null;
  onApply: () => void;
  onDiscard: () => void;
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") {
    return value.length > 240 ? `${value.slice(0, 240)}…` : value;
  }
  const encoded = JSON.stringify(value);
  return encoded.length > 240 ? `${encoded.slice(0, 240)}…` : encoded;
}

function IssueList({ issues, tone }: { issues: Warning[]; tone: "error" | "warning" }) {
  if (!issues.length) return null;
  return (
    <ul className={`issue-list ${tone}`}>
      {issues.map((issue, index) => (
        <li key={`${issue.code}-${issue.object_id}-${index}`}>
          <strong>{issue.code}</strong> {issue.message}
          {issue.object_id && <code>{issue.object_id}</code>}
        </li>
      ))}
    </ul>
  );
}

export default function ChangePreview({
  changeSet,
  busy,
  error,
  onApply,
  onDiscard,
}: Props) {
  const diff = changeSet.diff;
  const replacement = !Array.isArray(changeSet.operations);
  const hasErrors = changeSet.errors.length > 0 || changeSet.status === "invalid";

  return (
    <div className="change-preview">
      <div className="change-summary">
        <div>
          <p className="eyebrow">{replacement ? "Replacement change set" : "Editor change set"}</p>
          <h3>
            Base r{changeSet.base_revision} · {diff.counts.added} added ·{" "}
            {diff.counts.removed} removed · {diff.counts.changed} changed
          </h3>
          <p className="muted">{changeSet.reason || "No reason recorded."}</p>
        </div>
        <span className={`status-badge ${changeSet.status}`}>{changeSet.status}</span>
      </div>

      <IssueList issues={changeSet.errors} tone="error" />
      <IssueList issues={changeSet.warnings} tone="warning" />
      {error && <p className="form-error">{error}</p>}

      <div className="impact-strip">
        <div>
          <strong>{changeSet.impacted.instance_ids.length}</strong>
          <span>instances affected</span>
        </div>
        <div>
          <strong>{changeSet.impacted.assertion_ids.length}</strong>
          <span>assertions affected</span>
        </div>
        <div>
          <strong>
            {changeSet.impacted.warning_counts.before} →{" "}
            {changeSet.impacted.warning_counts.after}
          </strong>
          <span>warning count</span>
        </div>
      </div>

      <div className="diff-grid">
        <section>
          <h4>Added</h4>
          {diff.added.length === 0 && <p className="muted">None.</p>}
          <ul className="diff-list">
            {diff.added.map((entry) => (
              <li key={entry.id}>
                <span className={`kind-badge kind-${entry.kind}`}>
                  {entry.kind.replaceAll("_", " ")}
                </span>
                <strong>{entry.label}</strong>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h4>Removed</h4>
          {diff.removed.length === 0 && <p className="muted">None.</p>}
          <ul className="diff-list">
            {diff.removed.map((entry) => (
              <li key={entry.id}>
                <span className={`kind-badge kind-${entry.kind}`}>
                  {entry.kind.replaceAll("_", " ")}
                </span>
                <strong>{entry.label}</strong>
              </li>
            ))}
          </ul>
        </section>
        <section className="changed-column">
          <h4>Changed</h4>
          {diff.changed.length === 0 && <p className="muted">None.</p>}
          <ul className="diff-list">
            {diff.changed.map((entry) => (
              <li key={entry.id}>
                <span className={`kind-badge kind-${entry.kind}`}>
                  {entry.kind.replaceAll("_", " ")}
                </span>
                <strong>{entry.label}</strong>
                <dl className="field-diff">
                  {Object.entries(entry.fields).map(([field, values]) => (
                    <div key={field}>
                      <dt>{field}</dt>
                      <dd>
                        <span className="before">{valueText(values.before)}</span>
                        <span aria-hidden="true"> → </span>
                        <span className="after">{valueText(values.after)}</span>
                      </dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="inspector-actions">
        <button className="primary" onClick={onApply} disabled={busy || hasErrors}>
          {busy ? "Applying…" : "Apply change set"}
        </button>
        <button className="ghost" onClick={onDiscard} disabled={busy}>
          Discard
        </button>
        {hasErrors && (
          <span className="fine-print">
            Apply is disabled while structural errors remain.
          </span>
        )}
      </div>
    </div>
  );
}
