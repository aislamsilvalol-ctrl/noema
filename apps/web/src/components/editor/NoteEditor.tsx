'use client';

import { EditorContent, useEditor } from '@tiptap/react';
import { BubbleMenu } from '@tiptap/react/menus';
import StarterKit from '@tiptap/starter-kit';
import Image from '@tiptap/extension-image';
import Placeholder from '@tiptap/extension-placeholder';
import TaskItem from '@tiptap/extension-task-item';
import TaskList from '@tiptap/extension-task-list';
import { Table, TableCell, TableHeader, TableRow } from '@tiptap/extension-table';
import { Markdown } from 'tiptap-markdown';
import { useEffect, useRef } from 'react';

import { Callout } from './Callout';
import { Math } from './Math';
import { SlashCommands } from './SlashCommands';
import { WikiLink } from './WikiLink';

export type SelectionAction = 'explain' | 'simplify' | 'expand' | 'flashcard' | 'question' | 'ask';

const SELECTION_ACTIONS: { id: SelectionAction; label: string; available?: boolean }[] = [
  { id: 'explain', label: 'Explain' },
  { id: 'simplify', label: 'Simplify' },
  { id: 'expand', label: 'Expand' },
  { id: 'ask', label: 'Ask NOEMA' },
  { id: 'flashcard', label: 'Flashcard', available: false },
  { id: 'question', label: 'Question', available: false },
];

export function NoteEditor({
  value,
  onChange,
  onAction,
}: {
  value: string;
  onChange: (markdown: string) => void;
  onAction?: (action: SelectionAction, selection: string) => void;
}) {
  // Tracks the markdown this editor last emitted, so an echo of our own change
  // does not reset the document and drop the cursor mid-sentence.
  const lastEmitted = useRef(value);

  const editor = useEditor({
    immediatelyRender: false, // the document is client state; SSR would only flash
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        link: { openOnClick: false, autolink: true },
      }),
      TaskList,
      TaskItem.configure({ nested: true }),
      Image.configure({ allowBase64: false }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      Callout,
      Math,
      WikiLink,
      SlashCommands,
      Placeholder.configure({
        placeholder: "Write what you're trying to understand. Type / for blocks.",
      }),
      Markdown.configure({ html: false, transformPastedText: true, breaks: false }),
    ],
    content: value,
    editorProps: {
      attributes: {
        class: 'noema-prose focus:outline-none',
        spellcheck: 'true',
      },
    },
    onUpdate: ({ editor }) => {
      const markdown = editor.storage.markdown.getMarkdown() as string;
      lastEmitted.current = markdown;
      onChange(markdown);
    },
  });

  // Switching notes replaces the document; typing must not.
  useEffect(() => {
    if (!editor || value === lastEmitted.current) return;
    lastEmitted.current = value;
    editor.commands.setContent(value, { emitUpdate: false });
  }, [value, editor]);

  if (!editor) return null;

  return (
    <>
      <BubbleMenu editor={editor} options={{ placement: 'top' }}>
        <div className="flex items-center gap-0.5 rounded-md border border-line bg-raised p-1 shadow-lg">
          {SELECTION_ACTIONS.map((action) => (
            <button
              key={action.id}
              type="button"
              disabled={action.available === false || !onAction}
              onClick={() => {
                const { from, to } = editor.state.selection;
                const text = editor.state.doc.textBetween(from, to, ' ');
                if (text.trim()) onAction?.(action.id, text);
              }}
              className="rounded px-2 py-1 text-xs text-ink-700 transition-colors duration-state hover:bg-ink-100 disabled:text-ink-400 disabled:hover:bg-transparent"
            >
              {action.label}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-line" />
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleBold().run()}
            className="rounded px-2 py-1 text-xs font-semibold text-ink-700 transition-colors duration-state hover:bg-ink-100"
          >
            B
          </button>
          <button
            type="button"
            onClick={() => editor.chain().focus().toggleCode().run()}
            className="rounded px-2 py-1 font-mono text-xs text-ink-700 transition-colors duration-state hover:bg-ink-100"
          >
            {'<>'}
          </button>
        </div>
      </BubbleMenu>

      <EditorContent editor={editor} />
    </>
  );
}
