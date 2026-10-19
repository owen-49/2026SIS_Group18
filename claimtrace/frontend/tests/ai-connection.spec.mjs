import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/papers", route => route.fulfill({ json: { total: 0, papers: [] } }));
  await page.goto("/audit");
  await page.getByRole("button", { name: /^AI settings/ }).click();
});

async function fill(page) {
  const dialog = page.getByRole("dialog", { name: "AI settings", exact: true });
  await dialog.getByLabel("Model", { exact: true }).fill("text-chat");
  await dialog.getByLabel("API key", { exact: true }).fill("offline-secret-key");
  return dialog;
}
const saved = page => page.evaluate(async () => (await import("/src/data/aiSettings.ts")).getAISettings());

test("loads model candidates without a model and retains manual entry and official docs", async ({ page }) => {
  const dialog = page.getByRole("dialog", { name: "AI settings", exact: true });
  await dialog.getByLabel("API key", { exact: true }).fill("offline-secret-key");
  let body;
  await page.route("**/api/ai/models", route => {
    body = route.request().postDataJSON();
    return route.fulfill({ json: { supported: true, models: [{ id: "first-chat" }, { id: "second-chat" }] } });
  });
  await dialog.getByRole("button", { name: "Load models", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("2 text model candidates");
  expect(body).toEqual({ provider: "openai", api_key: "offline-secret-key" });
  await expect(dialog.locator("datalist option")).toHaveCount(2);
  await expect(dialog.getByRole("link", { name: "Find model IDs" })).toHaveAttribute("href", /openai.com/);
  await dialog.getByLabel("Model", { exact: true }).fill("manual-model");
  await expect(dialog.getByLabel("Model", { exact: true })).toHaveValue("manual-model");
  await dialog.getByLabel("Provider", { exact: true }).selectOption("deepseek");
  await expect(dialog.locator("datalist option")).toHaveCount(0);
});

test("unsupported model discovery allows manual input", async ({ page }) => {
  const dialog = await fill(page);
  await page.route("**/api/ai/models", route => route.fulfill({ json: { supported: false, models: [] } }));
  await dialog.getByRole("button", { name: "Load models", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("Copy a model ID from its console");
  await expect(dialog.getByLabel("Model", { exact: true })).toBeEditable();
});

test("save tests first, reports success and stores only tested memory state", async ({ page }) => {
  const dialog = await fill(page);
  await page.route("**/api/ai/test", async route => {
    await new Promise(resolve => setTimeout(resolve, 150));
    await route.fulfill({ json: { ok: true, model: "text-chat", latency_ms: 37 } });
  });
  await dialog.getByRole("button", { name: "Save configuration", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Testing connection…", exact: true })).toBeDisabled();
  await expect(dialog.getByRole("status")).toHaveText("Connected · text-chat · 37 ms");
  await expect(dialog).not.toBeVisible();
  expect(await saved(page)).toMatchObject({ tested: true, config: { model: "text-chat" } });
  await expect(page.getByLabel("Connection tested", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain("offline-secret-key");
  await page.reload();
  expect(await saved(page)).toEqual({ config: null, tested: false });
});

for (const [code, field] of [["AI_AUTH_FAILED", "API key"], ["AI_MODEL_UNAVAILABLE", "Model"], ["AI_MODEL_INCOMPATIBLE", "Model"], ["AI_REQUEST_REJECTED", "Model"], ["AI_QUOTA_EXCEEDED", null], ["AI_RATE_LIMITED", null], ["AI_TIMEOUT", null], ["AI_ACCESS_DENIED", null]]) {
  test(`${code} keeps the dialog open and points to the right field`, async ({ page }) => {
    const dialog = await fill(page);
    await page.route("**/api/ai/test", route => route.fulfill({ status: 422, json: { detail: { code, message: "safe backend message" } } }));
    await dialog.getByRole("button", { name: "Save configuration", exact: true }).click();
    await expect(dialog.getByRole("alert")).toBeVisible();
    if (field) await expect(dialog.getByLabel(field, { exact: true })).toHaveAttribute("aria-invalid", "true");
    await expect(dialog).toBeVisible();
    expect((await saved(page)).config).toBeNull();
  });
}

test("independent test never saves and edits clear the result; bypass is amber", async ({ page }) => {
  const dialog = await fill(page);
  let calls = 0;
  await page.route("**/api/ai/test", route => {
    calls++;
    return route.fulfill({ json: { ok: true, model: "text-chat", latency_ms: 10 } });
  });
  await dialog.getByRole("button", { name: "Test connection", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("Connected");
  expect((await saved(page)).config).toBeNull();
  await dialog.getByLabel("Model", { exact: true }).fill("other-model");
  await expect(dialog.getByRole("status")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Save without testing", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(calls).toBe(1);
  expect(await saved(page)).toMatchObject({ tested: false, config: { model: "other-model" } });
  await expect(page.getByLabel("Connection untested", { exact: true })).toHaveAttribute("title", /without a successful/);
});

test("late responses after editing cannot save stale credentials", async ({ page }) => {
  const dialog = await fill(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let started;
  const arrived = new Promise(resolve => { started = resolve; });
  await page.route("**/api/ai/test", async route => {
    started(); await gate;
    await route.fulfill({ json: { ok: true, model: "text-chat", latency_ms: 500 } }).catch(() => {});
  });
  await dialog.getByRole("button", { name: "Save configuration", exact: true }).click();
  await arrived;
  await dialog.getByLabel("Model", { exact: true }).fill("changed-model");
  release();
  await expect(dialog.getByRole("button", { name: "Save configuration", exact: true })).toBeEnabled();
  expect((await saved(page)).config).toBeNull();
  await expect(dialog.getByRole("status")).toHaveCount(0);
});


for (const field of ["Model", "API key", "Provider", "API region"]) {
  test(`editing ${field} clears saved test status`, async ({ page }) => {
    const dialog = await fill(page);
    await page.route("**/api/ai/test", route => route.fulfill({ json: { ok: true, model: "text-chat", latency_ms: 1 } }));
    await dialog.getByRole("button", { name: "Save configuration", exact: true }).click();
    await expect(dialog).not.toBeVisible();
    await page.getByRole("button", { name: /^AI settings/ }).click();
    if (field === "API region") {
      await dialog.getByLabel("Provider", { exact: true }).selectOption("qwen");
      await dialog.getByLabel("Model", { exact: true }).fill("text-chat");
      await dialog.getByLabel("API key", { exact: true }).fill("offline-secret-key");
      await dialog.getByRole("button", { name: "Save configuration", exact: true }).click();
      await expect(dialog).not.toBeVisible();
      await page.getByRole("button", { name: /^AI settings/ }).click();
      await dialog.getByLabel("API region", { exact: true }).selectOption("singapore");
    } else if (field === "Provider") {
      await dialog.getByLabel("Provider", { exact: true }).selectOption("deepseek");
    } else {
      await dialog.getByLabel(field, { exact: true }).fill("updated-value");
    }
    expect((await saved(page)).tested).toBe(false);
    await expect(dialog.getByRole("status")).toHaveCount(0);
  });
}
