"use client";

import {
  ArrowLeftIcon,
  DownloadIcon,
  ExternalLinkIcon,
  RefreshCwIcon,
  RotateCwIcon,
  Trash2Icon,
} from "lucide-react";
import Link from "next/link";
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type MarketplaceSkillDetail,
  getMarketSkill,
  installSkill,
  uninstallSkill,
  updateSkill,
} from "@/lib/api/marketplace";

export default function SkillDetailPage({
  params,
}: {
  params: Promise<{ skillId: string }>;
}) {
  const [skill, setSkill] = useState<MarketplaceSkillDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [uninstallConfirm, setUninstallConfirm] = useState(false);
  const [updating, setUpdating] = useState(false);

  const [resolvedParams, setResolvedParams] = useState<{ skillId: string } | null>(null);

  useEffect(() => {
    void params.then(setResolvedParams);
  }, [params]);

  const load = useCallback(async () => {
    if (!resolvedParams) return;
    setLoading(true);
    try {
      const data = await getMarketSkill(resolvedParams.skillId);
      setSkill(data);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, [resolvedParams]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInstall = async () => {
    if (!skill) return;
    setInstalling(true);
    try {
      await installSkill(skill.skill_id);
      toast.success(`Installed "${skill.name}"`);
      void load();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setInstalling(false);
    }
  };

  const handleUninstall = async () => {
    if (!skill) return;
    try {
      await uninstallSkill(skill.skill_id);
      toast.success(`Uninstalled "${skill.name}"`);
      setUninstallConfirm(false);
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleUpdate = async () => {
    if (!skill) return;
    setUpdating(true);
    try {
      await updateSkill(skill.skill_id);
      toast.success(`Updated "${skill.name}"`);
      void load();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setUpdating(false);
    }
  };

  if (loading || !resolvedParams) {
    return (
      <div className="flex size-full flex-col">
        <div className="border-b px-6 py-4">
          <Link
            href="/workspace/marketplace"
            className="text-muted-foreground inline-flex items-center gap-1 text-sm hover:underline"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            Back to Marketplace
          </Link>
        </div>
        <div className="text-muted-foreground flex flex-1 items-center justify-center text-sm">
          Loading...
        </div>
      </div>
    );
  }

  if (!skill) {
    return (
      <div className="flex size-full flex-col">
        <div className="border-b px-6 py-4">
          <Link
            href="/workspace/marketplace"
            className="text-muted-foreground inline-flex items-center gap-1 text-sm hover:underline"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            Back to Marketplace
          </Link>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3">
          <p className="text-muted-foreground">Skill not found</p>
          <Link href="/workspace/marketplace">
            <Button variant="outline">Return to Marketplace</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex size-full flex-col">
      <div className="border-b px-6 py-4">
        <Link
          href="/workspace/marketplace"
          className="text-muted-foreground inline-flex items-center gap-1 text-sm hover:underline"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to Marketplace
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-3xl space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold">{skill.name}</h1>
              <p className="text-muted-foreground mt-1">
                by {skill.author || "Unknown"} · v{skill.version}
              </p>
            </div>
            <div className="flex gap-2">
              {!skill.installed ? (
                <Button
                  onClick={() => void handleInstall()}
                  disabled={installing}
                >
                  {installing ? (
                    <RefreshCwIcon className="mr-1.5 h-4 w-4 animate-spin" />
                  ) : (
                    <DownloadIcon className="mr-1.5 h-4 w-4" />
                  )}
                  Install
                </Button>
              ) : (
                <>
                  <Button
                    variant="outline"
                    onClick={() => void handleUpdate()}
                    disabled={updating}
                  >
                    {updating ? (
                      <RefreshCwIcon className="mr-1.5 h-4 w-4 animate-spin" />
                    ) : (
                      <RotateCwIcon className="mr-1.5 h-4 w-4" />
                  )}
                  Update
                  </Button>
                  <Button
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => setUninstallConfirm(true)}
                  >
                    <Trash2Icon className="mr-1.5 h-4 w-4" />
                    Uninstall
                  </Button>
                </>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Badge
              variant={skill.installed ? "default" : "secondary"}
            >
              {skill.installed ? "Installed" : "Available"}
            </Badge>
            <Badge variant="outline" className="capitalize">
              {skill.category}
            </Badge>
            {skill.installed_version && (
              <Badge variant="secondary">
                Installed: v{skill.installed_version}
              </Badge>
            )}
            {skill.tags.map((tag) => (
              <Badge key={tag} variant="outline">
                {tag}
              </Badge>
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Description</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-sm">
                {skill.description}
              </p>
            </CardContent>
          </Card>

          {(skill.repository || skill.homepage) && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Links</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {skill.repository && (
                  <a
                    href={skill.repository}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary inline-flex items-center gap-1.5 text-sm hover:underline"
                  >
                    <ExternalLinkIcon className="h-3.5 w-3.5" />
                    Repository
                  </a>
                )}
                {skill.homepage && (
                  <a
                    href={skill.homepage}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary inline-flex items-center gap-1.5 text-sm hover:underline"
                  >
                    <ExternalLinkIcon className="h-3.5 w-3.5" />
                    Homepage
                  </a>
                )}
              </CardContent>
            </Card>
          )}

          {skill.dependencies.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Dependencies</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-inside list-disc space-y-1">
                  {skill.dependencies.map((dep) => (
                    <li
                      key={dep}
                      className="text-muted-foreground text-sm"
                    >
                      {dep}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {skill.permissions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Required Permissions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1.5">
                  {skill.permissions.map((perm) => (
                    <Badge key={perm} variant="outline">
                      {perm}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {skill.changelog && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Changelog</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground whitespace-pre-wrap text-sm">
                  {skill.changelog}
                </p>
              </CardContent>
            </Card>
          )}

          {skill.min_platform_version && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Minimum Platform Version
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground text-sm">
                  {skill.min_platform_version}
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <AlertDialog
        open={uninstallConfirm}
        onOpenChange={setUninstallConfirm}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Uninstall Skill</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to uninstall &quot;{skill.name}&quot;? This
              will remove the skill and its configuration.
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
