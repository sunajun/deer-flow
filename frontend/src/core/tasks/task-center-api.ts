import { fetch as fetchWithAuth } from "@/core/api/fetcher";

import type {
  TaskListResponse,
  TaskLogsResponse,
  TaskRecord,
} from "./task-center-types";

export async function listTasks(params?: {
  page?: number;
  pageSize?: number;
  status?: string;
  taskType?: string;
}): Promise<TaskListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.pageSize) searchParams.set("page_size", String(params.pageSize));
  if (params?.status) searchParams.set("status", params.status);
  if (params?.taskType) searchParams.set("task_type", params.taskType);

  const qs = searchParams.toString();
  const url = `/api/tasks${qs ? `?${qs}` : ""}`;

  const res = await fetchWithAuth(url);
  if (!res.ok) throw new Error(`Failed to list tasks: ${res.status}`);
  return res.json();
}

export async function getTaskDetail(taskId: string): Promise<TaskRecord> {
  const res = await fetchWithAuth(`/api/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Failed to get task detail: ${res.status}`);
  return res.json();
}

export async function getTaskLogs(
  taskId: string,
): Promise<TaskLogsResponse> {
  const res = await fetchWithAuth(`/api/tasks/${taskId}/logs`);
  if (!res.ok) throw new Error(`Failed to get task logs: ${res.status}`);
  return res.json();
}

export async function retryTask(taskId: string): Promise<TaskRecord> {
  const res = await fetchWithAuth(`/api/tasks/${taskId}/retry`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to retry task: ${res.status}`);
  return res.json();
}

export async function rerunTask(taskId: string): Promise<TaskRecord> {
  const res = await fetchWithAuth(`/api/tasks/${taskId}/rerun`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to rerun task: ${res.status}`);
  return res.json();
}

export async function cancelTask(taskId: string): Promise<TaskRecord> {
  const res = await fetchWithAuth(`/api/tasks/${taskId}/cancel`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Failed to cancel task: ${res.status}`);
  return res.json();
}

export async function exportAudit(taskId: string): Promise<string> {
  const res = await fetchWithAuth(`/api/tasks/${taskId}/export`);
  if (!res.ok) throw new Error(`Failed to export audit: ${res.status}`);
  return res.text();
}
