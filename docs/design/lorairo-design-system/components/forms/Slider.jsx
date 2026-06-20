import React from "react";

/**
 * Slider — labeled range control. Consolidates the raw `<input type="range">`
 * used for quality-score thresholds (Search) and manual score edits (Tag Edit)
 * into one primitive: accent fill, a mono value readout, optional min/max
 * captions and a unit suffix. Controlled (`value` + `onChange`) or uncontrolled
 * (`defaultValue`). Matches QSS QSlider (accent groove, ink track).
 */
export function Slider({
  label,
  value,
  defaultValue,
  onChange,
  min = 0,
  max = 10,
  step = 0.1,
  suffix = "",
  showValue = true,
  format,
  minLabel,
  maxLabel,
  disabled = false,
  id,
  style,
  ...rest
}) {
  const autoId = React.useId();
  const fieldId = id || autoId;
  const [internal, setInternal] = React.useState(defaultValue != null ? defaultValue : min);
  const controlled = value != null;
  const v = controlled ? value : internal;

  const handle = (e) => {
    const next = parseFloat(e.target.value);
    if (!controlled) setInternal(next);
    if (onChange) onChange(next, e);
  };

  const shown = format ? format(v) : (Number.isInteger(step) ? String(v) : Number(v).toFixed(2));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, opacity: disabled ? 0.55 : 1, ...style }}>
      {(label != null || showValue) && (
        <div style={{ display: "flex", alignItems: "baseline", gap: "var(--gap-2)" }}>
          {label != null && (
            <label htmlFor={fieldId} style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", fontWeight: 600 }}>
              {label}
            </label>
          )}
          <span style={{ flex: 1 }} />
          {showValue && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink)", fontWeight: 500 }}>
              {shown}{suffix}
            </span>
          )}
        </div>
      )}
      <input
        id={fieldId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        disabled={disabled}
        onChange={handle}
        style={{ width: "100%", accentColor: "var(--accent)", cursor: disabled ? "default" : "pointer" }}
        {...rest}
      />
      {(minLabel != null || maxLabel != null) && (
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>
          <span>{minLabel != null ? minLabel : min}</span>
          <span>{maxLabel != null ? maxLabel : max}</span>
        </div>
      )}
    </div>
  );
}
