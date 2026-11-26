import { useMemo, useState } from "react";

interface Props {
  projectId: string;
  version: number;
}

function baseUrl(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:8000/api/v1";
  if (window.location.port === "5173") return "http://127.0.0.1:8000/api/v1";
  return `${window.location.origin}/api/v1`;
}

export default function ConnectionPanel({ projectId, version }: Props) {
  const [copied, setCopied] = useState(false);
  const endpoint = useMemo(
    () => `${baseUrl()}/projects/${projectId}/schema`,
    [projectId],
  );
  const filePath = `graphloom/.local/projects/${projectId}.json`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(endpoint);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="connection-panel" aria-label="Read access">
      <div className="drawer-section-head">
        <h3>Read-only access</h3>
        <span className="revision-badge">v{version}</span>
      </div>
      <dl className="connection-facts">
        <div>
          <dt>Project ID</dt>
          <dd><code>{projectId}</code></dd>
        </div>
        <div>
          <dt>Read API base</dt>
          <dd><code>{baseUrl()}</code></dd>
        </div>
        <div>
          <dt>Saved JSON file</dt>
          <dd><code>{filePath}</code></dd>
        </div>
      </dl>

      <div className="code-block">
        <p className="eyebrow">Minimal read call</p>
        <code>curl &quot;{endpoint}&quot;</code>
        <p className="fine-print">
          The service binds to loopback and has no token. A consuming agent uses the read endpoints
          below, or reads the saved JSON file directly. The write endpoint is not part of the reader
          contract.
        </p>
      </div>

      <div className="inspector-actions">
        <button className="secondary compact" onClick={copy}>
          {copied ? "Copied" : "Copy endpoint"}
        </button>
        <a className="button-like compact" href="/api/v1/openapi.reader.json" target="_blank" rel="noreferrer">
          Reader OpenAPI
        </a>
      </div>
    </section>
  );
}
