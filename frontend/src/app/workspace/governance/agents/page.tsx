"use client";

import {
  MoreHorizontalIcon,
  PlusIcon,
  RotateCcwIcon,
  Trash2Icon,
  HistoryIcon,
  PencilIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type AgentConfigVersion,
  type AgentConfigVersionSnapshot,
  type CreateAgentConfigRequest,
  type UpdateAgentConfigRequest,
  createAgentConfig,
  deleteAgentConfig,
  getAgentConfigVersions,
  listAgentConfigs,
  rollbackAgentConfig,
  updateAgentConfig,
} from "@/lib/api/agent-configs";

const MODELS = [
  "deepseek-chat",
  "deepseek-reasoner",
  "gpt-4o",
  "gpt-4o-mini",
  "claude-sonnet-4-20250514",
  "qwen-max",
  "qwen-plus",
];

const TOOL_GROUPS = [
  "search",
  "code",
  "bash",
  "browser",
  "file",
  "mcp",
];

const SCENES = [
  "conversation",
  "planning",
  "file_operation",
  "code_generation",
  "data_analysis",
];

export default function AgentConfigPage() {
  const [configs, setConfigs] = useState<AgentConfigVersion[]>([]);
  const [loading, setLoading] = useState(true);

  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<AgentConfigVersion | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AgentConfigVersion | null>(
    null,
  );
  const [historyTarget, setHistoryTarget] =
    useState<AgentConfigVersion | null>(null);
  const [versions, setVersions] = useState<AgentConfigVersionSnapshot[]>([]);
  const [rollbackTarget, setRollbackTarget] = useState<{
    agent: AgentConfigVersion;
    version: string;
  } | null>(null);

  const [form, setForm] = useState<CreateAgentConfigRequest>({
    name: "",
    description: "",
    model: null,
    tool_groups: null,
    skills: null,
    allowed_scenes: [],
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listAgentConfigs();
      setConfigs(data);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async () => {
    try {
      await createAgentConfig(form);
      toast.success("Agent config created");
      setCreateOpen(false);
      setForm({
        name: "",
        description: "",
        model: null,
        tool_groups: null,
        skills: null,
        allowed_scenes: [],
      });
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleEdit = async () => {
    if (!editTarget) return;
    try {
      const data: UpdateAgentConfigRequest = {
        description: form.description ?? undefined,
        model: form.model,
        tool_groups: form.tool_groups,
        skills: form.skills,
        allowed_scenes: form.allowed_scenes,
        change_summary: "Updated via governance UI",
      };
      await updateAgentConfig(editTarget.name, data);
      toast.success("Agent config updated");
      setEditOpen(false);
      setEditTarget(null);
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteAgentConfig(deleteTarget.name);
      toast.success("Agent config deleted");
      setDeleteTarget(null);
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleShowHistory = async (agent: AgentConfigVersion) => {
    setHistoryTarget(agent);
    try {
      const v = await getAgentConfigVersions(agent.name);
      setVersions(v);
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleRollback = async () => {
    if (!rollbackTarget) return;
    try {
      await rollbackAgentConfig(
        rollbackTarget.agent.name,
        rollbackTarget.version,
      );
      toast.success("Rolled back successfully");
      setRollbackTarget(null);
      setHistoryTarget(null);
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const openEdit = (agent: AgentConfigVersion) => {
    setEditTarget(agent);
    setForm({
      name: agent.name,
      description: agent.description,
      model: agent.model,
      tool_groups: agent.tool_groups,
      skills: agent.skills,
      allowed_scenes: agent.allowed_scenes,
    });
    setEditOpen(true);
  };

  const toggleToolGroup = (group: string, checked: boolean) => {
    const current = form.tool_groups ?? [];
    const next = checked
      ? [...current, group]
      : current.filter((g) => g !== group);
    setForm((f) => ({ ...f, tool_groups: next.length > 0 ? next : null }));
  };

  const toggleScene = (scene: string, checked: boolean) => {
    const current = form.allowed_scenes ?? [];
    const next = checked
      ? [...current, scene]
      : current.filter((s) => s !== scene);
    setForm((f) => ({ ...f, allowed_scenes: next }));
  };

  const renderForm = () => (
    <div className="grid gap-4 py-4">
      <div className="grid gap-2">
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          disabled={editOpen}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="description">Description</Label>
        <Input
          id="description"
          value={form.description ?? ""}
          onChange={(e) =>
            setForm((f) => ({ ...f, description: e.target.value }))
          }
        />
      </div>
      <div className="grid gap-2">
        <Label>Model</Label>
        <Select
          value={form.model ?? "default"}
          onValueChange={(v) =>
            setForm((f) => ({ ...f, model: v === "default" ? null : v }))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="Select model" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="default">Default</SelectItem>
            {MODELS.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-2">
        <Label>Tool Groups</Label>
        <div className="flex flex-wrap gap-3">
          {TOOL_GROUPS.map((g) => (
            <label key={g} className="flex items-center gap-1.5 text-sm">
              <Checkbox
                checked={form.tool_groups?.includes(g) ?? false}
                onCheckedChange={(c) => toggleToolGroup(g, !!c)}
              />
              {g}
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Allowed Scenes</Label>
        <div className="flex flex-wrap gap-3">
          {SCENES.map((s) => (
            <label key={s} className="flex items-center gap-1.5 text-sm">
              <Checkbox
                checked={form.allowed_scenes?.includes(s) ?? false}
                onCheckedChange={(c) => toggleScene(s, !!c)}
              />
              {s}
            </label>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">Agent Config Management</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            Manage agent configurations with version tracking
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <PlusIcon className="mr-1.5 h-4 w-4" />
          Create Agent Config
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
            Loading...
          </div>
        ) : configs.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <p className="text-muted-foreground">No agent configs found</p>
            <Button variant="outline" onClick={() => setCreateOpen(true)}>
              <PlusIcon className="mr-1.5 h-4 w-4" />
              Create Agent Config
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Scenes</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.map((c) => (
                <TableRow key={c.name}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell>{c.model ?? "default"}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{c.version}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {c.allowed_scenes.map((s) => (
                        <Badge key={s} variant="outline" className="text-xs">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {new Date(c.updated_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <MoreHorizontalIcon className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => openEdit(c)}>
                          <PencilIcon className="mr-2 h-4 w-4" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={() => void handleShowHistory(c)}
                        >
                          <HistoryIcon className="mr-2 h-4 w-4" />
                          Version History
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => setDeleteTarget(c)}
                        >
                          <Trash2Icon className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Agent Config</DialogTitle>
          </DialogHeader>
          {renderForm()}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleCreate()} disabled={!form.name}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit Agent Config</DialogTitle>
          </DialogHeader>
          {renderForm()}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button onClick={() => void handleEdit()}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Agent Config</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.name}
              &quot;? This action cannot be undone and will also delete all
              version history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => void handleDelete()}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Drawer
        open={!!historyTarget}
        onOpenChange={(o) => !o && setHistoryTarget(null)}
      >
        <DrawerContent>
          <div className="mx-auto w-full max-w-2xl">
            <DrawerHeader>
              <DrawerTitle>
                Version History — {historyTarget?.name}
              </DrawerTitle>
            </DrawerHeader>
            <div className="max-h-96 overflow-y-auto px-4">
              {versions.length === 0 ? (
                <p className="text-muted-foreground py-8 text-center text-sm">
                  No version history
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Version</TableHead>
                      <TableHead>Summary</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {versions.map((v) => (
                      <TableRow key={v.version}>
                        <TableCell>
                          <Badge variant="secondary">{v.version}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-sm">
                          {v.change_summary || "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-sm">
                          {new Date(v.created_at).toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setRollbackTarget({
                                agent: historyTarget!,
                                version: v.version,
                              })
                            }
                          >
                            <RotateCcwIcon className="mr-1 h-3 w-3" />
                            Rollback
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
            <DrawerFooter>
              <DrawerClose asChild>
                <Button variant="outline">Close</Button>
              </DrawerClose>
            </DrawerFooter>
          </div>
        </DrawerContent>
      </Drawer>

      <AlertDialog
        open={!!rollbackTarget}
        onOpenChange={(o) => !o && setRollbackTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm Rollback</AlertDialogTitle>
            <AlertDialogDescription>
              Rollback &quot;{rollbackTarget?.agent.name}&quot; to version{" "}
              {rollbackTarget?.version}? Current configuration will be saved to
              version history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleRollback()}>
              Rollback
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
