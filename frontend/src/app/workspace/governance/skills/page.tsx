"use client";

import {
  DownloadIcon,
  PackageIcon,
  RefreshCwIcon,
  Trash2Icon,
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
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type SkillMarketEntry,
  checkUpdates,
  disableSkill,
  enableSkill,
  listMarketSkills,
  uninstallSkill,
} from "@/lib/api/skills";

export default function SkillManagementPage() {
  const [skills, setSkills] = useState<SkillMarketEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [updates, setUpdates] = useState<Record<string, unknown>[]>([]);
  const [checkingUpdates, setCheckingUpdates] = useState(false);

  const [installOpen, setInstallOpen] = useState(false);
  const [installForm, setInstallForm] = useState({
    skill_id: "",
    thread_id: "",
    path: "",
    version: "",
  });

  const [uninstallTarget, setUninstallTarget] =
    useState<SkillMarketEntry | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listMarketSkills();
      setSkills(data);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleToggle = async (skill: SkillMarketEntry) => {
    try {
      if (skill.enabled) {
        await disableSkill(skill.name);
        toast.success(`Disabled "${skill.name}"`);
      } else {
        await enableSkill(skill.name);
        toast.success(`Enabled "${skill.name}"`);
      }
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleInstall = async () => {
    try {
      const { installSkill } = await import("@/lib/api/skills");
      await installSkill({
        skill_id: installForm.skill_id,
        thread_id: installForm.thread_id,
        path: installForm.path,
        version: installForm.version || undefined,
      });
      toast.success(`Installed "${installForm.skill_id}"`);
      setInstallOpen(false);
      setInstallForm({ skill_id: "", thread_id: "", path: "", version: "" });
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleUninstall = async () => {
    if (!uninstallTarget) return;
    try {
      await uninstallSkill(uninstallTarget.name);
      toast.success(`Uninstalled "${uninstallTarget.name}"`);
      setUninstallTarget(null);
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleCheckUpdates = async () => {
    setCheckingUpdates(true);
    try {
      const data = await checkUpdates();
      setUpdates(data);
      if (data.length === 0) {
        toast.info("All skills are up to date");
      } else {
        toast.info(`${data.length} update(s) available`);
      }
    } catch (e) {
      toast.error(String(e));
    } finally {
      setCheckingUpdates(false);
    }
  };

  return (
    <div className="flex size-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">Skill Management</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            Install, enable, and manage skills
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => void handleCheckUpdates()}
            disabled={checkingUpdates}
          >
            <RefreshCwIcon
              className={`mr-1.5 h-4 w-4 ${checkingUpdates ? "animate-spin" : ""}`}
            />
            Check Updates
          </Button>
          <Button onClick={() => setInstallOpen(true)}>
            <DownloadIcon className="mr-1.5 h-4 w-4" />
            Install Skill
          </Button>
        </div>
      </div>

      {updates.length > 0 && (
        <div className="border-b bg-muted/50 px-6 py-3">
          <p className="mb-2 text-sm font-medium">
            Available Updates ({updates.length})
          </p>
          <div className="flex flex-wrap gap-2">
            {updates.map((u, i) => {
              const label =
                typeof u.skill_id === "string"
                  ? u.skill_id
                  : typeof u.name === "string"
                    ? u.name
                    : `update-${i}`;
              return (
                <Badge key={i} variant="outline">
                  {label}
                </Badge>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
            Loading...
          </div>
        ) : skills.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <PackageIcon className="text-muted-foreground h-10 w-10" />
            <p className="text-muted-foreground">No skills found</p>
            <Button variant="outline" onClick={() => setInstallOpen(true)}>
              <DownloadIcon className="mr-1.5 h-4 w-4" />
              Install Skill
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Installed</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {skills.map((s) => (
                <TableRow key={s.name}>
                  <TableCell>
                    <div>
                      <span className="font-medium">{s.name}</span>
                      <p className="text-muted-foreground text-xs">
                        {s.description}
                      </p>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{s.category}</Badge>
                  </TableCell>
                  <TableCell>
                    {s.version ? (
                      <Badge variant="secondary">{s.version}</Badge>
                    ) : (
                      <span className="text-muted-foreground text-sm">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={s.enabled}
                        onCheckedChange={() => void handleToggle(s)}
                      />
                      <span className="text-sm">
                        {s.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {s.installed_at
                      ? new Date(s.installed_at).toLocaleString()
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive"
                      onClick={() => setUninstallTarget(s)}
                    >
                      <Trash2Icon className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <Dialog open={installOpen} onOpenChange={setInstallOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Install Skill</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="skill_id">Skill ID</Label>
              <Input
                id="skill_id"
                value={installForm.skill_id}
                onChange={(e) =>
                  setInstallForm((f) => ({ ...f, skill_id: e.target.value }))
                }
                placeholder="e.g. my-custom-skill"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="thread_id">Thread ID</Label>
              <Input
                id="thread_id"
                value={installForm.thread_id}
                onChange={(e) =>
                  setInstallForm((f) => ({ ...f, thread_id: e.target.value }))
                }
                placeholder="Thread containing the .skill file"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="path">Path</Label>
              <Input
                id="path"
                value={installForm.path}
                onChange={(e) =>
                  setInstallForm((f) => ({ ...f, path: e.target.value }))
                }
                placeholder="e.g. mnt/user-data/outputs/skill.skill"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="version">Version (optional)</Label>
              <Input
                id="version"
                value={installForm.version}
                onChange={(e) =>
                  setInstallForm((f) => ({ ...f, version: e.target.value }))
                }
                placeholder="e.g. 1.0.0"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInstallOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => void handleInstall()}
              disabled={!installForm.skill_id || !installForm.thread_id || !installForm.path}
            >
              Install
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={!!uninstallTarget}
        onOpenChange={(o) => !o && setUninstallTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Uninstall Skill</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to uninstall &quot;{uninstallTarget?.name}
              &quot;? This will remove the skill and its configuration.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => void handleUninstall()}
            >
              Uninstall
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
