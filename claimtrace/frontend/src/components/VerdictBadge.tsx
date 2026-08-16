import type { Verdict } from "../types/api";

const labels: Record<Verdict, string> = {
  SUPPORT: "Supported",
  PARTIAL: "Partial",
  CONTRADICT: "Contradicted",
  NOT_FOUND: "Not found",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <span className={`verdict-badge verdict-${verdict.toLowerCase()}`}>{labels[verdict]}</span>;
}
