'use client';

import { useRef, useState } from 'react';
import { streamChat, type TutorMode } from '@/lib/api';

const MODES: { id: TutorMode; label: string; blurb: string }[] = [
  { id: 'explain', label: 'Explain', blurb: 'Direct answers, worked examples.' },
  { id: 'socratic', label: 'Socratic', blurb: 'Questions only. You reach the answer.' },
  { id: 'examiner', label: 'Examiner', blurb: 'Tests you. No hints.' },
  { id: 'study_partner', label: 'Partner', blurb: 'Thinks alongside you.' },
  { id: 'feynman', label: 'Feynman', blurb: 'You explain. It finds the gaps.' },
];

interface Turn {
  role: 'user' | 'assistant';
  content: string;
}

export function TutorPanel({ notebookId }: { notebookId: string }) {
  const [mode, setMode] = useState<TutorMode>('explain');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;

    const history: Turn[] = [...turns, { role: 'user', content: text }];
    setTurns([...history, { role: 'assistant', content: '' }]);
    setInput('');
    setStreaming(true);
    setError(null);

    abort.current = new AbortController();

    try {
      await streamChat(
        { notebook_id: notebookId, mode, messages: history },
        {
          onToken: (chunk) =>
            setTurns((current) => {
              const next = [...current];
              const last = next[next.length - 1];
              if (last) next[next.length - 1] = { ...last, content: last.content + chunk };
              return next;
            }),
          onError: (message) => setError(message),
        },
        abort.current.signal,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The tutor is unavailable.');
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <h2 className="text-xs font-medium uppercase tracking-wide text-ink-500">Tutor</h2>

      <div className="mt-3 flex flex-wrap gap-1">
        {MODES.map((option) => (
          <button
            key={option.id}
            type="button"
            title={option.blurb}
            onClick={() => setMode(option.id)}
            className={`rounded px-2 py-1 text-xs transition-colors duration-state ${
              mode === option.id
                ? 'bg-accent-soft text-accent'
                : 'text-ink-500 hover:text-ink-900'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <p className="mt-2 text-xs text-ink-400">
        {MODES.find((m) => m.id === mode)?.blurb}
      </p>

      <div className="mt-6 flex-1 space-y-4 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-ink-500">
            Ask about this notebook. Once documents are indexed, answers cite the page they
            came from — and say so when the answer is not in your material.
          </p>
        )}

        {turns.map((turn, index) => (
          <div key={index}>
            <span className="text-xs uppercase tracking-wide text-ink-400">
              {turn.role === 'user' ? 'You' : 'NOEMA'}
            </span>
            <p className="mt-1 whitespace-pre-wrap text-sm text-ink-800">
              {turn.content}
              {streaming && index === turns.length - 1 && (
                <span className="ml-0.5 inline-block h-4 w-px animate-pulse bg-accent align-middle" />
              )}
            </p>
          </div>
        ))}

        {error && (
          <p role="alert" className="text-sm text-critical">
            {error}
          </p>
        )}
      </div>

      <form onSubmit={send} className="mt-4 border-t border-line pt-4">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send(event);
            }
          }}
          rows={3}
          placeholder="Ask NOEMA…"
          className="w-full resize-none rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 outline-none transition-colors duration-state focus:border-accent placeholder:text-ink-400"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-ink-400">Enter to send</span>
          {streaming ? (
            <button
              type="button"
              onClick={() => abort.current?.abort()}
              className="text-xs text-ink-500 hover:text-ink-900"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              className="rounded-md bg-ink-900 px-3 py-1.5 text-xs font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
            >
              Send
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
