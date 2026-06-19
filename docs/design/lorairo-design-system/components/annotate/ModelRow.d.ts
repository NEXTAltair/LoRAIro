import * as React from "react";

export interface ModelRowProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Leading status slot — usually a <Chip> (installed / API ready / needs key). */
  status?: React.ReactNode;
  /** Model name. */
  name?: React.ReactNode;
  /** Provider / type slot — usually a <TypeBadge>. */
  badge?: React.ReactNode;
  /** Mono cost + speed meta, e.g. "$0.0011/img · ~0.8s". */
  cost?: React.ReactNode;
  /** Discontinued model — strike-through + faint, kept for history. */
  disabled?: boolean;
}

/**
 * A selectable model row in the picker: status · name · provider badge · cost.
 * Hover tints the row. Compose with Chip + TypeBadge.
 */
export function ModelRow(props: ModelRowProps): React.ReactElement;
