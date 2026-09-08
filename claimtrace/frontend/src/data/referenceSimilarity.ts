// Lexical title overlap only; this is not evidence of publication identity.
export function titleOverlap(left: string, right: string): number {
  const tokens = (text: string) => new Set(text.normalize("NFKC").toLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
  const a = tokens(left);
  const b = tokens(right);
  if (!a.size || !b.size) return 0;
  const shared = [...a].filter((token) => b.has(token)).length;
  return 2 * shared / (a.size + b.size);
}
