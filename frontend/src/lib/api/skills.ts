import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export interface SkillMarketEntry {
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  version: string | null;
  installed_at: string | null;
}

export interface InstallSkillRequest {
  skill_id: string;
  thread_id: string;
  path: string;
  version?: string | null;
}

export interface InstallSkillResponse {
  skill_id: string;
  install_path: string;
}

export interface UpdateSkillRequest {
  thread_id: string;
  path: string;
  version?: string | null;
}

const BASE = () => `${getBackendBaseURL()}/api/skills`;

export async function listMarketSkills(): Promise<SkillMarketEntry[]> {
  const res = await fetch(`${BASE()}/market`);
  if (!res.ok) throw new Error(`Failed to list market skills: ${res.statusText}`);
  const data = (await res.json()) as { skills: SkillMarketEntry[] };
  return data.skills;
}

export async function installSkill(
  data: InstallSkillRequest,
): Promise<InstallSkillResponse> {
  const res = await fetch(`${BASE()}/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to install skill: ${res.statusText}`);
  }
  return res.json() as Promise<InstallSkillResponse>;
}

export async function enableSkill(
  skillId: string,
  agentId?: string,
): Promise<void> {
  const body = agentId ? { agent_id: agentId } : {};
  const res = await fetch(`${BASE()}/${encodeURIComponent(skillId)}/enable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to enable skill: ${res.statusText}`);
  }
}

export async function disableSkill(
  skillId: string,
  agentId?: string,
): Promise<void> {
  const body = agentId ? { agent_id: agentId } : {};
  const res = await fetch(`${BASE()}/${encodeURIComponent(skillId)}/disable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to disable skill: ${res.statusText}`);
  }
}

export async function uninstallSkill(skillId: string): Promise<void> {
  const res = await fetch(`${BASE()}/${encodeURIComponent(skillId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to uninstall skill: ${res.statusText}`);
  }
}

export async function checkUpdates(): Promise<Record<string, unknown>[]> {
  const res = await fetch(`${BASE()}/check-updates`);
  if (!res.ok)
    throw new Error(`Failed to check updates: ${res.statusText}`);
  const data = (await res.json()) as { updates: Record<string, unknown>[] };
  return data.updates;
}

export async function updateSkill(
  skillId: string,
  data: UpdateSkillRequest,
): Promise<InstallSkillResponse> {
  const res = await fetch(
    `${BASE()}/${encodeURIComponent(skillId)}/update`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to update skill: ${res.statusText}`);
  }
  return res.json() as Promise<InstallSkillResponse>;
}
