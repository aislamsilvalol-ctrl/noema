/**
 * The Professor's replies, rendered as a lesson rather than as raw text.
 *
 * Noema answers in light markdown — bold for the term being defined, lists for
 * the steps of an example, a heading now and then, a quote when it cites. The
 * old screens printed that verbatim, asterisks and all, which is the single
 * most visible reason the Professor read as "a chatbot" (audit, screen 6).
 *
 * This is a small, deliberate subset built as React elements — never an HTML
 * string — so nothing a model or a stored transcript contains can become
 * markup. Anything outside the subset stays literal text, including an
 * unterminated `**` mid-stream: the text is re-rendered on every token, and
 * a pair that closes on the next chunk simply becomes bold then.
 */

import type { ReactNode } from 'react';

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'h'; text: string }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'code'; text: string }
  | { kind: 'hr' };

const HEADING = /^#{1,6}\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const QUOTE = /^>\s?(.*)$/;
const RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/;
const FENCE = /^\s*```/;

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? '';

    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (FENCE.test(line)) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE.test(lines[i] ?? '')) {
        body.push(lines[i] ?? '');
        i += 1;
      }
      i += 1; // closing fence, if it has arrived
      blocks.push({ kind: 'code', text: body.join('\n').replace(/\n$/, '') });
      continue;
    }

    if (RULE.test(line)) {
      blocks.push({ kind: 'hr' });
      i += 1;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: 'h', text: heading[1] ?? '' });
      i += 1;
      continue;
    }

    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = NUMBERED.test(line);
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [];
      while (i < lines.length) {
        const match = pattern.exec(lines[i] ?? '');
        if (!match) break;
        items.push(match[1] ?? '');
        i += 1;
        // A wrapped continuation line belongs to the item above it.
        while (
          i < lines.length &&
          (lines[i] ?? '').trim() &&
          !BULLET.test(lines[i] ?? '') &&
          !NUMBERED.test(lines[i] ?? '') &&
          /^\s{2,}/.test(lines[i] ?? '')
        ) {
          items[items.length - 1] += ` ${(lines[i] ?? '').trim()}`;
          i += 1;
        }
      }
      blocks.push({ kind: ordered ? 'ol' : 'ul', items });
      continue;
    }

    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (i < lines.length) {
        const match = QUOTE.exec(lines[i] ?? '');
        if (!match) break;
        body.push(match[1] ?? '');
        i += 1;
      }
      blocks.push({ kind: 'quote', lines: body });
      continue;
    }

    const paragraph: string[] = [];
    while (
      i < lines.length &&
      (lines[i] ?? '').trim() &&
      !HEADING.test(lines[i] ?? '') &&
      !BULLET.test(lines[i] ?? '') &&
      !NUMBERED.test(lines[i] ?? '') &&
      !QUOTE.test(lines[i] ?? '') &&
      !FENCE.test(lines[i] ?? '') &&
      !RULE.test(lines[i] ?? '')
    ) {
      paragraph.push(lines[i] ?? '');
      i += 1;
    }
    blocks.push({ kind: 'p', lines: paragraph });
  }

  return blocks;
}

// Bold, italic and inline code. Bold is matched first so `**x**` never reads
// as two empty italics; an italic marker inside a word (snake_case) is left
// alone by requiring the marker to sit at a word boundary.
const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|(?<![\w*])\*[^*\n]+\*(?![\w*])|(?<!\w)_[^_\n]+_(?!\w))/g;

export function renderInline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(INLINE)) {
    const token = match[0];
    const at = match.index ?? 0;
    if (at > last) parts.push(text.slice(last, at));
    if (token.startsWith('**')) {
      parts.push(
        <strong key={key++} className="font-medium text-ink-900">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith('`')) {
      parts.push(
        <code key={key++} className="rounded bg-sunken px-1 font-mono text-[0.9em] text-ink-800">
          {token.slice(1, -1)}
        </code>,
      );
    } else {
      parts.push(<em key={key++}>{token.slice(1, -1)}</em>);
    }
    last = at + token.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function Lines({ lines }: { lines: string[] }) {
  return (
    <>
      {lines.map((line, index) => (
        <span key={index}>
          {index > 0 && <br />}
          {renderInline(line)}
        </span>
      ))}
    </>
  );
}

/** Lesson prose: reading measure, generous leading, terms in ink-900. */
export function Markdown({ text, className = '' }: { text: string; className?: string }) {
  const blocks = parseBlocks(text);
  return (
    <div className={`space-y-4 text-base leading-relaxed text-ink-800 ${className}`}>
      {blocks.map((block, index) => {
        switch (block.kind) {
          case 'h':
            return (
              <h3 key={index} className="pt-2 font-display text-lg text-ink-900">
                {renderInline(block.text)}
              </h3>
            );
          case 'ul':
            return (
              <ul key={index} className="list-disc space-y-1.5 pl-5 marker:text-ink-400">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInline(item)}</li>
                ))}
              </ul>
            );
          case 'ol':
            return (
              <ol key={index} className="list-decimal space-y-1.5 pl-5 marker:text-ink-400">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex}>{renderInline(item)}</li>
                ))}
              </ol>
            );
          case 'quote':
            return (
              <blockquote
                key={index}
                className="border-l-2 border-signal pl-4 font-serif text-md text-ink-700"
              >
                <Lines lines={block.lines} />
              </blockquote>
            );
          case 'code':
            return (
              <pre
                key={index}
                className="overflow-x-auto rounded-md bg-sunken p-3 font-mono text-sm text-ink-800"
              >
                <code>{block.text}</code>
              </pre>
            );
          case 'hr':
            return <hr key={index} className="border-line" />;
          default:
            return (
              <p key={index}>
                <Lines lines={block.lines} />
              </p>
            );
        }
      })}
    </div>
  );
}
