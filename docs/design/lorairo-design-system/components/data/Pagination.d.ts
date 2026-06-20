import * as React from "react";

export interface PaginationProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange"> {
  /** 1-based current page. */
  page?: number;
  pageSize?: number;
  total?: number;
  /** Fires with the 1-based target page. */
  onChange?: (page: number) => void;
  /** Pages shown either side of the current one. Default 1. */
  siblingCount?: number;
  /** Counter unit (件 / 枚). Default 件. */
  unit?: string;
}

/**
 * Pagination — mono "1,247 件 / 表示 1–48" count line plus prev/next and
 * numbered page buttons with ellipsis. onChange(page) is 1-based.
 */
export function Pagination(props: PaginationProps): React.ReactElement;
