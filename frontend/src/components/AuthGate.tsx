import { FormEvent, useState } from "react";
import { ApiError, api } from "../api/client";

export default function AuthGate({ onConnect }: { onConnect: (token: string) => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const candidate = token.trim();
    if (!candidate) {
      setError("Enter the owner token printed by the local setup command.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const capabilities = await api.capabilities(candidate);
      if (capabilities.role !== "owner") {
        setError("This token is a reader credential. The workbench needs an owner token.");
        return;
      }
      onConnect(candidate);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(
          caught.status === 401
            ? "That token was not accepted. Create or rotate the owner token with the command below."
            : `${caught.code}: ${caught.message}`,
        );
      } else {
        setError("Could not reach the local Graphloom service.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            GL
          </span>
          <div>
            <p className="eyebrow">Local research workbench</p>
            <h1>Graphloom <span className="brand-cn">图思</span></h1>
          </div>
        </div>
        <p className="auth-intro">
          Build and inspect a visual-rhetoric ontology and its knowledge graph. The saved
          graph is exposed read-only to a consuming agent through the same HTTP contract
          the workbench uses.
        </p>

        <form onSubmit={submit} className="auth-form">
          <label htmlFor="owner-token">Owner token</label>
          <input
            id="owner-token"
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="gl_owner_…"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Checking…" : "Open workbench"}
          </button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}

        <div className="auth-help">
          <p className="eyebrow">First run</p>
          <code>cd graphloom/backend && uv run python -m app.cli init-owner</code>
          <p>
            The token is kept in memory for this tab only. A reload asks for it again; it
            is never written to local storage.
          </p>
          <p>
            Reader credentials for consuming agents are created inside the workbench under
            <strong> Read access</strong>.
          </p>
        </div>
      </section>
    </main>
  );
}
