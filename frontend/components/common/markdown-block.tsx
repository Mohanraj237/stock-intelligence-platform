/**
 * Tiny dependency-free markdown renderer for our chart-analysis sections.
 * Handles **bold**, *italic*, `code`, "- " bullet lists, and ₹X,XXX.XX prices.
 * Not a full CommonMark parser — just what analyze_chart_data emits.
 */
import { Fragment } from "react";

const INLINE_RE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;

function renderInline(text: string): React.ReactNode {
  const parts = text.split(INLINE_RE);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <strong key={i} className="text-white">{p.slice(2, -2)}</strong>;
    }
    if (p.startsWith("`") && p.endsWith("`")) {
      return <code key={i} className="rounded bg-[var(--color-surface-2)] px-1 py-0.5 text-[var(--color-warning)] text-[11px]">{p.slice(1, -1)}</code>;
    }
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) {
      return <em key={i} className="text-[var(--color-text)]">{p.slice(1, -1)}</em>;
    }
    return <Fragment key={i}>{p}</Fragment>;
  });
}

export function MarkdownBlock({ text }: { text: string }) {
  const lines = (text || "").split("\n").filter((l) => l.trim() !== "");
  const out: React.ReactNode[] = [];
  let bulletBuf: string[] = [];

  const flushBullets = () => {
    if (bulletBuf.length === 0) return;
    out.push(
      <ul key={`u${out.length}`} className="space-y-1 my-1.5 pl-4 list-disc marker:text-[var(--color-text-muted)]">
        {bulletBuf.map((b, i) => (
          <li key={i} className="text-sm leading-relaxed text-[var(--color-text)]">{renderInline(b)}</li>
        ))}
      </ul>
    );
    bulletBuf = [];
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith("- ") || line.startsWith("• ")) {
      bulletBuf.push(line.slice(2));
    } else {
      flushBullets();
      out.push(
        <p key={`p${out.length}`} className="text-sm leading-relaxed my-1.5 text-[var(--color-text)]">
          {renderInline(line)}
        </p>
      );
    }
  }
  flushBullets();

  return <div>{out}</div>;
}
