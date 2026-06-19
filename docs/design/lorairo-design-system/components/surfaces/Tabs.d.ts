import * as React from "react";

export interface TabItem {
  id: string;
  label: React.ReactNode;
}

/**
 * @startingPoint section="Navigation" subtitle="Top nav tab bar with accent underline" viewport="640x60"
 */
export interface TabsProps {
  tabs: TabItem[];
  /** Active tab id. */
  active: string;
  onChange?: (id: string) => void;
  style?: React.CSSProperties;
}

/**
 * Primary top navigation — the LoRAIro tab bar (検索 / マップ / アノテーション …).
 * Active tab gets a 2px accent underline + semibold ink label on a paper band.
 *
 * @startingPoint section="Navigation" subtitle="Top nav tab bar with accent underline" viewport="640x60"
 */
export function Tabs(props: TabsProps): React.ReactElement;
