export const testAI = { provider: 'openai', model: 'test-model', api_key: 'fake-key-for-offline-tests' };
export async function configureAI(page, { provider = testAI.provider, model = testAI.model, key = testAI.api_key, audit = false } = {}) {
  await page.getByRole('button', { name: /^AI settings/ }).click();
  const dialog = page.getByRole('dialog', { name: 'AI settings', exact: true });
  await dialog.getByLabel('Provider', { exact: true }).selectOption(provider);
  await dialog.getByLabel('Model', { exact: true }).fill(model);
  await dialog.getByLabel('API key', { exact: true }).fill(key);
  await dialog.getByLabel('Use AI for incomplete Audit references').setChecked(audit);
  await dialog.getByRole('button', { name: 'Save configuration' }).click();
}
