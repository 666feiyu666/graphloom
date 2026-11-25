import { FormEvent, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { useCredentials } from "../api/hooks";

interface Props {
  token: string;
  projectId: string;
}

function baseUrl(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:8000/api/v1";
  if (window.location.port === "5173") return "http://127.0.0.1:8000/api/v1";
  return `${window.location.origin}/api/v1`;
}

export default function ConnectionPanel({ token, projectId }: Props) {
  const queryClient = useQueryClient();
  const credentialsQuery = useCredentials(token, true);
  const [label, setLabel] = useState("reader");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const endpoint = useMemo(
    () => `${baseUrl()}/projects/${projectId}/schema?revision=0`,
    [projectId],
  );

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!label.trim()) {
      setError("A label is required.");
      return;
    }
    setBusy(true);
    setError(null);
    setNewToken(null);
    try {
      const credential = await api.createReaderCredential(token, label.trim(), [projectId]);
      setNewToken(credential.token ?? null);
      await queryClient.invalidateQueries({ queryKey: ["credentials"] });
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(credentialId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.deleteCredential(token, credentialId);
      await queryClient.invalidateQueries({ queryKey: ["credentials"] });
    } catch (caught) {
      setError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!newToken) return;
    try {
      await navigator.clipboard.writeText(newToken);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Could not copy to the clipboard; select the token manually.");
    }
  }

  const credentials = credentialsQuery.data?.credentials ?? [];

  return (
    <section className="connection-panel" aria-label="Reader access">
      <div className="drawer-section-head">
        <h3>Reader access</h3>
        <span className="revision-badge">{projectId.slice(0, 8)}</span>
      </div>
      <dl className="connection-facts">
        <div>
          <dt>Project ID</dt>
          <dd><code>{projectId}</code></dd>
        </div>
        <div>
          <dt>API base</dt>
          <dd><code>{baseUrl()}</code></dd>
        </div>
      </dl>

      <form className="credential-form" onSubmit={create}>
        <label>
          Reader label
          <input value={label} onChange={(event) => setLabel(event.target.value)} />
        </label>
        <button className="primary compact" type="submit" disabled={busy}>
          Create reader credential
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}

      {newToken && (
        <div className="token-reveal">
          <p className="eyebrow">New reader token — shown once</p>
          <code>{newToken}</code>
          <div className="inspector-actions">
            <button className="secondary compact" onClick={copy}>
              {copied ? "Copied" : "Copy token"}
            </button>
            <button className="ghost compact" onClick={() => setNewToken(null)}>
              Hide
            </button>
          </div>
        </div>
      )}

      <div className="credential-list">
        <p className="eyebrow">Credentials</p>
        <ul>
          {credentials.map((credential) => (
            <li key={credential.id}>
              <div>
                <strong>{credential.label}</strong>
                <span className="kind-badge">{credential.role}</span>
                {credential.revoked_at && <span className="muted">revoked</span>}
              </div>
              <span className="muted">
                scope: {credential.project_ids.length ? credential.project_ids.join(", ") : "all projects"}
              </span>
              {!credential.revoked_at && credential.role === "reader" && (
                <button
                  className="mini"
                  onClick={() => revoke(credential.id)}
                  disabled={busy}
                >
                  Revoke
                </button>
              )}
            </li>
          ))}
          {credentials.length === 0 && <li className="muted">No credentials yet.</li>}
        </ul>
      </div>

      <div className="code-block">
        <p className="eyebrow">Minimal reader call</p>
        <code>
          curl -H &quot;Authorization: Bearer &lt;reader-token&gt;&quot; \<br />
          &nbsp;&nbsp;&quot;{endpoint}&quot;
        </code>
        <p className="fine-print">
          Pin a revision, read the schema, then retrieve objects or bounded neighborhoods.
          Reader credentials cannot prepare or commit edits, import, restore, save layouts, or
          manage credentials.
        </p>
      </div>
    </section>
  );
}
