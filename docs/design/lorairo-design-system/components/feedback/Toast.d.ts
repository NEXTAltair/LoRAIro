import * as React from "react";

export type ToastKind = "ok" | "warn" | "err" | "info" | "neutral";

export interface ToastProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  /** Status family — sets the left stripe, glyph chip color (default "info"). */
  kind?: ToastKind;
  /** Bold first line. */
  title?: React.ReactNode;
  /** Secondary message (children). */
  children?: React.ReactNode;
  /** Renders the ✕ close button; also the auto-dismiss callback. */
  onClose?: () => void;
  /** Inline accent action handler (e.g. undo). */
  action?: () => void;
  /** Label for the inline action (default "元に戻す"). */
  actionLabel?: React.ReactNode;
  /** Auto-dismiss delay in ms — calls `onClose` when elapsed. */
  duration?: number;
  /** Pin fixed to the app's bottom-right corner. */
  floating?: boolean;
}

/**
 * Transient status notification with a status-colored stripe + glyph, optional
 * title / message / inline action / close, and optional auto-dismiss.
 */
export function Toast(props: ToastProps): React.ReactElement;
