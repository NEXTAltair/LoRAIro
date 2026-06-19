import React from "react";

/**
 * Text field. Optional `label` (small caps-ish field label above) and
 * `multiline` for a textarea. Focus draws the accent border + soft ring,
 * matching QSS QLineEdit:focus.
 */
export function Input({ label, multiline = false, rows = 3, style, id, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const autoId = React.useId();
  const fieldId = id || autoId;

  const fieldStyle = {
    width: "100%",
    boxSizing: "border-box",
    padding: "6px 10px",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--fs-base)",
    color: "var(--ink)",
    background: "var(--card)",
    border: "1px solid " + (focus ? "var(--accent)" : "var(--line)"),
    borderRadius: "var(--radius)",
    outline: focus ? "2px solid var(--accent-soft)" : "none",
    outlineOffset: 0,
    resize: multiline ? "vertical" : undefined,
    ...style,
  };

  const field = multiline ? (
    <textarea
      id={fieldId}
      rows={rows}
      style={fieldStyle}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      {...rest}
    />
  ) : (
    <input
      id={fieldId}
      style={fieldStyle}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      {...rest}
    />
  );

  if (!label) return field;
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <label
        htmlFor={fieldId}
        style={{
          fontSize: "var(--fs-small)",
          color: "var(--ink-soft)",
          fontWeight: 600,
          margin: "0 0 3px",
        }}
      >
        {label}
      </label>
      {field}
    </div>
  );
}
