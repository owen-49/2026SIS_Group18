import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { getPaperMarkdown, paperImageUrl } from "../api/client";
import { Icon } from "./Icon";

interface MarkdownViewProps {
  paperId: string;
}

/** The Parser references images as ![](<{paper_id}_images/name.png>); keep only the basename. */
function imageBasename(src: string | undefined): string | undefined {
  if (!src) return undefined;
  const cleaned = src.replace(/^<|>$/g, "").trim();
  const segments = cleaned.split(/[\\/]/).filter(Boolean);
  return segments.length ? segments[segments.length - 1] : undefined;
}

export function MarkdownView({ paperId }: MarkdownViewProps) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    getPaperMarkdown(paperId, signal)
      .then((result) => setMarkdown(result.markdown))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Markdown unavailable.");
      })
      .finally(() => setLoading(false));
  }, [paperId]);

  useEffect(() => {
    const controller = new AbortController();
    setMarkdown(null);
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

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
    <div className="markdown-view">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, rehypeSanitize, rehypeKatex]}
        components={{
          img: ({ src, alt }) => {
            const filename = imageBasename(src);
            return filename
              ? <img src={paperImageUrl(paperId, filename)} alt={alt || filename} loading="lazy" />
              : null;
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
