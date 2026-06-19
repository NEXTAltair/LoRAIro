import React from "react";

/**
 * Pipeline stage card (TAGGER → CAPTION → SCORER …). Caps label, the chosen
 * model name, and a status slot (usually a Chip). `active` draws the accent
 * border; `shadow` styles it as an auto-acquired side-product stage (dashed,
 * italic) per the multimodal "shadow chip" convention.
 */
export function StageCard({ label, model, status, active = false, shadow = false, style, ...rest }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        border: (shadow ? "1px dashed " : "1px solid ") + (active ? "var(--accent)" : "var(--line)"),
        borderRadius: "var(--radius)",
        background: "var(--card)",
        padding: "8px 12px",
        fontStyle: shadow ? "italic" : "normal",
        ...style,
      }}
      {...rest}
    >
      <div
        style={{
          fontSize: "var(--fs-small)",
          fontWeight: 700,
          color: "var(--ink-soft)",
          letterSpacing: "var(--letter-caps)",
          marginBottom: "4px",
        }}
      >
        {label}
      </div>
      <div style={{ marginBottom: status ? "6px" : 0, color: shadow ? "var(--ink-soft)" : "var(--ink)" }}>{model}</div>
      {status}
    </div>
  );
}
