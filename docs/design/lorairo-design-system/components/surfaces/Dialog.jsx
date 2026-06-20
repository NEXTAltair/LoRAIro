import React from "react";
import { Button } from "../forms/Button";

/**
 * Dialog — modal card over an ink scrim (var(--scrim)). title / body / footer
 * slots. ESC and scrim click call onClose; ✕ in the header too. `variant`
 * "confirm" renders a built-in cancel + primary-OK footer wired to onConfirm.
 * Mirrors the hand-rolled Settings overlay and QMessageBox confirms.
 */
export function Dialog({
  open = true,
  onClose,
  title,
  children,
  footer,
  variant = "default",
  confirmLabel = "OK",
  cancelLabel = "キャンセル",
  onConfirm,
  width = 460,
  closeOnScrim = true,
  style,
  ...rest
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape" && onClose) onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const foot = footer != null
    ? footer
    : variant === "confirm"
      ? (
        <React.Fragment>
          <Button onClick={onClose}>{cancelLabel}</Button>
          <Button variant="primary" onClick={onConfirm || onClose}>{confirmLabel}</Button>
        </React.Fragment>
      )
      : null;

  return (
    <div
      onClick={closeOnScrim ? onClose : undefined}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--scrim)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
        padding: "var(--gap-4)",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{
          width,
          maxWidth: "92vw",
          maxHeight: "88vh",
          display: "flex",
          flexDirection: "column",
          background: "var(--card)",
          border: "1px solid var(--line)",
          borderRadius: "var(--radius)",
          boxShadow: "var(--shadow-shell)",
          fontFamily: "var(--font-sans)",
          color: "var(--ink)",
          overflow: "hidden",
          ...style,
        }}
        {...rest}
      >
        {title != null && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--gap-2)",
              padding: "var(--gap-3)",
              borderBottom: "1px solid var(--line)",
            }}
          >
            <h3 style={{ margin: 0, fontSize: "var(--fs-h2)", fontWeight: 700 }}>{title}</h3>
            <span style={{ flex: 1 }} />
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label="close"
                style={{
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  fontSize: 15,
                  lineHeight: 1,
                  color: "var(--ink-soft)",
                  padding: 2,
                }}
              >✕</button>
            )}
          </div>
        )}

        <div style={{ padding: "var(--gap-3)", overflowY: "auto", fontSize: "var(--fs-base)", lineHeight: 1.6 }}>
          {children}
        </div>

        {foot && (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "var(--gap-2)",
              padding: "var(--gap-3)",
              borderTop: "1px solid var(--line)",
            }}
          >
            {foot}
          </div>
        )}
      </div>
    </div>
  );
}
