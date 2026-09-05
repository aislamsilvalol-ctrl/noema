// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Markdown, parseBlocks } from '@/lib/markdown';
import { LearningBlock } from './LearningBlocks';

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
});
