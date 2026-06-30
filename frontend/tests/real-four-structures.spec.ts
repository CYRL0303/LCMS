import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

test.skip(
  process.env.LEGACY_PILOT_RUN_REAL_FRONTEND_E2E !== "1",
  "Set LEGACY_PILOT_RUN_REAL_FRONTEND_E2E=1 to run real browser E2E.",
);

const SETTINGS_STORAGE_KEY = "legacyPilot.workbench.settings.v1";

test("runs the real four-structure incident pipeline from the workbench", async ({
  page,
}) => {
  const currentDir = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = path.resolve(currentDir, "..", "..");
  const fixtureRoot = path.join(
    repoRoot,
    "tests",
    "fixtures",
    "java_spring_production_demo",
  );
  const repoId = `repo-frontend-e2e-${Date.now()}`;

  await page.addInitScript((storageKey) => {
    window.localStorage.removeItem(storageKey);
  }, SETTINGS_STORAGE_KEY);
  await page.goto("/");

  await expect(page.getByText("legacy-pilot-interface-contract-middleware")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/Contract\s+1\.0\.0/)).toBeVisible();
  await expect(page.getByText(/S1\s+gitnexus_cli/)).toBeVisible();
  await expect(page.getByText(/S2\s+graph_context/)).toBeVisible();
  await expect(page.getByText(/S3\s+qwen_api/)).toBeVisible();
  await expect(page.getByText(/S4\s+postgresql/)).toBeVisible();

  await page.getByTestId("settings-button").click();
  await expect(page.getByTestId("settings-modal")).toBeVisible();
  await page.getByTestId("qwen-api-key-input").fill("sk-local-ui-test");
  await page.getByTestId("github-token-input").fill("github_pat_local_ui_test");
  await page.getByTestId("gitlab-token-input").fill("glpat-local-ui-test");
  await page.getByTestId("settings-modal").getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByTestId("settings-modal")).toBeHidden();
  await page.reload();
  await page.getByTestId("settings-button").click();
  await expect(page.getByTestId("qwen-api-key-input")).toHaveValue("sk-local-ui-test");
  await expect(page.getByTestId("github-token-input")).toHaveValue("github_pat_local_ui_test");
  await expect(page.getByTestId("gitlab-token-input")).toHaveValue("glpat-local-ui-test");
  await page.getByTestId("settings-modal").getByRole("button", { name: /^Clear$/ }).click();
  await page.getByTestId("settings-modal").getByRole("button", { name: /^Save$/ }).click();

  await page.getByLabel("Repo ID").fill(repoId);
  await page.getByTestId("repo-uri-input").fill(pathToFileURL(fixtureRoot).href);
  await page.getByRole("button", { name: /Index repo/i }).click();

  await expect(page.getByTestId("snapshot-summary")).toContainText("GraphSnapshot", {
    timeout: 180_000,
  });
  await expect(page.getByTestId("snapshot-summary")).toContainText("nodes");

  await page.getByTestId("alert-id-input").fill("ALERT-FRONTEND-E2E");
  await page.getByTestId("raw-log-input").fill(
    "java.lang.NullPointerException: Cannot invoke getDatasetId at DatasetService.getVersion(DatasetService.java:42). Hit /api/dataset/version.",
  );
  await page.getByLabel("Stack trace").fill(
    "at com.legacy.DatasetService.getVersion(DatasetService.java:42)",
  );
  await page.getByLabel("Error description").fill(
    "NPE while reading dataset version via /api/dataset/version",
  );
  await page.getByRole("button", { name: /Run full pipeline/i }).click();

  await expect(page.getByTestId("incident-query-summary")).toContainText(
    "NullPointerException",
    { timeout: 60_000 },
  );
  await expect(page.getByTestId("evidence-bundle")).toContainText("EvidenceBundle", {
    timeout: 120_000,
  });
  await expect(page.getByTestId("rca-report")).toContainText("Selected root cause", {
    timeout: 180_000,
  });
  await expect(page.getByTestId("reviewed-report")).toContainText("ReviewedRCAReport", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("latest-trace-id")).toContainText(
    "TRACE-ALERT-FRONTEND-E2E",
  );

  await page.getByTestId("user-confirmation-checkbox").check();
  await page.getByLabel("Fix outcome").fill("verified from frontend workbench");
  await page.getByLabel("Retention policy").fill("frontend-e2e");
  await page.getByTestId("save-incident-button").click();

  await expect(page.getByTestId("incident-record")).toContainText(
    "INC-ALERT-FRONTEND-E2E",
    { timeout: 60_000 },
  );
  await expect(page.getByTestId("incident-record")).toContainText("true");
  await expect(page.getByTestId("incident-readback")).toContainText(
    "INC-ALERT-FRONTEND-E2E",
    { timeout: 60_000 },
  );
});
