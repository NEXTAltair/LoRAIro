import * as React from "react";

export interface TagInputProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  /** Current tags (stored verbatim — danbooru canonical, never translated). */
  tags?: string[];
  /** `(next) => void` — fires with the full new array on add/remove. */
  onChange?: (tags: string[]) => void;
  /** Optional granular hook fired when a single token is committed. */
  onAdd?: (tag: string) => void;
  /** Optional granular hook fired when a single token is removed. */
  onRemove?: (tag: string, index: number) => void;
  placeholder?: string;
  /** Allow committing a value already present (default false — dedupes). */
  allowDuplicates?: boolean;
  disabled?: boolean;
  /** Key that commits a token in addition to Enter (default ","). */
  separator?: string;
}

/**
 * Token field for editing a tag set. Enter / comma commits, Backspace on an
 * empty draft pops the last, × removes any token. Accent pills, mono text.
 */
export function TagInput(props: TagInputProps): React.ReactElement;
