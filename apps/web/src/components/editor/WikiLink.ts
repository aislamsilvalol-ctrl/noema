import { Mark, markInputRule, mergeAttributes } from '@tiptap/core';

/**
 * `[[Concept]]` links between notes.
 *
 * A mark rather than a node, so the text stays selectable, searchable and
 * copy-pasteable as plain text. The backend already extracts these into
 * `notes.links` on save, which is what the knowledge graph will read in Phase 2.
 */
export const WikiLink = Mark.create({
  name: 'wikiLink',
  inclusive: false,

  addAttributes() {
    return {
      target: {
        default: '',
        parseHTML: (element) => element.getAttribute('data-wikilink') ?? '',
        renderHTML: (attributes) => ({ 'data-wikilink': attributes.target }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'a[data-wikilink]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['a', mergeAttributes(HTMLAttributes, { class: 'noema-wikilink' }), 0];
  },

  addInputRules() {
    return [
      markInputRule({
        find: /\[\[([^\]]+)\]\]$/,
        type: this.type,
        getAttributes: (match) => ({ target: match[1] }),
      }),
    ];
  },

  addStorage() {
    return {
      markdown: {
        serialize: {
          open: '[[',
          close: ']]',
          mixable: false,
          expelEnclosingWhitespace: true,
        },
        parse: {},
      },
    };
  },
});
