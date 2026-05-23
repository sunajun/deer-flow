export type TaskStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "paused"
  | "cancelled";

export type TaskType = "manual" | "scheduled" | "subagent" | "dag_node";

export interface TaskRecord {
  task_id: string;
  thread_id: string;
  task_type: string;
  name: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  log_ids: string[];
  created_by: string;
  parent_task_id: string | null;
}

export interface TaskListResponse {
  tasks: TaskRecord[];
  page: number;
  page_size: number;
}

export interface TaskLogsResponse {
  task_id: string;
  logs: string[];
}
