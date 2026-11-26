import { FormEvent, useState } from "react";
import { ApiError, api } from "../api/client";
import type { ProjectSummary } from "../api/types";

interface Props {
  projects: ProjectSummary[];
  error: string | null;
  onSelect: (projectId: string) => void;
  onCreated: () => Promise<void>;
}

export default function ProjectPicker({ projects, error, onSelect, onCreated }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("A project name is required.");
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const project = await api.createProject(name.trim(), description.trim());
      await onCreated();
      onSelect(project.id);
    } catch (caught) {
      setFormError(caught instanceof ApiError ? caught.message : "Could not create the project.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="picker-shell">
      <header className="picker-header">
        <div>
          <p className="eyebrow">Graphloom</p>
          <h1>Projects</h1>
          <p className="muted">
            Each project owns one ontology and graph, stored as a single local JSON file.
          </p>
        </div>
      </header>

      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="picker-grid">
        <section className="project-list" aria-label="Stored projects">
          {projects.length === 0 && (
            <div className="empty-card">
              <h2>No projects yet</h2>
              <p>Create an empty project to begin a synthetic modeling trial.</p>
            </div>
          )}
          {projects.map((project) => (
            <button
              key={project.id}
              className="project-card"
              onClick={() => onSelect(project.id)}
            >
              <div className="project-card-title">
                <strong>{project.name}</strong>
                <span className="revision-badge">v{project.version}</span>
              </div>
              {project.description && <p>{project.description}</p>}
              <dl className="project-counts">
                <div>
                  <dt>classes</dt>
                  <dd>{project.counts.classes}</dd>
                </div>
                <div>
                  <dt>instances</dt>
                  <dd>{project.counts.instances}</dd>
                </div>
                <div>
                  <dt>relations</dt>
                  <dd>{project.counts.relations}</dd>
                </div>
                <div>
                  <dt>assertions</dt>
                  <dd>{project.counts.assertions}</dd>
                </div>
              </dl>
            </button>
          ))}
        </section>

        <section className="create-card">
          <p className="eyebrow">New project</p>
          <h2>Start empty</h2>
          <form onSubmit={create} className="stacked-form">
            <label htmlFor="project-name">Name</label>
            <input
              id="project-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Working model"
            />
            <label htmlFor="project-description">Description</label>
            <textarea
              id="project-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What this model is for, and what it deliberately leaves out."
              rows={4}
            />
            <button type="submit" className="primary" disabled={busy}>
              {busy ? "Creating…" : "Create project"}
            </button>
          </form>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <p className="fine-print">
            Do not prepopulate disciplinary categories. Technical fixtures belong outside the
            research dataset and should be marked synthetic.
          </p>
        </section>
      </div>
    </main>
  );
}
