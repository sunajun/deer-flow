"use client";

import { CheckCircle2Icon, XCircleIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  type CheckAccessRequest,
  type CheckAccessResponse,
  type PermissionRule,
  type RoleData,
  checkAccess,
  listRoles,
  updateRole,
} from "@/lib/api/governance";

const SCENES = [
  "conversation",
  "planning",
  "file_operation",
  "code_generation",
  "data_analysis",
];

const ROLE_LABELS: Record<string, { label: string; description: string }> = {
  admin: {
    label: "Admin",
    description: "Full control permissions",
  },
  user: {
    label: "User",
    description: "Daily usage permissions",
  },
  guest: {
    label: "Guest",
    description: "Read-only conversation permissions",
  },
};

export default function PermissionsPage() {
  const [roles, setRoles] = useState<Record<string, RoleData>>({});
  const [loading, setLoading] = useState(true);
  const [expandedRole, setExpandedRole] = useState<string | null>(null);
  const [editData, setEditData] = useState<Record<string, PermissionRule>>({});
  const [saving, setSaving] = useState<string | null>(null);

  const [accessCheck, setAccessCheck] = useState<CheckAccessRequest>({
    role: "guest",
    resource_type: "tool",
    resource_id: "chat",
  });
  const [accessResult, setAccessResult] = useState<CheckAccessResponse | null>(
    null,
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listRoles();
      setRoles(data);
      const initial: Record<string, PermissionRule> = {};
      for (const [key, role] of Object.entries(data)) {
        initial[key] = { ...role.permissions };
      }
      setEditData(initial);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async (roleKey: string) => {
    const permissions = editData[roleKey];
    if (!permissions) return;
    setSaving(roleKey);
    try {
      await updateRole(roleKey, permissions);
      toast.success(`Role "${roleKey}" updated`);
      void load();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSaving(null);
    }
  };

  const toggleScene = (
    roleKey: string,
    scene: string,
    checked: boolean,
  ) => {
    const current = editData[roleKey];
    if (!current) return;
    const next = checked
      ? [...current.allowed_scenes, scene]
      : current.allowed_scenes.filter((s) => s !== scene);
    setEditData((d) => ({
      ...d,
      [roleKey]: { ...current, allowed_scenes: next },
    }));
  };

  const handleCheckAccess = async () => {
    try {
      const result = await checkAccess(accessCheck);
      setAccessResult(result);
    } catch (e) {
      toast.error(String(e));
    }
  };

  if (loading) {
    return (
      <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex size-full flex-col">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-semibold">Permission Configuration</h1>
        <p className="text-muted-foreground mt-0.5 text-sm">
          Configure role-based access control
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid gap-4">
          {Object.entries(roles).map(([roleKey, roleData]) => {
            const meta = ROLE_LABELS[roleKey] ?? {
              label: roleKey,
              description: roleData.description,
            };
            const permissions = editData[roleKey] ?? roleData.permissions;
            const isExpanded = expandedRole === roleKey;

            return (
              <Collapsible
                key={roleKey}
                open={isExpanded}
                onOpenChange={(open) =>
                  setExpandedRole(open ? roleKey : null)
                }
              >
                <Card>
                  <CollapsibleTrigger asChild>
                    <CardHeader className="cursor-pointer select-none">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <CardTitle className="text-base">
                            {meta.label}
                          </CardTitle>
                          <Badge variant="outline">{roleKey}</Badge>
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <span className="text-muted-foreground">
                            {permissions.allowed_scenes.length} scenes,{" "}
                            {permissions.allowed_tools.length} tools
                          </span>
                          <span className="text-muted-foreground">
                            {isExpanded ? "▲" : "▼"}
                          </span>
                        </div>
                      </div>
                      <p className="text-muted-foreground mt-1 text-sm">
                        {meta.description}
                      </p>
                    </CardHeader>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <CardContent className="space-y-6 pt-0">
                      <div className="grid gap-2">
                        <Label className="text-sm font-medium">
                          Allowed Scenes
                        </Label>
                        <div className="flex flex-wrap gap-3">
                          {SCENES.map((s) => (
                            <label
                              key={s}
                              className="flex items-center gap-1.5 text-sm"
                            >
                              <Checkbox
                                checked={permissions.allowed_scenes.includes(s)}
                                onCheckedChange={(c) =>
                                  toggleScene(roleKey, s, !!c)
                                }
                              />
                              {s}
                            </label>
                          ))}
                        </div>
                      </div>

                      <div className="grid gap-2">
                        <Label className="text-sm font-medium">
                          Allowed Tools
                        </Label>
                        <Input
                          value={permissions.allowed_tools.join(", ")}
                          onChange={(e) => {
                            const tools = e.target.value
                              .split(",")
                              .map((t) => t.trim())
                              .filter(Boolean);
                            setEditData((d) => ({
                              ...d,
                              [roleKey]: {
                                ...permissions,
                                allowed_tools: tools,
                              },
                            }));
                          }}
                          placeholder="e.g. *, !agent_manage, !skill_manage"
                        />
                        <p className="text-muted-foreground text-xs">
                          Use * for wildcard, ! prefix for exclusion (e.g. *,
                          !agent_manage)
                        </p>
                      </div>

                      <div className="grid gap-2">
                        <Label className="text-sm font-medium">
                          Max Parallel Sessions:{" "}
                          {permissions.max_parallel_sessions}
                        </Label>
                        <Slider
                          value={[permissions.max_parallel_sessions]}
                          min={1}
                          max={20}
                          step={1}
                          onValueChange={([v]) =>
                            setEditData((d) => ({
                              ...d,
                              [roleKey]: {
                                ...permissions,
                                max_parallel_sessions: v ?? 1,
                              },
                            }))
                          }
                        />
                      </div>

                      <div className="grid gap-3">
                        <Label className="text-sm font-medium">
                          Feature Toggles
                        </Label>
                        <div className="space-y-2">
                          {(
                            [
                              ["can_create_agents", "Can create agents"],
                              ["can_manage_skills", "Can manage skills"],
                              [
                                "can_schedule_tasks",
                                "Can schedule tasks",
                              ],
                            ] as const
                          ).map(([key, label]) => (
                            <label
                              key={key}
                              className="flex items-center gap-2 text-sm"
                            >
                              <Checkbox
                                checked={permissions[key]}
                                onCheckedChange={(c) =>
                                  setEditData((d) => ({
                                    ...d,
                                    [roleKey]: {
                                      ...permissions,
                                      [key]: !!c,
                                    },
                                  }))
                                }
                              />
                              {label}
                            </label>
                          ))}
                        </div>
                      </div>

                      <Button
                        onClick={() => void handleSave(roleKey)}
                        disabled={saving === roleKey}
                      >
                        {saving === roleKey ? "Saving..." : "Save Changes"}
                      </Button>
                    </CardContent>
                  </CollapsibleContent>
                </Card>
              </Collapsible>
            );
          })}
        </div>

        <div className="mt-8">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Permission Preview — Check Access
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="grid gap-2">
                  <Label>Role</Label>
                  <select
                    className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                    value={accessCheck.role}
                    onChange={(e) =>
                      setAccessCheck((a) => ({ ...a, role: e.target.value }))
                    }
                  >
                    <option value="admin">admin</option>
                    <option value="user">user</option>
                    <option value="guest">guest</option>
                  </select>
                </div>
                <div className="grid gap-2">
                  <Label>Resource Type</Label>
                  <select
                    className="border-input bg-background rounded-md border px-3 py-2 text-sm"
                    value={accessCheck.resource_type}
                    onChange={(e) =>
                      setAccessCheck((a) => ({
                        ...a,
                        resource_type: e.target.value as "scene" | "tool",
                      }))
                    }
                  >
                    <option value="scene">scene</option>
                    <option value="tool">tool</option>
                  </select>
                </div>
                <div className="grid gap-2">
                  <Label>Resource ID</Label>
                  <Input
                    value={accessCheck.resource_id}
                    onChange={(e) =>
                      setAccessCheck((a) => ({
                        ...a,
                        resource_id: e.target.value,
                      }))
                    }
                    placeholder="e.g. chat, conversation"
                  />
                </div>
              </div>
              <Button onClick={() => void handleCheckAccess()}>
                Check Access
              </Button>
              {accessResult && (
                <div
                  className={`flex items-center gap-2 rounded-md p-3 text-sm ${
                    accessResult.allowed
                      ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
                      : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
                  }`}
                >
                  {accessResult.allowed ? (
                    <CheckCircle2Icon className="h-4 w-4" />
                  ) : (
                    <XCircleIcon className="h-4 w-4" />
                  )}
                  <span>
                    Role &quot;{accessResult.role}&quot;{" "}
                    {accessResult.allowed ? "can" : "cannot"} access{" "}
                    {accessResult.resource_type} &quot;{accessResult.resource_id}
                    &quot;
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
