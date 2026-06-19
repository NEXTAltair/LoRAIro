import React from "react";

/**
 * Dark terminal / JSONL pane (the one dark surface in the app). Pass plain
 * children, or use the JSON syntax helpers exported alongside:
 * `Terminal.K` (key) `Terminal.S` (string) `Terminal.N` (number)
 * `Terminal.B` (boolean) `Terminal.Muted` (prompt / comment).
 */
export function Terminal({ children, style }) {
  return (
    <div
      style={{
        background: "var(--terminal)",
        borderRadius: "var(--radius)",
        padding: "10px 14px",
        fontFamily: "var(--font-mono)",
        fontSize: "12px",
        lineHeight: 1.7,
        color: "var(--terminal-fg)",
        overflowX: "auto",
        whiteSpace: "pre-wrap",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

Terminal.K = ({ children }) => <span style={{ color: "var(--terminal-key)" }}>{children}</span>;
Terminal.S = ({ children }) => <span style={{ color: "var(--terminal-str)" }}>{children}</span>;
Terminal.N = ({ children }) => <span style={{ color: "var(--terminal-num)" }}>{children}</span>;
Terminal.B = ({ children }) => <span style={{ color: "var(--terminal-bool)" }}>{children}</span>;
Terminal.Muted = ({ children }) => <span style={{ color: "var(--terminal-muted)" }}>{children}</span>;
