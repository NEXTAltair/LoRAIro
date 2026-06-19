import React from "react";

/**
 * Model picker row: status slot · model name · type badge slot · mono cost/speed.
 * Hover tints the row paper-shade. `disabled` greys the name (discontinued).
 */
export function ModelRow({ status, name, badge, cost, disabled = false, onClick, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--gap-2)",
        padding: "6px 8px",
        borderRadius: "var(--radius)",
        background: hover ? "var(--paper-shade)" : "transparent",
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
      {...rest}
    >
      {status}
      <span
        style={{
          flex: 1,
          minWidth: 0,
          color: disabled ? "var(--ink-faint)" : "var(--ink)",
          textDecoration: disabled ? "line-through" : "none",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {name}
      </span>
      {badge}
      {cost != null && (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)", whiteSpace: "nowrap" }}>
          {cost}
        </span>
      )}
    </div>
  );
}
