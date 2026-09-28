// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Markdown, parseBlocks } from '@/lib/markdown';
import { LearningBlock, QuizCheck } from './LearningBlocks';

const LAYERS =
  'Pensa nela como um iceberg.\n\n```noema:layers\n{"title": "A mente como iceberg", "above_label": "consciente", "above": ["o que você percebe agora"], "below_label": "inconsciente", "below": ["desejos reprimidos"], "note": "A parte submersa empurra o iceberg inteiro."}\n```\n\nEssa parte pequena acima da água…';

describe('learning blocks', () => {
  it('parses a closed noema:<tool> fence into a tool block and leaves prose around it', () => {
    const kinds = parseBlocks(LAYERS).map((b) => b.kind);
    expect(kinds).toEqual(['p', 'tool', 'p']);
  });

  it('holds back a block that is still streaming instead of flashing raw JSON', () => {
    const half = 'Olha isso.\n\n```noema:layers\n{"title": "A mente';
    expect(parseBlocks(half).map((b) => b.kind)).toEqual(['p']);
  });

  it('shows a malformed block as code, never as nothing', () => {
    const bad = '```noema:layers\n{not json\n```';
    expect(parseBlocks(bad).map((b) => b.kind)).toEqual(['code']);
  });

  it('renders the iceberg as UI when a renderer is given', () => {
    render(
      <Markdown
        text={LAYERS}
        renderTool={(tool, data, key) => <LearningBlock key={key} tool={tool} data={data} />}
      />,
    );
    expect(screen.getByText('A mente como iceberg')).toBeInTheDocument();
    expect(screen.getByText('desejos reprimidos')).toBeInTheDocument();
    expect(screen.queryByText(/noema:layers/)).toBeNull();
  });

  it('a quiz compares against the engine answer and emits the outcome — the UI never decides', async () => {
    const onEvent = vi.fn();
    render(
      <LearningBlock
        tool="quiz"
        data={{ question: 'Onde estava o nome?', options: ['Sumiu', 'Guardado'], answer: 1, explain: 'Pré-consciente.' }}
        onEvent={onEvent}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Sumiu' }));
    expect(onEvent).toHaveBeenCalledWith(
      'wrong',
      expect.objectContaining({ chosen: 'Sumiu', chosenIndex: 0, question: 'Onde estava o nome?' }),
    );
    expect(screen.getByText('Pré-consciente.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Guardado' })).toBeDisabled();
  });

  it('a quiz without its key asks the server after the choice, then reveals', async () => {
    const onEvent = vi.fn();
    const check = vi.fn().mockResolvedValue({ correct: true, answer: 1, explain: 'Regra da potência.' });
    render(
      <QuizCheck.Provider value={check}>
        <LearningBlock
          tool="quiz"
          data={{ question: 'Derivada de x^2?', options: ['x', '2x'] }}
          onEvent={onEvent}
        />
      </QuizCheck.Provider>,
    );
    expect(screen.queryByText('Regra da potência.')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '2x' }));
    expect(check).toHaveBeenCalledWith('Derivada de x^2?', '2x');
    expect(await screen.findByText('Regra da potência.')).toBeInTheDocument();
    expect(onEvent).toHaveBeenCalledWith('correct', expect.objectContaining({ chosen: '2x' }));
  });

  it('when the server cannot say, the choice still goes to Mino with no verdict shown', async () => {
    const onEvent = vi.fn();
    const check = vi.fn().mockRejectedValue(new Error('offline'));
    render(
      <QuizCheck.Provider value={check}>
        <LearningBlock tool="quiz" data={{ question: 'Q?', options: ['a', 'b'] }} onEvent={onEvent} />
      </QuizCheck.Provider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'a' }));
    await vi.waitFor(() => expect(onEvent).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'b' })).toBeDisabled();
  });
});
