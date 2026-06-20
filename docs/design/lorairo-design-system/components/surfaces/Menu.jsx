import React from "react";

/**
 * Menu — dropdown / context menu anchored to a trigger. Click the trigger to
 * toggle; ESC or an outside click closes; selecting an item fires `onSelect`
 * and closes. Items are `{ label, value, glyph, shortcut, disabled, danger }`
 * or `{ separator: true }`. White popover card with the app's hairline + shell
 * shadow; hover fills rows with paper-shade, danger rows go brick. Used for the
 * "サムネイル ▾" sort menu and thumbnail right-click actions.
 */
export function Menu({
  trigger,
  children,
  items = [],
  onSelect,
  align = "left",
  width,
  open: openProp,
  onOpenChange,
  style,
  ...rest
}) {
  const [openState, setOpenState] = React.useState(false);
  const open = openProp != null ? openProp : openState;
  const setOpen = (v) => { if (onOpenChange) onOpenChange(v); if (openProp == null) setOpenState(v); };
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  const [hover, setHover] = React.useState(-1);

  const choose = (it, i) => {
    if (it.disabled || it.separator) return;
    if (onSelect) onSelect(it.value != null ? it.value : it.label, it, i);
    setOpen(false);
  };

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-flex", ...style }} {...rest}>
      <span onClick={() => setOpen(!open)} style={{ display: "inline-flex" }}>
        {trigger || children}
      </span>
      {open && (
        <div
          role="menu"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            [align === "right" ? "right" : "left"]: 0,
            minWidth: width || 180,
            zIndex: 55,
            padding: "4px",
            background: "var(--card)",
            border: "1px solid var(--line)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-shell)",
            fontFamily: "var(--font-sans)",
          }}
        >
          {items.map((it, i) =>
            it.separator ? (
              <div key={"sep" + i} style={{ height: 1, background: "var(--line)", margin: "4px 2px" }} />
            ) : (
              <button
                key={(it.value != null ? it.value : it.label) + i}
                type="button"
                role="menuitem"
                disabled={it.disabled}
                onClick={() => choose(it, i)}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(-1)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--gap-2)",
                  width: "100%",
                  boxSizing: "border-box",
                  textAlign: "left",
                  border: "none",
                  borderRadius: "var(--radius-badge)",
                  padding: "5px 8px",
                  fontFamily: "var(--font-sans)",
                  fontSize: "var(--fs-base)",
                  cursor: it.disabled ? "default" : "pointer",
                  background: hover === i && !it.disabled ? (it.danger ? "var(--err-soft)" : "var(--paper-shade)") : "transparent",
                  color: it.disabled ? "var(--ink-faint)" : it.danger ? "var(--err)" : "var(--ink)",
                }}
              >
                {it.glyph != null && (
                  <span aria-hidden="true" style={{ flex: "none", width: 14, textAlign: "center", color: it.disabled ? "var(--ink-faint)" : it.danger ? "var(--err)" : "var(--ink-soft)" }}>{it.glyph}</span>
                )}
                <span style={{ flex: 1, whiteSpace: "nowrap" }}>{it.label}</span>
                {it.shortcut != null && (
                  <span style={{ flex: "none", fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--ink-faint)" }}>{it.shortcut}</span>
                )}
              </button>
            )
          )}
        </div>
      )}
    </span>
  );
}
