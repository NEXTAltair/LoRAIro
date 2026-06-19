import React from "react";

/**
 * Thumbnail tile for the search grid. Shows a square image (or a paper-gradient
 * placeholder with `label`) plus a mono meta footer (dimensions · score).
 * `selected` draws the accent outline; hover tints the border.
 */
export function Thumbnail({ src, label, dims, score, selected = false, onClick, style }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        border: "1px solid " + (hover && !selected ? "var(--accent)" : "var(--line)"),
        borderRadius: "var(--radius)",
        background: "var(--card)",
        overflow: "hidden",
        cursor: onClick ? "pointer" : "default",
        outline: selected ? "2px solid var(--accent)" : "none",
        outlineOffset: "-1px",
        ...style,
      }}
    >
      {src ? (
        <img src={src} alt={label || ""} style={{ display: "block", width: "100%", aspectRatio: "1", objectFit: "cover" }} />
      ) : (
        <div
          style={{
            aspectRatio: "1",
            background: "linear-gradient(135deg, var(--paper-shade), #e6e2d5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--fs-small)",
          }}
        >
          {label}
        </div>
      )}
      {(dims || score != null) && (
        <div
          style={{
            padding: "4px 8px",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--fs-meta)",
            color: "var(--ink-soft)",
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <span>{dims}</span>
          <span>{score}</span>
        </div>
      )}
    </div>
  );
}
