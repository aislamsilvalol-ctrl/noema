'use client';

/**
 * "Did this help?" under Mino's latest reply. Two words, no stars: the
 * verdict goes to the server with the move and strategy that produced the
 * reply, which is how a bad pattern gets found. A second tap changes it.
 */

import { useState } from 'react';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';

export function ReplyFeedback({ sessionId }: { sessionId: string }) {
  const t = useT();
  const [verdict, setVerdict] = useState<boolean | null>(null);

  function rate(helpful: boolean) {
    setVerdict(helpful);
    // Losing one rating to a network blip is not worth an error on screen.
    void api.rateReply(sessionId, helpful).catch(() => undefined);
  }

  const option = (helpful: boolean, label: string) => (
    <button
      type="button"
      aria-pressed={verdict === helpful}
      onClick={() => rate(helpful)}
      className={`min-h-11 px-2 text-sm transition-colors duration-fast ${
        verdict === helpful ? 'text-primary' : 'text-ink-500 hover:text-ink-900'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="-mt-4 flex flex-wrap items-center gap-x-2 text-sm text-ink-500" data-reply-feedback>
      <span>{verdict === null ? t.chat.feedbackQuestion : t.chat.feedbackThanks}</span>
      {option(true, t.chat.feedbackYes)}
      {option(false, t.chat.feedbackNo)}
    </div>
  );
}
