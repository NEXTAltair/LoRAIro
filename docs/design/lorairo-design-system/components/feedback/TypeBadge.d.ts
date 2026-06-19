import * as React from "react";

export interface TypeBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children?: React.ReactNode;
}

/** Neutral monospaced meta badge — provider / job-kind / model-type labels. */
export function TypeBadge(props: TypeBadgeProps): React.ReactElement;
