import { Fragment, type ReactNode } from "react";

/**
 * Just enough Markdown for a generated report: headings, bullets, numbered
 * lists, bold/italic/code and paragraphs.
 *
 * Rendered into React elements rather than through dangerouslySetInnerHTML.
 * The text comes from a language model, and while the model is local and the
 * data is the user's own, HTML injected into the page would be a real hole for
 * the sake of a formatting convenience that is not needed here.
 */

/** Split a line into bold / italic / code runs. */
function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  // One pass over the three markers, longest first so ** wins over *.
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];
    const key = `${keyBase}-i${i++}`;
    if (token.startsWith("**") || token.startsWith("__")) {
      out.push(
        <strong key={key} className="font-semibold text-slate-900 dark:text-slate-50">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("`")) {
      out.push(
        <code
          key={key}
          className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[0.85em] dark:bg-slate-800"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      out.push(<em key={key}>{token.slice(1, -1)}</em>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*)$/;

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  // Paragraph and list runs are accumulated and flushed when the kind of line
  // changes, so a list is one <ul> rather than one per bullet.
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let key = 0;

  const flushPara = () => {
    if (para.length === 0) return;
    const body = para.join(" ");
    blocks.push(
      <p key={`p${key++}`} className="text-sm leading-relaxed muted">
        {inline(body, `p${key}`)}
      </p>,
    );
    para = [];
  };

  const flushList = () => {
    if (!list) return;
    const { ordered, items } = list;
    const children = items.map((item, idx) => (
      <li key={idx} className="text-sm leading-relaxed muted">
        {inline(item, `l${key}-${idx}`)}
      </li>
    ));
    blocks.push(
      ordered ? (
        <ol key={`o${key++}`} className="ml-5 list-decimal space-y-1.5">
          {children}
        </ol>
      ) : (
        <ul key={`u${key++}`} className="ml-5 list-disc space-y-1.5">
          {children}
        </ul>
      ),
    );
    list = null;
  };

  const flushAll = () => {
    flushPara();
    flushList();
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (line.trim() === "") {
      flushAll();
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const content = inline(heading[2], `h${key}`);
      blocks.push(
        level <= 2 ? (
          <h2
            key={`h${key++}`}
            className="mt-6 text-lg font-semibold text-slate-900 first:mt-0 dark:text-slate-50"
          >
            {content}
          </h2>
        ) : (
          <h3
            key={`h${key++}`}
            className="mt-4 text-sm font-semibold uppercase tracking-wide subtle first:mt-0"
          >
            {content}
          </h3>
        ),
      );
      continue;
    }

    const numbered = NUMBERED.exec(line);
    if (numbered) {
      flushPara();
      if (!list?.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(numbered[2]);
      continue;
    }

    const bullet = BULLET.exec(line);
    if (bullet) {
      flushPara();
      if (list && !list.ordered) {
        list.items.push(bullet[1]);
      } else {
        flushList();
        list = { ordered: false, items: [bullet[1]] };
      }
      continue;
    }

    flushList();
    para.push(line.trim());
  }
  flushAll();

  return <div className="space-y-3">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</div>;
}
