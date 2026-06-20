import * as React from "react";

export interface MenuItem {
  /** Row text. */
  label?: React.ReactNode;
  /** Value passed to `onSelect` (falls back to `label`). */
  value?: string;
  /** Optional leading Unicode glyph (▾ → ▸ × etc — no emoji). */
  glyph?: React.ReactNode;
  /** Right-aligned mono shortcut hint, e.g. "⌘1". */
  shortcut?: React.ReactNode;
  disabled?: boolean;
  /** Render as a destructive (brick) row. */
  danger?: boolean;
  /** Render a divider instead of a row. */
  separator?: boolean;
}

export interface MenuProps
  extends Omit<React.HTMLAttributes<HTMLSpanElement>, "onSelect"> {
  /** Trigger element (also accepts `children`). Clicking toggles the menu. */
  trigger?: React.ReactNode;
  children?: React.ReactNode;
  items?: MenuItem[];
  /** `(value, item, index) => void` — fires on row select; menu then closes. */
  onSelect?: (value: string, item: MenuItem, index: number) => void;
  /** Anchor the popover to the trigger's left (default) or right edge. */
  align?: "left" | "right";
  /** Min width of the popover in px (default 180). */
  width?: number;
  /** Controlled open state. Omit for internal state. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/**
 * Dropdown / context menu anchored to a trigger, with ESC + outside-click close,
 * glyph + shortcut rows, separators, and disabled / danger items.
 */
export function Menu(props: MenuProps): React.ReactElement;
