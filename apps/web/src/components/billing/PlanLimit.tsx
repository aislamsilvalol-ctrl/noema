'use client';

/**
 * What a learner is told when the plan shapes a lesson: the tutor paused
 * (why, and until when), or running in standard mode, or the full lessons
 * nearly spent. Always with a way forward; never credits or tokens.
 */

import { Notice } from '@/components/ui/Notice';
import { track } from '@/lib/analytics';
import type { PlanLimit } from '@/lib/api';
import { useI18n, type Locale } from '@/lib/i18n';

const DATE_LOCALE: Record<Locale, string> = { pt: 'pt-BR', en: 'en-US', es: 'es' };

/** "20 de outubro" for a month boundary; with the time for a daily or weekly one. */
export function useLimitDate(): (iso: string | null, withTime?: boolean) => string {
  const { locale } = useI18n();
  return (iso, withTime = false) => {
    if (!iso) return '';
    const date = new Date(iso);
    return new Intl.DateTimeFormat(DATE_LOCALE[locale], {
      day: 'numeric',
      month: 'long',
      ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
    }).format(date);
  };
}

export function PlanLimitBlocked({ limit }: { limit: PlanLimit }) {
  const { t } = useI18n();
  const when = useLimitDate();
  const reason = limit.reason ?? 'monthly';
  const timed = reason === 'daily' || reason === 'weekly';
  const body = t.professor.limit.body[reason]?.(when(limit.resets_at, timed));
  return (
    <Notice
      kind="info"
      title={t.professor.limit.title[reason] ?? t.professor.limit.title.monthly ?? ''}
      body={body}
      action={{
        label: t.professor.limit.upgrade,
        href: '/pricing',
        onClick: () => track('upgrade_clicked', { from: 'limit', reason }),
      }}
    />
  );
}

/** One line above the composer: standard mode, or the last full lessons. */
export function PlanLimitNote({ limit }: { limit: PlanLimit }) {
  const { t } = useI18n();
  const when = useLimitDate();
  const text =
    limit.mode === 'standard'
      ? t.professor.limit.standard(when(limit.resets_at))
      : t.professor.limit.fullEnding(limit.full_lessons_left);
  return (
    <p className="mb-2 text-xs text-ink-500">
      {text}{' '}
      <a
        href="/pricing"
        onClick={() => track('upgrade_clicked', { from: 'note', mode: limit.mode })}
        className="underline decoration-line underline-offset-2 hover:text-ink-900"
      >
        {t.professor.limit.upgrade}
      </a>
    </p>
  );
}
