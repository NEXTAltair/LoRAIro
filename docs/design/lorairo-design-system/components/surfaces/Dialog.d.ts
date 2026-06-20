import * as React from "react";

export interface DialogProps {
  /** Controls visibility. Default true. */
  open?: boolean;
  /** Called on ESC, scrim click, ✕, and the confirm-variant cancel. */
  onClose?: () => void;
  title?: React.ReactNode;
  children?: React.ReactNode;
  /** Custom footer; overrides the variant footer. */
  footer?: React.ReactNode;
  /** `confirm` renders a built-in cancel + primary-OK footer. */
  variant?: "default" | "confirm";
  confirmLabel?: React.ReactNode;
  cancelLabel?: React.ReactNode;
  onConfirm?: () => void;
  /** Card width in px. Default 460. */
  width?: number;
  /** Close when the scrim is clicked. Default true. */
  closeOnScrim?: boolean;
  style?: React.CSSProperties;
}

/**
 * Modal dialog over an ink scrim — title / body / footer, ESC + scrim-click to
 * close. Replaces the hand-rolled Settings overlay and QMessageBox confirms.
 */
export function Dialog(props: DialogProps): React.ReactElement | null;
