import React from "react";

/**
 * Native select styled to match QSS QComboBox: card fill, line border,
 * accent focus border, custom ▾ caret. Optional label above.
 */
export function Select({ label, options = [], children, style, id, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const autoId = React.useId();
  const fieldId = id || autoId;

  const control = (
    <div style={{ position: "relative", width: "100%" }}>
      <select
        id={fieldId}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{
          width: "100%",
          boxSizing: "border-box",
          appearance: "none",
          WebkitAppearance: "none",
          padding: "6px 28px 6px 10px",
          fontFamily: "var(--font-sans)",
          fontSize: "var(--fs-base)",
          color: "var(--ink)",
          background: "var(--card)",
          border: "1px solid " + (focus ? "var(--accent)" : "var(--line)"),
          borderRadius: "var(--radius)",
          outline: "none",
          cursor: "pointer",
          ...style,
        }}
        {...rest}
      >
        {children || options.map((o) =>
          typeof o === "string"
            ? <option key={o} value={o}>{o}</option>
            : <option key={o.value} value={o.value}>{o.label}</option>
        )}
      </select>
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          right: "10px",
          top: "50%",
          transform: "translateY(-50%)",
          pointerEvents: "none",
          fontSize: "10px",
          color: "var(--ink-soft)",
        }}
      >▾</span>
    </div>
  );

  if (!label) return control;
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <label
        htmlFor={fieldId}
        style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", fontWeight: 600, margin: "0 0 3px" }}
      >
        {label}
      </label>
      {control}
    </div>
  );
}
