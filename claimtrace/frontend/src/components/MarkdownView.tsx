import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { getPaperMarkdown, paperImageUrl, usingMockApi } from "../api/client";
import { Icon } from "./Icon";
import { demoManuscriptMarkdown, demoManuscriptImages, demoRichParagraphLocations, demoPaperClaims, demoCitationGroups } from "../data/mockData";

interface MarkdownViewProps {
  paperId: string;
  example?: boolean;
  onExampleReady?: () => void;
  onCitationPick?: (key: string) => void;
}

/** The Parser references images as ![](<{paper_id}_images/name.png>); keep only the basename. */
function imageBasename(src: string | undefined): string | undefined {
  if (!src) return undefined;
  const cleaned = src.replace(/^<|>$/g, "").trim();
  const segments = cleaned.split(/[\\/]/).filter(Boolean);
  return segments.length ? segments[segments.length - 1] : undefined;
}

export function MarkdownView({ paperId, example = false, onExampleReady, onCitationPick }: MarkdownViewProps) {
  const demo = example || usingMockApi;
  const figureReady = useRef(false);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    (demo ? Promise.resolve({ markdown: demoManuscriptMarkdown }) : getPaperMarkdown(paperId, signal))
      .then((result) => { if (!signal?.aborted) setMarkdown(result.markdown); })
      .catch((reason: unknown) => {
        if (signal?.aborted) return;
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Markdown unavailable.");
      })
      .finally(() => { if (!signal?.aborted) setLoading(false); });
  }, [paperId, demo]);

  useEffect(() => {
    const controller = new AbortController();
    figureReady.current = false;
    setMarkdown(null);
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (!demo || loading || !markdown) return;
    const frame = requestAnimationFrame(() => {
      if (!figureReady.current) onExampleReady?.();
    });
    return () => cancelAnimationFrame(frame);
  }, [demo, loading, markdown, onExampleReady]);

  if (loading) {
    return <div className="manuscript-loading"><span className="spinner" /><strong>Loading Markdown…</strong></div>;
  }
  if (error) {
    return (
      <div className="manuscript-loading error">
        <Icon name="x" /><strong>Markdown unavailable</strong><p>{error}</p>
        <button className="button button-secondary" type="button" onClick={() => load()}>Try again</button>
      </div>
    );
  }
  if (!markdown) {
    return <div className="manuscript-loading"><Icon name="document" /><strong>No Markdown was returned for this paper.</strong></div>;
  }

  return (
    <div className="markdown-view" data-selectable-paragraph>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeSanitize, rehypeKatex]}
        components={{
          a: ({ href, children }) => {
            const key = demo && href?.startsWith("#claimtrace-citation-") ? href.slice("#claimtrace-citation-".length) : "";
            const group = key ? demoCitationGroups[key] : undefined;
            if (!group) return <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer">{children}</a>;
            const titles = group.claimIds.map(id => demoPaperClaims.claims.find(claim => claim.claim_id === id)?.cited_source?.title).filter(Boolean).join(" · ");
            return <a href={href} className="inline-paper-citation" data-citation-group={key} title={titles || group.marker} onDragStart={event => event.preventDefault()} onClick={event => {
              event.preventDefault();
              if (!window.getSelection()?.isCollapsed) return;
              onCitationPick?.(key);
            }}>{children}</a>;
          },
          p: ({ node, children }) => {
            const position = node?.position;
            const text = position ? markdown.split("\n").slice(position.start.line - 1, position.end.line).join(" ").replace(/\s+/g, " ").trim() : "";
            const location = demo ? demoRichParagraphLocations[text] : undefined;
            const claimLocation = demoPaperClaims.claims[0].manuscript_location;
            const demoClaim = location && location.page === claimLocation?.page && location.paragraph === claimLocation?.paragraph_index;
            return <p data-demo-claim={demoClaim ? "true" : undefined} data-selectable-paragraph={location ? "" : undefined} data-page={location?.page} data-paragraph={location?.paragraph}>{children}</p>;
          },
          img: ({ src, alt }) => {
            const filename = imageBasename(src);
            return filename
              ? <img src={demo ? demoManuscriptImages[filename] : paperImageUrl(paperId, filename)} alt={alt || filename} loading="lazy" onLoad={demo && filename === "bert-pretraining-finetuning.png" ? () => {
                if (figureReady.current) return;
                figureReady.current = true;
                onExampleReady?.();
              } : undefined} />
              : null;
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
