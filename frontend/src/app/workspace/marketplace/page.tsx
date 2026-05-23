"use client";

import {
  DownloadIcon,
  PackageIcon,
  RefreshCwIcon,
  RotateCwIcon,
  SearchIcon,
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
import { Input } from "@/components/ui/input";
import {
  type MarketplaceSkillSummary,
  checkUpdates,
  installSkill,
  listMarketSkills,
  refreshIndex,
  uninstallSkill,
  updateSkill,
} from "@/lib/api/marketplace";

const CATEGORY_OPTIONS = [
  "all",
  "productivity",
  "development",
  "data",
  "communication",
  "automation",
  "other",
] as const;

type CategoryFilter = (typeof CATEGORY_OPTIONS)[number];

export default function MarketplacePage() {
  const [skills, setSkills] = useState<MarketplaceSkillSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<CategoryFilter>("all");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize] = useState(12);

  const [installingId, setInstallingId] = useState<string | null>(null);
  const [uninstallTarget, setUninstallTarget] =
    useState<MarketplaceSkillSummary | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const [updates, setUpdates] = useState<Record<string, unknown>[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listMarketSkills({
        page,
        page_size: pageSize,
        category: activeCategory !== "all" ? activeCategory : undefined,
        query: searchQuery || undefined,
      });
      setSkills(data.skills);
      setTotal(data.total);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, activeCategory, searchQuery]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInstall = async (skillId: string) => {
    setInstallingId(skillId);
    try {
      await installSkill(skillId);
      toast.success(`Installed "${skillId}"`);
      void load();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setInstallingId(null);
    }
  };

  const handleUninstall = async () => {
    if (!uninstallTarget) return;
    try {
      await uninstallSkill(uninstallTarget.skill_id);
      toast.success(`Uninstalled "${uninstallTarget.skill_id}"`);
      setUninstallTarget(null);
      void load();
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleUpdate = async (skillId: string) => {
    setUpdatingId(skillId);
    try {
      await updateSkill(skillId);
      toast.success(`Updated "${skillId}"`);
      void load();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setUpdatingId(null);
    }
  };

  const handleCheckUpdates = async () => {
    try {
      const data = await checkUpdates();
      setUpdates(data.updates);
      if (data.updates.length === 0) {
        toast.info("All skills are up to date");
      } else {
        toast.info(`${data.updates.length} update(s) available`);
      }
    } catch (e) {
      toast.error(String(e));
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshIndex();
      toast.success("Index refreshed");
      setPage(1);
      void load();
    } catch (e) {
      toast.error(String(e));
    } finally {
      setRefreshing(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="flex size-full flex-col">
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Skill Marketplace</h1>
            <p className="text-muted-foreground mt-0.5 text-sm">
              Browse, install, and manage skills from the marketplace
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => void handleCheckUpdates()}
            >
              <RotateCwIcon className="mr-1.5 h-4 w-4" />
              Check Updates
            </Button>
            <Button
              variant="outline"
              onClick={() => void handleRefresh()}
              disabled={refreshing}
            >
              <RefreshCwIcon
                className={`mr-1.5 h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
              />
              Refresh
            </Button>
          </div>
        </div>

        {updates.length > 0 && (
          <div className="mt-3 rounded-md bg-muted/50 px-4 py-2">
            <p className="mb-1 text-sm font-medium">
              Available Updates ({updates.length})
            </p>
            <div className="flex flex-wrap gap-2">
              {updates.map((u, i) => {
                const label =
                  typeof u.skill_id === "string"
                    ? u.skill_id
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
      </div>

      <div className="border-b px-6 py-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative max-w-sm flex-1">
            <SearchIcon className="text-muted-foreground absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
            <Input
              placeholder="Search skills..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
              className="pl-9"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORY_OPTIONS.map((cat) => (
              <Button
                key={cat}
                variant={activeCategory === cat ? "default" : "outline"}
                size="sm"
                onClick={() => {
                  setActiveCategory(cat);
                  setPage(1);
                }}
                className="capitalize"
              >
                {cat}
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="text-muted-foreground flex h-40 items-center justify-center text-sm">
            Loading...
          </div>
        ) : skills.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-center">
            <PackageIcon className="text-muted-foreground h-10 w-10" />
            <p className="text-muted-foreground">No skills found</p>
            <Button variant="outline" onClick={() => void handleRefresh()}>
              <RefreshCwIcon className="mr-1.5 h-4 w-4" />
              Refresh Index
            </Button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {skills.map((skill) => (
                <Link
                  key={skill.skill_id}
                  href={`/workspace/marketplace/skills/${skill.skill_id}`}
                >
                  <Card className="transition-colors hover:bg-muted/50">
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <CardTitle className="truncate text-base">
                            {skill.name}
                          </CardTitle>
                          <p className="text-muted-foreground mt-0.5 text-xs">
                            by {skill.author || "Unknown"}
                          </p>
                        </div>
                        <Badge
                          variant={
                            skill.installed ? "default" : "secondary"
                          }
                        >
                          {skill.installed ? "Installed" : "Available"}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <p className="text-muted-foreground mb-3 line-clamp-2 text-sm">
                        {skill.description}
                      </p>
                      <div className="mb-3 flex flex-wrap gap-1.5">
                        <Badge variant="outline" className="capitalize">
                          {skill.category}
                        </Badge>
                        {skill.version && (
                          <Badge variant="secondary">v{skill.version}</Badge>
                        )}
                        {skill.tags.slice(0, 3).map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                      <div
                        className="flex gap-1.5"
                        onClick={(e) => e.preventDefault()}
                      >
                        {!skill.installed ? (
                          <Button
                            size="sm"
                            onClick={() => void handleInstall(skill.skill_id)}
                            disabled={installingId === skill.skill_id}
                          >
                            {installingId === skill.skill_id ? (
                              <RefreshCwIcon className="mr-1 h-3 w-3 animate-spin" />
                            ) : (
                              <DownloadIcon className="mr-1 h-3 w-3" />
                            )}
                            Install
                          </Button>
                        ) : (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void handleUpdate(skill.skill_id)}
                              disabled={updatingId === skill.skill_id}
                            >
                              {updatingId === skill.skill_id ? (
                                <RefreshCwIcon className="mr-1 h-3 w-3 animate-spin" />
                              ) : (
                                <RotateCwIcon className="mr-1 h-3 w-3" />
                            )}
                            Update
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-destructive"
                              onClick={() => setUninstallTarget(skill)}
                            >
                              <Trash2Icon className="mr-1 h-3 w-3" />
                              Uninstall
                            </Button>
                          </>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <span className="text-muted-foreground text-sm">
                  Page {page} of {totalPages} ({total} skills)
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <AlertDialog
        open={!!uninstallTarget}
        onOpenChange={(o) => !o && setUninstallTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Uninstall Skill</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to uninstall
              &quot;{uninstallTarget?.name}&quot;? This will remove the skill
              and its configuration.
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
