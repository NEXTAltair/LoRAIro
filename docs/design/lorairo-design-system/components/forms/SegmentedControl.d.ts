import * as React from "react";

export interface SegmentOption {
  value: string;
  label: React.ReactNode;
  /** Optional trailing count badge. */
  count?: number | string;
}

export interface SegmentedControlProps {
  options: (string | SegmentOption)[];
  value: string;
  onChange?: (value: string) => void;
  size?: "base" | "small";
  style?: React.CSSProperties;
}

/**
 * A bordered segmented toggle for status / mode filters (未解決 / 解決済 / すべて,
 * auto / direct / openrouter). Active segment gets an accent-soft fill.
 */
export function SegmentedControl(props: SegmentedControlProps): React.ReactElement;
