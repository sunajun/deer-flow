import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export interface MarketplaceSkillSummary {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  category: string;
  tags: string[];
  author: string;
  installed: boolean;
  installed_version: string | null;
}

export interface MarketplaceSkillListResponse {
  skills: MarketplaceSkillSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface MarketplaceSkillDetail {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  category: string;
  tags: string[];
  author: string;
  homepage: string;
  repository: string;
  min_platform_version: string;
  dependencies: string[];
  permissions: string[];
  changelog: string;
  installed: boolean;
  installed_version: string | null;
}

export interface CategoryItem {
  category: string;
  count: number;
}

export interface CategoryListResponse {
  categories: CategoryItem[];
}

export interface UpdateCheckResponse {
  updates: Record<string, unknown>[];
}

export interface ListMarketSkillsParams {
  page?: number;
  page_size?: number;
  category?: string;
  query?: string;
}

const BASE = () => `${getBackendBaseURL()}/api/marketplace`;

export async function listMarketSkills(
  params?: ListMarketSkillsParams,
): Promise<MarketplaceSkillListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.page_size)
    searchParams.set("page_size", String(params.page_size));
  if (params?.category) searchParams.set("category", params.category);
  if (params?.query) searchParams.set("query", params.query);

  const qs = searchParams.toString();
  const url = qs ? `${BASE()}/skills?${qs}` : `${BASE()}/skills`;
  const res = await fetch(url);
  if (!res.ok)
    throw new Error(`Failed to list marketplace skills: ${res.statusText}`);
  return res.json() as Promise<MarketplaceSkillListResponse>;
}

export async function getMarketSkill(
  skillId: string,
): Promise<MarketplaceSkillDetail> {
  const res = await fetch(
    `${BASE()}/skills/${encodeURIComponent(skillId)}`,
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to get skill: ${res.statusText}`,
    );
  }
  return res.json() as Promise<MarketplaceSkillDetail>;
}

export async function listCategories(): Promise<CategoryListResponse> {
  const res = await fetch(`${BASE()}/categories`);
  if (!res.ok)
    throw new Error(`Failed to list categories: ${res.statusText}`);
  return res.json() as Promise<CategoryListResponse>;
}

export async function installSkill(
  skillId: string,
): Promise<{ success: boolean; skill_id: string; message: string }> {
  const res = await fetch(
    `${BASE()}/skills/${encodeURIComponent(skillId)}/install`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to install skill: ${res.statusText}`,
    );
  }
  return res.json() as Promise<{
    success: boolean;
    skill_id: string;
    message: string;
  }>;
}

export async function uninstallSkill(
  skillId: string,
): Promise<{ success: boolean; skill_id: string; message: string }> {
  const res = await fetch(
    `${BASE()}/skills/${encodeURIComponent(skillId)}/uninstall`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to uninstall skill: ${res.statusText}`,
    );
  }
  return res.json() as Promise<{
    success: boolean;
    skill_id: string;
    message: string;
  }>;
}

export async function checkUpdates(): Promise<UpdateCheckResponse> {
  const res = await fetch(`${BASE()}/updates`);
  if (!res.ok)
    throw new Error(`Failed to check updates: ${res.statusText}`);
  return res.json() as Promise<UpdateCheckResponse>;
}

export async function updateSkill(
  skillId: string,
): Promise<{ success: boolean; skill_id: string; message: string }> {
  const res = await fetch(
    `${BASE()}/skills/${encodeURIComponent(skillId)}/update`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to update skill: ${res.statusText}`,
    );
  }
  return res.json() as Promise<{
    success: boolean;
    skill_id: string;
    message: string;
  }>;
}

export async function refreshIndex(): Promise<{
  success: boolean;
  message: string;
}> {
  const res = await fetch(`${BASE()}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to refresh index: ${res.statusText}`,
    );
  }
  return res.json() as Promise<{ success: boolean; message: string }>;
}
