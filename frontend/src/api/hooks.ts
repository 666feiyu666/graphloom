import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export function useCapabilities(token: string) {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api.capabilities(token),
    staleTime: 60_000,
  });
}

export function useProjects(token: string) {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(token),
  });
}

export function useProject(token: string, projectId: string) {
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(token, projectId),
    refetchInterval: () =>
      typeof document !== "undefined" && document.visibilityState === "visible"
        ? 2000
        : false,
    refetchOnWindowFocus: true,
  });
}

export function useGraphState(
  token: string,
  projectId: string,
  revision: number | undefined,
) {
  return useQuery({
    queryKey: ["state", projectId, revision ?? "current"],
    queryFn: () => api.getState(token, projectId, revision),
    enabled: revision !== undefined,
    placeholderData: keepPreviousData,
  });
}

export function useSchema(
  token: string,
  projectId: string,
  revision: number | undefined,
) {
  return useQuery({
    queryKey: ["schema", projectId, revision ?? "current"],
    queryFn: () => api.getSchema(token, projectId, revision),
    enabled: revision !== undefined,
    placeholderData: keepPreviousData,
  });
}

export function useLayout(token: string, projectId: string) {
  return useQuery({
    queryKey: ["layout", projectId],
    queryFn: () => api.getLayout(token, projectId),
  });
}

export function useRevisions(token: string, projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["revisions", projectId],
    queryFn: () => api.getRevisions(token, projectId, 0, 100),
    enabled,
  });
}

export function useSnapshots(token: string, projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["snapshots", projectId],
    queryFn: () => api.listSnapshots(token, projectId),
    enabled,
  });
}

export function useCredentials(token: string, enabled: boolean) {
  return useQuery({
    queryKey: ["credentials"],
    queryFn: () => api.listCredentials(token),
    enabled,
  });
}

export function invalidateProject(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
) {
  for (const prefix of [
    "project",
    "state",
    "schema",
    "objects",
    "revisions",
    "snapshots",
  ]) {
    void queryClient.invalidateQueries({ queryKey: [prefix, projectId] });
  }
}

export function invalidateLayout(
  queryClient: ReturnType<typeof useQueryClient>,
  projectId: string,
) {
  void queryClient.invalidateQueries({ queryKey: ["layout", projectId] });
}
