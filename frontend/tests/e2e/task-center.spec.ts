import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const MOCK_TASKS = [
  {
    task_id: "task_abc12345",
    thread_id: "thread_001",
    task_type: "manual",
    name: "Research Task",
    description: "A research task for testing",
    status: "success",
    created_at: "2025-01-15T10:00:00Z",
    started_at: "2025-01-15T10:00:05Z",
    finished_at: "2025-01-15T10:05:00Z",
    duration: 295,
    result: { summary: "Research completed" },
    error: null,
    log_ids: ["log_1"],
    created_by: "default",
    parent_task_id: null,
  },
  {
    task_id: "task_def67890",
    thread_id: "thread_002",
    task_type: "subagent",
    name: "Sub-agent Task",
    description: "A sub-agent task",
    status: "running",
    created_at: "2025-01-15T11:00:00Z",
    started_at: "2025-01-15T11:00:02Z",
    finished_at: null,
    duration: null,
    result: null,
    error: null,
    log_ids: [],
    created_by: "default",
    parent_task_id: "task_abc12345",
  },
  {
    task_id: "task_ghi11111",
    thread_id: "thread_003",
    task_type: "scheduled",
    name: "Scheduled Report",
    description: "Failed scheduled report",
    status: "failed",
    created_at: "2025-01-15T09:00:00Z",
    started_at: "2025-01-15T09:00:01Z",
    finished_at: "2025-01-15T09:01:00Z",
    duration: 59,
    result: null,
    error: "Connection timeout",
    log_ids: ["log_2"],
    created_by: "default",
    parent_task_id: null,
  },
];

const LOGS_RE = /\/api\/tasks\/[^/]+\/logs$/;
const RETRY_RE = /\/api\/tasks\/[^/]+\/retry$/;
const RERUN_RE = /\/api\/tasks\/[^/]+\/rerun$/;
const CANCEL_RE = /\/api\/tasks\/[^/]+\/cancel$/;
const EXPORT_RE = /\/api\/tasks\/[^/]+\/export$/;
const DETAIL_RE = /\/api\/tasks\/([^/?]+)$/;

function mockTaskAPI(page: Page) {
  void page.route("**/api/tasks*", (route) => {
    const url = route.request().url();

    if (LOGS_RE.exec(url)) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          task_id: "task_abc12345",
          logs: [
            "[2025-01-15T10:00:05] Task started",
            "[2025-01-15T10:02:00] Processing data...",
            "[2025-01-15T10:05:00] Task completed",
          ],
        }),
      });
    }

    if (RETRY_RE.exec(url)) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_TASKS[2],
          status: "pending",
          error: null,
        }),
      });
    }

    if (RERUN_RE.exec(url)) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_TASKS[0],
          task_id: "task_new_rerun",
          status: "pending",
        }),
      });
    }

    if (CANCEL_RE.exec(url)) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_TASKS[1],
          status: "cancelled",
        }),
      });
    }

    if (EXPORT_RE.exec(url)) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          task_id: "task_abc12345",
          name: "Research Task",
          status: "success",
          timeline: {},
          result: null,
          error: null,
          logs: [],
        }),
      });
    }

    const detailMatch = DETAIL_RE.exec(url);
    if (detailMatch && !LOGS_RE.exec(url) && !RETRY_RE.exec(url) && !RERUN_RE.exec(url) && !CANCEL_RE.exec(url) && !EXPORT_RE.exec(url)) {
      const task = MOCK_TASKS.find((t) => t.task_id === detailMatch[1]);
      if (task) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(task),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ error: "Task not found" }),
      });
    }

    const statusParam = new URL(url).searchParams.get("status");
    let filtered = MOCK_TASKS;
    if (statusParam) {
      filtered = MOCK_TASKS.filter((t) => t.status === statusParam);
    }
    const typeParam = new URL(url).searchParams.get("task_type");
    if (typeParam) {
      filtered = filtered.filter((t) => t.task_type === typeParam);
    }

    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        tasks: filtered,
        page: 1,
        page_size: 20,
      }),
    });
  });
}

test.describe("Task Center", () => {
  test("task list page displays tasks", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks");

    await expect(page.locator("table")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Research Task")).toBeVisible();
    await expect(page.getByText("Sub-agent Task")).toBeVisible();
    await expect(page.getByText("Scheduled Report")).toBeVisible();
  });

  test("task list status filter", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks");

    await expect(page.locator("table")).toBeVisible({ timeout: 15_000 });

    const statusSelect = page.locator("[data-slot='select-trigger']").first();
    await statusSelect.click();
    await page.getByText("Failed").click();

    await expect(page.getByText("Scheduled Report")).toBeVisible();
    await expect(page.getByText("Research Task")).not.toBeVisible();
  });

  test("task list pagination", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks");

    await expect(page.locator("table")).toBeVisible({ timeout: 15_000 });

    const prevButton = page.getByRole("button", { name: /previous|上一页/i });
    const nextButton = page.getByRole("button", { name: /next|下一页/i });

    await expect(prevButton).toBeDisabled();
    await expect(nextButton).toBeDisabled();
  });

  test("task detail page shows task info", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks/task_abc12345");

    await expect(page.getByText("Research Task")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("task_abc12345")).toBeVisible();
  });

  test("task retry operation", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks");

    await expect(page.locator("table")).toBeVisible({ timeout: 15_000 });

    const retryButton = page.getByRole("button", { name: /retry|重试/i }).first();
    if (await retryButton.isVisible()) {
      await retryButton.click();
      const confirmButton = page
        .getByRole("dialog")
        .getByRole("button", { name: /retry|重试/i });
      if (await confirmButton.isVisible()) {
        await confirmButton.click();
      }
    }
  });

  test("task cancel operation", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks");

    await expect(page.locator("table")).toBeVisible({ timeout: 15_000 });

    const cancelButton = page.getByRole("button", { name: /cancel|取消/i }).first();
    if (await cancelButton.isVisible()) {
      await cancelButton.click();
      const confirmButton = page
        .getByRole("dialog")
        .getByRole("button", { name: /cancel|取消/i });
      if (await confirmButton.isVisible()) {
        await confirmButton.click();
      }
    }
  });

  test("log viewer displays logs", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks/task_abc12345");

    await expect(page.getByText("Research Task")).toBeVisible({
      timeout: 15_000,
    });

    const logsTab = page.getByRole("tab", { name: /logs|日志/i });
    if (await logsTab.isVisible()) {
      await logsTab.click();
      await expect(page.getByText("Task started")).toBeVisible();
    }
  });

  test("audit export", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/tasks/task_abc12345");

    await expect(page.getByText("Research Task")).toBeVisible({
      timeout: 15_000,
    });

    const exportButton = page.getByRole("button", { name: /export|导出审计/i });
    if (await exportButton.isVisible()) {
      await exportButton.click();
    }
  });

  test("sidebar navigation to task center", async ({ page }) => {
    mockLangGraphAPI(page);
    mockTaskAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    const tasksLink = sidebar.locator("a[href='/workspace/tasks']");
    await expect(tasksLink).toBeVisible({ timeout: 15_000 });
    await tasksLink.click();

    await page.waitForURL("**/workspace/tasks");
    await expect(page).toHaveURL(/\/workspace\/tasks/);
  });
});
