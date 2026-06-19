import * as React from "react";

export interface TerminalProps {
  children?: React.ReactNode;
  style?: React.CSSProperties;
}

/**
 * The dark code / JSONL pane — the single dark surface in LoRAIro. Use the
 * static syntax helpers for coloured tokens.
 */
export function Terminal(props: TerminalProps): React.ReactElement & {
  /** JSON key colour. */
  K: React.FC<{ children?: React.ReactNode }>;
  /** String colour. */
  S: React.FC<{ children?: React.ReactNode }>;
  /** Number colour. */
  N: React.FC<{ children?: React.ReactNode }>;
  /** Boolean colour. */
  B: React.FC<{ children?: React.ReactNode }>;
  /** Muted prompt / comment colour. */
  Muted: React.FC<{ children?: React.ReactNode }>;
};
