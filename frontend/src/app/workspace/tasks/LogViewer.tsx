"use client";

import { Loader2Icon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useI18n } from "@/core/i18n/hooks";
import { getTaskLogs } from "@/core/tasks/task-center-api";
import type { TaskStatus } from "@/core/tasks/task-center-types";

interface LogViewerProps {
  taskId: string;
  taskStatus: TaskStatus;
}

export function LogViewer({ taskId, taskStatus }: LogViewerProps) {
  const { t } = useI18n();
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const isRunning = taskStatus === "running";

  const fetchLogs = useCallback(async () => {
    try {
      const data = await getTaskLogs(taskId);
      setLogs(data.logs);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!isRunning) return;
    const interval = setInterval(() => void fetchLogs(), 3000);
    return () => clearInterval(interval);
  }, [isRunning, fetchLogs]);

  useEffect(() => {
    if (isRunning && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isRunning]);

  const filteredLogs = search
    ? logs.filter((log) => log.toLowerCase().includes(search.toLowerCase()))
    : logs;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2Icon className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Input
        type="search"
        placeholder={t.taskCenter.logsSearch}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="h-8 text-sm"
      />
      {filteredLogs.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground text-sm">
          {t.taskCenter.logsEmpty}
        </div>
      ) : (
        <ScrollArea className="h-[400px] rounded-md border bg-muted/30">
          <div ref={scrollRef} className="p-3 font-mono text-xs leading-relaxed">
            {filteredLogs.map((log, i) => (
              <div key={i} className="hover:bg-muted/50 rounded px-1 py-0.5">
                {log}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
