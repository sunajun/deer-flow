import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export interface PermissionRule {
  allowed_scenes: string[];
  allowed_tools: string[];
  max_parallel_sessions: number;
  can_create_agents: boolean;
  can_manage_skills: boolean;
  can_schedule_tasks: boolean;
}

export interface RoleData {
  role_type: string;
  name: string;
  description: string;
  permissions: PermissionRule;
  created_at: string;
  updated_at: string;
}

export interface CheckAccessRequest {
  role: string;
  resource_type: "scene" | "tool";
  resource_id: string;
}

export interface CheckAccessResponse {
  role: string;
  resource_type: string;
  resource_id: string;
  allowed: boolean;
}

const BASE = () => `${getBackendBaseURL()}/api/governance`;

export async function listRoles(): Promise<Record<string, RoleData>> {
  const res = await fetch(`${BASE()}/roles`);
  if (!res.ok) throw new Error(`Failed to list roles: ${res.statusText}`);
  const data = (await res.json()) as { roles: Record<string, RoleData> };
  return data.roles;
}

export async function updateRole(
  role: string,
  permissions: PermissionRule,
): Promise<RoleData> {
  const res = await fetch(`${BASE()}/roles/${encodeURIComponent(role)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(permissions),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to update role: ${res.statusText}`);
  }
  return res.json() as Promise<RoleData>;
}

export async function checkAccess(
  params: CheckAccessRequest,
): Promise<CheckAccessResponse> {
  const res = await fetch(`${BASE()}/check-access`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to check access: ${res.statusText}`);
  }
  return res.json() as Promise<CheckAccessResponse>;
}
