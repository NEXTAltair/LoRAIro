import * as React from "react";

export interface SliderProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange" | "type"> {
  /** Field label rendered above-left of the value readout. */
  label?: React.ReactNode;
  /** Controlled value. Omit for uncontrolled (use `defaultValue`). */
  value?: number;
  defaultValue?: number;
  /** `(next, event) => void` — fires on drag. */
  onChange?: (value: number, event: React.ChangeEvent<HTMLInputElement>) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Unit appended to the readout, e.g. "↑", "px", "%". */
  suffix?: string;
  /** Show the mono value readout (default true). */
  showValue?: boolean;
  /** Custom value formatter; overrides the default 2-decimal / integer logic. */
  format?: (value: number) => React.ReactNode;
  /** Caption under the left end of the track (defaults to `min`). */
  minLabel?: React.ReactNode;
  /** Caption under the right end of the track (defaults to `max`). */
  maxLabel?: React.ReactNode;
  disabled?: boolean;
}

/**
 * Labeled range slider with accent fill, mono value readout and optional
 * min/max captions — the primitive behind quality-score and manual-score edits.
 */
export function Slider(props: SliderProps): React.ReactElement;
