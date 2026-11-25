import { useState } from "react";
import { ApiError } from "./api/client";
import { useCapabilities, useProjects } from "./api/hooks";
import AuthGate from "./components/AuthGate";
import ProjectPicker from "./components/ProjectPicker";
import Workbench from "./components/Workbench";
import { useUI } from "./store/ui";

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  if (!token) return <AuthGate onConnect={setToken} />;
  return <SignedIn token={token} onDisconnect={() => setToken(null)} />;
}

function SignedIn({
  token,
  onDisconnect,
}: {
  token: string;
  onDisconnect: () => void;
}) {
  const capabilitiesQuery = useCapabilities(token);
  const projectsQuery = useProjects(token);
  const [projectId, setProjectId] = useState<string | null>(null);
  const reset = useUI((state) => state.reset);

  if (capabilitiesQuery.isLoading || projectsQuery.isLoading) {
    return <main className="loading-screen">Opening the local workbench…</main>;
  }

  const error = capabilitiesQuery.error ?? projectsQuery.error;
  if (error) {
    const unauthorized = error instanceof ApiError && error.status === 401;
    return (
      <main className="loading-screen">
        <h1>{unauthorized ? "Session ended" : "Could not reach Graphloom"}</h1>
        <p>
          {error instanceof Error
            ? error.message
            : "Check that the local backend is running on 127.0.0.1:8000."}
        </p>
        <button className="primary" onClick={onDisconnect}>
          Enter a token again
        </button>
      </main>
    );
  }

  const capabilities = capabilitiesQuery.data;
  const projects = projectsQuery.data?.projects ?? [];
  if (!capabilities) return null;

  if (!projectId) {
    return (
      <ProjectPicker
        token={token}
        capabilities={capabilities}
        projects={projects}
        onSelect={(id) => {
          reset();
          setProjectId(id);
        }}
        onDisconnect={onDisconnect}
      />
    );
  }

  return (
    <Workbench
      key={projectId}
      token={token}
      projectId={projectId}
      capabilities={capabilities}
      onBack={() => {
        reset();
        setProjectId(null);
      }}
      onDisconnect={onDisconnect}
    />
  );
}
