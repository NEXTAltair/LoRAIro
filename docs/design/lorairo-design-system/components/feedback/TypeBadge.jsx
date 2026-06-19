import React from "react";

/**
 * Type badge — neutral mono pill for provider names, job kinds, model types
 * (anthropic, openai, multimodal, model_install…). Smaller + squarer than Chip.
 */
export function TypeBadge({ children, style, ...rest }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0 6px",
        borderRadius: "var(--radius-badge)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--fs-meta)",
        lineHeight: 1.7,
        background: "var(--paper-shade)",
        color: "var(--ink-soft)",
        border: "1px solid var(--line)",
        whiteSpace: "nowrap",
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  );
}
