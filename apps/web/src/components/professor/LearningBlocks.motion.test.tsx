// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LearningBlock, QuizCheck, type QuizChecker } from './LearningBlocks';

function media(reduced: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({
      matches: reduced && query.includes('prefers-reduced-motion'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** A server check that answers only when the test says so. */
function deferredCheck() {
  let resolve: (value: { correct: boolean; answer: number; explain: string }) => void = () => {};
  const check = vi.fn<QuizChecker>(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const answer = (index: number, explain: string) => resolve({ correct: false, answer: index, explain });
  return { check, answer };
}

function renderQuiz(check: QuizChecker, onEvent = vi.fn()) {
  const view = render(
    <QuizCheck.Provider value={check}>
      <LearningBlock tool="quiz" data={{ question: 'Derivada de x^2?', options: ['x', '2x', 'x^2'] }} onEvent={onEvent} />
    </QuizCheck.Provider>,
  );
  const quiz = view.container.querySelector('[data-quiz-state]') as HTMLElement;
  return { ...view, quiz, onEvent };
}

describe('quiz feedback motion', () => {
  it('acknowledges the press at once and shows a calm pending line while the server checks', async () => {
    media(false);
    const { check, answer } = deferredCheck();
    const { quiz, container } = renderQuiz(check);
    expect(quiz.dataset.quizState).toBe('open');

    await userEvent.click(screen.getByRole('button', { name: '2x' }));

    expect(quiz.dataset.quizState).toBe('pending');
    const chosen = screen.getByRole('button', { name: '2x' });
    expect(chosen.dataset.verdict).toBe('chosen');
    expect(chosen.className).toContain('bg-sunken');
    expect(chosen.querySelector('[data-quiz-pending]')).not.toBeNull();
    expect(container.querySelectorAll('[data-quiz-pending]')).toHaveLength(1);
    expect(container.querySelector('[data-quiz-explain]')?.getAttribute('data-quiz-explain')).toBe('closed');
    // Not a spinner: nothing in the card spins.
    expect(container.querySelector('.animate-spin')).toBeNull();

    await act(async () => answer(1, 'Regra da potência.'));

    expect(quiz.dataset.quizState).toBe('correct');
    expect(container.querySelector('[data-quiz-pending]')).toBeNull();
  });

  it('a right answer settles positive, draws its check mark and opens the explanation', async () => {
    media(false);
    const { check, answer } = deferredCheck();
    const { quiz, container, onEvent } = renderQuiz(check);
    await userEvent.click(screen.getByRole('button', { name: '2x' }));
    await act(async () => answer(1, 'Regra da potência.'));

    expect(quiz.dataset.quizState).toBe('correct');
    const chosen = screen.getByRole('button', { name: '2x' });
    expect(chosen.dataset.verdict).toBe('right');
    expect(chosen.className).toContain('border-positive');
    const mark = chosen.querySelector('[data-quiz-check]');
    expect(mark).not.toBeNull();
    expect(mark?.getAttribute('class')).toContain('noema-check-draw');
    const explain = container.querySelector('[data-quiz-explain]') as HTMLElement;
    expect(explain.dataset.quizExplain).toBe('open');
    expect(explain.className).toContain('grid-rows-[1fr]');
    expect(screen.getByText('Regra da potência.')).toBeInTheDocument();
    expect(onEvent).toHaveBeenCalledWith('correct', expect.objectContaining({ chosen: '2x' }));
  });

  it('a wrong answer settles critical on the choice and marks the right one, without shaking', async () => {
    media(false);
    const { check, answer } = deferredCheck();
    const { quiz, container } = renderQuiz(check);
    await userEvent.click(screen.getByRole('button', { name: 'x' }));
    await act(async () => answer(1, 'Desce o expoente.'));

    expect(quiz.dataset.quizState).toBe('wrong');
    const wrong = screen.getByRole('button', { name: 'x' });
    const right = screen.getByRole('button', { name: '2x' });
    expect(wrong.dataset.verdict).toBe('wrong');
    expect(wrong.className).toContain('border-critical');
    expect(wrong.querySelector('[data-quiz-check]')).toBeNull();
    expect(right.dataset.verdict).toBe('right');
    expect(right.querySelector('[data-quiz-check]')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'x²' }).dataset.verdict).toBe('other');
    expect(container.querySelector('[data-quiz-explain]')?.getAttribute('data-quiz-explain')).toBe('open');
    expect(screen.getByText('Desce o expoente.')).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/shake|bounce|animate-/);
  });

  it('under reduced motion the mark is simply there, not drawn', async () => {
    media(true);
    const { check, answer } = deferredCheck();
    renderQuiz(check);
    await userEvent.click(screen.getByRole('button', { name: '2x' }));
    await act(async () => answer(1, 'ok'));

    const mark = screen.getByRole('button', { name: '2x' }).querySelector('[data-quiz-check]');
    expect(mark).not.toBeNull();
    expect(mark?.getAttribute('class')).not.toContain('noema-check-draw');
  });
});
