import * as React from "react";

/**
 * @startingPoint section="Feedback" subtitle="Status chips — ok / warn / err / info" viewport="420x120"
 */
export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Semantic colour family. */
  kind?: "ok" | "warn" | "err" | "info" | "neutral" | "muted" | "accent";
  /** Leading dot. Defaults by kind (● for ok/info/accent/err, ○ for warn/neutral/muted). */
  dot?: "filled" | "open" | "none";
  children?: React.ReactNode;
}

/**
 * Small status pill with the LoRAIro dot grammar — ● available, ○ needs
 * action / inactive. Use for model/job/availability states.
 *
 * @startingPoint section="Feedback" subtitle="Status chips — ok / warn / err / info" viewport="420x120"
 */
export function Chip(props: ChipProps): React.ReactElement;
