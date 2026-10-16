import { fullBertDocument, fullBertRichLocations, fullBertClaimLocation } from "../assets/demo/bert-document";
import { bertReferences } from "../assets/demo/bert-references";
import originalBertPdf from "../assets/demo/bert-naacl2019.pdf";
import { demoSourceProfiles } from "./demoSourceProfiles";
import type { AuditResponse, AuditResult, ExtractedClaim, IdentifiedSource, SourceDocument } from "../types/api";

export type CitationGroup = { key: string; text: string; marker: string; claimIds: string[]; page: number; paragraph: number };
const normalise = (text: string) => text.normalize("NFKC").replace(/\s+/g, " ").trim();
const markerPattern = /((?:Tjong Kim Sang and De Meulder)|(?:[A-Z][\p{L}’'-]+(?:\s+(?:et al\.|and\s+[A-Z][\p{L}’'-]+))?))\s*(?:,\s*|\(\s*)((?:19|20)\d{2}[a-z]?(?:\s*,\s*(?:19|20)\d{2}[a-z]?)*)(\))?/gu;

function sentenceAt(text: string, offset: number) {
  let start = 0;
  for (const boundary of text.matchAll(/[.!?](?:\d{1,2})?\s+(?=[A-Z“])/g)) {
    const end = boundary.index! + boundary[0].trimEnd().length;
    if (end > offset) return text.slice(start, end).trim();
    start = boundary.index! + boundary[0].length;
  }
  return text.slice(start).trim();
}

function referenceUrl(raw: string) {
  const arxiv = raw.match(/arXiv:(\d{4}\.\d{4,5})/i)?.[1];
  return arxiv ? `https://arxiv.org/abs/${arxiv}` : null;
}

function sourceFor(reference: typeof bertReferences[number]): { source: IdentifiedSource; document: SourceDocument | null } {
  const profile = demoSourceProfiles[`${reference.alias}|${reference.yearLabel}`];
  return {
    source: {
      source_paper_id: profile ? `source-${reference.key}` : null,
      citation_key: reference.key, title: reference.title, authors: reference.authors,
      venue: profile?.venue || null, year: reference.year, doi: profile?.doi || null,
      url: profile?.url || referenceUrl(reference.raw), database: profile ? "ACL Anthology" : "Manuscript bibliography",
    },
    document: profile ? { total_pages: profile.totalPages, matched_location: { page: 1, paragraph_index: 0 }, pages: [{ page: 1, heading: "Abstract", paragraphs: [profile.abstract] }] } : null,
  };
}

export function createDemoCitations(primary: ExtractedClaim) {
  const groups: Record<string, CitationGroup> = {};
  const claims: ExtractedClaim[] = [];
  const locations = { ...fullBertRichLocations };
  for (const page of fullBertDocument.pages) {
    page.paragraphs.forEach((paragraph, paragraphIndex) => {
      [...paragraph.matchAll(markerPattern)].forEach((match, index) => {
        const alias = match[1];
        const years = match[2].split(/,\s*/);
        const key = `p${page.page}-n${paragraphIndex}-c${index}`;
        const text = sentenceAt(paragraph, match.index!);
        const group: CitationGroup = { key, text, marker: match[0], claimIds: [], page: page.page, paragraph: paragraphIndex };
        years.forEach((year, yearIndex) => {
          const reference = bertReferences.find(item => item.alias === alias && item.yearLabel === year);
          const primaryMatch = alias === "Vaswani et al." && year === "2017" && page.page === fullBertClaimLocation.page && paragraphIndex === fullBertClaimLocation.paragraph_index;
          const id = primaryMatch ? "claim-attention" : `${key}-r${yearIndex}`;
          const resolved = reference ? sourceFor(reference) : null;
          claims.push(primaryMatch ? { ...primary, text, manuscript_location: { page: page.page, paragraph_index: paragraphIndex } } : {
            claim_id: id, text, page: page.page, citation_marker: match[0],
            resolution_status: resolved ? "identified" : "not_found",
            resolution_message: resolved ? `Reference identified: ${reference!.title}.` : `Reference details for ${alias} (${year}) are not available in the extracted bibliography.`,
            cited_source: resolved?.source || null, source_document: resolved?.document || null,
            manuscript_location: { page: page.page, paragraph_index: paragraphIndex },
          });
          group.claimIds.push(id);
        });
        groups[key] = group;
      });
    });
  }
  // Keep the guided architecture example first without dropping other citations.
  claims.sort((a, b) => Number(b.claim_id === "claim-attention") - Number(a.claim_id === "claim-attention"));
  function decorate(markdown: string) {
    return markdown.split("\n\n").map(paragraph => {
      const location = fullBertRichLocations[normalise(paragraph)];
      if (!location) return paragraph;
      let index = 0;
      const decorated = paragraph.replace(markerPattern, marker => {
        const key = `p${location.page}-n${location.paragraph}-c${index++}`;
        return groups[key] ? `[${marker}](#claimtrace-citation-${key})` : marker;
      });
      locations[normalise(decorated)] = location;
      return decorated;
    }).join("\n\n");
  }
  return { claims, groups, locations, decorate };
}

export function createDemoAudit(): AuditResponse {
  const yearChanges: Record<string, number> = { "Vaswani et al.|2017": 2016, "Howard and Ruder|2018": 2019, "Zellers et al.|2018": 2017 };
  const reviewAliases = new Set(["Chen et al.", "Al-Rfou et al."]);
  const delayedAliases = new Set(["Hu et al.", "Sun et al."]);
  const results: AuditResult[] = bertReferences.map<AuditResult>(reference => {
    const profile = demoSourceProfiles[`${reference.alias}|${reference.yearLabel}`];
    const changedYear = yearChanges[`${reference.alias}|${reference.yearLabel}`];
    const notFound = reference.alias === "McCann et al.";
    const status = notFound ? "NOT_FOUND" : changedYear ? "METADATA_MISMATCH" : reviewAliases.has(reference.alias) ? "NEEDS_REVIEW" : delayedAliases.has(reference.alias) ? "LOOKUP_FAILED" : "VERIFIED";
    const metadata = { title: reference.title, authors: reference.authors, year: reference.year, venue: profile?.venue || "", doi: profile?.doi || "", raw_text: reference.raw };
    const url = reference.alias === "Vaswani et al." ? "https://papers.nips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html" : profile?.url || referenceUrl(reference.raw) || `${originalBertPdf}#page=${reference.page}`;
    const record = { provider: profile ? "ACL Anthology" : reference.alias === "Vaswani et al." ? "NeurIPS proceedings" : referenceUrl(reference.raw) ? "arXiv" : "Manuscript bibliography", record_id: reference.key, url, retrieved_at: "2026-10-16T01:00:00Z", metadata };
    const entryId = reference.alias === "Vaswani et al." ? "vaswani2017attention" : reference.key;
    return {
      entry: { entry_id: entryId, number: null, page_start: reference.page, page_end: reference.page, metadata: { ...metadata, year: changedYear || metadata.year } }, status,
      reason: status === "NOT_FOUND" ? "No matching publication record was returned for this reference." : status === "METADATA_MISMATCH" ? "The publication year differs from the source record." : status === "NEEDS_REVIEW" ? "The available metadata is insufficient to confirm one publication record." : status === "LOOKUP_FAILED" ? "Publication lookup timed out. Retry this reference." : "The reference metadata agrees with the publication record.",
      field_checks: status === "NEEDS_REVIEW" || status === "LOOKUP_FAILED" || status === "NOT_FOUND" ? [] : [
        { field_name: "title", input_value: reference.title, source_value: reference.title, status: "MATCH", detail: "Normalized title match." },
        { field_name: "year", input_value: String(changedYear || reference.year), source_value: String(reference.year), status: changedYear ? "MISMATCH" : "MATCH", detail: changedYear ? "Publication year differs." : "Publication year agrees." },
        { field_name: "authors", input_value: reference.authors.join(", "), source_value: reference.authors.join(", "), status: "MATCH", detail: "Author names agree." },
      ],
      matched_record: status === "VERIFIED" || status === "METADATA_MISMATCH" ? record : null,
      candidates: status === "NEEDS_REVIEW" ? [record] : [],
      lookup_attempts: [{ provider: record.provider, outcome: status === "NOT_FOUND" ? "not_found" : status === "LOOKUP_FAILED" ? "failed" : status === "NEEDS_REVIEW" ? "ambiguous" : "found", error_code: status === "LOOKUP_FAILED" ? "PROVIDER_TIMEOUT" : null, detail: status === "LOOKUP_FAILED" ? "The provider did not respond before the lookup deadline." : "Reference metadata lookup completed." }],
    };
  });
  const counts = { VERIFIED: 0, METADATA_MISMATCH: 0, NEEDS_REVIEW: 0, NOT_FOUND: 0, LOOKUP_FAILED: 0 };
  results.forEach(result => { counts[result.status]++; });
  return { contract_version: 2, audit_id: "bert-reference-audit", input_paper_id: "paper-manuscript", input_type: "pdf", checked_at: "2026-10-16T01:00:00Z", status: "completed_with_errors", total_entries: results.length, counts, warnings: [], results };
}
