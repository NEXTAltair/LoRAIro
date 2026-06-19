import * as React from "react";

export interface StageCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Caps stage label — TAGGER / CAPTION / SCORER / RATING / UPSCALE. */
  label: React.ReactNode;
  /** Chosen model name. */
  model?: React.ReactNode;
  /** Status slot — usually a <Chip>. */
  status?: React.ReactNode;
  /** Accent border for the focused stage. */
  active?: boolean;
  /** Dashed + italic "shadow" stage auto-filled by a multimodal model. */
  shadow?: boolean;
}

/**
 * One stage in the annotation pipeline strip. Place several with → arrows
 * between them. `shadow` marks a side-product stage filled by a multimodal model.
 */
export function StageCard(props: StageCardProps): React.ReactElement;
