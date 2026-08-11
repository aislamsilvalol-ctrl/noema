/**
 * `tiptap-markdown` registers itself on `editor.storage` at runtime but ships no
 * module augmentation for TipTap 3's typed `Storage`. Declaring the slice we
 * actually use keeps the call site honest instead of casting it away at each use.
 */
declare module '@tiptap/core' {
  interface Storage {
    markdown: {
      getMarkdown(): string;
    };
  }
}

export {};
