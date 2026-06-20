import React from "react";

const TOAST_PAL = {
  ok:      { fg: "var(--ok)",       soft: "var(--ok-soft)" },
  warn:    { fg: "var(--warn)",     soft: "var(--warn-soft)" },
  err:     { fg: "var(--err)",      soft: "var(--err-soft)" },
  info:    { fg: "var(--info)",     soft: "var(--info-soft)" },
  neutral: { fg: "var(--ink-soft)", soft: "var(--paper-shade)" },
};
// functional glyphs only (no emoji) — echoes the CLI [OK]/[!]/[i] marker vocabulary
const GLYPH = { ok: "✓", warn: "!", err: "✕", info: "i", neutral: "·" };

/**
 * Toast — transient status notification. White card, status-colored left
 * stripe + glyph chip, optional title / message / inline action / ✕ close.
 * Pass `duration` (ms) to auto-dismiss via `onClose`; `floating` pins it
 * bottom-right over the app. Earthy ok/warn/err/info palette. Used for job
 * completion, save confirmations, retry prompts.
 */
export function Toast({
  kind = "info",
  title,
  children,
  onClose,
  action,
  actionLabel = "元に戻す",
  duration,
  floating = false,
  style,
  ...rest
}) {
  React.useEffect(() => {
    if (!duration || !onClose) return;
    const t = setTimeout(onClose, duration);
    return () => clearTimeout(t);
  }, [duration, onClose]);

  const p = TOAST_PAL[kind] || TOAST_PAL.neutral;

  return (
    <div
      role="status"
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--gap-2)",
        width: 340,
        maxWidth: "92vw",
        boxSizing: "border-box",
        padding: "10px 12px",
        background: "var(--card)",
        border: "1px solid var(--line)",
        borderLeft: "3px solid " + p.fg,
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-shell)",
        fontFamily: "var(--font-sans)",
        color: "var(--ink)",
        ...(floating ? { position: "fixed", right: "var(--gap-4)", bottom: "var(--gap-4)", zIndex: 60 } : null),
        ...style,
      }}
      {...rest}
    >
      <span
        aria-hidden="true"
        style={{
          flex: "none",
          width: 18,
          height: 18,
          marginTop: 1,
          borderRadius: "var(--radius-badge)",
          background: p.soft,
          color: p.fg,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          fontWeight: 700,
          lineHeight: 1,
        }}
      >{GLYPH[kind] || GLYPH.neutral}</span>

      <div style={{ flex: 1, minWidth: 0 }}>
        {title != null && (
          <div style={{ fontSize: "var(--fs-base)", fontWeight: 600, lineHeight: 1.4 }}>{title}</div>
        )}
        {children != null && (
          <div style={{ fontSize: "var(--fs-small)", color: "var(--ink-soft)", lineHeight: 1.5, marginTop: title != null ? 2 : 0 }}>
            {children}
          </div>
        )}
        {action && (
          <button
            type="button"
            onClick={action}
            style={{ marginTop: 6, border: "none", background: "transparent", color: "var(--accent)", cursor: "pointer", padding: 0, fontFamily: "var(--font-sans)", fontSize: "var(--fs-small)", fontWeight: 600 }}
          >{actionLabel}</button>
        )}
      </div>

      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="close"
          style={{ flex: "none", border: "none", background: "transparent", color: "var(--ink-faint)", cursor: "pointer", padding: 2, fontSize: 13, lineHeight: 1 }}
        >✕</button>
      )}
    </div>
  );
}
