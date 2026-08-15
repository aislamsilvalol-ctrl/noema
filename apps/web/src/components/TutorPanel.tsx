'use client';

import { useEffect, useRef, useState } from 'react';
import { streamChat, type TutorMode } from '@/lib/api';
import { useT } from '@/lib/i18n';

const MODE_IDS: TutorMode[] = ['explain', 'socratic', 'examiner', 'study_partner', 'feynman'];

interface Turn {
  role: 'user' | 'assistant';
  content: string;
}

export function TutorPanel({ notebookId }: { notebookId: string }) {
  const t = useT();
  const [mode, setMode] = useState<TutorMode>('explain');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  // "Ask NOEMA" on a selection in the editor lands here rather than as a one-shot
  // rewrite, because a question is the start of a conversation.
  useEffect(() => {
    function onAsk(event: Event) {
      const { text } = (event as CustomEvent<{ text: string }>).detail;
      setInput((current) =>
        current ? `${current}\n\n> ${text}` : `About this passage:\n\n> ${text}\n\n`,
      );
    }
    window.addEventListener('noema:ask', onAsk);
    return () => window.removeEventListener('noema:ask', onAsk);
  }, []);

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
      setError(err instanceof Error ? err.message : t.tutor.unavailable);
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <h2 className="text-xs font-medium uppercase tracking-wide text-ink-500">{t.tutor.title}</h2>

      <div className="mt-3 flex flex-wrap gap-1">
        {MODE_IDS.map((id) => (
          <button
            key={id}
            type="button"
            title={t.tutor.modes[id].blurb}
            onClick={() => setMode(id)}
            className={`rounded px-2 py-1 text-xs transition-colors duration-state ${
              mode === id ? 'bg-accent-soft text-accent' : 'text-ink-500 hover:text-ink-900'
            }`}
          >
            {t.tutor.modes[id].label}
          </button>
        ))}
      </div>

      <p className="mt-2 text-xs text-ink-400">
        {t.tutor.modes[mode].blurb}
      </p>

      <div className="mt-6 flex-1 space-y-4 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-ink-500">
            {t.tutor.emptyLede}
          </p>
        )}

        {turns.map((turn, index) => (
          <div key={index}>
            <span className="text-xs uppercase tracking-wide text-ink-400">
              {turn.role === 'user' ? t.tutor.you : 'NOEMA'}
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
          placeholder={t.tutor.placeholder}
          className="w-full resize-none rounded-md border border-line bg-raised px-3 py-2 text-sm text-ink-900 outline-none transition-colors duration-state focus:border-accent placeholder:text-ink-400"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-ink-400">{t.common.enterToSend}</span>
          {streaming ? (
            <button
              type="button"
              onClick={() => abort.current?.abort()}
              className="text-xs text-ink-500 hover:text-ink-900"
            >
              {t.common.stop}
            </button>
          ) : (
            <button
              type="submit"
              className="rounded-md bg-ink-900 px-3 py-1.5 text-xs font-medium text-ink-50 transition-opacity duration-state hover:opacity-90"
            >
              {t.common.send}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
