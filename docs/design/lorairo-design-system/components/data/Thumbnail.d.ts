import * as React from "react";

export interface ThumbnailProps {
  /** Image URL. If omitted, a paper-gradient placeholder shows `label`. */
  src?: string;
  /** Placeholder caption / image id (e.g. "img_0001"). */
  label?: string;
  /** Dimensions string for the meta footer (e.g. "1024×1536"). */
  dims?: string;
  /** Aesthetic score for the meta footer (e.g. 0.82). */
  score?: number | string;
  /** Accent outline for the selected tile. */
  selected?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}

/**
 * Square image tile for the search results grid, with a mono meta footer
 * (dimensions · score). Lay tiles out in a CSS grid of minmax(132px, 1fr).
 */
export function Thumbnail(props: ThumbnailProps): React.ReactElement;
