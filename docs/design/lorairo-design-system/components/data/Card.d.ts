import * as React from "react";

/**
 * @startingPoint section="Surfaces" subtitle="Card surface with title" viewport="360x200"
 */
export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Optional heading row (semibold, 13px). */
  title?: React.ReactNode;
  /** Trailing element in the heading row — e.g. a TypeBadge or count. */
  aside?: React.ReactNode;
  bodyStyle?: React.CSSProperties;
  children?: React.ReactNode;
}

/**
 * Container surface used for every panel in LoRAIro (filter sidebar, model
 * picker, job tables). White fill, hairline border, optional title row.
 *
 * @startingPoint section="Surfaces" subtitle="Card surface with title" viewport="360x200"
 */
export function Card(props: CardProps): React.ReactElement;
