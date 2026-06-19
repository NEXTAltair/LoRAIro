import React from "react";

/**
 * Card — white surface, hairline border, 6px radius. Optional `title` row
 * (semibold) with a trailing `aside` slot (e.g. a TypeBadge).
 */
export function Card({ title, aside, children, style, bodyStyle, ...rest }) {
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        padding: "var(--gap-3)",
        ...style,
      }}
      {...rest}
    >
      {title && (
        <h3
          style={{
            margin: "0 0 var(--gap-2)",
            fontSize: "var(--fs-base)",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            gap: "var(--gap-2)",
          }}
        >
          {title}
          {aside && <span style={{ fontWeight: 400 }}>{aside}</span>}
        </h3>
      )}
      <div style={bodyStyle}>{children}</div>
    </div>
  );
}
