import React from "react";

/**
 * Thin progress bar. `value` 0–100. `tone` info (default, in-progress) or
 * ok (complete). `striped` indicates a rate-limited / waiting job.
 */
export function ProgressBar({ value = 0, tone = "info", striped = false, style }) {
  const pct = Math.max(0, Math.min(100, value));
  const fill = tone === "ok" ? "var(--ok)" : "var(--info)";
  return (
    <div
      role="progressbar"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      style={{
        height: "8px",
        minWidth: "120px",
        borderRadius: "4px",
        background: "var(--paper-shade)",
        border: "1px solid var(--line)",
        overflow: "hidden",
        ...style,
      }}
    >
      <div
        style={{
          width: pct + "%",
          height: "100%",
          background: fill,
          backgroundImage: striped
            ? "repeating-linear-gradient(45deg, rgba(255,255,255,.25) 0 6px, transparent 6px 12px)"
            : undefined,
          transition: "width .3s ease",
        }}
      />
    </div>
  );
}
