import React from "react";

const fmt = (n) => n.toLocaleString("en-US");

function buildPages(page, totalPages, sibling) {
  if (totalPages <= 1) return [1];
  const out = [1];
  const left = Math.max(2, page - sibling);
  const right = Math.min(totalPages - 1, page + sibling);
  if (left > 2) out.push("…l");
  for (let i = left; i <= right; i++) out.push(i);
  if (right < totalPages - 1) out.push("…r");
  out.push(totalPages);
  return out;
}

function PageBtn({ active, disabled, children, onClick }) {
  const [hover, setHover] = React.useState(false);
  const look = active
    ? { background: "var(--accent)", borderColor: "var(--accent)", color: "#fff" }
    : disabled
      ? { background: "var(--card)", borderColor: "var(--line)", color: "var(--ink-faint)" }
      : hover
        ? { background: "var(--card)", borderColor: "var(--accent)", color: "var(--accent)" }
        : { background: "var(--card)", borderColor: "var(--line-strong)", color: "var(--ink)" };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        minWidth: 26,
        height: 26,
        padding: "0 6px",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--fs-small)",
        fontWeight: active ? 600 : 400,
        borderRadius: "var(--radius)",
        border: "1px solid",
        cursor: disabled ? "default" : "pointer",
        transition: "color .12s, border-color .12s, background-color .12s",
        ...look,
      }}
    >{children}</button>
  );
}

/**
 * Pagination — mono count line ("1,247 件 / 表示 1–48") plus prev/next and
 * numbered page buttons (ellipsis on overflow). Counts and ranges are
 * JetBrains Mono. onChange(page) fires with the 1-based target page.
 * Used for search-result paging (ADR 0006).
 */
export function Pagination({
  page = 1,
  pageSize = 48,
  total = 0,
  onChange,
  siblingCount = 1,
  unit = "件",
  style,
  ...rest
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const cur = Math.min(Math.max(1, page), totalPages);
  const start = total === 0 ? 0 : (cur - 1) * pageSize + 1;
  const end = Math.min(cur * pageSize, total);
  const go = (p) => { if (p >= 1 && p <= totalPages && p !== cur && onChange) onChange(p); };
  const pages = buildPages(cur, totalPages, siblingCount);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--gap-3)",
        flexWrap: "wrap",
        fontFamily: "var(--font-sans)",
        ...style,
      }}
      {...rest}
    >
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-soft)", whiteSpace: "nowrap" }}>
        {fmt(total)} {unit} / 表示 {fmt(start)}–{fmt(end)}
      </span>
      <span style={{ flex: 1, minWidth: "var(--gap-4)" }} />
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <PageBtn disabled={cur <= 1} onClick={() => go(cur - 1)}>◂</PageBtn>
        {pages.map((p) =>
          typeof p === "string"
            ? <span key={p} style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-small)", color: "var(--ink-faint)", padding: "0 2px" }}>…</span>
            : <PageBtn key={p} active={p === cur} onClick={() => go(p)}>{p}</PageBtn>
        )}
        <PageBtn disabled={cur >= totalPages} onClick={() => go(cur + 1)}>▸</PageBtn>
      </div>
    </div>
  );
}
