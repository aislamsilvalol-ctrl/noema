'use client';

/**
 * The two moves a learner can always make, whatever Mino just did.
 *
 * "Explain differently" opens six ways to hear the same idea again; "Guide
 * me" asks for questions instead of the answer. Both send an ordinary
 * message through the same path as typing — the engine already reads
 * "explain it differently" as the confused signal and changes strategy on
 * the next turn (professor/moves.py), so nothing here talks to the API on
 * its own. The learner sees their own words in the transcript, which is
 * also why the messages are first person.
 *
 * Keyboard: the trigger is a button with `aria-expanded`; the list is a
 * menu whose items take arrow keys, Home/End, Escape (closes, focus back on
 * the trigger) and Tab (closes, focus moves on).
 */

import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { useT } from '@/lib/i18n';
import type { Dict } from '@/locales/en';

export type ReframeMode = keyof Dict['professor']['reframe']['modes'];

/** In the order the menu shows them: from "less" to "more", then by kind. */
export const REFRAME_MODES: ReframeMode[] = [
  'simpler',
  'technical',
  'analogy',
  'example',
  'steps',
  'realWorld',
];

export function ReframeActions({
  onAsk,
  disabled = false,
}: {
  /** The lesson's send path; receives the finished message. */
  onAsk: (text: string) => void;
  /** While a reply is streaming the send path ignores messages; say so. */
  disabled?: boolean;
}) {
  const t = useT();
  const copy = t.professor.reframe;
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();

  useEffect(() => {
    if (open) items.current[0]?.focus();
  }, [open]);

  // A click anywhere else closes the menu without stealing that click.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  function close() {
    setOpen(false);
    trigger.current?.focus();
  }

  function choose(mode: ReframeMode) {
    onAsk(copy.messages[mode]);
    close();
  }

  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const list = items.current.filter((item): item is HTMLButtonElement => item !== null);
    const index = list.findIndex((item) => item === document.activeElement);
    switch (event.key) {
      case 'Escape':
        event.preventDefault();
        close();
        break;
      case 'ArrowDown':
        event.preventDefault();
        list[(index + 1) % list.length]?.focus();
        break;
      case 'ArrowUp':
        event.preventDefault();
        list[(index - 1 + list.length) % list.length]?.focus();
        break;
      case 'Home':
        event.preventDefault();
        list[0]?.focus();
        break;
      case 'End':
        event.preventDefault();
        list[list.length - 1]?.focus();
        break;
      case 'Tab':
        // Focus leaves on its own; the menu must not stay open behind it.
        setOpen(false);
        break;
      default:
        break;
    }
  }

  return (
    <div ref={root} className="relative flex flex-wrap gap-2">
      <Button
        ref={trigger}
        size="sm"
        variant="secondary"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        {copy.button}
      </Button>
      <Button
        size="sm"
        variant="secondary"
        disabled={disabled}
        onClick={() => onAsk(copy.guideMessage)}
      >
        {copy.guide}
      </Button>

      {open && (
        // Above the trigger: the composer sits at the bottom of the screen,
        // so a menu that drops down would open into nothing.
        <div
          id={menuId}
          role="menu"
          aria-label={copy.menuLabel}
          onKeyDown={onMenuKeyDown}
          className="absolute bottom-full left-0 z-10 mb-2 min-w-48 animate-fade-up rounded-md border border-line bg-raised p-1 shadow-elevation-2"
        >
          {REFRAME_MODES.map((mode, index) => (
            <Button
              key={mode}
              ref={(element) => {
                items.current[index] = element;
              }}
              role="menuitem"
              tabIndex={-1}
              size="sm"
              variant="ghost"
              className="w-full justify-start focus-visible:ring-offset-0"
              onClick={() => choose(mode)}
            >
              {copy.modes[mode]}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
