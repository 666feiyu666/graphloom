import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "./api/client";
import type { ProjectSummary } from "./api/types";
import ProjectPicker from "./components/ProjectPicker";
import Workbench from "./components/Workbench";

export default function App() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const response = await api.listProjects();
      setProjects(response.projects);
      setError(null);
    } catch (caught) {
      setProjects([]);
      setError(
        caught instanceof ApiError
          ? `${caught.code}: ${caught.message}`
          : "Could not reach the local Graphloom service.",
      );
    }
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  if (projects === null) {
    return <main className="loading-screen">Opening the local workbench…</main>;
  }

  if (projectId) {
    return (
      <Workbench
        key={projectId}
        projectId={projectId}
        onBack={() => {
          setProjectId(null);
          void loadProjects();
        }}
      />
    );
  }

  return (
    <ProjectPicker
      projects={projects}
      error={error}
      onSelect={setProjectId}
      onCreated={loadProjects}
    />
  );
}
