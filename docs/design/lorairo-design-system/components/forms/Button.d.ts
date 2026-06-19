import * as React from "react";

/**
 * @startingPoint section="Forms" subtitle="Button — default / primary / ghost" viewport="360x120"
 */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual treatment. `primary` = accent fill (one per view), `default` = bordered, `ghost` = transparent toolbar button. */
  variant?: "default" | "primary" | "ghost";
  /** `base` (6×14) or compact `small` (3×10, 11px). */
  size?: "base" | "small";
  disabled?: boolean;
  children?: React.ReactNode;
}

/**
 * Primary text button for LoRAIro. Bordered card-fill by default; accent-filled
 * `primary` for the single main action per view; `ghost` for low-emphasis toolbar actions.
 *
 * @startingPoint section="Forms" subtitle="Button — default / primary / ghost" viewport="360x120"
 */
export function Button(props: ButtonProps): React.ReactElement;
