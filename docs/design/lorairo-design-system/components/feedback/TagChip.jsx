import React from "react";

/**
 * Tag chip — accent-tinted pill for annotation tags (1girl, outdoor, …).
 * Optional `onRemove` renders a × affordance.
 */
export function TagChip({ children, onRemove, style, ...rest }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "1px 8px",
        borderRadius: "var(--radius-chip)",
        fontSize: "var(--fs-small)",
        background: "var(--accent-soft)",
        color: "var(--accent-hover)",
        border: "1px solid var(--accent-border)",
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="remove tag"
          style={{
            border: "none",
            background: "transparent",
            color: "var(--accent-hover)",
            cursor: "pointer",
            padding: 0,
            fontSize: "11px",
            lineHeight: 1,
          }}
        >×</button>
      )}
    </span>
  );
}
