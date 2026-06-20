import * as React from "react";

export interface SummaryStatProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Small caption label (e.g. "未解決 unresolved"). */
  label?: React.ReactNode;
  /** Large monospaced value (e.g. "33 件"). */
  value?: React.ReactNode;
  /** Optional mono sub line (e.g. "retry可 31 · 上限到達 2"). */
  sub?: React.ReactNode;
  /** Colours the value. */
  tone?: "ok" | "warn" | "err" | "info" | "accent";
}

/**
 * KPI summary tile for the Jobs / Errors / Results header strips —
 * label · big mono value · sub line. Lay several in a flex/grid row.
 */
export function SummaryStat(props: SummaryStatProps): React.ReactElement;
