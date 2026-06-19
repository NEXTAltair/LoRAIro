import * as React from "react";

export interface Column {
  /** Stable column id. */
  key: string;
  /** Header label. */
  header?: React.ReactNode;
  /** Optional fixed width (e.g. "120px"). */
  width?: string;
  /** Cell text alignment. */
  align?: "left" | "center" | "right";
  /** Custom cell renderer; falls back to `row[key]`. */
  render?: (row: any) => React.ReactNode;
}

export interface DataTableProps {
  columns: Column[];
  rows: any[];
  /** Stable key per row; defaults to `row.id` then index. */
  rowKey?: (row: any, index: number) => string | number;
  /** Key of the selected row — tints it accent-soft. */
  selectedKey?: string | number;
  onRowClick?: (row: any) => void;
  style?: React.CSSProperties;
}

/**
 * List/table with the LoRAIro styling — paper-shade sticky-feel header,
 * hairline row separators, hover + selected tints. Used in Jobs / Errors / History.
 */
export function DataTable(props: DataTableProps): React.ReactElement;
