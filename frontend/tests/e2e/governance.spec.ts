import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const MOCK_AGENT_CONFIGS = [
  {
    name: "test-agent",
    description: "A test agent",
    model: "deepseek-chat",
    tool_groups: ["search", "code"],
    skills: null,
    version: "1.0.0",
    allowed_scenes: ["conversation"],
    skill_whitelist: null,
    skill_blacklist: null,
    max_retries: 3,
    temperature: 0.7,
    system_prompt_suffix: "",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
];

const MOCK_SKILLS = [
  {
    name: "web-search",
    description: "Search the web",
    category: "public",
    enabled: true,
    version: "1.0.0",
    installed_at: "2025-01-01T00:00:00Z",
  },
  {
    name: "code-gen",
    description: "Generate code",
    category: "custom",
    enabled: false,
    version: null,
    installed_at: null,
  },
];

const MOCK_ROLES = {
  admin: {
    role_type: "admin",
    name: "Admin",
    description: "Full control permissions",
    permissions: {
      allowed_scenes: ["*"],
      allowed_tools: ["*"],
      max_parallel_sessions: 10,
      can_create_agents: true,
      can_manage_skills: true,
      can_schedule_tasks: true,
    },
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  user: {
    role_type: "user",
    name: "User",
    description: "Daily usage permissions",
    permissions: {
      allowed_scenes: ["conversation", "planning", "file_operation"],
      allowed_tools: ["*", "!agent_manage", "!skill_manage"],
      max_parallel_sessions: 3,
      can_create_agents: false,
      can_manage_skills: false,
      can_schedule_tasks: true,
    },
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  guest: {
    role_type: "guest",
    name: "Guest",
    description: "Read-only conversation permissions",
    permissions: {
      allowed_scenes: ["conversation"],
      allowed_tools: ["chat", "clarify"],
      max_parallel_sessions: 1,
      can_create_agents: false,
      can_manage_skills: false,
      can_schedule_tasks: false,
    },
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
};

function mockGovernanceAPI(page: Page) {
  mockLangGraphAPI(page);

  void page.route("**/api/agent-configs", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ configs: MOCK_AGENT_CONFIGS }),
      });
    }
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_AGENT_CONFIGS[0],
          name: "new-agent",
          description: "New agent",
        }),
      });
    }
    return route.fallback();
  });

  void page.route("**/api/agent-configs/*/versions", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        versions: [
          {
            agent_name: "test-agent",
            version: "1.0.0",
            snapshot: MOCK_AGENT_CONFIGS[0],
            created_at: "2025-01-01T00:00:00Z",
            change_summary: "Initial version",
          },
        ],
      }),
    });
  });

  void page.route("**/api/agent-configs/*/rollback", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_AGENT_CONFIGS[0]),
    });
  });

  void page.route("**/api/agent-configs/*", (route) => {
    if (route.request().method() === "PUT") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_AGENT_CONFIGS[0],
          description: "Updated",
        }),
      });
    }
    if (route.request().method() === "DELETE") {
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fallback();
  });

  void page.route("**/api/skills/market", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ skills: MOCK_SKILLS }),
    });
  });

  void page.route("**/api/skills/*/enable", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true }),
    });
  });

  void page.route("**/api/skills/*/disable", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true }),
    });
  });

  void page.route("**/api/skills/check-updates", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ updates: [] }),
    });
  });

  void page.route("**/api/governance/roles", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ roles: MOCK_ROLES }),
    });
  });

  void page.route("**/api/governance/roles/*", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_ROLES.guest),
    });
  });

  void page.route("**/api/governance/check-access", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        role: "guest",
        resource_type: "tool",
        resource_id: "chat",
        allowed: true,
      }),
    });
  });
}

test.describe("Governance - Sidebar Navigation", () => {
  test("governance nav link is visible in sidebar", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    await expect(
      sidebar.locator("a[href='/workspace/governance']"),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("clicking governance link navigates to governance page", async ({
    page,
  }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    const governanceLink = sidebar.locator(
      "a[href='/workspace/governance']",
    );
    await expect(governanceLink).toBeVisible({ timeout: 15_000 });
    await governanceLink.click();

    await page.waitForURL("**/workspace/governance");
    await expect(page).toHaveURL(/\/workspace\/governance$/);
  });
});

test.describe("Governance - Agent Management Page", () => {
  test("displays agent config list", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/agents");

    await expect(page.getByText("test-agent")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("deepseek-chat")).toBeVisible();
  });

  test("create agent dialog opens and has form fields", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/agents");

    const createButton = page.getByRole("button", {
      name: /create agent/i,
    });
    await expect(createButton).toBeVisible({ timeout: 15_000 });
    await createButton.click();

    await expect(page.getByText("Create Agent Config")).toBeVisible();
    await expect(page.getByLabel("Name")).toBeVisible();
    await expect(page.getByLabel("Description")).toBeVisible();
  });

  test("delete confirmation dialog appears", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/agents");

    await expect(page.getByText("test-agent")).toBeVisible({
      timeout: 15_000,
    });

    const menuButton = page
      .getByRole("row")
      .filter({ hasText: "test-agent" })
      .getByRole("button")
      .last();
    await menuButton.click();

    await page.getByText("Delete").click();

    await expect(
      page.getByText(/are you sure you want to delete/i),
    ).toBeVisible();
  });
});

test.describe("Governance - Skill Management Page", () => {
  test("displays skill list with enable/disable toggles", async ({
    page,
  }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/skills");

    await expect(page.getByText("web-search")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("code-gen")).toBeVisible();
  });

  test("install skill dialog opens", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/skills");

    const installButton = page.getByRole("button", {
      name: /install skill/i,
    });
    await expect(installButton).toBeVisible({ timeout: 15_000 });
    await installButton.click();

    await expect(page.getByText("Install Skill")).toBeVisible();
    await expect(page.getByLabel("Skill ID")).toBeVisible();
  });

  test("check updates button is present", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/skills");

    await expect(
      page.getByRole("button", { name: /check updates/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Governance - Permission Configuration Page", () => {
  test("displays role cards", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/permissions");

    await expect(page.getByText("Admin")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("User")).toBeVisible();
    await expect(page.getByText("Guest")).toBeVisible();
  });

  test("permission preview check access works", async ({ page }) => {
    mockGovernanceAPI(page);

    await page.goto("/workspace/governance/permissions");

    await expect(
      page.getByText("Permission Preview"),
    ).toBeVisible({ timeout: 15_000 });

    const checkButton = page.getByRole("button", {
      name: /check access/i,
    });
    await expect(checkButton).toBeVisible();
    await checkButton.click();

    await expect(page.getByText(/can access/i)).toBeVisible();
  });
});
