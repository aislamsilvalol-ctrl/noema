import { Node, mergeAttributes } from '@tiptap/core';
import type { Node as ProseMirrorNode } from '@tiptap/pm/model';

import type { MarkdownSerializerState } from './markdown';

/**
 * A callout block: a container that holds paragraphs and reads as an aside.
 *
 * Serialised to Markdown as a blockquote prefixed with the kind, e.g. `> [!note]`,
 * which is the convention Obsidian and GitHub both understand. That matters because
 * notes are exported as plain Markdown, and a bespoke syntax would make exports
 * useful only inside NOEMA.
 */
export type CalloutKind = 'note' | 'insight' | 'warning' | 'question';

export const CALLOUT_KINDS: CalloutKind[] = ['note', 'insight', 'warning', 'question'];

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    callout: {
      setCallout: (kind: CalloutKind) => ReturnType;
      toggleCallout: (kind: CalloutKind) => ReturnType;
    };
  }
}

export const Callout = Node.create({
  name: 'callout',
  group: 'block',
  content: 'block+',
  defining: true,

  addAttributes() {
    return {
      kind: {
        default: 'note' as CalloutKind,
        parseHTML: (element) => element.getAttribute('data-kind') ?? 'note',
        renderHTML: (attributes) => ({ 'data-kind': attributes.kind }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'aside[data-callout]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['aside', mergeAttributes(HTMLAttributes, { 'data-callout': '' }), 0];
  },

  addCommands() {
    return {
      setCallout:
        (kind) =>
        ({ commands }) =>
          commands.wrapIn(this.name, { kind }),
      toggleCallout:
        (kind) =>
        ({ commands }) =>
          commands.toggleWrap(this.name, { kind }),
    };
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
          state.write(`> [!${node.attrs.kind}]\n`);
          state.wrapBlock('> ', null, node, () => state.renderContent(node));
          state.closeBlock(node);
        },
        parse: {
          // The Markdown parser sees a plain blockquote; leaving this empty means a
          // round-trip degrades a callout to a quote rather than losing the text.
        },
      },
    };
  },
});
