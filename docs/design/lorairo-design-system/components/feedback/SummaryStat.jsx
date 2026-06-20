import React from "react";

/**
 * Summary stat block — the KPI tiles in the Jobs / Errors / Results header
 * strips. Small label, large value (mono), optional sub line. `tone` colours
 * the value (ok / warn / err / info / accent); default is plain ink.
 */
export function SummaryStat({ label, value, sub, tone, style, ...rest }) {
  const toneColor = {
    ok: "var(--ok)", warn: "var(--warn)", err: "var(--err)",
    info: "var(--info)", accent: "var(--accent)",
  }[tone] || "var(--ink)";
  return (
    <div
      style={{
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        padding: "8px 12px",
        minWidth: 0,
        ...style,
      }}
      {...rest}
    >
      <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "20px", fontWeight: 500, color: toneColor, lineHeight: 1.3, marginTop: 2 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {sub}
        </div>
      )}
    </div>
  );
}
