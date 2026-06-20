import React from "react";

/**
 * Segmented control — the status / filter toggle used across Errors, Results,
 * Settings (未解決 / 解決済 / 無視 / すべて · auto/direct/openrouter). Active
 * segment = accent-soft fill + accent text; the group sits in a bordered track.
 * `options` = [{ value, label, count }] or plain strings.
 */
export function SegmentedControl({ options = [], value, onChange, size = "base", style }) {
  const pad = size === "small" ? "2px 8px" : "4px 12px";
  const fs = size === "small" ? "var(--fs-small)" : "var(--fs-base)";
  return (
    <div
      role="tablist"
      style={{
        display: "inline-flex",
        padding: "2px",
        gap: "2px",
        background: "var(--paper-shade)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        ...style,
      }}
    >
      {options.map((o) => {
        const opt = typeof o === "string" ? { value: o, label: o } : o;
        const on = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange && onChange(opt.value)}
            style={{
              appearance: "none",
              border: "1px solid " + (on ? "var(--accent-border)" : "transparent"),
              background: on ? "var(--card)" : "transparent",
              color: on ? "var(--accent-hover)" : "var(--ink-soft)",
              fontWeight: on ? 600 : 400,
              borderRadius: "calc(var(--radius) - 2px)",
              padding: pad,
              fontFamily: "var(--font-sans)",
              fontSize: fs,
              cursor: "pointer",
              whiteSpace: "nowrap",
              display: "inline-flex",
              alignItems: "center",
              gap: "5px",
            }}
          >
            {opt.label}
            {opt.count != null && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: on ? "var(--accent-hover)" : "var(--ink-faint)" }}>
                {opt.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
