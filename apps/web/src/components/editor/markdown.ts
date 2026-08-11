import type { Node as ProseMirrorNode } from '@tiptap/pm/model';

/**
 * The slice of prosemirror-markdown's serializer state our custom nodes use.
 *
 * `tiptap-markdown` passes this through untyped. Declaring the four methods we
 * actually call is better than an `any` that would let a typo through silently.
 */
export interface MarkdownSerializerState {
  write(text: string): void;
  wrapBlock(
    delim: string,
    firstDelim: string | null,
    node: ProseMirrorNode,
    fn: () => void,
  ): void;
  renderContent(node: ProseMirrorNode): void;
  closeBlock(node: ProseMirrorNode): void;
}
