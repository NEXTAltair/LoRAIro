import * as React from "react";

export interface TagChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Optional remove handler — renders a × button when provided. */
  onRemove?: () => void;
  children?: React.ReactNode;
}

/** Accent-tinted pill for an annotation tag, optionally removable. */
export function TagChip(props: TagChipProps): React.ReactElement;
