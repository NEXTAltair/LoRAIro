import React from "react";

/**
 * Checkbox — custom box matching QSS QCheckBox::indicator. `checked` fills the
 * box with accent and a white ✓; `indeterminate` shows a – (cleared once
 * checked). Focus draws the accent ring. Optional `label` to the right.
 * Used for multi-select: model picker, filter facets, DataTable row selection.
 */
export function Checkbox({
  checked = false,
  indeterminate = false,
  onChange,
  label,
  disabled = false,
  id,
  style,
  ...rest
}) {
  const [focus, setFocus] = React.useState(false);
  const ref = React.useRef(null);
  const autoId = React.useId();
  const fieldId = id || autoId;

  React.useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate && !checked;
  }, [indeterminate, checked]);

  const mixed = indeterminate && !checked;
  const on = checked || mixed;

  const box = {
    position: "relative",
    flex: "none",
    width: 16,
    height: 16,
    boxSizing: "border-box",
    borderRadius: "var(--radius-badge)",
    border: "1px solid " + (disabled ? "var(--line)" : on ? "var(--accent)" : "var(--line-strong)"),
    background: disabled ? "var(--paper-shade)" : on ? "var(--accent)" : "var(--card)",
    outline: focus && !disabled ? "2px solid var(--accent-soft)" : "none",
    outlineOffset: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: disabled ? "var(--ink-faint)" : "#fff",
    fontSize: 11,
    lineHeight: 1,
    transition: "background-color .12s, border-color .12s",
  };

  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--gap-2)",
        cursor: disabled ? "default" : "pointer",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--fs-base)",
        color: disabled ? "var(--ink-faint)" : "var(--ink)",
        userSelect: "none",
        ...style,
      }}
    >
      <input
        ref={ref}
        id={fieldId}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{ position: "absolute", opacity: 0, width: 0, height: 0, margin: 0 }}
        {...rest}
      />
      <span aria-hidden="true" style={box}>{mixed ? "–" : checked ? "✓" : ""}</span>
      {label != null && <span>{label}</span>}
    </label>
  );
}
