// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown, parseBlocks, renderInline } from './markdown';

describe('parseBlocks', () => {
  it('groups the shapes the Professor actually uses', () => {
    const blocks = parseBlocks(
      [
        '**Exemplo concreto primeiro.** Imagine alguém.',
        '',
        '- Uma parte grita: *quero agora*. Essa é o **id**.',
        '- Outra parte diz não.',
        '',
        '## A analogia',
        '',
        '> o ego é um cavaleiro',
        '',
        '1. primeiro',
        '2. segundo',
      ].join('\n'),
    );
    expect(blocks.map((b) => b.kind)).toEqual(['p', 'ul', 'h', 'quote', 'ol']);
    expect(blocks[1]).toMatchObject({ items: ['Uma parte grita: *quero agora*. Essa é o **id**.', 'Outra parte diz não.'] });
    expect(blocks[4]).toMatchObject({ items: ['primeiro', 'segundo'] });
  });

  it('keeps a fence that has not closed yet, as it streams', () => {
    const blocks = parseBlocks('```\nprint(1)\n');
    expect(blocks).toEqual([{ kind: 'code', text: 'print(1)' }]);
  });
});

describe('renderInline', () => {
  it('leaves an unterminated marker literal rather than swallowing text', () => {
    const { container } = render(<p>{renderInline('a **bold start')}</p>);
    expect(container.textContent).toBe('a **bold start');
    expect(container.querySelector('strong')).toBeNull();
  });

  it('does not italicise snake_case', () => {
    const { container } = render(<p>{renderInline('use current_topic and next_topic')}</p>);
    expect(container.querySelector('em')).toBeNull();
    expect(container.textContent).toBe('use current_topic and next_topic');
  });
});

describe('Markdown', () => {
  it('never turns text into markup', () => {
    render(<Markdown text={'<img src=x onerror=alert(1)> and **bold**'} />);
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText('bold').tagName).toBe('STRONG');
  });
});
