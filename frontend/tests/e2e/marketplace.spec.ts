import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const MOCK_MARKETPLACE_SKILLS = [
  {
    skill_id: "web-search",
    name: "Web Search",
    description: "Search the web for information",
    version: "1.0.0",
    category: "productivity",
    tags: ["search", "web"],
    author: "deerflow",
    installed: true,
    installed_version: "1.0.0",
  },
  {
    skill_id: "code-gen",
    name: "Code Generator",
    description: "Generate code from descriptions",
    version: "2.0.0",
    category: "development",
    tags: ["code", "generation"],
    author: "community",
    installed: false,
    installed_version: null,
  },
  {
    skill_id: "data-analyzer",
    name: "Data Analyzer",
    description: "Analyze and visualize data",
    version: "1.2.0",
    category: "data",
    tags: ["data", "analysis"],
    author: "deerflow",
    installed: false,
    installed_version: null,
  },
];

const MOCK_SKILL_DETAIL = {
  skill_id: "web-search",
  name: "Web Search",
  description: "Search the web for information using various search engines",
  version: "1.0.0",
  category: "productivity",
  tags: ["search", "web"],
  author: "deerflow",
  homepage: "https://example.com/web-search",
  repository: "https://github.com/example/web-search",
  min_platform_version: "0.1.0",
  dependencies: ["httpx"],
  permissions: ["network"],
  changelog: "Initial release",
  installed: true,
  installed_version: "1.0.0",
};

const MOCK_CATEGORIES = {
  categories: [
    { category: "productivity", count: 1 },
    { category: "development", count: 1 },
    { category: "data", count: 1 },
  ],
};

function mockMarketplaceAPI(page: Page) {
  mockLangGraphAPI(page);

  void page.route("**/api/marketplace/skills*", (route) => {
    const url = new URL(route.request().url());
    const category = url.searchParams.get("category");
    const query = url.searchParams.get("query");

    let skills = MOCK_MARKETPLACE_SKILLS;
    if (category && category !== "all") {
      skills = skills.filter((s) => s.category === category);
    }
    if (query) {
      const q = query.toLowerCase();
      skills = skills.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q),
      );
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        skills,
        total: skills.length,
        page: 1,
        page_size: 20,
      }),
    });
  });

  void page.route("**/api/marketplace/skills/web-search", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SKILL_DETAIL),
    });
  });

  void page.route("**/api/marketplace/skills/*/install", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        skill_id: "code-gen",
        message: "Skill installed",
      }),
    });
  });

  void page.route("**/api/marketplace/skills/*/uninstall", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        skill_id: "web-search",
        message: "Skill uninstalled",
      }),
    });
  });

  void page.route("**/api/marketplace/skills/*/update", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        skill_id: "web-search",
        message: "Skill updated",
      }),
    });
  });

  void page.route("**/api/marketplace/updates", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ updates: [] }),
    });
  });

  void page.route("**/api/marketplace/categories", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_CATEGORIES),
    });
  });

  void page.route("**/api/marketplace/refresh", (route) => {
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, message: "Index refreshed" }),
    });
  });
}

test.describe("Marketplace - Sidebar Navigation", () => {
  test("marketplace nav link is visible in sidebar", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    await expect(
      sidebar.locator("a[href='/workspace/marketplace']"),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("clicking marketplace link navigates to marketplace page", async ({
    page,
  }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    const marketplaceLink = sidebar.locator(
      "a[href='/workspace/marketplace']",
    );
    await expect(marketplaceLink).toBeVisible({ timeout: 15_000 });
    await marketplaceLink.click();

    await page.waitForURL("**/workspace/marketplace");
    await expect(page).toHaveURL(/\/workspace\/marketplace$/);
  });
});

test.describe("Marketplace - Skill List Page", () => {
  test("displays skill cards in the marketplace", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace");

    await expect(page.getByText("Web Search")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Code Generator")).toBeVisible();
    await expect(page.getByText("Data Analyzer")).toBeVisible();
  });

  test("search filters skills", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace");

    await expect(page.getByText("Web Search")).toBeVisible({
      timeout: 15_000,
    });

    const searchInput = page.getByPlaceholder("Search skills...");
    await searchInput.fill("code");

    await expect(page.getByText("Code Generator")).toBeVisible();
  });

  test("category filter buttons are present", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace");

    await expect(
      page.getByRole("button", { name: /productivity/i }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("button", { name: /development/i }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /data/i })).toBeVisible();
  });

  test("installed badge shows on installed skills", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace");

    const webSearchCard = page
      .locator("[class*='card']")
      .filter({ hasText: "Web Search" });
    await expect(webSearchCard.getByText("Installed")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("refresh button is present", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace");

    await expect(
      page.getByRole("button", { name: /refresh/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Marketplace - Skill Detail Page", () => {
  test("displays skill detail information", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace/skills/web-search");

    await expect(page.getByText("Web Search")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("by deerflow")).toBeVisible();
    await expect(
      page.getByText("Search the web for information using various search engines"),
    ).toBeVisible();
  });

  test("shows repository link", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace/skills/web-search");

    await expect(
      page.getByRole("link", { name: /repository/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("shows dependencies and permissions", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace/skills/web-search");

    await expect(page.getByText("Dependencies")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("httpx")).toBeVisible();
    await expect(page.getByText("Required Permissions")).toBeVisible();
    await expect(page.getByText("network")).toBeVisible();
  });

  test("shows changelog", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace/skills/web-search");

    await expect(page.getByText("Changelog")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Initial release")).toBeVisible();
  });

  test("uninstall button is present for installed skills", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace/skills/web-search");

    await expect(
      page.getByRole("button", { name: /uninstall/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("back link navigates to marketplace", async ({ page }) => {
    mockMarketplaceAPI(page);

    await page.goto("/workspace/marketplace/skills/web-search");

    const backLink = page.getByRole("link", {
      name: /back to marketplace/i,
    });
    await expect(backLink).toBeVisible({ timeout: 15_000 });
  });
});
