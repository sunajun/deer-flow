"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  ClockIcon,
  Loader2Icon,
  PauseIcon,
  RotateCcwIcon,
  PlayIcon,
  XCircleIcon,
  ListTodoIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useI18n } from "@/core/i18n/hooks";
import { cancelTask, listTasks, retryTask, rerunTask } from "@/core/tasks/task-center-api";
import type { TaskRecord, TaskStatus } from "@/core/tasks/task-center-types";
import { formatTimeAgo } from "@/core/utils/datetime";

const STATUS_FILTER_OPTIONS: (TaskStatus | "all")[] = [
  "all",
  "running",
  "success",
  "failed",
  "cancelled",
  "pending",
];

const TYPE_FILTER_OPTIONS = ["all", "manual", "scheduled", "subagent", "dag_node"] as const;

function statusBadgeVariant(status: TaskStatus) {
  switch (status) {
    case "success":
      return "default" as const;
    case "failed":
      return "destructive" as const;
    case "running":
      return "secondary" as const;
    case "pending":
      return "outline" as const;
    case "paused":
      return "outline" as const;
    case "cancelled":
      return "outline" as const;
  }
}

function StatusIcon({ status }: { status: TaskStatus }) {
  switch (status) {
    case "success":
      return <CheckCircle2Icon className="size-3.5 text-green-600" />;
    case "failed":
      return <XCircleIcon className="size-3.5 text-red-500" />;
    case "running":
      return <Loader2Icon className="size-3.5 animate-spin text-blue-500" />;
    case "pending":
      return <ClockIcon className="size-3.5 text-yellow-500" />;
    case "paused":
      return <PauseIcon className="size-3.5 text-orange-500" />;
    case "cancelled":
      return <AlertCircleIcon className="size-3.5 text-gray-500" />;
  }
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "-";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export default function TasksPage() {
  const { t } = useI18n();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [confirmDialog, setConfirmDialog] = useState<{
    type: "retry" | "rerun" | "cancel";
    task: TaskRecord;
  } | null>(null);
  const [operating, setOperating] = useState(false);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listTasks({
        page,
        pageSize,
        status: statusFilter !== "all" ? statusFilter : undefined,
        taskType: typeFilter !== "all" ? typeFilter : undefined,
      });
      setTasks(data.tasks);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, statusFilter, typeFilter]);

  useEffect(() => {
    void fetchTasks();
  }, [fetchTasks]);

  useEffect(() => {
    document.title = `${t.taskCenter.title} - ${t.pages.appName}`;
  }, [t.taskCenter.title, t.pages.appName]);

  const handleConfirmAction = async () => {
    if (!confirmDialog) return;
    setOperating(true);
    try {
      const { type, task } = confirmDialog;
      if (type === "retry") {
        await retryTask(task.task_id);
      } else if (type === "rerun") {
        await rerunTask(task.task_id);
      } else if (type === "cancel") {
        await cancelTask(task.task_id);
      }
      toast.success(t.taskCenter.operationSuccess);
      await fetchTasks();
    } catch {
      toast.error(t.taskCenter.operationFailed);
    } finally {
      setOperating(false);
      setConfirmDialog(null);
    }
  };

  const statusLabel = (status: TaskStatus) => {
    const map: Record<TaskStatus, string> = {
      pending: t.taskCenter.statusPending,
      running: t.taskCenter.statusRunning,
      success: t.taskCenter.statusSuccess,
      failed: t.taskCenter.statusFailed,
      paused: t.taskCenter.statusPaused,
      cancelled: t.taskCenter.statusCancelled,
    };
    return map[status];
  };

  const typeLabel = (taskType: string) => {
    const map: Record<string, string> = {
      manual: t.taskCenter.typeManual,
      scheduled: t.taskCenter.typeScheduled,
      subagent: t.taskCenter.typeSubagent,
      dag_node: t.taskCenter.typeDagNode,
    };
    return map[taskType] ?? taskType;
  };

  const confirmTitle =
    confirmDialog?.type === "retry"
      ? t.taskCenter.retryConfirmTitle
      : confirmDialog?.type === "rerun"
        ? t.taskCenter.rerunConfirmTitle
        : t.taskCenter.cancelConfirmTitle;

  const confirmDesc =
    confirmDialog?.type === "retry"
      ? t.taskCenter.retryConfirmDescription
      : confirmDialog?.type === "rerun"
        ? t.taskCenter.rerunConfirmDescription
        : t.taskCenter.cancelConfirmDescription;

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody>
        <div className="flex size-full flex-col">
          <div className="mx-auto flex w-full max-w-(--container-width-md) flex-col gap-4 px-4 py-6">
            <div className="flex items-center gap-3">
              <ListTodoIcon className="size-6 text-primary" />
              <h1 className="text-2xl font-semibold">{t.taskCenter.title}</h1>
            </div>

            <div className="flex items-center gap-3">
              <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_FILTER_OPTIONS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s === "all"
                        ? t.taskCenter.filterAll
                        : statusLabel(s)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPE_FILTER_OPTIONS.map((tp) => (
                    <SelectItem key={tp} value={tp}>
                      {tp === "all"
                        ? t.taskCenter.typeAll
                        : typeLabel(tp)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="rounded-md border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium">{t.taskCenter.taskId}</th>
                    <th className="px-4 py-3 text-left font-medium">{t.taskCenter.name}</th>
                    <th className="px-4 py-3 text-left font-medium">{t.taskCenter.type}</th>
                    <th className="px-4 py-3 text-left font-medium">{t.taskCenter.status}</th>
                    <th className="px-4 py-3 text-left font-medium">{t.taskCenter.createdAt}</th>
                    <th className="px-4 py-3 text-left font-medium">{t.taskCenter.duration}</th>
                    <th className="px-4 py-3 text-right font-medium">{t.common.more}</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                        <Loader2Icon className="mx-auto mb-2 size-5 animate-spin" />
                        {t.common.loading}
                      </td>
                    </tr>
                  ) : tasks.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                        {t.taskCenter.noTasks}
                      </td>
                    </tr>
                  ) : (
                    tasks.map((task) => (
                      <tr
                        key={task.task_id}
                        className="border-b transition-colors hover:bg-muted/30"
                      >
                        <td className="px-4 py-3">
                          <Link
                            href={`/workspace/tasks/${task.task_id}`}
                            className="text-primary hover:underline"
                          >
                            {task.task_id.length > 12
                              ? `${task.task_id.slice(0, 12)}...`
                              : task.task_id}
                          </Link>
                        </td>
                        <td className="max-w-[200px] truncate px-4 py-3">
                          <Link
                            href={`/workspace/tasks/${task.task_id}`}
                            className="hover:underline"
                          >
                            {task.name}
                          </Link>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline">{typeLabel(task.task_type)}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={statusBadgeVariant(task.status)}>
                            <StatusIcon status={task.status} />
                            {statusLabel(task.status)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatTimeAgo(task.created_at)}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatDuration(task.duration)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            {task.status === "failed" && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setConfirmDialog({ type: "retry", task })
                                }
                              >
                                <RotateCcwIcon className="size-3.5" />
                                {t.taskCenter.retry}
                              </Button>
                            )}
                            {(task.status === "success" ||
                              task.status === "failed" ||
                              task.status === "cancelled") && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setConfirmDialog({ type: "rerun", task })
                                }
                              >
                                <PlayIcon className="size-3.5" />
                                {t.taskCenter.rerun}
                              </Button>
                            )}
                            {(task.status === "running" ||
                              task.status === "pending") && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                  setConfirmDialog({ type: "cancel", task })
                                }
                              >
                                <XCircleIcon className="size-3.5" />
                                {t.taskCenter.cancel}
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-muted-foreground text-sm">
                {t.taskCenter.page} {page}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  {t.taskCenter.prev}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={tasks.length < pageSize}
                  onClick={() => setPage((p) => p + 1)}
                >
                  {t.taskCenter.next}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </WorkspaceBody>

      <Dialog
        open={confirmDialog !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmDialog(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmTitle}</DialogTitle>
            <DialogDescription>{confirmDesc}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmDialog(null)}
              disabled={operating}
            >
              {t.common.cancel}
            </Button>
            <Button onClick={handleConfirmAction} disabled={operating}>
              {operating && <Loader2Icon className="size-4 animate-spin" />}
              {confirmDialog?.type === "retry"
                ? t.taskCenter.retry
                : confirmDialog?.type === "rerun"
                  ? t.taskCenter.rerun
                  : t.taskCenter.cancel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </WorkspaceContainer>
  );
}
