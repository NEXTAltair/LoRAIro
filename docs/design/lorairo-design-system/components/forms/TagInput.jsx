import React from "react";

/**
 * TagInput — token field for editing a tag set (manual annotation tags, query
 * facets). Tokens are accent pills with a × affordance; typing + Enter or comma
 * commits a token, Backspace on an empty draft removes the last. Controlled via
 * `tags` + `onChange(next)`. Values are stored verbatim (danbooru canonical) —
 * the field never translates. Mirrors the Tag Edit manual-tag row.
 */
export function TagInput({
  tags = [],
  onChange,
  onAdd,
  onRemove,
  placeholder = "タグを追加…",
  allowDuplicates = false,
  disabled = false,
  separator = ",",
  style,
  ...rest
}) {
  const [draft, setDraft] = React.useState("");
  const [focus, setFocus] = React.useState(false);
  const inputRef = React.useRef(null);

  const commit = (raw) => {
    const v = raw.trim().replace(/[,，]$/, "").trim();
    if (!v) return;
    if (!allowDuplicates && tags.includes(v)) { setDraft(""); return; }
    if (onAdd) onAdd(v);
    if (onChange) onChange([...tags, v]);
    setDraft("");
  };

  const removeAt = (i) => {
    const t = tags[i];
    if (onRemove) onRemove(t, i);
    if (onChange) onChange(tags.filter((_, j) => j !== i));
  };

  const onKey = (e) => {
    if (e.key === "Enter" || e.key === separator) { e.preventDefault(); commit(draft); }
    else if (e.key === "Backspace" && draft === "" && tags.length) { e.preventDefault(); removeAt(tags.length - 1); }
  };

  return (
    <div
      onClick={() => inputRef.current && inputRef.current.focus()}
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "var(--gap-2)",
        padding: "5px 8px",
        minHeight: 32,
        boxSizing: "border-box",
        background: disabled ? "var(--paper-shade)" : "var(--card)",
        border: "1px solid " + (focus && !disabled ? "var(--accent)" : "var(--line)"),
        borderRadius: "var(--radius)",
        outline: focus && !disabled ? "2px solid var(--accent-soft)" : "none",
        cursor: disabled ? "default" : "text",
        ...style,
      }}
      {...rest}
    >
      {tags.map((t, i) => (
        <span
          key={t + i}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            padding: "1px 4px 1px 8px",
            borderRadius: "var(--radius-chip)",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--fs-small)",
            background: "var(--accent-soft)",
            color: "var(--accent-hover)",
            border: "1px solid var(--accent-border)",
            whiteSpace: "nowrap",
          }}
        >
          {t}
          {!disabled && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeAt(i); }}
              aria-label={"remove " + t}
              style={{ border: "none", background: "transparent", color: "var(--accent-hover)", cursor: "pointer", padding: "0 2px", fontSize: 11, lineHeight: 1 }}
            >×</button>
          )}
        </span>
      ))}
      <input
        ref={inputRef}
        value={draft}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={() => { setFocus(false); commit(draft); }}
        onFocus={() => setFocus(true)}
        placeholder={tags.length ? "" : placeholder}
        style={{
          flex: 1,
          minWidth: 80,
          border: "none",
          outline: "none",
          background: "transparent",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--fs-small)",
          color: "var(--ink)",
          padding: "1px 0",
        }}
      />
    </div>
  );
}
