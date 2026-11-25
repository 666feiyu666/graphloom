import type {
  Capabilities,
  ChangeSet,
  CommitResult,
  Credential,
  CredentialsResponse,
  GraphObject,
  GraphState,
  Kind,
  LayoutResponse,
  NativeExport,
  ObjectsResponse,
  ProjectSummary,
  RevisionsResponse,
  SchemaResponse,
  Snapshot,
  SnapshotsResponse,
} from "./types";

const API = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type QueryValue = string | number | boolean | null | undefined;

function qs(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

async function request<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API}${path}`, { ...init, headers });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    const envelope = body as
      | { error?: { code?: string; message?: string; details?: Record<string, unknown> }; request_id?: string }
      | null;
    throw new ApiError(
      response.status,
      envelope?.error?.code ?? "http_error",
      envelope?.error?.message ?? response.statusText,
      envelope?.error?.details ?? {},
      envelope?.request_id ?? response.headers.get("X-Request-ID"),
    );
  }
  return body as T;
}

export const api = {
  capabilities: (token: string) => request<Capabilities>(token, "/capabilities"),

  listProjects: (token: string) =>
    request<{ projects: ProjectSummary[] }>(token, "/projects"),

  createProject: (token: string, name: string, description: string) =>
    request<ProjectSummary>(token, "/projects", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  getProject: (token: string, projectId: string) =>
    request<ProjectSummary>(token, `/projects/${projectId}`),

  getState: (token: string, projectId: string, revision?: number) =>
    request<GraphState>(
      token,
      `/projects/${projectId}/state${qs({ revision })}`,
    ),

  getSchema: (token: string, projectId: string, revision?: number) =>
    request<SchemaResponse>(
      token,
      `/projects/${projectId}/schema${qs({ revision })}`,
    ),

  getObjects: (
    token: string,
    projectId: string,
    params: {
      kind?: Kind;
      q?: string;
      cursor?: string | null;
      revision?: number;
      limit?: number;
    },
  ) =>
    request<ObjectsResponse>(
      token,
      `/projects/${projectId}/objects${qs(params)}`,
    ),

  getObject: (token: string, projectId: string, objectId: string, revision?: number) =>
    request<{ project_id: string; revision: number; object: GraphObject }>(
      token,
      `/projects/${projectId}/objects/${objectId}${qs({ revision })}`,
    ),

  query: (
    token: string,
    projectId: string,
    body: Record<string, unknown>,
  ) =>
    request<Record<string, unknown>>(token, `/projects/${projectId}/query`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getRevisions: (token: string, projectId: string, after = 0, limit = 100) =>
    request<RevisionsResponse>(
      token,
      `/projects/${projectId}/revisions${qs({ after, limit })}`,
    ),

  getDiff: (token: string, projectId: string, from: number, to: number) =>
    request<{ project_id: string; from_revision: number; to_revision: number; diff: unknown }>(
      token,
      `/projects/${projectId}/diff${qs({ from, to })}`,
    ),

  listSnapshots: (token: string, projectId: string) =>
    request<SnapshotsResponse>(token, `/projects/${projectId}/snapshots`),

  createSnapshot: (token: string, projectId: string, name: string, revision?: number) =>
    request<Snapshot>(token, `/projects/${projectId}/snapshots`, {
      method: "POST",
      body: JSON.stringify({ name, revision }),
    }),

  restorePreview: (token: string, projectId: string, snapshotId: string, reason = "") =>
    request<ChangeSet>(
      token,
      `/projects/${projectId}/snapshots/${snapshotId}/restore-preview`,
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      },
    ),

  restoreRevisionPreview: (
    token: string,
    projectId: string,
    revision: number,
    reason = "",
  ) =>
    request<ChangeSet>(
      token,
      `/projects/${projectId}/revisions/${revision}/restore-preview`,
      {
        method: "POST",
        body: JSON.stringify({ reason }),
      },
    ),

  importPreview: (token: string, projectId: string, payload: unknown) =>
    request<ChangeSet>(token, `/projects/${projectId}/import-preview`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  exportNative: (token: string, projectId: string, revision?: number, includeLayout = false) =>
    request<NativeExport>(
      token,
      `/projects/${projectId}/export${qs({
        format: "native-json",
        revision,
        include_layout: includeLayout,
      })}`,
    ),

  exportTurtle: async (token: string, projectId: string, revision?: number) => {
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(
      `${API}/projects/${projectId}/export${qs({ format: "turtle", revision })}`,
      { headers },
    );
    if (!response.ok) {
      throw new ApiError(response.status, "export_failed", "RDF export failed");
    }
    return response.text();
  },

  getLayout: (token: string, projectId: string) =>
    request<LayoutResponse>(token, `/projects/${projectId}/layout`),

  putLayout: (
    token: string,
    projectId: string,
    expectedVersion: number,
    data: Record<string, unknown>,
  ) =>
    request<LayoutResponse>(token, `/projects/${projectId}/layout`, {
      method: "PUT",
      body: JSON.stringify({ expected_version: expectedVersion, data }),
    }),

  prepareChangeSet: (
    token: string,
    projectId: string,
    body: {
      base_revision: number;
      reason: string;
      operations: unknown[];
    },
  ) =>
    request<ChangeSet>(token, `/projects/${projectId}/change-sets`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getChangeSet: (token: string, projectId: string, changeSetId: string) =>
    request<ChangeSet>(
      token,
      `/projects/${projectId}/change-sets/${changeSetId}`,
    ),

  commitChangeSet: (
    token: string,
    projectId: string,
    changeSetId: string,
    expectedRevision: number,
  ) =>
    request<CommitResult>(
      token,
      `/projects/${projectId}/change-sets/${changeSetId}/commit`,
      {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ expected_revision: expectedRevision }),
      },
    ),

  listCredentials: (token: string) =>
    request<CredentialsResponse>(token, "/credentials"),

  createReaderCredential: (
    token: string,
    label: string,
    projectIds: string[],
  ) =>
    request<Credential>(token, "/credentials", {
      method: "POST",
      body: JSON.stringify({ label, project_ids: projectIds }),
    }),

  deleteCredential: (token: string, credentialId: string) =>
    request<Credential>(token, `/credentials/${credentialId}`, {
      method: "DELETE",
    }),
};
