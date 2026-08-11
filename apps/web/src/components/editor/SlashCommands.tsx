'use client';

import { Extension, type Editor, type Range } from '@tiptap/core';
import Suggestion from '@tiptap/suggestion';
import { ReactRenderer } from '@tiptap/react';
import { forwardRef, useEffect, useImperativeHandle, useState } from 'react';

export interface SlashItem {
  title: string;
  hint?: string;
  /** Phase-gated entries stay listed but inert, so the roadmap is visible in the UI. */
  available?: boolean;
  run: (editor: Editor, range: Range) => void;
}

export const SLASH_ITEMS: SlashItem[] = [
  {
    title: 'Heading',
    hint: '##',
    run: (editor, range) =>
      editor.chain().focus().deleteRange(range).setNode('heading', { level: 2 }).run(),
  },
  {
    title: 'Bullet list',
    run: (editor, range) => editor.chain().focus().deleteRange(range).toggleBulletList().run(),
  },
  {
    title: 'Numbered list',
    run: (editor, range) => editor.chain().focus().deleteRange(range).toggleOrderedList().run(),
  },
  {
    title: 'Checklist',
    run: (editor, range) => editor.chain().focus().deleteRange(range).toggleTaskList().run(),
  },
  {
    title: 'Callout',
    hint: 'aside',
    run: (editor, range) => editor.chain().focus().deleteRange(range).setCallout('note').run(),
  },
  {
    title: 'Code block',
    run: (editor, range) => editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
  },
  {
    title: 'Formula',
    hint: 'LaTeX',
    run: (editor, range) =>
      editor.chain().focus().deleteRange(range).insertMath('x^2').run(),
  },
  {
    title: 'Table',
    run: (editor, range) =>
      editor
        .chain()
        .focus()
        .deleteRange(range)
        .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
        .run(),
  },
  {
    title: 'Divider',
    run: (editor, range) => editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
  },
  // The commands the product actually exists for. They land with the engines that
  // back them; listing them now is a promise the roadmap has to keep.
  { title: 'Flashcard', hint: 'Phase 3', available: false, run: () => undefined },
  { title: 'Question', hint: 'Phase 3', available: false, run: () => undefined },
  { title: 'Quiz', hint: 'Phase 3', available: false, run: () => undefined },
  { title: 'Concept', hint: 'Phase 2', available: false, run: () => undefined },
];

interface MenuProps {
  items: SlashItem[];
  command: (item: SlashItem) => void;
}

const SlashMenu = forwardRef<{ onKeyDown: (props: { event: KeyboardEvent }) => boolean }, MenuProps>(
  function SlashMenu({ items, command }, ref) {
    const [selected, setSelected] = useState(0);

    useEffect(() => setSelected(0), [items]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }) => {
        if (event.key === 'ArrowUp') {
          setSelected((i) => (i + items.length - 1) % items.length);
          return true;
        }
        if (event.key === 'ArrowDown') {
          setSelected((i) => (i + 1) % items.length);
          return true;
        }
        if (event.key === 'Enter') {
          const item = items[selected];
          if (item && item.available !== false) command(item);
          return true;
        }
        return false;
      },
    }));

    if (items.length === 0) {
      return (
        <div className="w-56 rounded-md border border-line bg-raised p-2 text-sm text-ink-500 shadow-lg">
          No matching block.
        </div>
      );
    }

    return (
      <ul className="w-56 overflow-hidden rounded-md border border-line bg-raised py-1 shadow-lg">
        {items.map((item, index) => {
          const disabled = item.available === false;
          return (
            <li key={item.title}>
              <button
                type="button"
                disabled={disabled}
                onMouseEnter={() => setSelected(index)}
                onClick={() => command(item)}
                className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-sm transition-colors duration-state ${
                  index === selected && !disabled ? 'bg-ink-100' : ''
                } ${disabled ? 'text-ink-400' : 'text-ink-800'}`}
              >
                {item.title}
                {item.hint && <span className="text-xs text-ink-400">{item.hint}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    );
  },
);

export const SlashCommands = Extension.create({
  name: 'slashCommands',

  addProseMirrorPlugins() {
    return [
      Suggestion<SlashItem>({
        editor: this.editor,
        char: '/',
        startOfLine: false,
        items: ({ query }) =>
          SLASH_ITEMS.filter((item) =>
            item.title.toLowerCase().startsWith(query.toLowerCase()),
          ),
        command: ({ editor, range, props }) => props.run(editor, range),
        render: () => {
          let renderer: ReactRenderer<
            { onKeyDown: (props: { event: KeyboardEvent }) => boolean },
            MenuProps
          >;
          let element: HTMLElement | null = null;

          const place = (rect: DOMRect | null | undefined) => {
            if (!element || !rect) return;
            element.style.top = `${rect.bottom + window.scrollY + 6}px`;
            element.style.left = `${rect.left + window.scrollX}px`;
          };

          return {
            onStart: (props) => {
              renderer = new ReactRenderer(SlashMenu, { props, editor: props.editor });
              element = renderer.element as HTMLElement;
              element.style.position = 'absolute';
              element.style.zIndex = '60';
              document.body.appendChild(element);
              place(props.clientRect?.());
            },
            onUpdate: (props) => {
              renderer.updateProps(props);
              place(props.clientRect?.());
            },
            onKeyDown: (props) => {
              if (props.event.key === 'Escape') {
                element?.remove();
                return true;
              }
              return renderer.ref?.onKeyDown(props) ?? false;
            },
            onExit: () => {
              element?.remove();
              renderer?.destroy();
            },
          };
        },
      }),
    ];
  },
});
