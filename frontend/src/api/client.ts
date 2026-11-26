import type {
  BatchResult,
  Capabilities,
  GraphObject,
  GraphState,
  Kind,
  LayoutData,
  LayoutResponse,
  ObjectsResponse,
  Operation,
  ProjectSummary,
  SchemaResponse,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
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
      | {
          error?: {
            code?: string;
            message?: string;
            details?: Record<string, unknown>;
          };
          request_id?: string;
        }
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
  capabilities: () => request<Capabilities>("/capabilities"),

  listProjects: () => request<{ projects: ProjectSummary[] }>("/projects"),

  createProject: (name: string, description: string) =>
    request<ProjectSummary>("/projects", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  getProject: (projectId: string) =>
    request<ProjectSummary>(`/projects/${projectId}`),

  getState: (projectId: string) =>
    request<GraphState>(`/projects/${projectId}/state`),

  getSchema: (projectId: string) =>
    request<SchemaResponse>(`/projects/${projectId}/schema`),

  getObjects: (
    projectId: string,
    params: { kind?: Kind; q?: string; cursor?: string | null; limit?: number },
  ) =>
    request<ObjectsResponse>(`/projects/${projectId}/objects${qs(params)}`),

  getObject: (projectId: string, objectId: string) =>
    request<{ project_id: string; version: number; object: GraphObject }>(
      `/projects/${projectId}/objects/${objectId}`,
    ),

  neighborhood: (projectId: string, objectId: string, depth = 1) =>
    request<Record<string, unknown>>(
      `/projects/${projectId}/neighborhood${qs({ id: objectId, depth })}`,
    ),

  instances: (projectId: string, classId: string, includeDescendants = true) =>
    request<Record<string, unknown>>(
      `/projects/${projectId}/instances${qs({
        class_id: classId,
        include_descendants: includeDescendants,
      })}`,
    ),

  references: (projectId: string, objectId: string) =>
    request<Record<string, unknown>>(
      `/projects/${projectId}/references${qs({ id: objectId })}`,
    ),

  applyBatch: (projectId: string, operations: Operation[]) =>
    request<BatchResult>(`/projects/${projectId}/batch`, {
      method: "POST",
      body: JSON.stringify({ operations }),
    }),

  getLayout: (projectId: string) =>
    request<LayoutResponse>(`/projects/${projectId}/layout`),

  putLayout: (projectId: string, data: LayoutData) =>
    request<LayoutResponse>(`/projects/${projectId}/layout`, {
      method: "PUT",
      body: JSON.stringify({ data }),
    }),
};
