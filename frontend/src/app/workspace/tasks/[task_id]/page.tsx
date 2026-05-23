"use client";

import {
  ArrowLeftIcon,
  DownloadIcon,
  Loader2Icon,
  PlayIcon,
  RotateCcwIcon,
  XCircleIcon,
} from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import {
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useI18n } from "@/core/i18n/hooks";
import {
  cancelTask,
  exportAudit,
  getTaskDetail,
  listTasks,
  retryTask,
  rerunTask,
} from "@/core/tasks/task-center-api";
import type { TaskRecord, TaskStatus } from "@/core/tasks/task-center-types";

import { LogViewer } from "../LogViewer";

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

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "-";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function TaskDetailPage({
  params,
}: {
  params: Promise<{ task_id: string }>;
}) {
  const { task_id: taskId } = use(params);

  const { t } = useI18n();
  const [task, setTask] = useState<TaskRecord | null>(null);
  const [subtasks, setSubtasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDialog, setConfirmDialog] = useState<{
    type: "retry" | "rerun" | "cancel";
  } | null>(null);
  const [operating, setOperating] = useState(false);

  const fetchTask = useCallback(async () => {
    if (!taskId) return;
    try {
      const data = await getTaskDetail(taskId);
      setTask(data);
      const subtaskData = await listTasks({ pageSize: 100 });
      setSubtasks(
        subtaskData.tasks.filter((st) => st.parent_task_id === taskId),
      );
    } catch {
      setTask(null);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    void fetchTask();
  }, [fetchTask]);

  useEffect(() => {
    if (task) {
      document.title = `${task.name} - ${t.pages.appName}`;
    }
  }, [task, t.pages.appName]);

  const handleConfirmAction = async () => {
    if (!confirmDialog || !taskId) return;
    setOperating(true);
    try {
      const { type } = confirmDialog;
      if (type === "retry") {
        await retryTask(taskId);
      } else if (type === "rerun") {
        await rerunTask(taskId);
      } else if (type === "cancel") {
        await cancelTask(taskId);
      }
      toast.success(t.taskCenter.operationSuccess);
      await fetchTask();
    } catch {
      toast.error(t.taskCenter.operationFailed);
    } finally {
      setOperating(false);
      setConfirmDialog(null);
    }
  };

  const handleExportAudit = async () => {
    if (!taskId) return;
    try {
      const report = await exportAudit(taskId);
      const blob = new Blob([report], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit-${taskId}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(t.taskCenter.exportSuccess);
    } catch {
      toast.error(t.taskCenter.operationFailed);
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

  if (loading) {
    return (
      <WorkspaceContainer>
        <WorkspaceHeader />
        <WorkspaceBody>
          <div className="flex items-center justify-center py-20">
            <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
          </div>
        </WorkspaceBody>
      </WorkspaceContainer>
    );
  }

  if (!task) {
    return (
      <WorkspaceContainer>
        <WorkspaceHeader />
        <WorkspaceBody>
          <div className="flex flex-col items-center gap-4 py-20">
            <p className="text-muted-foreground">Task not found</p>
            <Link href="/workspace/tasks">
              <Button variant="outline">
                <ArrowLeftIcon className="size-4" />
                {t.taskCenter.title}
              </Button>
            </Link>
          </div>
        </WorkspaceBody>
      </WorkspaceContainer>
    );
  }

  return (
    <WorkspaceContainer>
      <WorkspaceHeader>
        <BreadcrumbItem className="hidden md:block">
          <BreadcrumbLink asChild>
            <Link href="/workspace/tasks">{t.taskCenter.title}</Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator className="hidden md:block" />
        <BreadcrumbItem>
          <BreadcrumbPage>{task.name}</BreadcrumbPage>
        </BreadcrumbItem>
      </WorkspaceHeader>
      <WorkspaceBody>
        <ScrollArea className="size-full">
          <div className="mx-auto flex w-full max-w-(--container-width-md) flex-col gap-6 px-4 py-6">
            <div className="flex items-start justify-between gap-4">
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <Link href="/workspace/tasks">
                    <Button variant="ghost" size="icon-sm">
                      <ArrowLeftIcon className="size-4" />
                    </Button>
                  </Link>
                  <h1 className="text-xl font-semibold">{task.name}</h1>
                  <Badge variant={statusBadgeVariant(task.status)}>
                    {statusLabel(task.status)}
                  </Badge>
                </div>
                {task.description && (
                  <p className="text-muted-foreground ml-12 text-sm">
                    {task.description}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {task.status === "failed" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmDialog({ type: "retry" })}
                  >
                    <RotateCcwIcon className="size-3.5" />
                    {t.taskCenter.retry}
                  </Button>
                )}
                {(task.status === "success" ||
                  task.status === "failed" ||
                  task.status === "cancelled") && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmDialog({ type: "rerun" })}
                  >
                    <PlayIcon className="size-3.5" />
                    {t.taskCenter.rerun}
                  </Button>
                )}
                {(task.status === "running" || task.status === "pending") && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmDialog({ type: "cancel" })}
                  >
                    <XCircleIcon className="size-3.5" />
                    {t.taskCenter.cancel}
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportAudit}
                >
                  <DownloadIcon className="size-3.5" />
                  {t.taskCenter.exportAudit}
                </Button>
              </div>
            </div>

            <Tabs defaultValue="info">
              <TabsList>
                <TabsTrigger value="info">{t.taskCenter.basicInfo}</TabsTrigger>
                <TabsTrigger value="logs">{t.taskCenter.logs}</TabsTrigger>
                {subtasks.length > 0 && (
                  <TabsTrigger value="subtasks">
                    {t.taskCenter.subtasks}
                  </TabsTrigger>
                )}
              </TabsList>

              <TabsContent value="info">
                <div className="grid gap-4 md:grid-cols-2">
                  <InfoCard label={t.taskCenter.taskId} value={task.task_id} />
                  <InfoCard
                    label={t.taskCenter.type}
                    value={typeLabel(task.task_type)}
                  />
                  <InfoCard
                    label={t.taskCenter.status}
                    value={statusLabel(task.status)}
                  />
                  <InfoCard
                    label={t.taskCenter.createdAt}
                    value={formatDateTime(task.created_at)}
                  />
                  <InfoCard
                    label={t.taskCenter.duration}
                    value={formatDuration(task.duration)}
                  />
                  {task.parent_task_id && (
                    <InfoCard
                      label={t.taskCenter.parentTask}
                      value={
                        <Link
                          href={`/workspace/tasks/${task.parent_task_id}`}
                          className="text-primary hover:underline"
                        >
                          {task.parent_task_id}
                        </Link>
                      }
                    />
                  )}
                </div>

                {task.error && (
                  <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
                    <h3 className="mb-1 font-medium text-red-700 dark:text-red-400">
                      {t.taskCenter.error}
                    </h3>
                    <pre className="overflow-x-auto text-sm text-red-600 dark:text-red-300">
                      {task.error}
                    </pre>
                  </div>
                )}

                {task.result && (
                  <div className="mt-4 rounded-md border bg-muted/30 p-4">
                    <h3 className="mb-2 font-medium">{t.taskCenter.result}</h3>
                    <pre className="overflow-x-auto text-sm">
                      {JSON.stringify(task.result, null, 2)}
                    </pre>
                  </div>
                )}

                <div className="mt-4 rounded-md border p-4">
                  <h3 className="mb-3 font-medium">{t.taskCenter.timeline}</h3>
                  <div className="flex flex-col gap-2 text-sm">
                    <TimelineEntry
                      label={t.taskCenter.statusPending}
                      time={formatDateTime(task.created_at)}
                    />
                    {task.started_at && (
                      <TimelineEntry
                        label={t.taskCenter.statusRunning}
                        time={formatDateTime(task.started_at)}
                      />
                    )}
                    {task.finished_at && (
                      <TimelineEntry
                        label={
                          task.status === "success"
                            ? t.taskCenter.statusSuccess
                            : task.status === "failed"
                              ? t.taskCenter.statusFailed
                              : t.taskCenter.statusCancelled
                        }
                        time={formatDateTime(task.finished_at)}
                      />
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="logs">
                <LogViewer taskId={taskId} taskStatus={task.status} />
              </TabsContent>

              {subtasks.length > 0 && (
                <TabsContent value="subtasks">
                  <div className="rounded-md border">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b bg-muted/50">
                          <th className="px-4 py-3 text-left font-medium">
                            {t.taskCenter.taskId}
                          </th>
                          <th className="px-4 py-3 text-left font-medium">
                            {t.taskCenter.name}
                          </th>
                          <th className="px-4 py-3 text-left font-medium">
                            {t.taskCenter.status}
                          </th>
                          <th className="px-4 py-3 text-left font-medium">
                            {t.taskCenter.duration}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {subtasks.map((st) => (
                          <tr
                            key={st.task_id}
                            className="border-b hover:bg-muted/30"
                          >
                            <td className="px-4 py-3">
                              <Link
                                href={`/workspace/tasks/${st.task_id}`}
                                className="text-primary hover:underline"
                              >
                                {st.task_id.slice(0, 12)}...
                              </Link>
                            </td>
                            <td className="px-4 py-3">{st.name}</td>
                            <td className="px-4 py-3">
                              <Badge variant={statusBadgeVariant(st.status)}>
                                {statusLabel(st.status)}
                              </Badge>
                            </td>
                            <td className="px-4 py-3 text-muted-foreground">
                              {formatDuration(st.duration)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </TabsContent>
              )}
            </Tabs>
          </div>
        </ScrollArea>
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

function InfoCard({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="rounded-md border p-3">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </div>
  );
}

function TimelineEntry({ label, time }: { label: string; time: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="bg-primary size-2 rounded-full" />
      <span className="font-medium">{label}</span>
      <span className="text-muted-foreground">{time}</span>
    </div>
  );
}
