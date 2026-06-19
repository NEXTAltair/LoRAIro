import * as React from "react";

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement & HTMLTextAreaElement>, "size"> {
  /** Optional field label rendered above the control (semibold, 11px, ink-soft). */
  label?: React.ReactNode;
  /** Render a multi-line textarea instead of a single-line input. */
  multiline?: boolean;
  /** Rows for the textarea when `multiline`. */
  rows?: number;
  placeholder?: string;
}

/**
 * Single-line text input (or textarea) with optional label. Focus shows an
 * accent border + soft ring. Used for tag search, score thresholds, NLQ, etc.
 */
export function Input(props: InputProps): React.ReactElement;
