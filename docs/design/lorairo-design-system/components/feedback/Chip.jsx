import React from "react";

const PALETTE = {
  ok:      { bg: "var(--ok-soft)",     fg: "var(--ok)",        bd: "var(--ok-border)" },
  warn:    { bg: "var(--warn-soft)",   fg: "var(--warn)",      bd: "var(--warn-border)" },
  err:     { bg: "var(--err-soft)",    fg: "var(--err)",       bd: "var(--err-border)" },
  info:    { bg: "var(--info-soft)",   fg: "var(--info)",      bd: "var(--info-border)" },
  neutral: { bg: "var(--paper-shade)", fg: "var(--ink-soft)",  bd: "var(--line)" },
  muted:   { bg: "var(--paper-shade)", fg: "var(--ink-faint)", bd: "var(--line)" },
  accent:  { bg: "var(--accent-soft)", fg: "var(--accent-hover)", bd: "var(--accent-border)" },
};

// ● = available (ok/info/accent) · ○ = needs-action / inactive (warn/neutral/muted)
const DEFAULT_DOT = {
  ok: "filled", info: "filled", accent: "filled", err: "filled",
  warn: "open", neutral: "open", muted: "open",
};

/**
 * Status chip. Soft fill + same-family border + 10px radius. The leading dot
 * encodes the chip grammar: ● available, ○ needs action / inactive.
 */
export function Chip({ kind = "neutral", dot, children, style, ...rest }) {
  const p = PALETTE[kind] || PALETTE.neutral;
  const dotMode = dot || DEFAULT_DOT[kind] || "none";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "1px 9px",
        borderRadius: "var(--radius-chip)",
        fontSize: "var(--fs-small)",
        fontWeight: 600,
        lineHeight: 1.5,
        background: p.bg,
        color: p.fg,
        border: "1px solid " + p.bd,
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {dotMode !== "none" && (
        <span aria-hidden="true" style={{ fontSize: "9px", lineHeight: 1 }}>
          {dotMode === "filled" ? "●" : "○"}
        </span>
      )}
      {children}
    </span>
  );
}
