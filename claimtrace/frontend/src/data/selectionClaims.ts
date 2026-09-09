import type { ExtractedClaim } from "../types/api";

function normalise(text: string) {
  return text.normalize("NFKC").replace(/\s+/g, " ").trim();
}

/** Associate selected text with returned claims without guessing a source by title. */
export function matchSelectionClaims(claims: ExtractedClaim[], text: string, page: number, paragraph: number) {
  const selected = normalise(text);
  if (!selected) return [];
  const matches = claims.filter((claim) => {
    if (claim.manuscript_location && (claim.manuscript_location.page !== page
      || claim.manuscript_location.paragraph_index !== paragraph)) return false;
    if (!claim.manuscript_location && claim.page != null && claim.page !== page) return false;
    const sentence = normalise(claim.text);
    return sentence && (sentence.includes(selected) || selected.includes(sentence));
  });
  // A marker explicitly included in the selection distinguishes citations in one sentence.
  const marked = matches.filter((claim) => claim.citation_marker && selected.includes(normalise(claim.citation_marker)));
  return marked.length ? marked : matches;
}
