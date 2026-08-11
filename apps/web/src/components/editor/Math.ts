import { Node, mergeAttributes, nodeInputRule } from '@tiptap/core';
import type { Node as ProseMirrorNode } from '@tiptap/pm/model';
import katex from 'katex';

import type { MarkdownSerializerState } from './markdown';

/**
 * Inline LaTeX, written and stored as `$…$`.
 *
 * Rendered by KaTeX into an atom the cursor steps over rather than into. Editing
 * happens by deleting and retyping, which is crude but predictable — a half-working
 * inline formula editor is worse than none when the source is one keystroke away.
 */
declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    math: {
      insertMath: (latex: string) => ReturnType;
    };
  }
}

export const Math = Node.create({
  name: 'math',
  group: 'inline',
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      latex: {
        default: '',
        parseHTML: (element) => element.getAttribute('data-latex') ?? '',
        renderHTML: (attributes) => ({ 'data-latex': attributes.latex }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-latex]' }];
  },

  renderHTML({ HTMLAttributes, node }) {
    // Static serialisation only — it may run on the server, where there is no DOM.
    // The live rendering happens in the node view below.
    return [
      'span',
      mergeAttributes(HTMLAttributes, { class: 'noema-math' }),
      `$${node.attrs.latex}$`,
    ];
  },

  addNodeView() {
    return ({ node }) => {
      const dom = document.createElement('span');
      dom.className = 'noema-math';
      dom.setAttribute('data-latex', node.attrs.latex as string);
      try {
        katex.render(node.attrs.latex as string, dom, {
          throwOnError: false,
          displayMode: false,
        });
      } catch {
        dom.textContent = `$${node.attrs.latex}$`;
      }
      return { dom };
    };
  },

  addCommands() {
    return {
      insertMath:
        (latex) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs: { latex } }),
    };
  },

  addInputRules() {
    return [
      nodeInputRule({
        // `$x^2$` becomes a formula as soon as the closing delimiter is typed.
        find: /\$([^$]+)\$$/,
        type: this.type,
        getAttributes: (match) => ({ latex: match[1] }),
      }),
    ];
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
          state.write(`$${node.attrs.latex}$`);
        },
        parse: {},
      },
    };
  },
});
