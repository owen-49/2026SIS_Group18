import { test, expect } from "@playwright/test";
import { configureAI } from "./ai-helpers.mjs";

test("all providers can be saved without the removed Audit switch", async ({
  page,
}) => {
  await page.route("**/api/papers", (route) =>
    route.fulfill({ json: { total: 0, papers: [] } }),
  );
  await page.goto("/audit");
  const providers = [
    "openai",
    "deepseek",
    "anthropic",
    "gemini",
    "xai",
    "mistral",
    "cohere",
    "qwen",
    "moonshot",
    "zhipu",
    "minimax",
    "doubao",
    "groq",
    "together",
    "fireworks",
    "siliconflow",
    "openrouter",
  ];
  for (const provider of providers) {
    await configureAI(page, {
      provider,
      model: "account-model",
      key: "offline-test-key",
    });
    const saved = await page.evaluate(async () =>
      (await import("/src/data/aiSettings.ts")).getAISettings(),
    );
    expect(saved.config.provider).toBe(provider);
    expect(saved).not.toHaveProperty("auditEnabled");
  }
  await page.getByRole("button", { name: /^AI settings/ }).click();
  const dialog = page.getByRole("dialog", { name: "AI settings", exact: true });
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  const storage = await page.evaluate(() =>
    JSON.stringify([localStorage, sessionStorage]),
  );
  expect(storage).not.toContain("offline-test-key");
});

test("changing provider or region clears credentials and preserves region in requests", async ({
  page,
}) => {
  await page.route("**/api/papers", (route) =>
    route.fulfill({ json: { total: 0, papers: [] } }),
  );
  await page.goto("/audit");
  await configureAI(page);
  await page.getByRole("button", { name: /^AI settings/ }).click();
  const dialog = page.getByRole("dialog", { name: "AI settings", exact: true });
  await dialog.getByLabel("Provider", { exact: true }).selectOption("qwen");
  await expect(dialog.getByLabel("API key", { exact: true })).toHaveValue("");
  await dialog.getByLabel("Model", { exact: true }).fill("qwen3-plus");
  await dialog.getByLabel("API key", { exact: true }).fill("old-region-key");
  await dialog
    .getByLabel("API region", { exact: true })
    .selectOption("singapore");
  await expect(dialog.getByLabel("API key", { exact: true })).toHaveValue("");
  await dialog
    .getByLabel("API key", { exact: true })
    .fill("offline-singapore-key");
  await dialog
    .getByLabel("Qwen workspace ID", { exact: true })
    .fill("workspace123");
  await dialog.getByRole("button", { name: "Save configuration" }).click();
  let body;
  await page.route("**/api/audit", (route) => {
    body = route.request().postDataJSON();
    return route.fulfill({ json: { contract_version: 2, results: [] } });
  });
  await page.evaluate(async () => {
    const { runAudit } = await import("/src/api/client.ts");
    await runAudit("paper", "pdf");
  });
  expect(body.ai_config).toEqual({
    provider: "qwen",
    model: "qwen3-plus",
    api_key: "offline-singapore-key",
    region: "singapore",
    workspace: "workspace123",
  });
  await page.reload();
  const cleared = await page.evaluate(async () =>
    (await import("/src/data/aiSettings.ts")).getAISettings(),
  );
  expect(cleared.config).toBeNull();
});


test("Qwen workspace rejects invalid DNS labels before saving", async ({ page }) => {
  await page.route("**/api/papers", route => route.fulfill({ json: { total: 0, papers: [] } }));
  await page.goto("/audit");
  await page.getByRole("button", { name: /^AI settings/ }).click();
  const dialog = page.getByRole("dialog", { name: "AI settings", exact: true });
  await dialog.getByLabel("Provider", { exact: true }).selectOption("qwen");
  await dialog.getByLabel("Model", { exact: true }).fill("qwen-plus");
  await dialog.getByLabel("API key", { exact: true }).fill("offline-key");
  const workspace = dialog.getByLabel("Qwen workspace ID", { exact: true });
  for (const invalid of ["bad.workspace", "-workspace", "workspace-", "a".repeat(64)]) {
    await workspace.fill(invalid);
    expect(await workspace.evaluate(el => el.checkValidity())).toBe(false);
    await dialog.getByRole("button", { name: "Save configuration" }).click();
    await expect(dialog).toBeVisible();
  }
  await workspace.fill("valid-workspace");
  await dialog.getByRole("button", { name: "Save configuration" }).click();
  await expect(dialog).not.toBeVisible();
});
