import * as React from "react";

export interface ProgressBarProps {
  /** Completion 0–100. */
  value?: number;
  /** `info` (running, default) or `ok` (complete) fill colour. */
  tone?: "info" | "ok";
  /** Diagonal stripes for a rate-limited / waiting job. */
  striped?: boolean;
  style?: React.CSSProperties;
}

/** Thin determinate progress bar — info fill while running, ok fill when done. */
export function ProgressBar(props: ProgressBarProps): React.ReactElement;
