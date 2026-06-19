import * as React from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  /** Optional field label rendered above the control. */
  label?: React.ReactNode;
  /** Convenience option list — strings or `{value,label}`. Ignored if children given. */
  options?: (string | SelectOption)[];
  children?: React.ReactNode;
}

/**
 * Dropdown select with a custom ▾ caret, styled to match the QComboBox QSS.
 */
export function Select(props: SelectProps): React.ReactElement;
