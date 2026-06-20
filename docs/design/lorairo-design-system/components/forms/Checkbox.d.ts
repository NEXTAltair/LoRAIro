import * as React from "react";

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "onChange" | "type"> {
  checked?: boolean;
  /** Mixed state — renders a – and clears once `checked` becomes true. */
  indeterminate?: boolean;
  onChange?: React.ChangeEventHandler<HTMLInputElement>;
  /** Optional label rendered to the right of the box. */
  label?: React.ReactNode;
  disabled?: boolean;
}

/**
 * Checkbox with a custom accent-fill box and ✓ / – glyphs; focus draws the
 * accent ring. Used for multi-select — model picker, filter facets, table rows.
 */
export function Checkbox(props: CheckboxProps): React.ReactElement;
