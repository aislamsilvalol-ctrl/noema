// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Composer, actionsFor } from '@/components/professor/Lesson';
import { en } from '@/locales/en';

function renderComposer(overrides: Partial<Parameters<typeof Composer>[0]> = {}) {
  const onAsk = vi.fn();
  render(
    <Composer
      value=""
      onChange={() => {}}
      onSubmit={() => {}}
      onStop={() => {}}
      streaming={false}
      placeholder="Ask"
      onAsk={onAsk}
      {...overrides}
    />,
  );
  return { onAsk };
}

const reframe = en.professor.reframe;

describe('Composer: explain differently', () => {
  it('is there even when the last move offers no quick actions', () => {
    renderComposer({ quickActions: null });

    expect(screen.getByRole('button', { name: reframe.button })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.getByRole('button', { name: reframe.guide })).toBeInTheDocument();
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('opens a menu of six modes and sends the chosen one through the send path', async () => {
    const user = userEvent.setup();
    const { onAsk } = renderComposer();

    await user.click(screen.getByRole('button', { name: reframe.button }));

    expect(screen.getByRole('button', { name: reframe.button })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    const items = screen.getAllByRole('menuitem');
    expect(items.map((item) => item.textContent)).toEqual([
      reframe.modes.simpler,
      reframe.modes.technical,
      reframe.modes.analogy,
      reframe.modes.example,
      reframe.modes.steps,
      reframe.modes.realWorld,
    ]);

    await user.click(screen.getByRole('menuitem', { name: reframe.modes.analogy }));

    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(onAsk).toHaveBeenCalledWith(reframe.messages.analogy);
    // The message is what the engine reads as "confused": keep the phrase.
    expect(reframe.messages.analogy.toLowerCase()).toContain('explain it differently');
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByRole('button', { name: reframe.button })).toHaveFocus();
  });

  it('walks the menu with the keyboard and closes on Escape, focus back on the trigger', async () => {
    const user = userEvent.setup();
    const { onAsk } = renderComposer();

    const trigger = screen.getByRole('button', { name: reframe.button });
    trigger.focus();
    await user.keyboard('{ArrowDown}');

    expect(screen.getByRole('menuitem', { name: reframe.modes.simpler })).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: reframe.modes.analogy })).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}{ArrowUp}'); // wraps to the end
    expect(screen.getByRole('menuitem', { name: reframe.modes.realWorld })).toHaveFocus();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).toBeNull();
    expect(trigger).toHaveFocus();
    expect(onAsk).not.toHaveBeenCalled();
  });

  it('chooses with Enter from the keyboard', async () => {
    const user = userEvent.setup();
    const { onAsk } = renderComposer();

    await user.click(screen.getByRole('button', { name: reframe.button }));
    await user.keyboard('{End}{Enter}');

    expect(onAsk).toHaveBeenCalledWith(reframe.messages.realWorld);
  });

  it('"Guide me" sends the request for questions, not answers', async () => {
    const user = userEvent.setup();
    const { onAsk } = renderComposer();

    await user.click(screen.getByRole('button', { name: reframe.guide }));

    expect(onAsk).toHaveBeenCalledWith(reframe.guideMessage);
  });

  it('waits while a reply is streaming, since the send path would drop the message', () => {
    renderComposer({ streaming: true });

    expect(screen.getByRole('button', { name: reframe.button })).toBeDisabled();
    expect(screen.getByRole('button', { name: reframe.guide })).toBeDisabled();
  });

  it('is absent when the page gives the composer no send path', () => {
    renderComposer({ onAsk: undefined });

    expect(screen.queryByRole('button', { name: reframe.button })).toBeNull();
  });
});

describe('actionsFor', () => {
  it('offers nothing while a question waits for its answer', () => {
    expect(actionsFor('teach', true, en)).toBeNull();
    expect(actionsFor('question', false, en)).toBeNull();
  });

  it('after a correct answer, offers to go on or hear it again', () => {
    expect(actionsFor('correct', false, en)?.map((a) => a.label)).toEqual([
      en.professor.actions.gotIt,
      en.professor.actions.stillNot,
      en.professor.actions.example,
    ]);
  });
});
