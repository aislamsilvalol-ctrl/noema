// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { Input, Select, Textarea } from '@/components/ui/Input';
import { SegmentedControl } from '@/components/ui/SegmentedControl';

describe('Input, Textarea, Select', () => {
  it('pass native props through and share one box', () => {
    render(
      <>
        <Input aria-label="Name" placeholder="Ada" disabled />
        <Textarea aria-label="Notes" rows={3} />
        <Select aria-label="Pick">
          <option value="a">A</option>
        </Select>
      </>,
    );
    const input = screen.getByRole('textbox', { name: 'Name' });
    const textarea = screen.getByRole('textbox', { name: 'Notes' });
    const select = screen.getByRole('combobox', { name: 'Pick' });
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute('placeholder', 'Ada');
    expect(textarea).toHaveAttribute('rows', '3');
    for (const field of [input, textarea, select]) {
      expect(field).toHaveClass('border-line', 'bg-raised', 'focus-visible:ring-signal');
    }
  });

  it("sizes the padding and keeps the caller's width classes", () => {
    render(<Input aria-label="Wide" size="lg" className="w-full" />);
    const input = screen.getByRole('textbox', { name: 'Wide' });
    expect(input).toHaveClass('px-4', 'py-3', 'text-base', 'w-full');
    expect(input).not.toHaveAttribute('size');
  });

  it('hands the ref to the element', () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Input aria-label="Focused" ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });
});

function Depth() {
  const [depth, setDepth] = useState(1);
  return (
    <SegmentedControl
      label="Depth"
      value={depth}
      onChange={setDepth}
      options={[1, 2, 3].map((level) => ({ value: level, label: String(level) }))}
    />
  );
}

describe('SegmentedControl', () => {
  it('is a radiogroup with one checked radio and one tab stop', () => {
    render(<Depth />);
    const radios = screen.getAllByRole('radio');
    expect(screen.getByRole('radiogroup', { name: 'Depth' })).toBeInTheDocument();
    expect(radios).toHaveLength(3);
    expect(radios[0]).toBeChecked();
    expect(radios[1]).not.toBeChecked();
    expect(radios.filter((radio) => radio.tabIndex === 0)).toHaveLength(1);
  });

  it('changes on click and walks with arrow keys, wrapping at the ends', async () => {
    const user = userEvent.setup();
    render(<Depth />);
    await user.click(screen.getByRole('radio', { name: '3' }));
    expect(screen.getByRole('radio', { name: '3' })).toBeChecked();

    screen.getByRole('radio', { name: '3' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: '1' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '1' })).toHaveFocus();

    await user.keyboard('{ArrowLeft}');
    expect(screen.getByRole('radio', { name: '3' })).toBeChecked();
  });

  it('reports the option value, not its index', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SegmentedControl
        label="Mode"
        value="basic"
        onChange={onChange}
        options={[
          { value: 'basic', label: 'Basic' },
          { value: 'cloze', label: 'Cloze' },
        ]}
      />,
    );
    await user.click(screen.getByRole('radio', { name: 'Cloze' }));
    expect(onChange).toHaveBeenCalledWith('cloze');
  });
});
