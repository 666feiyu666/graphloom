import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

const backendDir = path.resolve(process.cwd(), "../backend");
const dbPath = path.resolve(process.cwd(), ".e2e", "graphloom.db");
const projectName = "E2E synthetic project";

let ownerToken = "";

test.beforeAll(() => {
  const output = execFileSync(
    "uv",
    ["run", "python", "-m", "app.cli", "init-owner", "--label", "owner"],
    {
      cwd: backendDir,
      env: { ...process.env, GRAPPHLOOM_DB_PATH: dbPath },
      encoding: "utf8",
    },
  );
  ownerToken = JSON.parse(output).token;
});

async function connect(page: Page) {
  await page.goto("/");
  await page.getByLabel("OWNER TOKEN").fill(ownerToken);
  await page.getByRole("button", { name: "Open workbench" }).click();
  await expect(page.getByRole("heading", { name: "Projects", exact: true })).toBeVisible();
}

async function openProject(page: Page) {
  await connect(page);
  await page.getByRole("button", { name: new RegExp(projectName) }).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();
}

async function createDraftObject(
  page: Page,
  kind: string,
  label: string,
  definition: string,
  extra?: () => Promise<void>,
) {
  await page.getByLabel("Kind to create").selectOption(kind);
  await page.getByRole("button", { name: "New", exact: true }).click();
  await page.getByRole("textbox", { name: "LABEL" }).fill(label);
  await page.getByRole("textbox", { name: /Definition/i }).fill(definition);
  if (extra) await extra();
  await page.getByRole("button", { name: "Create and save" }).click();
}

async function ownerHeaders(request: APIRequestContext) {
  return { Authorization: `Bearer ${ownerToken}` };
}

test.describe.serial("Graphloom workbench", () => {
  test("creates a synthetic graph and exposes it read-only", async ({ page }) => {
    await connect(page);
    await page.getByLabel("Name").fill(projectName);
    await page
      .getByLabel("Description")
      .fill("Synthetic technical fixture for E2E verification; not research data.");
    await page.getByRole("button", { name: "Create project" }).click();
    await expect(page.getByRole("heading", { name: projectName })).toBeVisible();

    await createDraftObject(page, "class", "E2E class", "Synthetic E2E class.");
    await expect(page.getByText("Saved to revision 1.")).toBeVisible();
    await expect(page.getByRole("button", { name: "E2E class" }).first()).toBeVisible();

    await createDraftObject(
      page,
      "instance",
      "E2E instance",
      "Synthetic E2E instance.",
      async () => {
        await page
          .getByRole("listbox", { name: /Classes/i })
          .selectOption({ label: "E2E class" });
      },
    );
    await expect(page.getByText("Saved to revision 2.")).toBeVisible();

    await page.getByRole("button", { name: "Table" }).click();
    await expect(page.getByRole("region", { name: "Table view" })).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Table view" }).getByText("E2E instance", { exact: true }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Read access" }).click();
    await expect(page.getByRole("region", { name: "Read access", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Full state" }).click();
    await expect(page.locator(".read-json")).toContainText("E2E instance");
  });

  test("creates a snapshot, restores it, and reopens persisted state", async ({ page }) => {
    await openProject(page);

    await page.getByRole("button", { name: "History" }).click();
    await page.getByPlaceholder(/Name revision/).fill("E2E baseline");
    await page.getByRole("button", { name: "Save snapshot" }).click();
    await expect(page.getByText("E2E baseline")).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();

    await page.getByRole("button", { name: "E2E class" }).first().click();
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("textbox", { name: "LABEL" }).fill("E2E class v2");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Saved to revision 3.")).toBeVisible();
    await expect(page.getByRole("button", { name: "E2E class v2" }).first()).toBeVisible();

    await page.getByRole("button", { name: "History" }).click();
    await page.getByRole("button", { name: "Preview restore", exact: true }).click();
    await expect(page.getByText("REPLACEMENT CHANGE SET")).toBeVisible();
    await expect(page.getByText("E2E class v2").first()).toBeVisible();
    await page.getByRole("button", { name: "Apply change set" }).click();
    await expect(page.getByText(/Restored state as a new revision/)).toBeVisible();
    await expect(page.getByRole("button", { name: "E2E class" }).first()).toBeVisible();

    await page.reload();
    await openProject(page);
    await expect(page.getByRole("button", { name: "E2E class" }).first()).toBeVisible();
  });

  test("preserves a dirty draft when another session advances the revision", async ({
    page,
    request,
  }) => {
    await openProject(page);
    await page.getByRole("button", { name: "E2E class" }).first().click();
    await page.getByRole("button", { name: "Edit" }).click();
    await page.getByRole("textbox", { name: "LABEL" }).fill("Draft label not saved");

    const headers = await ownerHeaders(request);
    const projectsResponse = await request.get(
      "http://127.0.0.1:8000/api/v1/projects",
      { headers },
    );
    const projects = await projectsResponse.json();
    const project = projects.projects.find(
      (item: { name: string }) => item.name === projectName,
    );
    const stateResponse = await request.get(
      `http://127.0.0.1:8000/api/v1/projects/${project.id}/state?revision=${project.current_revision}`,
      { headers },
    );
    const state = await stateResponse.json();
    const classObject = state.objects.find(
      (item: { kind: string; label: string }) =>
        item.kind === "class" && item.label === "E2E class",
    );

    const preparedResponse = await request.post(
      `http://127.0.0.1:8000/api/v1/projects/${project.id}/change-sets`,
      {
        headers,
        data: {
          base_revision: project.current_revision,
          reason: "External edit from another session",
          operations: [
            {
              op: "update",
              id: classObject.id,
              fields: { label: "E2E class external" },
            },
          ],
        },
      },
    );
    const prepared = await preparedResponse.json();
    const commitResponse = await request.post(
      `http://127.0.0.1:8000/api/v1/projects/${project.id}/change-sets/${prepared.id}/commit`,
      {
        headers: { ...headers, "Idempotency-Key": "e2e-external-edit" },
        data: { expected_revision: prepared.base_revision },
      },
    );
    expect(commitResponse.ok()).toBeTruthy();

    await expect(page.getByText(/Revision conflict\./)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Discard draft" }).click();
    await expect(page.getByText("Draft discarded.")).toBeVisible();
  });
});
