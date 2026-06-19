import React from "react";

/**
 * Top navigation tabs. Active tab = ink text, semibold, 2px accent underline,
 * paper fill; others ink-soft on the paper-shade band. `tabs` = [{id,label}].
 */
export function Tabs({ tabs = [], active, onChange, style }) {
  const [hover, setHover] = React.useState(null);
  return (
    <div
      role="tablist"
      style={{
        display: "flex",
        gap: "2px",
        padding: "0 10px",
        background: "var(--paper-shade)",
        borderBottom: "1px solid var(--line)",
        ...style,
      }}
    >
      {tabs.map((t) => {
        const on = t.id === active;
        const isHover = hover === t.id;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={on}
            onClick={() => onChange && onChange(t.id)}
            onMouseEnter={() => setHover(t.id)}
            onMouseLeave={() => setHover(null)}
            style={{
              appearance: "none",
              border: "none",
              background: on ? "var(--paper)" : "transparent",
              padding: "9px 16px 7px",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--fs-base)",
              fontWeight: on ? 600 : 400,
              color: on || isHover ? "var(--ink)" : "var(--ink-soft)",
              cursor: "pointer",
              borderBottom: "2px solid " + (on ? "var(--accent)" : "transparent"),
              marginBottom: "-1px",
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
