import React from "react";

/**
 * LoRAIro button. Mirrors QSS QPushButton: bordered card-fill default,
 * accent-filled primary, transparent ghost (QToolButton). Hover tints the
 * border + text accent; press fills accent-soft.
 */
export function Button({
  variant = "default",
  size = "base",
  disabled = false,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const [active, setActive] = React.useState(false);

  const sizes = {
    base: { padding: "6px 14px", fontSize: "var(--fs-base)" },
    small: { padding: "3px 10px", fontSize: "var(--fs-small)" },
  };

  const base = {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    fontFamily: "var(--font-sans)",
    borderRadius: "var(--radius)",
    border: "1px solid var(--line-strong)",
    cursor: disabled ? "default" : "pointer",
    lineHeight: 1.4,
    whiteSpace: "nowrap",
    transition: "color .12s, border-color .12s, background-color .12s",
    ...sizes[size],
  };

  let look;
  if (variant === "primary") {
    look = {
      background: active && !disabled ? "var(--accent-hover)" : "var(--accent)",
      borderColor: active && !disabled ? "var(--accent-hover)" : "var(--accent)",
      color: "#fff",
      fontWeight: 600,
      ...(hover && !disabled ? { background: "var(--accent-hover)", borderColor: "var(--accent-hover)" } : {}),
    };
  } else if (variant === "ghost") {
    look = {
      background: hover && !disabled ? "var(--paper-shade)" : "transparent",
      borderColor: hover && !disabled ? "var(--line-strong)" : "transparent",
      color: "var(--ink)",
    };
  } else {
    look = {
      background: active && !disabled ? "var(--accent-soft)" : "var(--card)",
      color: hover && !disabled ? "var(--accent)" : "var(--ink)",
      borderColor: hover && !disabled ? "var(--accent)" : "var(--line-strong)",
    };
  }

  const disabledLook = disabled
    ? {
        background: variant === "ghost" ? "transparent" : "var(--paper-shade)",
        color: "var(--ink-faint)",
        borderColor: variant === "ghost" ? "transparent" : "var(--line)",
        fontWeight: variant === "primary" ? 600 : undefined,
      }
    : {};

  return (
    <button
      type="button"
      disabled={disabled}
      style={{ ...base, ...look, ...disabledLook, ...style }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setActive(false); }}
      onMouseDown={() => setActive(true)}
      onMouseUp={() => setActive(false)}
      {...rest}
    >
      {children}
    </button>
  );
}
