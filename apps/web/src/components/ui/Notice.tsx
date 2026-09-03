/**
 * Empty, error and info states, in one shape.
 *
 * A title that says what is (or is not) here, a body in plain language, and
 * the one action that makes sense next — in that order, always. Errors are
 * human sentences with a retry; a provider's or a database's own wording is
 * never what goes in `body` (see `lib/errors.ts`). Mino is an optional slot:
 * useful on a first-run empty state, noise on a list that simply has no rows
 * yet — the caller decides, this component just leaves room.
 */

import type { ReactNode } from 'react';
import { Button, ButtonLink } from '@/components/ui/Button';

type Kind = 'empty' | 'error' | 'info';

export function Notice({
  kind = 'info',
  title,
  body,
  action,
  mino,
  className = '',
}: {
  kind?: Kind;
  title: string;
  body?: ReactNode;
  action?: { label: string; onClick?: () => void; href?: string; busy?: ReactNode };
  mino?: ReactNode;
  className?: string;
}) {
  const isError = kind === 'error';
  return (
    <div
      role={isError ? 'alert' : undefined}
      className={`flex max-w-reading gap-6 ${kind === 'empty' ? 'mt-16' : 'mt-6'} ${className}`}
    >
      {mino && <div className="shrink-0 pt-1">{mino}</div>}
      <div className="min-w-0">
        <h2 className={`text-lg ${isError ? 'text-critical' : 'text-ink-900'}`}>{title}</h2>
        {body && <p className="mt-2 text-base text-ink-600">{body}</p>}
        {action &&
          (action.href ? (
            <ButtonLink
              href={action.href}
              variant={kind === 'empty' ? 'primary' : 'secondary'}
              className="mt-6"
            >
              {action.label}
            </ButtonLink>
          ) : (
            <Button
              onClick={action.onClick}
              variant={kind === 'empty' ? 'primary' : 'secondary'}
              busy={action.busy}
              className="mt-6"
            >
              {action.label}
            </Button>
          ))}
      </div>
    </div>
  );
}
